"""统一的 A 股股票 / 指数行情图表服务。

该模块只负责图表所需的 OHLCV 数据：上游适配、轻量进程缓存、过期降级和
离线 fixture。详情页的财务/研报等数据仍由现有接口提供。
"""

from __future__ import annotations

import os
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Any


PERIODS = {"intraday", "five_day", "daily", "weekly", "monthly"}
ADJUSTS = {"qfq", "hfq", ""}
INDEX_CODES = {
    "000001": ("上证指数", "sh000001"),
    "399001": ("深证成指", "sz399001"),
    "399006": ("创业板指", "sz399006"),
    "000300": ("沪深300", "sh000300"),
}

STALE_MAX_AGE = 86_400
CACHE_MAX_ENTRIES = 128
_CACHE: OrderedDict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = OrderedDict()
class ChartUnavailable(RuntimeError):
    """没有上游数据且没有可用缓存时抛出。"""


def normalize_asset_code(asset: str, code: str) -> str:
    if asset not in {"stock", "index"}:
        raise ValueError("asset 必须是 stock 或 index")
    normalized = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", normalized):
        raise ValueError("代码必须是 6 位数字")
    if asset == "index" and normalized not in INDEX_CODES:
        raise ValueError("第一阶段仅支持上证指数、深证成指、创业板指和沪深300")
    return normalized


def clear_cache() -> None:
    _CACHE.clear()


def _is_a_share_trading_time(now: datetime) -> bool:
    """Return whether a local Asia/Shanghai clock is inside an A-share session."""
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 570 <= minutes <= 690 or 780 <= minutes <= 900


def cache_ttl(period: str, now: datetime | None = None) -> int:
    """Short cache while prices move; reuse the closing snapshot after hours."""
    current = now or datetime.now()
    if _is_a_share_trading_time(current):
        return 15 if period in {"intraday", "five_day"} else 60
    return 300 if period in {"intraday", "five_day"} else 21_600


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float:
    if value is None or value == "" or value == "-":
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _date_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("/", "-")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat(timespec="minutes")
    except ValueError:
        return text[:19]


