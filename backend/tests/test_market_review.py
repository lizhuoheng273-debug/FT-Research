from datetime import datetime, timedelta

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


def test_previous_day_index_quotes_cannot_replace_same_day_cached_indices(tmp_path):
    adapters = _complete_adapters()
    service = market_review.MarketReviewService(
        cache_dir=tmp_path,
        now_fn=lambda: datetime(2026, 9, 4, 11, 0, tzinfo=market_review.BEIJING),
        adapters=adapters,
    )
    original = service.get_review(force=True)
    adapters["indices"] = lambda: [
        {**row, "updatedAt": "2026-09-03 15:00:00"}
        for row in _complete_adapters()["indices"]()
    ]

    refreshed = service.get_review(force=True)

    assert refreshed["indices"] == original["indices"]
    assert next(row for row in refreshed["sources"] if row["name"] == "indices")["status"] == "stale"


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


def test_expired_review_returns_cached_snapshot_without_waiting_for_refresh(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    now = [datetime(2026, 9, 2, 16, 0, tzinfo=market_review.BEIJING)]
    adapters = _complete_adapters()
    service = market_review.MarketReviewService(cache_dir=tmp_path, now_fn=lambda: now[0], adapters=adapters)
    original = service.get_review(force=True)
    now[0] += timedelta(minutes=6)
    release = threading.Event()
    original_indices = adapters["indices"]
    def slow_indices():
        release.wait(2)
        return original_indices()
    adapters["indices"] = slow_indices

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.get_review)
        result = future.result(timeout=0.2)
    release.set()

    assert result["generatedAt"] == original["generatedAt"]
    assert result["refreshing"] is True
    assert result["stale"] is True


def test_new_trading_day_returns_latest_snapshot_while_current_day_warms(tmp_path):
    now = [datetime(2026, 9, 2, 16, 0, tzinfo=market_review.BEIJING)]
    service = market_review.MarketReviewService(cache_dir=tmp_path, now_fn=lambda: now[0], adapters=_complete_adapters())
    original = service.get_review(force=True)
    now[0] = datetime(2026, 9, 3, 9, 0, tzinfo=market_review.BEIJING)

    result = service.get_review()

    assert result["tradingDate"] == original["tradingDate"]
    assert result["refreshing"] is True
    assert result["stale"] is True


def test_requested_refresh_returns_current_snapshot_and_updates_in_background(tmp_path):
    import threading

    adapters = _complete_adapters()
    service = market_review.MarketReviewService(cache_dir=tmp_path, adapters=adapters)
    original = service.get_review(force=True)
    release = threading.Event()
    original_indices = adapters["indices"]
    def slow_indices():
        release.wait(1)
        return original_indices()
    adapters["indices"] = slow_indices

    result = service.get_review(refresh=True)
    release.set()

    assert result["generatedAt"] == original["generatedAt"]
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


def test_intraday_liquidity_compares_previous_trading_day_at_the_same_time(monkeypatch):
    rows = [
        {"code": "000001", "amountYuan": 560_288_286_118, "updatedAt": "2026-09-04 12:05:00"},
        {"code": "399001", "amountYuan": 673_883_645_486, "updatedAt": "2026-09-04 12:05:00"},
        {"code": "399006", "amountYuan": 310_000_000_000, "updatedAt": "2026-09-04 12:05:00"},
    ]
    histories = {
        "sh000001": [
            {"date": "2026-09-04", "points": [{"time": "11:30", "amountYuan": 560_288_286_118}]},
            {"date": "2026-09-03", "points": [{"time": "11:29", "amountYuan": 514_000_000_000}, {"time": "11:30", "amountYuan": 515_810_581_316.60}]},
        ],
        "sz399001": [
            {"date": "2026-09-04", "points": [{"time": "11:30", "amountYuan": 673_883_645_486}]},
            {"date": "2026-09-03", "points": [{"time": "11:30", "amountYuan": 582_858_337_014.86}]},
        ],
    }
    monkeypatch.setattr(market_review.astock, "index_intraday_days", lambda code: histories[code], raising=False)

    result = market_review.fetch_live_liquidity(rows, datetime(2026, 9, 4).date(), datetime(2026, 9, 3).date())

    assert result == {"todayAmountYuan": 1_234_171_931_604, "previousAmountYuan": 1_098_668_918_331.46}


