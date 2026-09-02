from datetime import datetime

import pytest

import market_review


def _complete_adapters():
    return {
        "indices": lambda: [
            {"code": "000001", "name": "上证指数", "price": 3900.0, "change_pct": 0.2, "change_amt": 7.8},
            {"code": "399001", "name": "深证成指", "price": 12000.0, "change_pct": -0.1, "change_amt": -12.0},
            {"code": "399006", "name": "创业板指", "price": 2500.0, "change_pct": 0.4, "change_amt": 10.0},
            {"code": "000300", "name": "沪深300", "price": 3900.0, "change_pct": 0.1, "change_amt": 4.0},
        ],
        "breadth": lambda: {"up": 1200, "down": 800, "limitUp": 55, "limitDown": 9},
        "liquidity": lambda: {"todayAmountYuan": 1_000_000_000_000, "previousAmountYuan": 900_000_000_000},
        "shortTermEmotion": lambda: {"max_boards": 5, "lianban_count": 12},
        "turnoverTop": lambda: [{"code": "600000", "name": "示例", "price": 10.0, "pct": 1.2, "amount": 3_000_000_000}],
        "sectors": lambda: [{"name": "电子", "net": 1_000_000}],
    }


def test_breadth_exposes_no_flat_and_ratios_sum_to_100():
    result = market_review.build_breadth(600, 400, 30, 8)

    assert set(result) == {"up", "down", "upRatio", "downRatio", "limitUp", "limitDown"}
    assert result["upRatio"] + result["downRatio"] == 100


def test_liquidity_uses_same_yuan_unit_and_direction():
    result = market_review.build_liquidity(1_100, 1_000)

    assert result == {
        "todayAmountYuan": 1_100,
        "previousAmountYuan": 1_000,
        "changeAmountYuan": 100,
        "changePct": 10.0,
        "direction": "expanded",
    }


def test_review_contract_marks_partial_when_required_component_is_missing(tmp_path):
    adapters = _complete_adapters()
    adapters["liquidity"] = lambda: None
    service = market_review.MarketReviewService(
        cache_dir=tmp_path,
        now_fn=lambda: datetime(2026, 9, 2, 16, 0, tzinfo=market_review.BEIJING),
        adapters=adapters,
    )

    result = service.get_review(force=True)

    assert result["partial"] is True
    assert result["liquidity"]["todayAmountYuan"] is None
    assert result["brief"]["status"] == "missing"


def test_review_falls_back_to_real_cached_snapshot_as_stale(tmp_path):
    adapters = _complete_adapters()
    now = [datetime(2026, 9, 2, 16, 0, tzinfo=market_review.BEIJING)]
    service = market_review.MarketReviewService(cache_dir=tmp_path, now_fn=lambda: now[0], adapters=adapters)
    fresh = service.get_review(force=True)

    adapters["indices"] = lambda: (_ for _ in ()).throw(RuntimeError("indices offline"))
    stale = service.get_review(force=True)

    assert fresh["stale"] is False
    assert stale["stale"] is True
    assert stale["indices"][0]["price"] == 3900.0
    assert any(source["status"] == "stale" for source in stale["sources"])


def test_official_amount_parser_excludes_non_stock_rows():
    rows = [
        {"证券类别": "股票", "成交金额(亿元)": "1200"},
        {"证券类别": "基金", "成交金额(亿元)": "9999"},
        {"证券类别": "债券", "成交金额(亿元)": "9999"},
        {"证券类别": "回购", "成交金额(亿元)": "9999"},
    ]

    assert market_review.extract_official_stock_amount(rows) == 120_000_000_000


def test_review_endpoint_contract_is_unwrapped(monkeypatch):
    import app as app_module
    from fastapi.testclient import TestClient

    expected = {"tradingDate": "2026-09-02", "generatedAt": "now", "final": False, "stale": False, "partial": False,
                "sources": [], "indices": [], "breadth": {}, "liquidity": {}, "shortTermEmotion": {},
                "turnoverTop": [], "sectors": [], "brief": {"status": "missing"}}
    monkeypatch.setattr(app_module.market_review_service, "get_review", lambda force=False: expected)

    response = TestClient(app_module.app).get("/api/market/review")

    assert response.status_code == 200
    assert response.json() == expected
