"""A 股代码/名称搜索契约测试。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
import astock


client = TestClient(app_module.app)


def test_stock_search_matches_name_and_returns_code(monkeypatch):
    monkeypatch.setattr(
        astock,
        "search_a_stocks",
        lambda query, limit=20: [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "600519", "name": "贵州茅台"},
        ],
    )

    response = client.get("/api/stock/search?q=茅台")

    assert response.status_code == 200
    assert response.json() == {"data": [{"code": "600519", "name": "贵州茅台"}]}


def test_stock_search_rejects_empty_query():
    assert client.get("/api/stock/search?q=").status_code == 400


def test_stock_search_uses_persisted_universe_when_upstream_is_unavailable(monkeypatch, tmp_path):
    cache = tmp_path / "a-stock-universe.json"
    cache.write_text(json.dumps({
        "savedAt": 100.0,
        "items": [{"code": "600519", "name": "贵州茅台"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", cache, raising=False)
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock.time, "time", lambda: 101.0)
    monkeypatch.setattr(astock, "_akshare", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    assert astock.search_a_stocks("茅台") == [{"code": "600519", "name": "贵州茅台"}]


def test_stale_persisted_universe_is_returned_while_refresh_runs_in_background(monkeypatch, tmp_path):
    cache = tmp_path / "a-stock-universe.json"
    cache.write_text(json.dumps({
        "savedAt": 100.0,
        "items": [{"code": "300750", "name": "宁德时代"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", cache, raising=False)
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock.time, "time", lambda: 100.0 + astock._A_STOCK_UNIVERSE_TTL + 1)
    monkeypatch.setattr(astock, "_akshare", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    assert astock.search_a_stocks("宁德") == [{"code": "300750", "name": "宁德时代"}]


def test_concurrent_cold_searches_share_one_universe_fetch(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    started = threading.Event()
    release = threading.Event()
    calls = []
    def fetch():
        calls.append("fetch")
        started.set()
        release.wait(1)
        return [{"code": "600519", "name": "贵州茅台"}]

    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", tmp_path / "universe.json")
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock, "_fetch_a_stock_universe", fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(astock.search_a_stocks, "茅台")
        assert started.wait(0.2)
        second = pool.submit(astock.search_a_stocks, "茅台")
        with pytest.raises(astock.StockUniverseWarming):
            first.result(timeout=1)
        with pytest.raises(astock.StockUniverseWarming):
            second.result(timeout=1)
        release.set()
    for _ in range(100):
        if astock._a_stock_universe:
            break
        threading.Event().wait(0.01)

    assert calls == ["fetch"]
    assert astock.search_a_stocks("茅台") == [{"code": "600519", "name": "贵州茅台"}]


def test_failed_stale_refresh_is_not_retried_for_every_keystroke(monkeypatch, tmp_path):
    import threading

    cache = tmp_path / "universe.json"
    cache.write_text(json.dumps({
        "savedAt": 100.0,
        "items": [{"code": "600519", "name": "贵州茅台"}],
    }, ensure_ascii=False), encoding="utf-8")
    attempted = threading.Event()
    calls = []
    def fail():
        calls.append("fetch")
        attempted.set()
        raise RuntimeError("offline")

    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", cache)
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock, "_a_stock_universe_attempt_at", 0.0, raising=False)
    monkeypatch.setattr(astock.time, "time", lambda: 100.0 + astock._A_STOCK_UNIVERSE_TTL + 1)
    monkeypatch.setattr(astock, "_fetch_a_stock_universe", fail)

    assert astock.search_a_stocks("茅")
    assert attempted.wait(0.2)
    assert astock.search_a_stocks("茅台")

    assert calls == ["fetch"]


def test_empty_cold_cache_starts_background_warmup_instead_of_blocking_search(monkeypatch, tmp_path):
    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock, "_a_stock_universe_attempt_at", 0.0)
    monkeypatch.setattr(astock, "_a_stock_universe_refresh_thread", None)
    monkeypatch.setattr(astock, "_fetch_a_stock_universe", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    with pytest.raises(astock.StockUniverseWarming):
        astock.search_a_stocks("茅台")


def test_failed_cold_warmup_obeys_retry_backoff(monkeypatch, tmp_path):
    import threading

    attempted = threading.Event()
    calls = []
    def fail():
        calls.append("fetch")
        attempted.set()
        raise RuntimeError("offline")
    monkeypatch.setattr(astock, "_A_STOCK_UNIVERSE_CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(astock, "_a_stock_universe", [])
    monkeypatch.setattr(astock, "_a_stock_universe_at", 0.0)
    monkeypatch.setattr(astock, "_a_stock_universe_attempt_at", 0.0)
    monkeypatch.setattr(astock, "_a_stock_universe_refresh_thread", None)
    monkeypatch.setattr(astock.time, "time", lambda: 1000.0)
    monkeypatch.setattr(astock, "_fetch_a_stock_universe", fail)

    with pytest.raises(astock.StockUniverseWarming):
        astock.search_a_stocks("茅")
    assert attempted.wait(0.2)
    with pytest.raises(astock.StockUniverseWarming):
        astock.search_a_stocks("茅台")

    assert calls == ["fetch"]


def test_stock_search_reports_warmup_as_retryable(monkeypatch):
    monkeypatch.setattr(astock, "search_a_stocks", lambda *_args, **_kwargs: (_ for _ in ()).throw(astock.StockUniverseWarming()))

    response = client.get("/api/stock/search?q=茅台")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
