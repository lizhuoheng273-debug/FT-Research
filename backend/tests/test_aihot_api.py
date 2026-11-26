from aihot_api import AihotClient, normalize_item
from fastapi.testclient import TestClient
import app


def test_normalize_aihot_item_keeps_links_and_score():
    item = normalize_item({
        "id": "cmt_1", "title": "标题", "summary": "摘要", "score": 88,
        "reason": "多源报道", "publishedAt": "2026-08-27T10:00:00Z",
        "source": {"name": "Example"},
        "links": {"aihot": "https://aihot/item", "original": "https://source/item", "story": "https://aihot/story/uuid"},
    })
    assert item == {
        "id": "cmt_1", "title": "标题", "summary": "摘要", "score": 88,
        "reason": "多源报道", "category": "", "publishedAt": "2026-08-27T10:00:00Z", "source": "Example",
        "links": {"aihot": "https://aihot/item", "original": "https://source/item", "story": "https://aihot/story/uuid"},
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


def test_normalize_hot_topic_source_is_string(monkeypatch):
    client = AihotClient(base_url="https://example.test")
    monkeypatch.setattr(client, "_get", lambda *args, **kwargs: {"items": [{"id": "x", "source": {"name": "来源"}}]})
    assert client.hot_topics()["items"][0]["source"] == "来源"


def test_parse_aihot_item_html_and_api_route(monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    from aihot_api import parse_aihot_item_html
    from route_policy import policy_for

    sample_html = """
    <html><body><main>
      <article>
        <div>TechCrunch：AI · 2026-11-26 01:35 · 精选 AI 评分 85</div>
        <h1>42 州总检察长介入 Character.AI 破产程序</h1>
        <p>Character.AI plan challenged by state AGs</p>
        <section>AI 导读<p>42 州总检察长介入破产程序，反对拍卖用户私密聊天记录。</p></section>
        <section>推荐理由<p>披露了 2100 万账户数据保护争议。</p></section>
        <section>
          <div><span>正文 · AI 翻译</span><nav><a href="/items/j0hoj1rlmltoft6okserijp25">中文</a><a href="/items/j0hoj1rlmltoft6okserijp25/original">原文</a></nav></div>
          <div>
            <h2>核心背景</h2>
            <p>当一家 <a href="https://example.com/inline">AI公司破产</a> 时，用户对话数据的归属成为焦点。</p>
            <h2>后续影响</h2>
            <p>多州检察长联名要求法院暂停拍卖流程，直到完成隐私审查。</p>
          </div>
        </section>
        <p>来源：<a href="https://techcrunch.com/2026/11/25/character-ai/">TechCrunch：AI</a></p>
        <div><a href="/daily/2026-11-26">收录于 11月26日 AI 日报</a><a href="/topics/safety">安全对齐</a></div>
        <section>所属事件<a href="/story/5525eb2a-16ec-491d-bf45-89cf70e7966a">查看完整事件</a><a href="/story/5525eb2a-16ec-491d-bf45-89cf70e7966a">42州总检察长介入阻止拍卖</a></section>
      </article>
    </main></body></html>
    """.encode("utf-8")

    parsed = parse_aihot_item_html(sample_html, "j0hoj1rlmltoft6okserijp25", "https://aihot.news/items/j0hoj1rlmltoft6okserijp25")
    assert parsed["title"] == "42 州总检察长介入 Character.AI 破产程序"
    assert parsed["originalTitle"] == "Character.AI plan challenged by state AGs"
    assert parsed["sourceName"] == "TechCrunch：AI"
    assert parsed["originalUrl"] == "https://techcrunch.com/2026/11/25/character-ai/"
    assert parsed["score"] == 85
    assert parsed["bodyMode"] == "full"
    assert parsed["hasOriginalLang"] is True
    assert [o["text"] for o in parsed["outline"]] == ["核心背景", "后续影响"]
    assert parsed["story"]["storyId"] == "5525eb2a-16ec-491d-bf45-89cf70e7966a"
    assert parsed["dailyEdition"]["date"] == "2026-11-26"
    assert parsed["tags"] == ["安全对齐"]

    assert policy_for("GET", "/api/ai/reports/items/j0hoj1rlmltoft6okserijp25") == "authenticated"
    monkeypatch.setattr(app_module.aihot_edition_client, "item_detail", lambda item_id, lang="zh": {**parsed, "id": item_id, "lang": lang})
    with TestClient(app_module.app) as test_client:
        res = test_client.get("/api/ai/reports/items/j0hoj1rlmltoft6okserijp25?lang=original")
        assert res.status_code == 200
        assert res.json()["lang"] == "original"
        assert res.json()["sourceName"] == "TechCrunch：AI"

