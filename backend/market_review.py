"""统一每日市场复盘快照。

这个模块只聚合客观数据，并为每个数据组件保留来源状态。生产路径不生成
fixture：上游成功值才会写入快照，失败时只能回填最近一次真实快照。
"""

from __future__ import annotations

import json
import hashlib
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import astock
import market
from data_paths import cache_path


BEIJING = ZoneInfo("Asia/Shanghai")
PROMPT_VERSION = "market-review-brief-v2"
INDEX_CODES = ("000001", "399001", "399006", "000300", "000680", "000688")
REVIEW_CACHE_DIR = cache_path("market-review")
REVIEW_REFRESH_SECONDS = 5 * 60
BREADTH_DISTRIBUTION_REFRESH_SECONDS = 15 * 60
_breadth_lock = threading.Lock()
_breadth_distribution_cache: tuple[float, dict[str, Any]] | None = None
_breadth_distribution_thread: threading.Thread | None = None
REVIEW_FILE_LOCK = threading.RLock()


def _as_number(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso(value: datetime) -> str:
    return value.astimezone(BEIJING).isoformat(timespec="seconds")


def _ensure_beijing(value: datetime) -> datetime:
    return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)


def _trading_date(value: datetime) -> date:
    current = _ensure_beijing(value).date()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Hash objective snapshot content while ignoring volatile/cache-only fields."""
    stable = {key: value for key, value in snapshot.items() if key not in {"brief", "generatedAt", "sources", "refreshing"}}
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _previous_trading_date(current: date) -> date:
    previous = current - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous


def build_change_distribution(changes: list[Any]) -> dict[str, int]:
    """Assign each valid percentage change to exactly one display bucket."""
    buckets = {
        "downOver10": 0, "down7To10": 0, "down5To7": 0, "down3To5": 0, "down0To3": 0,
        "flat": 0,
        "up0To3": 0, "up3To5": 0, "up5To7": 0, "up7To10": 0, "upOver10": 0,
    }
    for raw in changes:
        value = _as_number(raw)
        if value is None:
            continue
        if value < -10:
            key = "downOver10"
        elif value < -7:
            key = "down7To10"
        elif value < -5:
            key = "down5To7"
        elif value < -3:
            key = "down3To5"
        elif value < 0:
            key = "down0To3"
        elif value == 0:
            key = "flat"
        elif value <= 3:
            key = "up0To3"
        elif value <= 5:
            key = "up3To5"
        elif value <= 7:
            key = "up5To7"
        elif value <= 10:
            key = "up7To10"
        else:
            key = "upOver10"
        buckets[key] += 1
    return buckets


def build_breadth(up: int | None, down: int | None, limit_up: int | None, limit_down: int | None,
                  distribution: dict[str, int] | None = None) -> dict[str, Any]:
    """Normalize market breadth without exposing flat-count data."""
    total = (up or 0) + (down or 0) if up is not None and down is not None else 0
    up_ratio = round(up / total * 100, 2) if total and up is not None else None
    down_ratio = round(down / total * 100, 2) if total and down is not None else None
    return {
        "up": up,
        "down": down,
        "upRatio": up_ratio,
        "downRatio": down_ratio,
        "limitUp": limit_up,
        "limitDown": limit_down,
        "distribution": distribution,
    }


def build_liquidity(today_amount_yuan: int | float | None, previous_amount_yuan: int | float | None) -> dict[str, Any]:
    today = _as_number(today_amount_yuan)
    previous = _as_number(previous_amount_yuan)
    change = today - previous if today is not None and previous is not None else None
    change_pct = round(change / previous * 100, 2) if change is not None and previous else None
    direction = None
    if change is not None:
        direction = "expanded" if change > 0 else "contracted" if change < 0 else "unchanged"
    return {
        "todayAmountYuan": today,
        "previousAmountYuan": previous,
        "changeAmountYuan": change,
        "changePct": change_pct,
        "direction": direction,
    }


def _records(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    return [dict(row) for row in rows]


def _unit_multiplier(key: str) -> float:
    text = str(key)
    if "亿元" in text:
        return 100_000_000
    if "万元" in text:
        return 10_000
    if "万" in text:
        return 10_000
    return 1


def extract_official_stock_amount(rows: Any) -> int | None:
    """Extract a stock-only amount from SSE/SZSE summary rows in yuan.

    Official adapters expose slightly different column names. The parser accepts
    both a row labelled ``股票`` and an amount column labelled ``成交金额``/``成交额``.
    Explicit non-stock categories are always excluded.
    """
    candidates: list[float] = []
    for row in _records(rows):
        values = [str(value) for value in row.values() if value not in (None, "")]
        text = " ".join(values)
        excluded = any(word in text for word in ("基金", "债券", "回购", "期权", "权证"))
        category = " ".join(str(value) for key, value in row.items() if any(word in str(key) for word in ("类别", "类型", "品种", "证券")))
        stock_label = "股票" in category or any("股票" in str(key) for key in row)
        if excluded or not stock_label:
            continue
        amount_items = [(str(key), value) for key, value in row.items() if any(word in str(key) for word in ("成交金额", "成交额", "成交金额", "金额"))]
        if not amount_items:
            amount_items = [(str(key), value) for key, value in row.items() if "股票" in str(key)]
        for key, value in amount_items:
            amount = _as_number(value)
            if amount is not None:
                candidates.append(amount * _unit_multiplier(key))
                break
    if not candidates:
        return None
    return int(round(sum(candidates)))


def fetch_official_stock_amount(trading_date: date) -> int | None:
    """Fetch one day's stock-only turnover from the two official exchanges."""
    try:
        import akshare as ak
        ymd = trading_date.strftime("%Y%m%d")
        sse = extract_official_stock_amount(ak.stock_sse_deal_daily(date=ymd))
        szse = extract_official_stock_amount(ak.stock_szse_summary(date=ymd))
        return sse + szse if sse is not None and szse is not None else None
    except Exception:
        return None


