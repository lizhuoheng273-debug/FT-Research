"""统一历史行情研究摘要。"""

import pytest

import research_chart
import tools


def _point(day: int, close: float = 10.0, volume: float = 100.0) -> dict:
    return {
        "time": f"2026-08-{day:02d}",
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": volume,
        "amount": volume * close,
    }


def test_summarize_points_returns_objective_price_volume_and_ema_metrics():
    points = [_point(day, volume=100.0) for day in range(1, 10)] + [_point(10, volume=200.0)]

    summary = research_chart.summarize_points(points, count=10)

    assert summary["status"] == "ok"
    assert summary["point_count"] == 10
    assert summary["return_pct"] == 0.0
    assert summary["high"] == 11.0
    assert summary["low"] == 9.0
    assert summary["average_volume"] == 110.0
    assert summary["volume_ratio"] == 2.0
    assert summary["volatility_pct"] == 0.0
    assert summary["ema"] == {"ema5": 10.0, "ema10": 10.0, "ema20": 10.0, "ema60": 10.0}


def test_summarize_points_rejects_missing_history_instead_of_making_data_up():
    assert research_chart.summarize_points([], count=60) == {
        "status": "unavailable",
        "data_gap": "历史行情为空",
    }


def test_sector_matching_uses_only_a_unique_exact_normalized_name():
    result = research_chart.match_sector_board(
        "低空经济板块",
        concept_names=["低空经济", "商业航天"],
        industry_names=["航空机场"],
    )

    assert result == {"status": "matched", "board_type": "concept", "symbol": "低空经济"}


def test_sector_matching_reports_ambiguity_without_silently_choosing():
    result = research_chart.match_sector_board(
        "半导体",
        concept_names=["半导体概念"],
        industry_names=["半导体"],
    )

    assert result["status"] == "ambiguous"
    assert result["data_gap"] == "板块名称存在多个精确匹配"
    assert result["candidates"] == [
        {"board_type": "concept", "symbol": "半导体概念"},
        {"board_type": "industry", "symbol": "半导体"},
    ]


def test_sector_matching_reports_candidates_but_does_not_use_fuzzy_match():
    result = research_chart.match_sector_board(
        "AI算力",
        concept_names=["算力租赁", "东数西算"],
        industry_names=["计算机设备"],
    )

    assert result["status"] == "unmatched"
    assert result["data_gap"] == "没有唯一精确匹配的公开板块"
    assert result["candidates"] == []


def test_sector_fetch_uses_stale_cache_when_upstream_temporarily_fails(monkeypatch):
    research_chart.clear_cache()
    clock = {"value": 1_000.0}
    monkeypatch.setattr(research_chart.time, "time", lambda: clock["value"])
    monkeypatch.setattr(
        research_chart,
        "load_sector_catalogs",
        lambda: {"concept": ["低空经济"], "industry": []},
    )
    monkeypatch.setattr(
        research_chart,
        "_fetch_sector_points",
        lambda _kind, _symbol, _period, _count=60: [_point(day) for day in range(1, 11)],
    )

    first = research_chart.fetch_chart_summary("sector", "低空经济", "day", 10)
    clock["value"] += research_chart.SECTOR_CACHE_TTL + 1
    monkeypatch.setattr(
        research_chart,
        "_fetch_sector_points",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("upstream unavailable")),
    )
    second = research_chart.fetch_chart_summary("sector", "低空经济", "day", 10)

    assert first["stale"] is False
    assert second["status"] == "ok"
    assert second["stale"] is True


def test_sector_fetch_without_cache_returns_explicit_data_gap(monkeypatch):
    research_chart.clear_cache()
    monkeypatch.setattr(
        research_chart,
        "load_sector_catalogs",
        lambda: {"concept": ["低空经济"], "industry": []},
    )
    monkeypatch.setattr(
        research_chart,
        "_fetch_sector_points",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("upstream unavailable")),
    )

    result = research_chart.fetch_chart_summary("sector", "低空经济", "day", 10)

    assert result["status"] == "unavailable"
    assert "upstream unavailable" in result["data_gap"]
    assert "ema" not in result


@pytest.mark.parametrize("asset,identifier", [("stock", "600519"), ("index", "000001")])
def test_stock_and_index_use_existing_market_chart_service(monkeypatch, asset, identifier):
    monkeypatch.setattr(
        research_chart.market_chart,
        "get_chart",
        lambda got_asset, got_identifier, period, adjust, count=60: {
            "asset": got_asset,
            "code": got_identifier,
            "period": period,
            "source": "fixture",
            "stale": False,
            "points": [_point(day) for day in range(1, 11)],
        },
    )

    result = research_chart.fetch_chart_summary(asset, identifier, "day", 10)

    assert result["status"] == "ok"
    assert result["asset"] == asset
    assert result["identifier"] == identifier
    assert result["period"] == "day"


def test_sector_history_request_uses_requested_count_window(monkeypatch):
    research_chart.clear_cache()
    seen = {}
    monkeypatch.setattr(
        research_chart,
        "load_sector_catalogs",
        lambda: {"concept": ["低空经济"], "industry": []},
    )

    def fetch(_kind, _symbol, _period, count=60):
        seen["count"] = count
        return [_point(day) for day in range(1, 11)]

    monkeypatch.setattr(research_chart, "_fetch_sector_points", fetch)
    research_chart.fetch_chart_summary("sector", "低空经济", "day", 30)

    assert seen["count"] == 30


def test_ai_tool_exposes_condensed_market_chart_summary(monkeypatch):
    expected = {
        "status": "ok",
        "asset": "sector",
        "identifier": "低空经济",
        "period": "week",
        "ema": {"ema5": 10.0},
    }
    monkeypatch.setattr(research_chart, "fetch_chart_summary", lambda *args: expected)

    result = tools.exec_tool(
        "query_market_chart",
        {"asset": "sector", "identifier": "低空经济", "period": "week", "count": 60},
    )

    assert result == expected
