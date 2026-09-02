"""统一每日市场复盘快照。

这个模块只聚合客观数据，并为每个数据组件保留来源状态。生产路径不生成
fixture：上游成功值才会写入快照，失败时只能回填最近一次真实快照。
"""

from __future__ import annotations

import json
import hashlib
import math
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import astock
import market


BEIJING = ZoneInfo("Asia/Shanghai")
PROMPT_VERSION = "market-review-brief-v2"
INDEX_CODES = ("000001", "399001", "399006", "000300")
REVIEW_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "market-review"
_breadth_lock = threading.Lock()
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


def build_breadth(up: int | None, down: int | None, limit_up: int | None, limit_down: int | None) -> dict[str, Any]:
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


def fetch_official_liquidity(trading_date: date, previous_date: date) -> dict[str, Any] | None:
    """Fetch same-scope stock turnover from official SSE and SZSE statistics."""
    try:
        import akshare as ak

        def ymd(value: date) -> str:
            return value.strftime("%Y%m%d")

        def total(value: date) -> int:
            sse = extract_official_stock_amount(ak.stock_sse_deal_daily(date=ymd(value)))
            szse = extract_official_stock_amount(ak.stock_szse_summary(date=ymd(value)))
            if sse is None or szse is None:
                raise RuntimeError("官方交易所统计缺少股票成交额")
            return sse + szse

        return {"todayAmountYuan": total(trading_date), "previousAmountYuan": total(previous_date)}
    except Exception:
        return None


def _normalize_index(row: dict[str, Any]) -> dict[str, Any] | None:
    code = str(row.get("code") or row.get("代码") or "")
    if code not in INDEX_CODES:
        return None
    price = _as_number(row.get("price", row.get("现价")))
    change_pct = _as_number(row.get("change_pct", row.get("changePct", row.get("涨跌幅"))))
    change = _as_number(row.get("change_amt", row.get("change", row.get("涨跌"))))
    if price is None:
        return None
    return {
        "code": code,
        "name": str(row.get("name") or row.get("名称") or code),
        "price": price,
        "change": change,
        "changePct": change_pct,
        "source": str(row.get("source") or "腾讯行情"),
        "updatedAt": str(row.get("updatedAt") or row.get("更新时间") or ""),
        "stale": bool(row.get("stale", False)),
    }


def _normalize_indices(rows: Any) -> list[dict[str, Any]]:
    output = [_normalize_index(row) for row in _records(rows)]
    return [row for row in output if row]


def fetch_em_breadth() -> dict[str, Any] | None:
    """Count a complete沪深京 A-share universe; never treat a partial page as market breadth."""
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            rows: dict[str, dict] = {}
            total = None
            for page in range(1, 101):
                params = {"pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                          "fid": "f12", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
                          "fields": "f2,f3,f12,f13"}
                payload = astock.em_get(f"https://{host}/api/qt/clist/get", params=params,
                                       headers={"User-Agent": astock.UA}, timeout=12).json().get("data") or {}
                count = int(payload.get("total") or 0)
                if count <= 0 or (total is not None and count != total):
                    raise ValueError("行情分页总数不完整")
                total = count
                before = len(rows)
                for row in payload.get("diff") or []:
                    code = str(row.get("f12", ""))
                    if len(code) == 6 and code.isdigit():
                        rows[f"{row.get('f13')}:{code}"] = row
                if len(rows) == total:
                    break
                if len(rows) <= before:
                    raise ValueError("行情分页为空或重复")
            if len(rows) != total:
                raise ValueError("行情分页未收齐")
            changes = [_as_number(row.get("f3")) for row in rows.values()
                       if (_as_number(row.get("f2")) or 0) > 0]
            changes = [value for value in changes if value is not None]
            if not changes:
                raise ValueError("行情涨幅缺失")
            return {"up": sum(v > 0 for v in changes), "down": sum(v < 0 for v in changes),
                    "limitUp": None, "limitDown": None,
                    "source": "东方财富全量沪深京A股" + ("（延迟行情）" if "delay" in host else "")}
        except Exception:
            continue
    return None


