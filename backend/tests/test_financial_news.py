from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app
from financial_news import FinancialNewsService, hot_score, urgency_score


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def _item(**overrides):
    item = {
        "id": "x",
        "title": "监管部门发布资本市场新规",
        "summary": "政策正式发布",
        "publishedAt": "2026-08-31T07:55:00+00:00",
        "category": "宏观政策",
        "source": "财联社",
        "sourceTier": 35,
        "originalUrl": "https://example.test/x",
        "sourceLevel": "A",
    }
    item.update(overrides)
    return item


def test_urgency_score_is_quantified_and_explainable():
    score, reasons = urgency_score(_item(), now=NOW, related_source_count=3)
    assert score == 100
    assert any("3 个独立来源" in reason for reason in reasons)
    assert any("监管" in reason for reason in reasons)


def test_hot_score_uses_sources_authority_recency_breadth_and_continuity():
    score, reasons = hot_score(
        _item(), now=NOW, related_source_count=5, category_count=2, update_count=3
    )
    assert score == 100
    assert "5 个独立来源" in reasons[0]


def test_future_dated_rss_is_not_treated_as_just_published():
    future = _item(publishedAt="2026-11-13T00:00:00+00:00")
    urgency, reasons = urgency_score(future, now=NOW, related_source_count=1)
    assert urgency == 55
    assert not any("10 分钟内" in reason for reason in reasons)


def test_company_announcement_is_company_news_not_macro_policy(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    assert service.classify("中来股份：控股子公司中标项目16亿元", "公司公告") == "公司"


def test_future_dated_rss_items_are_excluded_from_news_feed(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    radar = {
        "industries": [{
            "name": "半导体",
            "items": [
                {"zh": "未来活动预告", "ts": datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()},
                {"zh": "今日产业新闻", "ts": datetime(2026, 8, 31, 7, 50, tzinfo=timezone.utc).timestamp()},
            ],
        }],
    }

    items = service.normalize_radar(radar)

    assert [item["title"] for item in items] == ["今日产业新闻"]


def test_service_normalizes_ths_and_cls_and_clusters_same_event(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    ths = service.normalize_quick_rows(
        [{"标题": "七部门发布消费支持政策", "摘要": "政策落地", "发布时间": "2026-08-31 15:56:00", "链接": "https://ths/x"}],
        source="同花顺快讯",
    )
    cls = service.normalize_quick_rows(
        [{"标题": "七部门发布消费支持政策！", "内容": "政策正式落地", "发布日期": "2026-08-31", "发布时间": "15:55:00", "等级": "A"}],
        source="财联社电报",
    )
    events = service.cluster_items(ths + cls)
    assert len(events) == 1
    assert events[0]["relatedSourceCount"] == 2
    assert events[0]["source"] in {"财联社电报", "同花顺快讯"}


def test_cached_overview_is_returned_stale_when_all_sources_fail(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.save_payload({"generatedAt": NOW.isoformat(), "urgent": [_item()], "hot": [], "feed": []})
    service.quick_fetchers = {"broken": lambda: (_ for _ in ()).throw(RuntimeError("offline"))}
    result = service.refresh_quick()
    assert result["stale"] is True
    assert result["urgent"][0]["title"] == _item()["title"]


def test_glm_refinement_is_batched_and_cached_by_event_content(tmp_path, monkeypatch):
    import chat
    import glm_config

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test", "baseURL": "https://example.test/v4", "model": "glm"})
    calls = []

    def fake_call(_cfg, messages, use_tools):
        calls.append(messages[-1]["content"])
        event_id = "event-1"
        return {"choices": [{"message": {"content": json.dumps([{"id": event_id, "digest": "精炼导读", "impactTags": ["政策"]}], ensure_ascii=False)}}]}

    import json
    monkeypatch.setattr(chat, "_call_llm", fake_call)
    event = {**_item(id="event-1"), "relatedSourceCount": 2, "relatedSources": ["A", "B"], "hotScore": 80}
    service._apply_ai_refinements([event])
    service._apply_ai_refinements([event])
    assert len(calls) == 1
    assert event["aiDigest"] == "精炼导读"

    changed = {**event, "summary": "事件新增重要进展"}
    service._apply_ai_refinements([changed])
    assert len(calls) == 2


def test_financial_news_endpoints_expose_overview_feed_detail_and_status(monkeypatch):
    payload = {
        "generatedAt": NOW.isoformat(),
        "stale": False,
        "urgent": [_item(id="event-1")],
        "hot": [_item(id="event-1")],
        "feed": [_item(id="event-1")],
        "sourceStatus": [],
    }
    monkeypatch.setattr(app.financial_news_service, "overview", lambda: payload)
    monkeypatch.setattr(app.financial_news_service, "feed", lambda **_: payload["feed"])
    monkeypatch.setattr(app.financial_news_service, "event", lambda event_id: {**_item(id=event_id), "reports": []})
    monkeypatch.setattr(app.financial_news_service, "status", lambda: {"quickIntervalSeconds": 180, "rssIntervalSeconds": 1800})
    client = TestClient(app.app)
    assert client.get("/api/finance/news/overview").json()["data"]["urgent"][0]["id"] == "event-1"
    assert client.get("/api/finance/news/feed?category=all&limit=20").status_code == 200
    assert client.get("/api/finance/news/events/event-1").json()["data"]["id"] == "event-1"
    assert client.get("/api/finance/news/status").json()["data"]["quickIntervalSeconds"] == 180
