import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import time

import market_chart
import app as app_module

client = TestClient(app_module.app)


def test_normalize_asset_code_keeps_index_namespace_separate():
    assert market_chart.normalize_asset_code("stock", "600519") == "600519"
    assert market_chart.normalize_asset_code("index", "000001") == "000001"
    assert market_chart.normalize_asset_code("index", "000680") == "000680"
    assert market_chart.normalize_asset_code("index", "000688") == "000688"
    assert market_chart.INDEX_CODES["000680"] == ("科创综指", "sh000680")
    assert market_chart.INDEX_CODES["000688"] == ("科创50", "sh000688")
    with pytest.raises(ValueError):
        market_chart.normalize_asset_code("stock", "sh000001")


def test_fixture_generator_has_uniform_ohlcv_points():
    points = market_chart.fixture_points("stock", "600519", "daily")
    assert points
    assert {"time", "open", "high", "low", "close", "average", "volume", "amount"} <= set(points[0])


def test_five_day_fixture_contains_five_trading_dates():
    points = market_chart.fixture_points("stock", "600519", "five_day")
    dates = {point["time"][:10] for point in points}
    assert len(dates) == 5


def test_cache_hit_returns_fresh_data_without_upstream(monkeypatch):
    market_chart.clear_cache()
    calls = []
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: calls.append(1) or market_chart.fixture_points("index", "000001", "daily"))
    first = market_chart.get_chart("index", "000001", "daily", "qfq")
    second = market_chart.get_chart("index", "000001", "daily", "qfq")
    assert first["stale"] is False
    assert second["source"] == first["source"]
    assert len(calls) == 1


def test_force_refresh_bypasses_fresh_cache_and_fetches_upstream(monkeypatch):
    market_chart.clear_cache()
    calls = []
    first_points = market_chart.fixture_points("index", "000001", "daily")
    second_points = [{**first_points[-1], "close": first_points[-1]["close"] + 1}]

    def fetch(*args, **kwargs):
        calls.append(kwargs)
        return ("fixture", first_points if len(calls) == 1 else second_points, first_points)

    monkeypatch.setattr(market_chart, "_fetch_from_akshare", fetch)
    first = market_chart.get_chart("index", "000001", "daily", "qfq")
    refreshed = market_chart.get_chart("index", "000001", "daily", "qfq", force=True)

    assert len(calls) == 2
    assert refreshed["points"] == second_points
    assert refreshed["stale"] is False


def test_force_refresh_preserves_cached_chart_when_upstream_fails(monkeypatch):
    market_chart.clear_cache()
    points = market_chart.fixture_points("stock", "600519", "daily")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: ("fixture", points, points))
    cached = market_chart.get_chart("stock", "600519", "daily", "qfq")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    fallback = market_chart.get_chart("stock", "600519", "daily", "qfq", force=True)

    assert fallback["points"] == cached["points"]
    assert fallback["stale"] is True


def test_market_chart_endpoint_exposes_contract(monkeypatch):
    monkeypatch.setattr(app_module.market_chart, "get_chart", lambda asset, code, period, adjust, *, force=False: {
        "asset": asset, "code": code, "name": "测试指数", "period": period, "adjust": adjust,
        "source": "fixture", "fetchedAt": "2026-08-28T07:00:00Z", "stale": True,
        "quote": {}, "points": [],
    })
    response = client.get("/api/market/chart?asset=index&code=000001&period=daily&adjust=qfq")
    assert response.status_code == 200
    assert response.json()["asset"] == "index"


def test_market_chart_endpoint_forwards_refresh_query_to_service(monkeypatch):
    seen = {}

    def fake_get_chart(asset, code, period, adjust, *, force=False):
        seen["force"] = force
        return {"asset": asset, "code": code, "name": "测试指数", "period": period, "adjust": adjust,
                "source": "fixture", "fetchedAt": "2026-08-28T07:00:00Z", "stale": False,
                "quote": {}, "points": []}

    monkeypatch.setattr(app_module.market_chart, "get_chart", fake_get_chart)
    response = client.get("/api/market/chart?asset=index&code=000001&period=daily&refresh=true")

    assert response.status_code == 200
    assert seen["force"] is True


def test_market_chart_endpoint_forwards_full_history_scope(monkeypatch):
    seen = {}

    def fake_get_chart(asset, code, period, adjust, scope="recent", *, force=False):
        seen["scope"] = scope
        return {
            "asset": asset, "code": code, "name": "测试指数", "period": period, "adjust": adjust,
            "source": "fixture", "fetchedAt": "2026-08-28T07:00:00Z", "stale": False,
            "quote": {}, "points": [],
            "history": {"complete": scope == "full", "earliestTime": None, "latestTime": None},
        }

    monkeypatch.setattr(app_module.market_chart, "get_chart", fake_get_chart)
    response = client.get("/api/market/chart?asset=index&code=000001&period=daily&scope=full")

    assert response.status_code == 200
    assert seen["scope"] == "full"