def _field(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _point(row: dict[str, Any]) -> dict[str, Any] | None:
    stamp = _field(row, "time", "时间", "日期", "date", "Date", "datetime")
    close = _number(_field(row, "close", "收盘", "收盘价", "最新价", "最新"))
    if not stamp or close == 0:
        return None
    opening = _number(_field(row, "open", "开盘", "开盘价")) or close
    high = _number(_field(row, "high", "最高", "最高价")) or max(opening, close)
    low = _number(_field(row, "low", "最低", "最低价")) or min(opening, close)
    average = _number(_field(row, "average", "均价", "均价")) or (opening + high + low + close) / 4
    return {
        "time": _date_key(stamp), "open": opening, "high": high, "low": low,
        "close": close, "average": average,
        "volume": _number(_field(row, "volume", "成交量", "vol", "成交量(手)")),
        "amount": _number(_field(row, "amount", "成交额", "成交额(元)", "成交额(千元)")),
    }


def _rows_to_points(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    points = [_point(dict(row)) for row in rows]
    return sorted((point for point in points if point), key=lambda item: item["time"])


def _aggregate(points: list[dict[str, Any]], granularity: str) -> list[dict[str, Any]]:
    if granularity == "daily":
        return points
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        try:
            d = datetime.fromisoformat(point["time"]).date()
        except ValueError:
            continue
        key = f"{d.year}-W{d.isocalendar().week:02d}" if granularity == "weekly" else f"{d.year}-{d.month:02d}"
        groups.setdefault(key, []).append(point)
    out = []
    for rows in groups.values():
        volume = sum(item["volume"] for item in rows)
        amount = sum(item["amount"] for item in rows)
        out.append({
            "time": rows[-1]["time"], "open": rows[0]["open"],
            "high": max(item["high"] for item in rows), "low": min(item["low"] for item in rows),
            "close": rows[-1]["close"],
            "average": sum(item["average"] for item in rows) / len(rows),
            "volume": volume, "amount": amount,
        })
    return out


def _trading_dates(count: int) -> list[date]:
    cursor = date(2026, 8, 28)
    out: list[date] = []
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(out))


def fixture_points(asset: str, code: str, period: str) -> list[dict[str, Any]]:
    """Deterministic offline fixture used by tests and disconnected development."""
    dates = _trading_dates(5 if period == "five_day" else 120 if period == "daily" else 260)
    if period in {"weekly", "monthly"}:
        dates = _trading_dates(260)
    points: list[dict[str, Any]] = []
    base = 100.0 + (int(code[-2:]) % 31) + (10 if asset == "index" else 0)
    if period in {"intraday", "five_day"}:
        dates = dates[-1:] if period == "intraday" else dates[-5:]
        for day_index, current in enumerate(dates):
            for minute_index, minute in enumerate((570, 600, 630, 660, 690, 720, 750, 810)):
                close = round(base + day_index * 0.7 + minute_index * 0.12, 2)
                opening = round(close - 0.08, 2)
                points.append({
                    "time": datetime.combine(current, datetime.min.time()).replace(hour=minute // 60, minute=minute % 60).isoformat(timespec="minutes"),
                    "open": opening, "high": round(close + 0.12, 2), "low": round(opening - 0.1, 2),
                    "close": close, "average": round((opening + close) / 2, 2),
                    "volume": float(1000 + day_index * 50 + minute_index * 10),
                    "amount": float((1000 + day_index * 50 + minute_index * 10) * close),
                })
    else:
        for day_index, current in enumerate(dates):
            close = round(base + day_index * 0.18, 2)
            opening = round(close - 0.15, 2)
            points.append({
                "time": current.isoformat(), "open": opening, "high": round(close + 0.25, 2),
                "low": round(opening - 0.2, 2), "close": close, "average": round((opening + close) / 2, 2),
                "volume": float(10000 + day_index * 100), "amount": float((10000 + day_index * 100) * close),
            })
        if period in {"weekly", "monthly"}:
            points = _aggregate(points, period)
    return points


def _akshare_rows(asset: str, code: str, period: str, adjust: str) -> Any:
    try:
        import akshare as ak
    except ImportError as exc:
        raise ChartUnavailable("akshare 未安装") from exc
    if asset == "stock":
        if period in {"intraday", "five_day"}:
            fn = getattr(ak, "stock_zh_a_hist_min_em", None)
            if fn is None:
                raise ChartUnavailable("AKShare 缺少 A 股分时接口")
            end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            start = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
            return fn(symbol=code, start_date=start, end_date=end, period="1", adjust=adjust)
        fn = getattr(ak, "stock_zh_a_hist", None)
        if fn is None:
            raise ChartUnavailable("AKShare 缺少 A 股历史接口")
        return fn(symbol=code, period="daily", adjust=adjust)
    if period in {"intraday", "five_day"}:
        fn = getattr(ak, "index_zh_a_hist_min_em", None)
        if fn is None:
            raise ChartUnavailable("AKShare 缺少指数分时接口")
        end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
        return fn(symbol=code, start_date=start, end_date=end, period="1")
    fn = getattr(ak, "index_zh_a_hist", None)
    if fn is None:
        raise ChartUnavailable("AKShare 缺少指数历史接口")
    return fn(symbol=code, period="daily")


def _fetch_from_akshare(asset: str, code: str, period: str, adjust: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    points = _rows_to_points(_akshare_rows(asset, code, period, adjust))
    quote_points = list(points)
    if period == "five_day":
        dates = {point["time"][:10] for point in points}
        if len(dates) < 5:
            raise ChartUnavailable("上游未返回完整五日分时")
        points = [point for point in points if point["time"][:10] in sorted(dates)[-5:]]
    elif period == "intraday":
        today = date.today().isoformat()
        today_points = [point for point in points if point["time"].startswith(today)]
        points = today_points or points[-240:]
    elif period in {"weekly", "monthly"}:
        points = _aggregate(points, period)
    if not points:
        raise ChartUnavailable("上游未返回行情数据")
    return "AKShare", points, quote_points


def _quote(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        raise ChartUnavailable("行情摘要缺少数据")
    dates = sorted({point["time"][:10] for point in points})
    latest_date = dates[-1]
    current = [point for point in points if point["time"][:10] == latest_date]
    previous_points = [point for point in points if point["time"][:10] < latest_date]
    latest = current[-1]
    close = latest["close"]
    prev_close = previous_points[-1]["close"] if previous_points else current[0]["open"]
    change = close - prev_close
    return {
        "price": close, "change": round(change, 4),
        "changePct": round(change / prev_close * 100, 4) if prev_close else 0,
        "open": current[0]["open"],
        "high": max(point["high"] for point in current),
        "low": min(point["low"] for point in current),
        "prevClose": prev_close,
        "volume": sum(point["volume"] for point in current),
        "amount": sum(point["amount"] for point in current),
    }


def get_chart(asset: str, code: str, period: str, adjust: str = "qfq") -> dict[str, Any]:
    code = normalize_asset_code(asset, code)
    if period not in PERIODS:
        raise ValueError("period 不受支持")
    if adjust not in ADJUSTS:
        raise ValueError("adjust 必须是 qfq、hfq 或空字符串")
    key = (asset, code, period, adjust)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < cache_ttl(period):
        _CACHE.move_to_end(key)
        return cached[1]
    try:
        fetched = _fetch_from_akshare(asset, code, period, adjust)
        if isinstance(fetched, tuple) and len(fetched) == 3:
            source, points, quote_points = fetched
        elif isinstance(fetched, tuple) and len(fetched) == 2:
            source, points = fetched
            quote_points = points
        else:
            source, points = "AKShare", fetched
            quote_points = points
        stale = False
    except Exception as exc:  # upstream is deliberately isolated from the detail cards
        if cached and now - cached[0] <= STALE_MAX_AGE:
            payload = dict(cached[1])
            payload["stale"] = True
            _CACHE.move_to_end(key)
            return payload
        _CACHE.pop(key, None)
        if os.environ.get("VR_ENABLE_MARKET_CHART_FIXTURE", "").lower() in {"1", "true", "yes"}:
            source, points, stale = "fixture", fixture_points(asset, code, period), True
            quote_points = fixture_points(asset, code, "five_day") if period == "intraday" else points
        else:
            raise ChartUnavailable(str(exc)) from exc
    name = INDEX_CODES[code][0] if asset == "index" else code
    payload = {
        "asset": asset, "code": code, "name": name, "period": period, "adjust": adjust,
        "source": source, "fetchedAt": _iso_now(), "stale": stale,
        "quote": _quote(quote_points), "points": points,
    }
    _CACHE[key] = (now, payload)
    _CACHE.move_to_end(key)
    while len(_CACHE) > CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)
    return payload