def fetch_latest_official_stock_amount(on_or_before: date, lookback_days: int = 15) -> int | None:
    """Find the latest published exchange total, including across holidays."""
    for offset in range(max(1, lookback_days)):
        candidate = on_or_before - timedelta(days=offset)
        if candidate.weekday() >= 5:
            continue
        amount = fetch_official_stock_amount(candidate)
        if amount is not None:
            return amount
    return None


def fetch_official_liquidity(trading_date: date, previous_date: date) -> dict[str, Any] | None:
    """Fetch same-scope stock turnover from official SSE and SZSE statistics."""
    today = fetch_official_stock_amount(trading_date)
    previous = fetch_latest_official_stock_amount(previous_date)
    return {"todayAmountYuan": today, "previousAmountYuan": previous} if today is not None and previous is not None else None


def fetch_live_liquidity(indices: list[dict[str, Any]], trading_date: date, previous_date: date) -> dict[str, Any] | None:
    """Compare current turnover with the previous session at the same minute."""
    expected_date = trading_date.isoformat()
    market_rows = {str(row.get("code")): row for row in indices}
    if any(not str((market_rows.get(code) or {}).get("updatedAt") or "").startswith(expected_date)
           for code in ("000001", "399001")):
        return None
    amounts = {str(row.get("code")): _as_number(row.get("amountYuan")) for row in indices}
    shanghai, shenzhen = amounts.get("000001"), amounts.get("399001")
    if shanghai is None or shenzhen is None:
        return None
    timestamps: list[datetime] = []
    for code in ("000001", "399001"):
        try:
            timestamps.append(datetime.strptime(str(market_rows[code]["updatedAt"]), "%Y-%m-%d %H:%M:%S"))
        except (KeyError, TypeError, ValueError):
            return None
    cutoff = min(timestamps).strftime("%H:%M")

    def previous_amount(prefixed_code: str) -> float | None:
        try:
            histories = astock.index_intraday_days(prefixed_code)
        except Exception:
            return None
        prior_days = [day for day in histories if str(day.get("date") or "") <= previous_date.isoformat()]
        matching = max(prior_days, key=lambda day: str(day.get("date") or ""), default=None)
        points = (matching or {}).get("points") or []
        eligible = [point for point in points if str(point.get("time") or "") <= cutoff]
        return _as_number(eligible[-1].get("amountYuan")) if eligible else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        previous_parts = list(pool.map(previous_amount, ("sh000001", "sz399001")))
    previous = sum(previous_parts) if all(value is not None for value in previous_parts) else None
    return {"todayAmountYuan": shanghai + shenzhen, "previousAmountYuan": previous}


