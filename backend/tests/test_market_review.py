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


def test_null_breadth_cannot_overwrite_successful_counts(tmp_path):
    adapters = _complete_adapters()
    service = market_review.MarketReviewService(cache_dir=tmp_path, adapters=adapters)
    service.get_review(force=True)
    adapters["breadth"] = lambda: {"up": None, "down": None, "limitUp": None, "limitDown": None}
    result = service.get_review(force=True)
    assert result["breadth"]["up"] == 1200
    assert result["breadth"]["down"] == 800
    assert next(s for s in result["sources"] if s["name"] == "breadth")["status"] == "stale"


def test_empty_breadth_is_missing_not_fresh(tmp_path):
    adapters = _complete_adapters()
    adapters["breadth"] = lambda: {"up": None, "down": None}
    result = market_review.MarketReviewService(cache_dir=tmp_path, adapters=adapters).get_review(force=True)
    assert next(s for s in result["sources"] if s["name"] == "breadth")["status"] == "missing"


def test_review_serves_last_snapshot_while_background_collection_is_busy(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    service = market_review.MarketReviewService(cache_dir=tmp_path, adapters=_complete_adapters())
    first = service.get_review(force=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with service._lock:
            future = pool.submit(service.get_review)
            result = future.result(timeout=0.2)
    assert result["breadth"] == first["breadth"]
    assert result["refreshing"] is True


def test_late_market_collection_cannot_restore_an_older_brief(tmp_path):
    from datetime import date
    service = market_review.MarketReviewService(cache_dir=tmp_path, adapters=_complete_adapters())
    original = service.get_review(force=True)
    updated = {**original, "brief": {"text": "新版完整简述。", "generatedAt": "2026-09-02T21:00:00+08:00", "promptVersion": "market-review-brief-v2"}}
    day = date.fromisoformat(original["tradingDate"])
    service._save(day, updated)
    service._save(day, original)
    assert service._load(day)["brief"]["text"] == "新版完整简述。"


def test_breadth_fallback_counts_complete_pages_and_ignores_suspended(monkeypatch):
    pages = {
        1: [{"f12": "600001", "f13": 1, "f2": 10, "f3": 2}, {"f12": "600002", "f13": 1, "f2": 10, "f3": -2}],
        2: [{"f12": "000001", "f13": 0, "f2": 10, "f3": 0}, {"f12": "000002", "f13": 0, "f2": "-", "f3": "-"}],
        3: [{"f12": "000003", "f13": 0, "f2": 12, "f3": 1}],
    }
    def get(url, params, **kwargs):
        return type("Response", (), {"json": lambda self: {"data": {"total": 5, "diff": pages[params["pn"]]}}})()
    monkeypatch.setattr(market_review.astock, "em_get", get)
    result = market_review.fetch_em_breadth()
    assert result["up"] == 2
    assert result["down"] == 1
    assert result["limitUp"] is None  # Do not infer a price-limit count from a generic % threshold.


def test_breadth_fallback_rejects_incomplete_or_repeated_pages(monkeypatch):
    monkeypatch.setattr(market_review.astock, "em_get", lambda *a, **kw: type("Response", (), {"json": lambda self: {"data": {"total": 5, "diff": [{"f12": "600001", "f13": 1, "f2": 10, "f3": 2}]}}})())
    assert market_review.fetch_em_breadth() is None


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
