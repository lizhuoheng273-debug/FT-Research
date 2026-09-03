"""面向 AI 研究的统一量价摘要，不向提示词注入整段原始 K 线。"""

from __future__ import annotations

import re
import statistics
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

import market_chart


SECTOR_CACHE_TTL = 300
SECTOR_STALE_MAX_AGE = 86_400
CATALOG_STALE_MAX_AGE = 86_400
_SECTOR_CACHE: OrderedDict[tuple[str, str, str, int], tuple[float, dict[str, Any]]] = OrderedDict()
_CATALOG_CACHE: tuple[float, dict[str, list[str]]] | None = None
_PERIOD_MAP = {"day": "daily", "week": "weekly", "month": "monthly"}
_SECTOR_PERIOD_MAP = {"day": "日k", "week": "周k", "month": "月k"}


def clear_cache() -> None:
    global _CATALOG_CACHE
    _SECTOR_CACHE.clear()
    _CATALOG_CACHE = None


def _round(value: float) -> float:
    return round(float(value), 4)


def _ema(values: list[float], window: int) -> float:
    alpha = 2 / (window + 1)
    value = values[0]
    for current in values[1:]:
        value = alpha * current + (1 - alpha) * value
    return _round(value)


def summarize_points(points: list[dict[str, Any]], count: int = 60) -> dict[str, Any]:
    rows = list(points or [])[-max(2, min(int(count or 60), 250)):]
    if not rows:
        return {"status": "unavailable", "data_gap": "历史行情为空"}
    closes = [float(row.get("close") or 0) for row in rows]
    highs = [float(row.get("high") or 0) for row in rows]
    lows = [float(row.get("low") or 0) for row in rows]
    volumes = [float(row.get("volume") or 0) for row in rows]
    amounts = [float(row.get("amount") or 0) for row in rows]
    returns = [
        (closes[index] / closes[index - 1] - 1) * 100
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    previous_volume = volumes[max(0, len(volumes) - 6):-1]
    previous_average = statistics.fmean(previous_volume) if previous_volume else 0
    start_close = closes[0]
    return {
        "status": "ok",
        "point_count": len(rows),
        "start": rows[0].get("time"),
        "end": rows[-1].get("time"),
        "latest_close": _round(closes[-1]),
        "return_pct": _round((closes[-1] / start_close - 1) * 100) if start_close else 0.0,
        "high": _round(max(highs)),
        "low": _round(min(lows)),
        "average_volume": _round(statistics.fmean(volumes)),
        "average_amount": _round(statistics.fmean(amounts)),
        "latest_volume": _round(volumes[-1]),
        "volume_ratio": _round(volumes[-1] / previous_average) if previous_average else None,
        "volatility_pct": _round(statistics.pstdev(returns)) if returns else 0.0,
        "ema": {f"ema{window}": _ema(closes, window) for window in (5, 10, 20, 60)},
    }


def _normalize_board_name(value: str) -> str:
    return re.sub(r"(?:概念|板块)$", "", re.sub(r"[\s\-_—]+", "", str(value or ""))).casefold()


def match_sector_board(keyword: str, concept_names: list[str], industry_names: list[str]) -> dict[str, Any]:
    target = _normalize_board_name(keyword)
    exact = []
    for board_type, names in (("concept", concept_names), ("industry", industry_names)):
        for symbol in names:
            if target and _normalize_board_name(symbol) == target:
                candidate = {"board_type": board_type, "symbol": symbol}
                if candidate not in exact:
                    exact.append(candidate)
    if len(exact) == 1:
        return {"status": "matched", **exact[0]}
    if len(exact) > 1:
        return {
            "status": "ambiguous",
            "data_gap": "板块名称存在多个精确匹配",
            "candidates": exact,
        }
    candidates = []
    for board_type, names in (("concept", concept_names), ("industry", industry_names)):
        for symbol in names:
            normalized = _normalize_board_name(symbol)
            if target and (target in normalized or normalized in target):
                candidates.append({"board_type": board_type, "symbol": symbol})
    return {
        "status": "unmatched",
        "data_gap": "没有唯一精确匹配的公开板块",
        "candidates": candidates[:8],
    }


def _catalog_names(rows: Any) -> list[str]:
    records = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows or [])
    output = []
    for row in records:
        value = next((row.get(key) for key in ("板块名称", "名称", "name", "symbol") if row.get(key)), None)
        if value and str(value) not in output:
            output.append(str(value))
    return output