def _normalize_index(row: dict[str, Any], expected_date: date | None = None) -> dict[str, Any] | None:
    code = str(row.get("code") or row.get("代码") or "")
    if code not in INDEX_CODES:
        return None
    price = _as_number(row.get("price", row.get("现价")))
    change_pct = _as_number(row.get("change_pct", row.get("changePct", row.get("涨跌幅"))))
    change = _as_number(row.get("change_amt", row.get("change", row.get("涨跌"))))
    if price is None:
        return None
    updated_at = str(row.get("updatedAt") or row.get("更新时间") or "")
    if expected_date and updated_at and not updated_at.startswith(expected_date.isoformat()):
        return None
    return {
        "code": code,
        "name": str(row.get("name") or row.get("名称") or code),
        "price": price,
        "change": change,
        "changePct": change_pct,
        "source": str(row.get("source") or "腾讯行情"),
        "updatedAt": updated_at,
        "stale": bool(row.get("stale", False)),
    }


def _normalize_indices(rows: Any, expected_date: date | None = None) -> list[dict[str, Any]]:
    output = [_normalize_index(row, expected_date) for row in _records(rows)]
    return [row for row in output if row]


def fetch_em_breadth_summary() -> dict[str, Any] | None:
    """Fetch沪深京 A-share advance/decline totals in a single lightweight request."""
    expected_codes = {"000002", "399107", "899050"}

    def fetch_host(host: str) -> dict[str, Any] | None:
        try:
            params = {
                "secids": "1.000002,0.399107,0.899050",
                "fields": "f12,f14,f104,f105,f106",
                "fltt": 2,
                "invt": 2,
            }
            payload = astock.em_get(
                f"https://{host}/api/qt/ulist.np/get",
                params=params,
                headers={"User-Agent": astock.UA},
                timeout=3,
            ).json().get("data") or {}
            rows = {str(row.get("f12") or ""): row for row in (payload.get("diff") or [])}
            if not expected_codes.issubset(rows):
                raise ValueError("市场汇总口径不完整")
            values = {
                key: [_as_number(rows[code].get(field)) for code in expected_codes]
                for key, field in (("up", "f104"), ("down", "f105"), ("flat", "f106"))
            }
            if any(value is None or value < 0 or not value.is_integer()
                   for counts in values.values() for value in counts):
                raise ValueError("市场汇总家数无效")
            return {
                "up": int(sum(values["up"])),
                "down": int(sum(values["down"])),
                "flat": int(sum(values["flat"])),
                "limitUp": None,
                "limitDown": None,
                "distribution": None,
                "source": "东方财富沪深京A股汇总" + ("（延迟行情）" if "delay" in host else ""),
            }
        except Exception:
            return None

    hosts = ("push2.eastmoney.com", "push2delay.eastmoney.com")
    pool = ThreadPoolExecutor(max_workers=2)
    futures = {pool.submit(fetch_host, host): host for host in hosts}
    try:
        for future in as_completed(futures):
            value = future.result()
            if not _valid_breadth(value):
                continue
            if futures[future] == hosts[0]:
                return value
            realtime = next(item for item, host in futures.items() if host == hosts[0])
            try:
                preferred = realtime.result(timeout=0.1)
            except Exception:
                preferred = None
            return preferred if _valid_breadth(preferred) else value
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def fetch_em_breadth() -> dict[str, Any] | None:
    """Count a complete沪深京 A-share universe; never treat a partial page as market breadth."""
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            def fetch_page(page: int) -> tuple[int, list[dict[str, Any]]]:
                params = {"pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                          "fid": "f12", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
                          "fields": "f2,f3,f12,f13"}
                payload = astock.em_get(f"https://{host}/api/qt/clist/get", params=params,
                                       headers={"User-Agent": astock.UA}, timeout=12).json().get("data") or {}
                count = int(payload.get("total") or 0)
                if count <= 0:
                    raise ValueError("行情分页总数不完整")
                return count, payload.get("diff") or []

            rows: dict[str, dict] = {}

            def add_rows(page_rows: list[dict[str, Any]]) -> None:
                before = len(rows)
                for row in page_rows:
                    code = str(row.get("f12", ""))
                    if len(code) == 6 and code.isdigit():
                        rows[f"{row.get('f13')}:{code}"] = row
                if len(rows) <= before:
                    raise ValueError("行情分页为空或重复")

            total, first_rows = fetch_page(1)
            add_rows(first_rows)
            page_count = math.ceil(total / 100)
            if page_count > 1 and len(first_rows) >= min(100, total):
                with ThreadPoolExecutor(max_workers=min(8, page_count - 1)) as pool:
                    futures = [pool.submit(fetch_page, page) for page in range(2, page_count + 1)]
                    for future in as_completed(futures):
                        page_total, page_rows = future.result()
                        if page_total != total:
                            raise ValueError("行情分页总数不完整")
                        add_rows(page_rows)
            else:
                # Some test/proxy sources return smaller pages despite pz=100.
                for page in range(2, 101):
                    if len(rows) >= total:
                        break
                    page_total, page_rows = fetch_page(page)
                    if page_total != total:
                        raise ValueError("行情分页总数不完整")
                    add_rows(page_rows)
            if len(rows) != total:
                raise ValueError("行情分页未收齐")
            changes = [_as_number(row.get("f3")) for row in rows.values()
                       if (_as_number(row.get("f2")) or 0) > 0]
            changes = [value for value in changes if value is not None]
            if not changes:
                raise ValueError("行情涨幅缺失")
            return {"up": sum(v > 0 for v in changes), "down": sum(v < 0 for v in changes),
                    "limitUp": None, "limitDown": None,
                    "distribution": build_change_distribution(changes),
                    "source": "东方财富全量沪深京A股" + ("（延迟行情）" if "delay" in host else "")}
        except Exception:
            continue
    return None


