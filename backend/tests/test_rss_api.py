from fastapi.testclient import TestClient

import app


def test_rss_sources_has_unified_fields(monkeypatch):
    source = {
        "id": "ithome",
        "name": "IT之家",
        "category": "tech",
        "region": "cn",
        "priority": 1,
        "homepage": "https://www.ithome.com",
        "lastSuccessAt": None,
        "stale": False,
        "error": "尚未成功抓取",
        "items": [],
    }
    monkeypatch.setattr(app.rss_catalog, "sources", lambda urls=None: [source])
    response = TestClient(app.app).get("/api/ai/rss/sources")
    assert response.status_code == 200
    assert response.json()["sources"][0] == source


def test_rss_resolve_returns_preview_without_persisting_subscription(monkeypatch):
    resolved = {
        "id": "custom-abc",
        "name": "自定义媒体",
        "category": "tech",
        "region": "custom",
        "priority": 100,
        "homepage": "https://example.com",
        "lastSuccessAt": "2026-09-02T02:00:00+00:00",
        "stale": False,
        "error": None,
        "items": [{"id": "1", "title": "预览", "summary": "摘要", "publishedAt": None, "originalUrl": "https://example.com/1"}],
    }
    monkeypatch.setattr(app.rss_catalog, "resolve", lambda url: resolved)
    response = TestClient(app.app).post("/api/ai/rss/resolve", json={"url": "https://example.com/feed"})
    assert response.status_code == 200
    assert response.json() == {"source": resolved}


def test_rss_resolve_rejects_bad_url(monkeypatch):
    def reject(_url):
        from rss import RssSecurityError
        raise RssSecurityError("仅支持 HTTP/HTTPS")

    monkeypatch.setattr(app.rss_catalog, "resolve", reject)
    response = TestClient(app.app).post("/api/ai/rss/resolve", json={"url": "ftp://example.com/feed"})
    assert response.status_code == 400


def test_radar_keeps_legacy_industries_and_media_snapshots(monkeypatch):
    payload = {"generated_at": "now", "industries": [], "stats": {}, "sources": [], "sourceHealth": []}
    monkeypatch.setattr(app.newsradar, "get_radar", lambda force=False: payload)
    response = TestClient(app.app).get("/api/radar")
    assert response.status_code == 200
    assert "industries" in response.json()["data"]
    assert "sources" in response.json()["data"]


def test_fetch_radar_preserves_media_items_before_cross_source_dedup(monkeypatch):
    import newsradar

    config = {
        "fetch": {"per_source": 3, "recent_days": 7},
        "industries": [{"key": "tech", "name": "科技", "accent": "#fff"}],
        "sources": [{"id": "demo", "name": "演示媒体", "hint": "tech", "type": "rss", "url": "https://example.com/feed"}],
        "redline_keywords": [],
    }
    monkeypatch.setattr(newsradar, "SOURCES_FILE", str(__file__))
    monkeypatch.setattr(newsradar.json, "load", lambda _file: config)
    monkeypatch.setattr(newsradar, "_fetch_source", lambda source, per, cutoff, redline: [{"title": "转载标题", "url": "https://example.com/a", "time": "09-02 10:00", "ts": 10, "summary": "媒体摘要", "source": source["name"]}])
    recorded = []
    monkeypatch.setattr(newsradar.rss.rss_catalog, "record_radar_result", lambda source, items: recorded.append((source["name"], items)))
    monkeypatch.setattr(newsradar.rss.rss_catalog, "sources", lambda: [{"id": "demo", "name": "演示媒体", "items": [{"title": "转载标题"}], "stale": False, "error": None, "lastSuccessAt": "now"}])
    result = newsradar.fetch_radar()
    assert result["industries"][0]["items"][0]["title"] == "转载标题"
    assert result["sources"][0]["items"][0]["title"] == "转载标题"
    assert recorded[0][0] == "演示媒体"
