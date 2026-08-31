from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app
from financial_news import FinancialNewsScheduler, FinancialNewsService, hot_score, urgency_score


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
    assert "10 分钟内更新" in reasons


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


def test_undated_items_keep_unknown_time_and_receive_no_recency_boost(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    item = service.normalize_quick_rows([{"标题": "没有发布时间的旧消息"}], source="新浪财经快讯")[0]
    events = service.cluster_items([item])

    assert item["publishedAt"] is None
    assert events[0]["urgencyScore"] == 22
    assert "发布时间未知" in events[0]["urgencyReasons"]
    overview = service._compose([item], [], [])
    assert overview["urgent"] == []
    assert overview["hot"] == []

    corroborated = {**item, "title": "监管部门发布资本市场新规", "summary": "政策正式发布", "sourceTier": 35}
    corroborated_event = service.cluster_items([corroborated, {**corroborated, "source": "另一权威来源"}])[0]
    assert corroborated_event["urgencyScore"] >= 60
    assert service._compose([corroborated, {**corroborated, "source": "另一权威来源"}], [], [])["urgent"] == []


def test_sina_content_only_schema_is_normalized(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    items = service.normalize_quick_rows(
        [{"时间": "2026-08-31 15:59:00", "内容": "新浪快讯正文可作为标题"}],
        source="新浪财经快讯",
    )

    assert len(items) == 1
    assert items[0]["title"] == "新浪快讯正文可作为标题"


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
    persisted = service.overview()
    assert persisted["stale"] is True
    assert persisted["staleComponents"]["quick"] is True
    assert persisted["sourceStatus"][0]["ok"] is False


def test_rss_cycle_does_not_clear_quick_source_outage(tmp_path, monkeypatch):
    import newsradar

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(newsradar, "get_radar", lambda force=False: {"industries": []})
    monkeypatch.setattr(newsradar, "fetch_radar", lambda: {"industries": []})
    service.quick_fetchers = {"同花顺快讯": lambda: [{"标题": "已缓存快讯", "发布时间": "2026-08-31 15:58:00"}]}
    service.refresh_quick()
    service.quick_fetchers = {"同花顺快讯": lambda: (_ for _ in ()).throw(RuntimeError("offline"))}
    service.refresh_quick()

    result = service.refresh_rss()

    assert result["stale"] is True
    assert result["staleComponents"]["quick"] is True
    assert any(row["source"] == "同花顺快讯" and row["ok"] is False for row in result["sourceStatus"])


def test_successful_empty_quick_cycle_does_not_relabel_old_items_as_fresh(tmp_path, monkeypatch):
    import newsradar

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(newsradar, "get_radar", lambda force=False: {"industries": []})
    service._write(service.quick_file, {
        "items": [_item(title="旧快讯")], "sourceStatus": [], "stale": False,
        "lastSuccessAt": "2026-08-30T08:00:00+00:00",
    })
    service.quick_fetchers = {"同花顺快讯": lambda: []}

    result = service.refresh_quick()

    assert result["stale"] is False
    assert result["feed"] == []
    assert result["freshness"]["quick"]["lastSuccessAt"] == NOW.isoformat()


def test_empty_rss_failure_persists_degraded_snapshot_and_last_success(tmp_path, monkeypatch):
    import newsradar

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.save_payload({
        "generatedAt": "2026-08-30T08:00:00+00:00", "stale": False,
        "staleComponents": {"quick": False, "rss": False},
        "freshness": {
            "quick": {"lastSuccessAt": "2026-08-30T08:00:00+00:00", "attemptedAt": "2026-08-30T08:00:00+00:00"},
            "rss": {"lastSuccessAt": "2026-08-30T08:00:00+00:00", "attemptedAt": "2026-08-30T08:00:00+00:00"},
        },
        "urgent": [_item()], "hot": [], "feed": [_item()], "sourceStatus": [],
    })
    monkeypatch.setattr(newsradar, "fetch_radar", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(newsradar, "get_radar", lambda force=False: {"industries": []})

    result = service.refresh_rss()

    assert result["stale"] is True
    assert service.overview()["stale"] is True
    assert result["freshness"]["rss"]["lastSuccessAt"] == "2026-08-30T08:00:00+00:00"
    assert result["freshness"]["rss"]["attemptedAt"] == NOW.isoformat()


def test_event_recency_and_order_use_latest_report_not_authoritative_lead(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    authoritative = _item(
        title="同一事件取得进展", source="财联社电报", sourceTier=35,
        publishedAt="2026-08-31T06:00:00+00:00",
    )
    latest = _item(
        title="同一事件取得进展！", source="东方财富快讯", sourceTier=24,
        publishedAt="2026-08-31T07:58:00+00:00",
    )

    event = service.cluster_items([authoritative, latest])[0]

    assert event["source"] == "财联社电报"
    assert event["publishedAt"] == latest["publishedAt"]
    assert "10 分钟内更新" in event["urgencyReasons"]
    assert event["urgencyReasons"] != event["hotReasons"]


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


def test_glm_refinement_rejects_ungrounded_numbers_and_prompt_instructions(tmp_path, monkeypatch):
    import chat
    import glm_config
    import json

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test", "baseURL": "https://example.test/v4", "model": "glm"})
    captured = []

    def fake_call(_cfg, messages, use_tools):
        captured.extend(messages)
        return {"choices": [{"message": {"content": json.dumps([{
            "id": "event-1", "digest": "公司确认盈利9999亿元", "impactTags": ["公司", {"bad": True}],
        }], ensure_ascii=False)}}]}

    monkeypatch.setattr(chat, "_call_llm", fake_call)
    event = {**_item(id="event-1"), "relatedSourceCount": 2, "relatedSources": ["A", "B"], "hotScore": 80}
    service._apply_ai_refinements([event])

    assert captured[0]["role"] == "system"
    assert "不可信" in captured[0]["content"]
    assert "aiDigest" not in event


def test_scheduler_uses_single_process_leader_and_contains_refresh_errors(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path / "cache", now_fn=lambda: NOW)
    first = FinancialNewsScheduler(service, lock_file=tmp_path / "scheduler.lock")
    second = FinancialNewsScheduler(service, lock_file=tmp_path / "scheduler.lock")

    assert first._acquire_leader() is True
    assert second._acquire_leader() is False
    assert first._refresh_safely(lambda: (_ for _ in ()).throw(RuntimeError("offline"))) is False
    first.stop()
    assert second._acquire_leader() is True
    second.stop()


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


def test_successive_quick_refreshes_accumulate_a_rolling_event_library(tmp_path, monkeypatch):
    import newsradar

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(newsradar, "get_radar", lambda force=False: {"industries": []})
    batches = [[{"标题": "早间政策快讯", "发布时间": "2026-08-31 15:01:00"}], [{"标题": "午间政策快讯", "发布时间": "2026-08-31 15:55:00"}]]
    service.quick_fetchers = {"同花顺快讯": lambda: batches.pop(0)}

    service.refresh_quick()
    result = service.refresh_quick()

    assert {report["title"] for item in result["feed"] for report in item["reports"]} == {"早间政策快讯", "午间政策快讯"}
    assert result["eventLibraryHours"] >= 24


def test_reposts_are_visible_in_timeline_but_do_not_count_as_independent_sources(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    rows = [
        service.normalize_quick_rows([{"标题": "同一市场传闻", "发布时间": "2026-08-31 15:55:00", "链接": "https://a.test/1"}], source="同花顺快讯")[0],
        service.normalize_quick_rows([{"标题": "同一市场传闻！", "发布时间": "2026-08-31 15:56:00", "链接": "https://b.test/1"}], source="东方财富快讯")[0],
    ]

    event = service.cluster_items(rows)[0]

    assert event["relatedSourceCount"] == 2
    assert event["independentSourceCount"] == 1
    assert len(event["reports"]) == 2


def test_overseas_event_without_linkage_is_capped_in_global_observation(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    titles = ["美国央行发布海外事件", "欧洲能源供应发生海外事件", "日本市场出现海外事件", "港股市场出现海外事件", "美股公司发布海外事件", "纳斯达克出现海外事件"]
    rows = [service.normalize_quick_rows([{
        "标题": title, "发布时间": "2026-08-31 15:55:00"
    }], source="Federal Reserve")[0] for title in titles]
    result = service._compose(rows, [], [])

    assert len(result["globalObservation"]) == 5
    assert result["aShareHot"] == []


def test_glm_failure_does_not_stop_objective_event_composition(tmp_path, monkeypatch):
    import chat
    import glm_config

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test"})
    monkeypatch.setattr(chat, "_call_llm", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("glm offline")))
    row = service.normalize_quick_rows([{
        "标题": "监管部门发布资本市场政策", "发布时间": "2026-08-31 15:55:00"
    }], source="财联社电报")[0]

    result = service._compose([row], [], [])

    assert result["feed"]
    assert result["feed"][0]["aShareImpactScore"] >= 0