def _valid_breadth(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    counts = [_as_number(row.get(key)) for key in ("up", "down")]
    return all(v is not None and v >= 0 and v.is_integer() for v in counts) and sum(counts) > 0


def _default_adapters(trading_date: date, previous_date: date) -> dict[str, Callable[[], Any]]:
    def indices():
        return astock.index_quote()

    def breadth():
        row = market._sentiment()
        if not _valid_breadth(row):
            with _breadth_lock:
                fallback = market._cached("review_breadth", fetch_em_breadth)
            if not _valid_breadth(fallback):
                raise RuntimeError("涨跌家数主源和备用源暂不可用")
            return fallback
        return {
            "up": row.get("up"), "down": row.get("down"),
            "limitUp": row.get("zt_real", row.get("zt")),
            "limitDown": row.get("dt_real", row.get("dt")),
            "source": "乐咕乐股市场宽度",
        }

    def liquidity():
        return fetch_official_liquidity(trading_date, previous_date)

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

    def _path(self, trading_date: date) -> Path:
        return self.cache_dir / f"{trading_date.isoformat()}.json"

    def _load(self, trading_date: date) -> dict[str, Any] | None:
        path = self._path(trading_date)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload.get("review") if isinstance(payload, dict) else None
        except (OSError, ValueError):
            return None

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
        adapters = self.adapters or _default_adapters(trading_date, _previous_trading_date(trading_date))
        source_rows: list[dict[str, Any]] = []
        stale = False
        values: dict[str, Any] = {}
        defaults = {"indices": [], "breadth": {}, "liquidity": build_liquidity(None, None), "shortTermEmotion": {}, "turnoverTop": [], "sectors": []}
        for name in ("indices", "breadth", "liquidity", "shortTermEmotion", "turnoverTop", "sectors"):
            try:
                raw = adapters[name]()
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
        breadth = build_breadth(raw_breadth.get("up"), raw_breadth.get("down"), raw_breadth.get("limitUp"), raw_breadth.get("limitDown"))
        raw_liquidity = values["liquidity"] or {}
        liquidity = build_liquidity(raw_liquidity.get("todayAmountYuan"), raw_liquidity.get("previousAmountYuan"))
        indices = _normalize_indices(values["indices"])
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

    def get_review(self, force: bool = False) -> dict[str, Any]:
        # API requests and the post-close scheduler must share one collection.
        acquired = self._lock.acquire(blocking=False)
        if not acquired and not force:
            day = _trading_date(_ensure_beijing(self.now_fn()))
            hit = self._memory.get(day.isoformat())
            cached = hit[1] if hit else self._load(day)
            if cached:
                return {**cached, "stale": True, "refreshing": True}
        if not acquired:
            self._lock.acquire()
        try:
            return self._get_review(force)
        finally:
            self._lock.release()

    def _get_review(self, force: bool = False) -> dict[str, Any]:
        current = _ensure_beijing(self.now_fn())
        trading_date = _trading_date(current)
        key = trading_date.isoformat()
        memory = self._memory.get(key)
        if not force and memory and (current - memory[0]).total_seconds() < 60:
            return memory[1]
        cached = self._load(trading_date)
        if not force and cached and cached.get("generatedAt"):
            try:
                if (current - datetime.fromisoformat(cached["generatedAt"])).total_seconds() < 60:
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
        key = str(trading_date)
        current = self._memory.get(key)
        review = current[1] if current else self._load(date.fromisoformat(key))
        if not review:
            return
        updated = {**review, "brief": brief}
        self._save(date.fromisoformat(key), updated)
        self._memory[key] = (current[0] if current else _ensure_beijing(self.now_fn()), updated)


market_review_service = MarketReviewService()