def test_tencent_intraday_parser_keeps_dates_times_and_yuan_amounts():
    payload = {
        "code": 0,
        "data": {
            "sh000001": {
                "data": [
                    {"date": "20260904", "data": ["0930 3955.55 4776944 6930221455.20", "1130 3955.85 324693271 560288286118"]},
                    {"date": "20260903", "data": ["1130 3958.19 320081276 515810581316.60"]},
                ]
            }
        },
    }

    assert market_review.astock._parse_index_intraday_days(payload, "sh000001") == [
        {"date": "2026-09-04", "points": [
            {"time": "09:30", "amountYuan": 6_930_221_455.20},
            {"time": "11:30", "amountYuan": 560_288_286_118.0},
        ]},
        {"date": "2026-09-03", "points": [{"time": "11:30", "amountYuan": 515_810_581_316.60}]},
    ]


def test_intraday_liquidity_keeps_current_total_when_same_time_history_is_missing(monkeypatch):
    rows = [
        {"code": "000001", "amountYuan": 560_000_000_000, "updatedAt": "2026-09-04 11:47:00"},
        {"code": "399001", "amountYuan": 670_000_000_000, "updatedAt": "2026-09-04 11:47:00"},
    ]
    monkeypatch.setattr(market_review.astock, "index_intraday_days", lambda _code: [], raising=False)

    assert market_review.fetch_live_liquidity(rows, datetime(2026, 9, 4).date(), datetime(2026, 9, 3).date()) == {
        "todayAmountYuan": 1_230_000_000_000,
        "previousAmountYuan": None,
    }


def test_intraday_liquidity_uses_latest_session_before_an_exchange_holiday(monkeypatch):
    rows = [
        {"code": "000001", "amountYuan": 560_000_000_000, "updatedAt": "2026-10-09 11:30:00"},
        {"code": "399001", "amountYuan": 670_000_000_000, "updatedAt": "2026-10-09 11:30:00"},
    ]
    histories = {
        "sh000001": [{"date": "2026-09-30", "points": [{"time": "11:30", "amountYuan": 500_000_000_000}]}],
        "sz399001": [{"date": "2026-09-30", "points": [{"time": "11:30", "amountYuan": 600_000_000_000}]}],
    }
    monkeypatch.setattr(market_review.astock, "index_intraday_days", lambda code: histories[code])

    assert market_review.fetch_live_liquidity(rows, datetime(2026, 10, 9).date(), datetime(2026, 10, 8).date()) == {
        "todayAmountYuan": 1_230_000_000_000,
        "previousAmountYuan": 1_100_000_000_000,
    }


def test_postclose_current_day_prefers_same_source_full_day_comparison(monkeypatch):
    current = datetime(2026, 9, 4, 16, 0, tzinfo=market_review.BEIJING)
    rows = [
        {"code": "000001", "name": "上证指数", "price": 3900, "change_pct": 0.1, "updatedAt": "2026-09-04 15:00:00", "amountYuan": 600_000_000_000},
        {"code": "399001", "name": "深证成指", "price": 12000, "change_pct": 0.1, "updatedAt": "2026-09-04 15:00:00", "amountYuan": 700_000_000_000},
    ]
    histories = {
        "sh000001": [{"date": "2026-09-03", "points": [{"time": "15:00", "amountYuan": 550_000_000_000}]}],
        "sz399001": [{"date": "2026-09-03", "points": [{"time": "15:00", "amountYuan": 650_000_000_000}]}],
    }
    monkeypatch.setattr(market_review.astock, "index_quote", lambda: rows)
    monkeypatch.setattr(market_review.astock, "index_intraday_days", lambda code: histories[code], raising=False)
    monkeypatch.setattr(market_review, "fetch_official_liquidity", lambda *_args: {"todayAmountYuan": 1, "previousAmountYuan": 1})
    adapters = market_review._default_adapters(current, current.date(), datetime(2026, 9, 3).date())
    adapters["indices"]()

    assert adapters["liquidity"]() == {"todayAmountYuan": 1_300_000_000_000, "previousAmountYuan": 1_200_000_000_000}