def load_sector_catalogs() -> dict[str, list[str]]:
    global _CATALOG_CACHE
    now = time.time()
    if _CATALOG_CACHE and now - _CATALOG_CACHE[0] < SECTOR_CACHE_TTL:
        return _CATALOG_CACHE[1]
    try:
        import akshare as ak
        catalogs = {
            "concept": _catalog_names(ak.stock_board_concept_name_em()),
            "industry": _catalog_names(ak.stock_board_industry_name_em()),
        }
    except Exception:
        if _CATALOG_CACHE and now - _CATALOG_CACHE[0] <= CATALOG_STALE_MAX_AGE:
            return _CATALOG_CACHE[1]
        raise
    _CATALOG_CACHE = (now, catalogs)
    return catalogs


def _fetch_sector_points(board_type: str, symbol: str, period: str, count: int = 60) -> list[dict[str, Any]]:
    import akshare as ak

    start = (datetime.now() - timedelta(days=market_chart._request_window_days(_PERIOD_MAP[period], count))).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    function = ak.stock_board_concept_hist_em if board_type == "concept" else ak.stock_board_industry_hist_em
    rows = function(symbol=symbol, start_date=start, end_date=end, period=_SECTOR_PERIOD_MAP[period], adjust="")
    return market_chart._rows_to_points(rows)


def _sector_summary(identifier: str, period: str, count: int) -> dict[str, Any]:
    catalogs = load_sector_catalogs()
    match = match_sector_board(identifier, catalogs.get("concept", []), catalogs.get("industry", []))
    if match["status"] != "matched":
        return {"asset": "sector", "identifier": identifier, "period": period, **match}
    key = (match["board_type"], match["symbol"], period, count)
    now = time.time()
    cached = _SECTOR_CACHE.get(key)
    if cached and now - cached[0] < SECTOR_CACHE_TTL:
        return dict(cached[1])
    try:
        points = _fetch_sector_points(match["board_type"], match["symbol"], period, count)
        result = {
            "asset": "sector",
            "identifier": identifier,
            "matched_symbol": match["symbol"],
            "board_type": match["board_type"],
            "period": period,
            "source": "AKShare/Eastmoney",
            "stale": False,
            **summarize_points(points, count),
        }
        if result["status"] != "ok":
            raise RuntimeError(result["data_gap"])
    except Exception as exc:
        if cached and now - cached[0] <= SECTOR_STALE_MAX_AGE:
            result = dict(cached[1])
            result["stale"] = True
            return result
        return {
            "asset": "sector",
            "identifier": identifier,
            "period": period,
            "status": "unavailable",
            "data_gap": f"板块历史行情不可用：{exc}",
        }
    _SECTOR_CACHE[key] = (now, result)
    while len(_SECTOR_CACHE) > 64:
        _SECTOR_CACHE.popitem(last=False)
    return result


def fetch_chart_summary(asset: str, identifier: str, period: str = "day", count: int = 60) -> dict[str, Any]:
    if asset not in {"stock", "index", "sector"}:
        raise ValueError("asset 必须是 stock、index 或 sector")
    if period not in _PERIOD_MAP:
        raise ValueError("period 必须是 day、week 或 month")
    count = max(5, min(int(count or 60), 250))
    if asset == "sector":
        return _sector_summary(str(identifier or "").strip(), period, count)
    chart = market_chart.get_chart(asset, identifier, _PERIOD_MAP[period], "qfq" if asset == "stock" else "", count)
    return {
        "asset": asset,
        "identifier": identifier,
        "period": period,
        "source": chart.get("source"),
        "stale": bool(chart.get("stale")),
        **summarize_points(chart.get("points") or [], count),
    }