def _cached_em_breadth_distribution() -> dict[str, Any] | None:
    """Return the last full distribution immediately and refresh it off the request path."""
    global _breadth_distribution_cache, _breadth_distribution_thread
    now = time.monotonic()
    with _breadth_lock:
        cached = _breadth_distribution_cache
        fresh = cached is not None and now - cached[0] < BREADTH_DISTRIBUTION_REFRESH_SECONDS
        if not fresh and (_breadth_distribution_thread is None or not _breadth_distribution_thread.is_alive()):
            def refresh() -> None:
                global _breadth_distribution_cache, _breadth_distribution_thread
                try:
                    value = fetch_em_breadth()
                    if _valid_breadth(value) and value.get("distribution") is not None:
                        with _breadth_lock:
                            _breadth_distribution_cache = (time.monotonic(), value)
                finally:
                    with _breadth_lock:
                        _breadth_distribution_thread = None

            _breadth_distribution_thread = threading.Thread(
                target=refresh,
                name="ft-breadth-distribution-refresh",
                daemon=True,
            )
            _breadth_distribution_thread.start()
        return cached[1] if cached else None


def _valid_breadth(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    counts = [_as_number(row.get(key)) for key in ("up", "down")]
    return all(v is not None and v >= 0 and v.is_integer() for v in counts) and sum(counts) > 0


def _default_adapters(current: datetime, trading_date: date, previous_date: date) -> dict[str, Callable[[], Any]]:
    index_rows: list[dict[str, Any]] = []

    def indices():
        rows = astock.index_quote()
        index_rows[:] = rows
        return rows

    def breadth():
        # MarketReviewService already owns the five-minute snapshot cache.
        # Calling the lightweight summary directly lets an explicit refresh
        # actually reread current counts instead of hitting a nested cache.
        summary = fetch_em_breadth_summary()
        full_market = _cached_em_breadth_distribution()
        if _valid_breadth(summary):
            return {**summary, "distribution": (full_market or {}).get("distribution")}
        if _valid_breadth(full_market):
            return full_market
        row = market._sentiment()
        if not _valid_breadth(row):
            raise RuntimeError("涨跌家数主源和备用源暂不可用")
        return {
            "up": row.get("up"), "down": row.get("down"),
            "limitUp": row.get("zt_real", row.get("zt")),
            "limitDown": row.get("dt_real", row.get("dt")),
            "distribution": None,
            "source": "乐咕乐股市场宽度",
        }

    def liquidity():
        if current.date() == trading_date and (current.hour, current.minute) >= (9, 15):
            return fetch_live_liquidity(index_rows or indices(), trading_date, previous_date)
        official = fetch_official_liquidity(trading_date, previous_date)
        return official

    def emotion():
        return market.get_short_term_emotion()

    def turnover():
        return (market.get_turnover_top() or {}).get("stocks", [])

    def sectors():
        return (market.get_overview() or {}).get("sectors", [])

    return {"indices": indices, "breadth": breadth, "liquidity": liquidity,
            "shortTermEmotion": emotion, "turnoverTop": turnover, "sectors": sectors}


class MarketReviewService:
    """Collect and cache the shared daily market snapshot."""

    def __init__(self, cache_dir: Path | None = None, now_fn: Callable[[], datetime] | None = None,
                 adapters: dict[str, Callable[[], Any]] | None = None):
        self.cache_dir = Path(cache_dir or REVIEW_CACHE_DIR)
        self.now_fn = now_fn or (lambda: datetime.now(BEIJING))
        self.adapters = adapters
        self._memory: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self._refresh_guard = threading.Lock()
        self._refresh_thread: threading.Thread | None = None

    def _path(self, trading_date: date) -> Path:
        return self.cache_dir / f"{trading_date.isoformat()}.json"

    def _load(self, trading_date: date) -> dict[str, Any] | None:
        path = self._path(trading_date)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload.get("review") if isinstance(payload, dict) else None
        except (OSError, ValueError):
            return None

    def _load_latest(self) -> dict[str, Any] | None:
        for path in sorted(self.cache_dir.glob("????-??-??.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                review = payload.get("review") if isinstance(payload, dict) else None
                if isinstance(review, dict) and self._required_complete(review):
                    return review
            except (OSError, ValueError):
                continue
        return None

    def _refresh_in_background(self) -> None:
        with self._refresh_guard:
            if self._refresh_thread and self._refresh_thread.is_alive():
                return
            def run():
                try:
                    self.get_review(force=True)
                except Exception:
                    # The API has already served the last real snapshot; a
                    # background outage must not surface as an unhandled thread.
                    pass
                finally:
                    with self._refresh_guard:
                        self._refresh_thread = None
            self._refresh_thread = threading.Thread(target=run, name="ft-market-review-refresh", daemon=True)
            self._refresh_thread.start()

    def prewarm(self) -> None:
        self._refresh_in_background()

    def _save(self, trading_date: date, review: dict[str, Any]) -> None:
        with REVIEW_FILE_LOCK:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            latest_brief = (self._load(trading_date) or {}).get("brief") or {}
            incoming_brief = review.get("brief") or {}
            if (latest_brief.get("generatedAt") or "") > (incoming_brief.get("generatedAt") or ""):
                review["brief"] = latest_brief
            path = self._path(trading_date)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps({"savedAt": review["generatedAt"], "review": review}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)

    @staticmethod
    def _required_complete(review: dict[str, Any]) -> bool:
        breadth = review.get("breadth") or {}
        liquidity = review.get("liquidity") or {}
        return len(review.get("indices") or []) >= 3 and breadth.get("up") is not None and breadth.get("down") is not None and liquidity.get("todayAmountYuan") is not None and liquidity.get("previousAmountYuan") is not None

    def _collect(self, current: datetime, trading_date: date, cached: dict[str, Any] | None) -> dict[str, Any]:
        adapters = self.adapters or _default_adapters(current, trading_date, _previous_trading_date(trading_date))
        source_rows: list[dict[str, Any]] = []
        stale = False
        values: dict[str, Any] = {}
        defaults = {"indices": [], "breadth": {}, "liquidity": build_liquidity(None, None), "shortTermEmotion": {}, "turnoverTop": [], "sectors": []}
        for name in ("indices", "breadth", "liquidity", "shortTermEmotion", "turnoverTop", "sectors"):
            try:
                raw = adapters[name]()
                if name == "indices":
                    raw = _normalize_indices(raw, trading_date)
                valid = raw is not None and raw != [] and raw != {}
                if name == "breadth":
                    valid = _valid_breadth(raw)
                if not valid:
                    raise RuntimeError("上游返回空数据")
                values[name] = raw
                source_rows.append({"name": name, "status": "fresh", "fetchedAt": _iso(current), "detail": raw.get("source", "") if name == "breadth" else ""})
            except Exception as exc:
                old = (cached or {}).get(name)
                if old not in (None, [], {}) and (name != "breadth" or _valid_breadth(old)):
                    values[name] = old
                    stale = True
                    source_rows.append({"name": name, "status": "stale", "fetchedAt": (cached or {}).get("generatedAt"), "detail": str(exc)})
                else:
                    values[name] = defaults[name]
                    source_rows.append({"name": name, "status": "missing", "fetchedAt": None, "detail": str(exc)})

        raw_breadth = values["breadth"] or {}
        distribution = raw_breadth.get("distribution")
        cached_distribution = ((cached or {}).get("breadth") or {}).get("distribution")
        if distribution is None and cached_distribution is not None:
            distribution = cached_distribution
            stale = True
            for source in source_rows:
                if source["name"] == "breadth":
                    source["status"] = "stale"
                    prefix = f"{source['detail']}；" if source["detail"] else ""
                    source["detail"] = prefix + "涨跌分布使用最近真实缓存"
                    break
        breadth = build_breadth(raw_breadth.get("up"), raw_breadth.get("down"), raw_breadth.get("limitUp"), raw_breadth.get("limitDown"), distribution)
        raw_liquidity = values["liquidity"] or {}
        liquidity = build_liquidity(raw_liquidity.get("todayAmountYuan"), raw_liquidity.get("previousAmountYuan"))
        indices = _normalize_indices(values["indices"], trading_date)
        missing_or_stale = stale or any(row["status"] != "fresh" for row in source_rows)
        review = {
            "tradingDate": trading_date.isoformat(),
            "generatedAt": _iso(current),
            "final": current.hour > 15 or (current.hour == 15 and current.minute >= 30),
            "stale": missing_or_stale,
            "partial": False,
            "sources": source_rows,
            "indices": indices,
            "breadth": breadth,
            "liquidity": liquidity,
            "shortTermEmotion": values["shortTermEmotion"] or {},
            "turnoverTop": values["turnoverTop"] or [],
            "sectors": values["sectors"] or [],
            "brief": (cached or {}).get("brief") or {"text": "", "status": "missing", "generatedAt": None, "promptVersion": PROMPT_VERSION},
        }
        review["partial"] = not self._required_complete(review) or missing_or_stale
        return review

    def get_review(self, force: bool = False, refresh: bool = False) -> dict[str, Any]:
        if force:
            with self._lock:
                return self._get_review(True)

        current = _ensure_beijing(self.now_fn())
        day = _trading_date(current)
        key = day.isoformat()
        memory = self._memory.get(key)
        cached = memory[1] if memory else self._load(day)
        busy = not self._lock.acquire(blocking=False)
        if not busy:
            self._lock.release()
        if cached and self._required_complete(cached):
            generated = cached.get("generatedAt")
            try:
                fresh = bool(generated) and (current - datetime.fromisoformat(generated)).total_seconds() < REVIEW_REFRESH_SECONDS
            except (TypeError, ValueError):
                fresh = False
            if fresh and not busy and not refresh:
                return cached
            self._refresh_in_background()
            return {**cached, "stale": bool(cached.get("stale")) or not fresh, "refreshing": True}

        latest = self._load_latest()
        if latest:
            self._refresh_in_background()
            return {**latest, "stale": True, "refreshing": True}

        if cached:
            self._refresh_in_background()
            return {**cached, "stale": True, "refreshing": True}

        with self._lock:
            return self._get_review(False)

    def _get_review(self, force: bool = False) -> dict[str, Any]:
        current = _ensure_beijing(self.now_fn())
        trading_date = _trading_date(current)
        key = trading_date.isoformat()
        memory = self._memory.get(key)
        if not force and memory and (current - memory[0]).total_seconds() < REVIEW_REFRESH_SECONDS:
            return memory[1]
        cached = self._load(trading_date)
        if not force and cached and cached.get("generatedAt"):
            try:
                if (current - datetime.fromisoformat(cached["generatedAt"])).total_seconds() < REVIEW_REFRESH_SECONDS:
                    self._memory[key] = (current, cached)
                    return cached
            except ValueError:
                pass
        review = self._collect(current, trading_date, cached)
        completed = _ensure_beijing(self.now_fn())
        review["generatedAt"] = _iso(completed)
        if any(row["status"] == "fresh" for row in review["sources"]):
            self._save(trading_date, review)
        self._memory[key] = (completed, review)
        return review

    def set_brief(self, trading_date: str, brief: dict[str, Any]) -> None:
        """Merge a generated brief without recollecting objective market data."""
        with self._lock:
            key = str(trading_date)
            current = self._memory.get(key)
            review = current[1] if current else self._load(date.fromisoformat(key))
            if not review:
                return
            updated = {**review, "brief": brief}
            self._save(date.fromisoformat(key), updated)
            self._memory[key] = (current[0] if current else _ensure_beijing(self.now_fn()), updated)


market_review_service = MarketReviewService()