def test_intraday_liquidity_rejects_previous_day_tencent_values(monkeypatch):
    rows = [
        {"code": "000001", "amountYuan": 560_000_000_000, "updatedAt": "2026-09-03 15:00:00"},
        {"code": "399001", "amountYuan": 670_000_000_000, "updatedAt": "2026-09-03 15:00:00"},
    ]
    monkeypatch.setattr(market_review, "fetch_official_stock_amount", lambda _day: 900_000_000_000)

    assert market_review.fetch_live_liquidity(rows, datetime(2026, 9, 4).date(), datetime(2026, 9, 3).date()) is None


def test_premarket_adapter_does_not_fall_back_to_same_day_live_turnover(monkeypatch):
    current = datetime(2026, 9, 4, 9, 0, tzinfo=market_review.BEIJING)
    rows = [
        {"code": "000001", "name": "上证指数", "price": 3900, "change_pct": 0.1, "updatedAt": "2026-09-04 09:00:00", "amountYuan": 1},
        {"code": "399001", "name": "深证成指", "price": 12000, "change_pct": 0.1, "updatedAt": "2026-09-04 09:00:00", "amountYuan": 1},
    ]
    monkeypatch.setattr(market_review.astock, "index_quote", lambda: rows)
    monkeypatch.setattr(market_review, "fetch_official_liquidity", lambda *_args: None)
    adapters = market_review._default_adapters(current, current.date(), datetime(2026, 9, 3).date())
    adapters["indices"]()

    assert adapters["liquidity"]() is None


def test_previous_official_total_searches_back_across_exchange_holidays(monkeypatch):
    amounts = {datetime(2026, 9, 30).date(): 880_000_000_000}
    monkeypatch.setattr(market_review, "fetch_official_stock_amount", lambda day: amounts.get(day))

    result = market_review.fetch_latest_official_stock_amount(datetime(2026, 10, 6).date())

    assert result == 880_000_000_000


def test_latest_fallback_skips_newer_incomplete_snapshot(tmp_path):
    from datetime import date
    service = market_review.MarketReviewService(
        cache_dir=tmp_path,
        now_fn=lambda: datetime(2026, 9, 2, 16, 0, tzinfo=market_review.BEIJING),
        adapters=_complete_adapters(),
    )
    complete = service.get_review(force=True)
    incomplete = {**complete, "tradingDate": "2026-09-03", "liquidity": market_review.build_liquidity(None, None), "partial": True}
    service._save(date(2026, 9, 3), incomplete)

    assert service._load_latest()["tradingDate"] == complete["tradingDate"]


def test_brief_write_cannot_restore_market_data_replaced_by_refresh(tmp_path):
    import threading
    from datetime import date

    adapters = _complete_adapters()
    service = market_review.MarketReviewService(cache_dir=tmp_path, adapters=adapters)
    original = service.get_review(force=True)
    adapters["indices"] = lambda: [{**row, "price": 2.0} for row in _complete_adapters()["indices"]()]
    saved = threading.Event()
    setter_entered_save = threading.Event()
    release = threading.Event()
    original_save = service._save
    def paused_save(day, review):
        if threading.current_thread().name == "brief-setter":
            setter_entered_save.set()
            return original_save(day, review)
        original_save(day, review)
        saved.set()
        release.wait(1)
    service._save = paused_save
    refresher = threading.Thread(target=lambda: service.get_review(force=True))
    refresher.start()
    assert saved.wait(0.2)
    setter = threading.Thread(name="brief-setter", target=lambda: service.set_brief(original["tradingDate"], {"text": "new", "generatedAt": "2026-09-02T21:00:00+08:00"}))
    setter.start()
    setter_entered_save.wait(0.1)
    release.set()
    refresher.join(1)
    setter.join(1)

    persisted = service._load(date.fromisoformat(original["tradingDate"]))
    assert persisted["indices"][0]["price"] == 2.0
    assert persisted["brief"]["text"] == "new"


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
