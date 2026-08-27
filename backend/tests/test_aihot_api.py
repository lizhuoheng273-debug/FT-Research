from aihot_api import AihotClient, normalize_item
from fastapi.testclient import TestClient
import app


def test_normalize_aihot_item_keeps_links_and_score():
    item = normalize_item({
        "id": "cmt_1", "title": "标题", "summary": "摘要", "score": 88,
        "reason": "多源报道", "publishedAt": "2026-08-27T10:00:00Z",
        "source": {"name": "Example"},
        "links": {"aihot": "https://aihot/item", "original": "https://source/item"},
    })
    assert item == {
        "id": "cmt_1", "title": "标题", "summary": "摘要", "score": 88,
        "reason": "多源报道", "publishedAt": "2026-08-27T10:00:00Z", "source": "Example",
        "links": {"aihot": "https://aihot/item", "original": "https://source/item"},
    }


def test_etag_304_returns_cached_payload(monkeypatch):
    client = AihotClient(base_url="https://example.test")
    calls = []

    class Response:
        def __init__(self, status, payload=None, headers=None):
            self.status_code, self._payload, self.headers = status, payload, headers or {}
            self.text = ""
        def json(self): return self._payload
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    responses = iter([
        Response(200, {"items": [{"id": "1"}]}, {"ETag": '"v1"'}),
        Response(304),
    ])
    def fake_get(url, **kwargs):
        calls.append(kwargs.get("headers", {}))
        return next(responses)
    monkeypatch.setattr(client._session, "get", fake_get)
    assert client.items(limit=1)["items"][0]["id"] == "1"
    assert client.items(limit=1)["items"][0]["id"] == "1"
    assert calls[1]["If-None-Match"] == '"v1"'


def test_aihot_items_endpoint_maps_items(monkeypatch):
    monkeypatch.setattr(app.aihot_client, "items", lambda **params: {"items": [{"id": "x", "title": "热点"}], "stale": False})
    response = TestClient(app.app).get("/api/ai/news")
    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "热点"
