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
    with pytest.raises(ValueError):
        market_chart.normalize_asset_code("stock", "sh000001")


def test_fixture_chart_has_uniform_response_and_ohlcv_points(monkeypatch):
    monkeypatch.setenv("VR_ENABLE_MARKET_CHART_FIXTURE", "1")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    result = market_chart.get_chart("stock", "600519", "daily", "qfq")
    assert set(result) == {"asset", "code", "name", "period", "adjust", "source", "fetchedAt", "stale", "quote", "points"}
    assert result["asset"] == "stock"
    assert result["code"] == "600519"
    assert result["points"]
    assert {"time", "open", "high", "low", "close", "average", "volume", "amount"} <= set(result["points"][0])
    assert result["stale"] is True


def test_five_day_fixture_contains_five_trading_dates(monkeypatch):
    monkeypatch.setenv("VR_ENABLE_MARKET_CHART_FIXTURE", "1")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    result = market_chart.get_chart("stock", "600519", "five_day", "qfq")
    dates = {point["time"][:10] for point in result["points"]}
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


def test_market_chart_endpoint_exposes_contract(monkeypatch):
    monkeypatch.setattr(app_module.market_chart, "get_chart", lambda asset, code, period, adjust: {
        "asset": asset, "code": code, "name": "测试指数", "period": period, "adjust": adjust,
        "source": "fixture", "fetchedAt": "2026-08-28T07:00:00Z", "stale": True,
        "quote": {}, "points": [],
    })
    response = client.get("/api/market/chart?asset=index&code=000001&period=daily&adjust=qfq")
    assert response.status_code == 200
    assert response.json()["asset"] == "index"


def test_market_chart_endpoint_rejects_non_supported_index(monkeypatch):
    monkeypatch.setattr(app_module.market_chart, "get_chart", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unsupported")))
    response = client.get("/api/market/chart?asset=index&code=399300&period=daily")
    assert response.status_code == 400


def test_index_intraday_uses_installed_akshare_adapter(monkeypatch):
    import akshare as ak

    seen = {}

    def fake_index_minute(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(ak, "index_zh_a_hist_min_em", fake_index_minute)
    market_chart._akshare_rows("index", "000001", "intraday", "qfq")
    assert seen["symbol"] == "000001"
    assert seen["period"] == "1"
    start = datetime.strptime(seen["start_date"], "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(seen["end_date"], "%Y-%m-%d %H:%M:%S")
    assert (end - start).days >= 30


def test_index_daily_uses_a_share_index_adapter(monkeypatch):
    import akshare as ak

    seen = {}

    def fake_index_history(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(ak, "index_zh_a_hist", fake_index_history)
    market_chart._akshare_rows("index", "000001", "daily", "qfq")
    assert seen["symbol"] == "000001"
    assert seen["period"] == "daily"


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


def test_fixture_requires_explicit_development_switch(monkeypatch):
    market_chart.clear_cache()
    monkeypatch.setenv("VR_ENABLE_MARKET_CHART_FIXTURE", "1")
    monkeypatch.setattr(
        market_chart,
        "_fetch_from_akshare",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    result = market_chart.get_chart("stock", "600519", "daily", "qfq")
    assert result["source"] == "fixture"
    assert result["stale"] is True


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


def test_cache_has_a_hard_entry_limit(monkeypatch):
    market_chart.clear_cache()
    points = market_chart.fixture_points("stock", "600000", "daily")
    monkeypatch.setattr(market_chart, "_fetch_from_akshare", lambda *args: ("test", points, points))
    for number in range(market_chart.CACHE_MAX_ENTRIES + 5):
        market_chart.get_chart("stock", f"{600000 + number:06d}", "daily", "qfq")
    assert len(market_chart._CACHE) == market_chart.CACHE_MAX_ENTRIES