def test_market_chart_endpoint_rejects_non_supported_index(monkeypatch):
    monkeypatch.setattr(app_module.market_chart, "get_chart", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unsupported")))
    response = client.get("/api/market/chart?asset=index&code=399300&period=daily")
    assert response.status_code == 400


def test_index_intraday_uses_sina_adapter(monkeypatch):
    import akshare as ak

    seen = {}

    def fake_index_minute(**kwargs):
        seen.update(kwargs)
        return [{"day": "2026-08-31 09:30:00", "close": 3952.0}]

    monkeypatch.setattr(ak, "stock_zh_a_minute", fake_index_minute)
    market_chart._akshare_rows("index", "000001", "intraday", "qfq")
    assert seen["symbol"] == "sh000001"
    assert seen["period"] == "1"
    assert seen["adjust"] == ""


def test_index_daily_uses_sina_index_adapter(monkeypatch):
    import akshare as ak

    seen = {}

    def fake_index_history(**kwargs):
        seen.update(kwargs)
        return [{"日期": "2026-08-28", "收盘": 3952.0}]

    monkeypatch.setattr(ak, "stock_zh_index_daily", fake_index_history)
    market_chart._akshare_rows("index", "000001", "daily", "qfq")
    assert seen["symbol"] == "sh000001"


def test_upstream_failure_without_cache_never_returns_fake_market_data(monkeypatch):
    market_chart.clear_cache()
    monkeypatch.delenv("VR_ENABLE_MARKET_CHART_FIXTURE", raising=False)
    monkeypatch.setattr(
        market_chart,
        "_fetch_from_akshare",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with pytest.raises(market_chart.ChartUnavailable, match="offline"):
        market_chart.get_chart("stock", "600519", "daily", "qfq")


def test_legacy_fixture_switch_cannot_put_fake_data_on_runtime_api(monkeypatch):
    market_chart.clear_cache()
    monkeypatch.setenv("VR_ENABLE_MARKET_CHART_FIXTURE", "1")
    monkeypatch.setattr(
        market_chart,
        "_fetch_from_akshare",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with pytest.raises(market_chart.ChartUnavailable, match="offline"):
        market_chart.get_chart("stock", "600519", "daily", "qfq")


def test_index_daily_falls_back_to_eastmoney_when_sina_fails(monkeypatch):
    import akshare as ak

    expected = [{"date": "2026-08-28", "close": 3952.179}]
    monkeypatch.setattr(ak, "stock_zh_index_daily", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sina offline")))
    monkeypatch.setattr(ak, "index_zh_a_hist", lambda **kwargs: expected if kwargs["symbol"] == "000001" else [])
    assert market_chart._akshare_rows("index", "000001", "daily", "") == expected


def test_index_daily_prefers_working_sina_source_without_waiting_for_eastmoney(monkeypatch):
    import akshare as ak

    expected = [{"date": "2026-08-28", "close": 3952.179}]
    monkeypatch.setattr(ak, "stock_zh_index_daily", lambda **kwargs: expected)
    monkeypatch.setattr(ak, "index_zh_a_hist", lambda **kwargs: pytest.fail("不应先请求当前不可用的东方财富源"))
    assert market_chart._akshare_rows("index", "000001", "daily", "") == expected


def test_daily_market_request_uses_count_based_window(monkeypatch):
    import akshare as ak

    seen = {}
    monkeypatch.setattr(ak, "stock_zh_a_daily", lambda **kwargs: seen.update(kwargs) or [{"date": "2026-08-28", "close": 1.0}])
    monkeypatch.setattr(ak, "stock_zh_a_hist", lambda **kwargs: pytest.fail("不应先请求东方财富源"))

    market_chart._akshare_rows("stock", "600519", "daily", "qfq", count=30)

    start = datetime.strptime(seen["start_date"], "%Y%m%d")
    assert (datetime.now() - start).days < 120


def test_full_stock_history_starts_before_a_share_market_and_is_not_trimmed(monkeypatch):
    import akshare as ak

    seen = {}
    rows = [
        {"date": f"{year}-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5}
        for year in range(1991, 2027)
    ]
    monkeypatch.setattr(ak, "stock_zh_a_daily", lambda **kwargs: seen.update(kwargs) or rows)
    monkeypatch.setattr(ak, "stock_zh_a_hist", lambda **kwargs: pytest.fail("首选源有数据时不应调用备用源"))

    source, points, _quote_points = market_chart._fetch_from_akshare(
        "stock", "600519", "daily", "qfq", scope="full"
    )

    assert source == "AKShare"
    assert seen["start_date"] == "19900101"
    assert len(points) == len(rows)
    assert points[0]["time"].startswith("1991-01-02")


def test_full_history_marks_range_complete_and_rejects_minute_periods(monkeypatch):
    market_chart.clear_cache()
    points = market_chart.fixture_points("stock", "600519", "daily")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: ("fixture", points, points))

    result = market_chart.get_chart("stock", "600519", "daily", "qfq", scope="full")

    assert result["history"] == {
        "complete": True,
        "earliestTime": points[0]["time"],
        "latestTime": points[-1]["time"],
    }
    with pytest.raises(ValueError, match="完整历史仅支持"):
        market_chart.get_chart("stock", "600519", "intraday", "", scope="full")


def test_stock_minute_falls_back_to_eastmoney_when_sina_fails(monkeypatch):
    import akshare as ak

    expected = [{"day": "2026-08-31 14:40:00", "close": 153.45}]
    monkeypatch.setattr(ak, "stock_zh_a_minute", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sina offline")))
    monkeypatch.setattr(
        ak,
        "stock_zh_a_hist_min_em",
        lambda **kwargs: expected if kwargs["symbol"] == "600183" and kwargs["period"] == "1" else [],
    )
    assert market_chart._akshare_rows("stock", "600183", "five_day", "qfq") == expected


def test_stock_minute_uses_unadjusted_prices_so_current_session_is_not_nan(monkeypatch):
    import akshare as ak

    seen = {}
    monkeypatch.setattr(
        ak,
        "stock_zh_a_minute",
        lambda **kwargs: seen.update(kwargs) or [{"day": "2026-08-31 14:48:00", "close": 153.15}],
    )
    market_chart._akshare_rows("stock", "600183", "five_day", "qfq")
    assert seen["adjust"] == ""


def test_rows_to_points_drops_non_finite_prices():
    rows = [
        {"day": "2026-08-31 14:40:00", "open": 153.0, "high": 154.0, "low": 152.0, "close": 153.5},
        {"day": "2026-08-31 14:41:00", "open": float("nan"), "high": float("nan"), "low": float("nan"), "close": float("nan")},
    ]
    points = market_chart._rows_to_points(rows)
    assert [point["time"] for point in points] == ["2026-08-31T14:40"]


def test_intraday_average_is_cumulative_vwap_and_resets_each_trading_day():
    points = [
        {"time": "2026-08-28T09:31", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "average": 10.05, "volume": 100.0, "amount": 1_000.0},
        {"time": "2026-08-28T09:32", "open": 10.1, "high": 12.2, "low": 10.0, "close": 12.0, "average": 11.075, "volume": 300.0, "amount": 3_600.0},
        {"time": "2026-08-31T09:31", "open": 20.0, "high": 20.2, "low": 19.9, "close": 20.1, "average": 20.05, "volume": 200.0, "amount": 4_000.0},
        {"time": "2026-08-31T09:32", "open": 20.1, "high": 22.2, "low": 20.0, "close": 22.0, "average": 21.075, "volume": 200.0, "amount": 4_400.0},
    ]

    result = market_chart._apply_intraday_vwap(points)

    assert [point["average"] for point in result] == [10.0, 11.5, 20.0, 21.0]


@pytest.mark.parametrize("period", ["intraday", "five_day"])
def test_index_chart_points_do_not_have_an_average_line(period):
    points = [{
        "time": "2026-09-01T09:31", "open": 4000.0, "high": 4010.0,
        "low": 3990.0, "close": 4005.0, "average": 4002.5,
        "volume": 100.0, "amount": 400500.0,
    }]

    result = market_chart.prepare_points("index", period, points)

    assert result[0]["close"] == 4005.0
    assert result[0]["average"] is None


def test_intraday_vwap_keeps_last_value_for_zero_volume_bar():
    points = [
        {"time": "2026-08-31T09:31", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "average": 10.0, "volume": 100.0, "amount": 1_000.0},
        {"time": "2026-08-31T09:32", "open": 10.1, "high": 10.1, "low": 10.1, "close": 10.1, "average": 10.1, "volume": 0.0, "amount": 0.0},
    ]

    result = market_chart._apply_intraday_vwap(points)

    assert result[-1]["average"] == 10.0


def test_cache_ttl_is_longer_outside_a_share_trading_hours():
    during_market = datetime(2026, 8, 31, 10, 0)
    after_market = datetime(2026, 8, 31, 18, 0)
    assert market_chart.cache_ttl("intraday", during_market) == 15
    assert market_chart.cache_ttl("daily", during_market) == 60
    assert market_chart.cache_ttl("intraday", after_market) > 15
    assert market_chart.cache_ttl("daily", after_market) > 60


def test_intraday_quote_uses_session_totals_and_previous_session_close():
    points = [
        {"time": "2026-08-28T14:59", "open": 9.8, "high": 10.2, "low": 9.7, "close": 10.0, "average": 9.9, "volume": 100, "amount": 990},
        {"time": "2026-08-31T09:30", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "average": 10.15, "volume": 80, "amount": 812},
        {"time": "2026-08-31T09:31", "open": 10.2, "high": 10.5, "low": 10.1, "close": 10.4, "average": 10.25, "volume": 120, "amount": 1230},
    ]
    quote = market_chart._quote(points)
    assert quote == {
        "price": 10.4, "change": 0.4, "changePct": 4.0,
        "open": 10.1, "high": 10.5, "low": 10.0, "prevClose": 10.0,
        "volume": 200, "amount": 2042,
    }


def test_weekly_chart_quote_comes_from_latest_daily_session(monkeypatch):
    market_chart.clear_cache()
    weekly = [{"time": "2026-08-31", "open": 9.0, "high": 11.0, "low": 8.0, "close": 10.4, "average": 9.6, "volume": 999, "amount": 9999}]
    daily = [
        {"time": "2026-08-28", "open": 9.8, "high": 10.2, "low": 9.7, "close": 10.0, "average": 9.9, "volume": 100, "amount": 990},
        {"time": "2026-08-31", "open": 10.1, "high": 10.5, "low": 10.0, "close": 10.4, "average": 10.2, "volume": 200, "amount": 2042},
    ]
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args: ("AKShare", weekly, daily))
    result = market_chart.get_chart("stock", "600519", "weekly", "qfq")
    assert result["points"] == weekly
    assert result["quote"]["prevClose"] == 10.0
    assert result["quote"]["open"] == 10.1


def test_expired_cache_is_not_returned_forever(monkeypatch):
    market_chart.clear_cache()
    key = ("stock", "600519", "daily", "qfq")
    payload = {"asset": "stock", "code": "600519", "name": "贵州茅台", "period": "daily", "adjust": "qfq", "source": "AKShare", "fetchedAt": "2026-08-01T00:00:00Z", "stale": False, "quote": {}, "points": []}
    market_chart._CACHE[key] = (time.time() - market_chart.STALE_MAX_AGE - 1, payload)
    monkeypatch.delenv("VR_ENABLE_MARKET_CHART_FIXTURE", raising=False)
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(market_chart.ChartUnavailable, match="offline"):
        market_chart.get_chart(*key)


def test_full_history_never_reuses_a_legacy_recent_cache(monkeypatch):
    market_chart.clear_cache()
    legacy_key = ("stock", "600519", "daily", "qfq")
    points = market_chart.fixture_points("stock", "600519", "daily")
    market_chart._CACHE[legacy_key] = (time.time(), {
        "asset": "stock", "code": "600519", "name": "贵州茅台", "period": "daily",
        "adjust": "qfq", "source": "AKShare", "fetchedAt": "2026-09-05T00:00:00Z",
        "stale": False, "quote": {}, "points": points,
    })
    monkeypatch.setattr(
        market_chart,
        "_fetch_from_akshare",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("full offline")),
    )

    with pytest.raises(market_chart.ChartUnavailable, match="full offline"):
        market_chart.get_chart("stock", "600519", "daily", "qfq", scope="full")


def test_cache_has_a_hard_entry_limit(monkeypatch):
    market_chart.clear_cache()
    points = market_chart.fixture_points("stock", "600000", "daily")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args: ("test", points, points))
    for number in range(market_chart.CACHE_MAX_ENTRIES + 5):
        market_chart.get_chart("stock", f"{600000 + number:06d}", "daily", "qfq")
    assert len(market_chart._CACHE) == market_chart.CACHE_MAX_ENTRIES


def test_cache_evicts_old_history_when_point_budget_is_exceeded(monkeypatch):
    market_chart.clear_cache()
    monkeypatch.setattr(market_chart, "CACHE_MAX_POINTS", 150)
    points = market_chart.fixture_points("stock", "600000", "daily")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: ("fixture", points, points))

    market_chart.get_chart("stock", "600000", "daily", "qfq", scope="full")
    market_chart.get_chart("stock", "600001", "daily", "qfq", scope="full")

    assert sum(len(payload["points"]) for _, payload in market_chart._CACHE.values()) <= 150
    assert all(key[1] != "600000" for key in market_chart._CACHE)
