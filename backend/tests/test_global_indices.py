import market


def _fresh_row(key: str, name: str, region: str) -> dict:
    return {"key": key, "name": name, "region": region, "price": 100.0, "change_pct": 1.2}


def test_global_snapshot_keeps_independent_region_slots_when_one_feed_is_missing(monkeypatch):
    market._GLOBAL_INDEX_CACHE.clear()
    monkeypatch.setattr(
        market.gstock,
        "global_indices",
        lambda: [_fresh_row("dji", "道琼斯", "美股"), _fresh_row("hsi", "恒生指数", "港股")],
    )

    rows = market.get_global_indices_snapshot(force=True)

    assert [row["key"] for row in rows] == ["dji", "spx", "ndx", "hsi", "hstech"]
    assert rows[0]["status"] == "fresh"
    assert rows[0]["stale"] is False
    assert rows[1]["status"] == "unavailable"
    assert rows[1]["price"] is None
    assert rows[3]["status"] == "fresh"


def test_global_snapshot_uses_last_real_value_as_stale_cache(monkeypatch):
    market._GLOBAL_INDEX_CACHE.clear()
    monkeypatch.setattr(market.gstock, "global_indices", lambda: [_fresh_row("dji", "道琼斯", "美股")])
    first = market.get_global_indices_snapshot(force=True)

    monkeypatch.setattr(market.gstock, "global_indices", lambda: [])
    stale = market.get_global_indices_snapshot(force=True)

    assert first[0]["status"] == "fresh"
    assert stale[0]["status"] == "stale"
    assert stale[0]["stale"] is True
    assert stale[0]["price"] == 100.0


def test_global_indices_endpoint_uses_snapshot_contract(monkeypatch):
    import app as app_module
    from fastapi.testclient import TestClient

    expected = [{"key": "dji", "name": "道琼斯", "region": "美股", "price": None, "change_pct": None,
                 "status": "unavailable", "stale": False}]
    monkeypatch.setattr(app_module.market, "get_global_indices_snapshot", lambda force=False: expected)

    response = TestClient(app_module.app).get("/api/global/indices")

    assert response.status_code == 200
    assert response.json() == {"data": expected}
