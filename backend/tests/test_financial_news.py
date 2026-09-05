from datetime import datetime, timezone
import threading

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


def test_overview_exposes_platform_hot_rank_and_event_detail(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    ranked = {
        "id": "ranked-1", "rank": 1, "title": "多平台财经热点", "platformCount": 3,
        "rankScore": 27, "bestSourceRank": 1, "publishedAt": NOW.isoformat(),
        "originalUrl": "https://example.test/hot", "placements": [],
        "aiDigestStatus": "pending", "stale": False,
    }
    service.hotlist._write({
        "generatedAt": NOW.isoformat(),
        "sources": {"cls": {"entries": [{
            "sourceId": "cls", "sourceName": "财联社", "listKind": "popularity",
            "sourceRank": 1, "title": ranked["title"], "originalUrl": ranked["originalUrl"],
            "fetchedAt": NOW.isoformat(), "publishedAt": NOW.isoformat(),
        }], "lastSuccessAt": NOW.isoformat(), "lastAttemptAt": NOW.isoformat()}},
    })

    overview = service.overview()
    event = service.event(overview["hotRank"][0]["id"])

    assert overview["hotRankGeneratedAt"] == NOW.isoformat()
    assert overview["hotRank"][0]["title"] == "多平台财经热点"
    assert event["placements"][0]["sourceName"] == "财联社"


def test_refresh_hotlists_keeps_existing_financial_news_snapshot(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.save_payload({"generatedAt": NOW.isoformat(), "feed": [_item()], "globalHighlights": [_item()]})
    service.hotlist.fetch_fn = lambda source_id: [{
        "sourceId": source_id, "sourceName": source_id, "listKind": "popularity",
        "sourceRank": 1, "title": "央行发布重要货币政策", "originalUrl": f"https://{source_id}.test/policy",
        "fetchedAt": NOW.isoformat(),
    }]

    result = service.refresh_hotlists(force=True)

    assert result["hotRank"][0]["platformCount"] == 4
    assert result["feed"][0]["id"] == "x"


def test_manual_refresh_updates_platform_hotlist_before_slow_rss_pipeline(tmp_path, monkeypatch):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    order = []
    monkeypatch.setattr(service, "refresh_hotlists", lambda force=False: order.append("hotlist"))
    monkeypatch.setattr(service, "refresh_quick", lambda: order.append("quick"))
    monkeypatch.setattr(service, "refresh_rss", lambda: order.append("rss"))
    monkeypatch.setattr(service, "overview", lambda: {"visible": True})

    result = service.refresh_all()

    assert order == ["hotlist", "quick", "rss"]
    assert result == {"visible": True}


def test_hotlist_ai_digest_is_generated_once_per_event_content_hash(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.hotlist.fetch_fn = lambda source_id: [{
        "sourceId": source_id, "sourceName": source_id, "listKind": "popularity",
        "sourceRank": 1, "title": "OpenAI发布GPT-6模型，软件板块走强",
        "summary": "多个财经平台将其列入热点榜。",
        "originalUrl": f"https://{source_id}.test/gpt", "fetchedAt": NOW.isoformat(),
    }]
    calls = []
    service.hotlist_digest_provider = lambda events: calls.append(events) or {
        events[0]["id"]: "OpenAI发布GPT-6模型，多个财经平台同步关注，市场重点讨论其对软件、云服务和人工智能产业链的影响。"
    }

    service.refresh_hotlists(force=True)
    service.wait_for_hotlist_digests()
    first = service.overview()
    service.refresh_hotlists(force=True)
    service.wait_for_hotlist_digests()
    second = service.overview()

    assert first["hotRank"][0]["aiDigestStatus"] == "ready"
    assert "OpenAI" in first["hotRank"][0]["aiDigest"]
    assert second["hotRank"][0]["aiDigest"] == first["hotRank"][0]["aiDigest"]


def test_hotlist_ai_failure_has_backoff_for_unchanged_events(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.hotlist.fetch_fn = lambda source_id: [{
        "sourceId": source_id, "sourceName": "来源", "listKind": "editorial", "sourceRank": 1,
        "title": "OpenAI发布GPT新模型", "summary": "模型发布", "publishedAt": NOW.isoformat(),
        "originalUrl": f"https://{source_id}.test/story", "fetchedAt": NOW.isoformat(),
    }]
    calls = []
    service.hotlist_digest_provider = lambda events: calls.append(events) or None

    service.refresh_hotlists(force=True)
    service.wait_for_hotlist_digests()
    service.refresh_hotlists(force=True)
    service.wait_for_hotlist_digests()

    assert len(calls) == 1


def test_partial_hotlist_ai_response_backs_off_only_missing_digests(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    events = [
        {"id": "one", "eventDay": "2026-09-04", "placements": [{"sourceId": "ths", "title": "央行发布政策", "fetchedAt": NOW.isoformat(), "originalUrl": "https://news.10jqka.com.cn/one"}]},
        {"id": "two", "eventDay": "2026-09-04", "placements": [{"sourceId": "sina", "title": "美联储发布利率决议", "fetchedAt": NOW.isoformat(), "originalUrl": "https://finance.sina.com.cn/two"}]},
    ]
    calls = []
    service.hotlist_digest_provider = lambda requested: calls.append([event["id"] for event in requested]) or {"one": "央行公布最新政策，市场关注其对流动性与权益资产估值的影响。"}

    service._apply_hotlist_digests(events)
    service._apply_hotlist_digests(events)

    assert calls == [["one", "two"]]
    attached = service._attach_hotlist_digests(events)
    assert attached[0]["aiDigestStatus"] == "ready"
    assert attached[1]["aiDigestStatus"] == "unavailable"


def test_hotlist_digest_fingerprint_ignores_refresh_time_but_changes_across_event_days():
    base = {
        "eventDay": "2026-09-04",
        "placements": [{
            "sourceId": "ths", "sourceRank": 1, "title": "央行发布政策", "summary": "政策摘要",
            "originalUrl": "https://news.10jqka.com.cn/one", "fetchedAt": "2026-09-04T08:00:00+00:00",
        }],
    }
    refreshed = {**base, "placements": [{**base["placements"][0], "fetchedAt": "2026-09-04T08:05:00+00:00"}]}
    next_day = {**base, "eventDay": "2026-09-05"}

    assert FinancialNewsService._hotlist_fingerprint(base) == FinancialNewsService._hotlist_fingerprint(refreshed)
    assert FinancialNewsService._hotlist_fingerprint(base) != FinancialNewsService._hotlist_fingerprint(next_day)


def test_hotlist_digest_batch_gets_a_background_only_extended_timeout(tmp_path, monkeypatch):
    import chat
    import glm_config

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    captured = {}
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test", "baseURL": "https://example.com/v4", "model": "test"})
    def fake_call(_config, _messages, use_tools, **kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": '[{"id":"one","digest":"已核对原始报道的财经事件导读。"}]'}}]}
    monkeypatch.setattr(chat, "_call_llm", fake_call)

    result = service._generate_hotlist_digests([{"id": "one", "placements": []}])

    assert result == {"one": "已核对原始报道的财经事件导读。"}
    assert captured["timeout_seconds"] == 240


def test_hotlist_refresh_returns_before_slow_digest_generation(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.hotlist.fetch_fn = lambda source_id: [{
        "sourceId": source_id, "sourceName": source_id, "listKind": "popularity",
        "sourceRank": 1, "title": "央行发布重要货币政策",
        "originalUrl": f"https://{source_id}.test/policy", "fetchedAt": NOW.isoformat(),
    }]
    entered = threading.Event()
    release = threading.Event()
    def slow_digest(_events):
        entered.set()
        release.wait(2)
        return None
    service.hotlist_digest_provider = slow_digest

    result = service.refresh_hotlists(force=True)

    assert result["hotRank"]
    assert entered.wait(1)
    release.set()
    service.wait_for_hotlist_digests()


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


def test_content_only_quick_news_uses_a_concise_headline_and_preserves_body(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    body = (
        "OpenAI发布新一代GPT模型，多项能力获得提升。"
        "受此影响，A股软件与AI应用方向走强，多只概念股涨停。"
        "后续仍需关注模型的实际发布时间和上市公司公告。"
    )

    item = service.normalize_quick_rows(
        [{"时间": "2026-08-31 15:59:00", "内容": body}],
        source="新浪财经快讯",
    )[0]

    assert item["title"] == "OpenAI发布新一代GPT模型，多项能力获得提升"
    assert item["summary"] == body
    assert len(item["title"]) <= 64


def test_existing_cached_long_title_gets_a_safe_display_title(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    long_title = "美联储公布最新利率决议并释放政策信号。" + "后续正文" * 30
    event = {
        **_item(title=long_title, id="long"), "independentSourceCount": 2,
        "independentSources": ["新华社", "路透社"], "relatedSourceCount": 2,
        "relatedSources": ["新华社", "路透社"], "globalScore": 90,
        "importanceType": "policy_decision", "latestAt": NOW.isoformat(),
    }
    service.save_payload({"editorialVersion": 4, "globalHighlights": [event], "feed": [event]})

    result = service.overview()["globalHighlights"][0]

    assert result["displayTitle"] == "美联储公布最新利率决议并释放政策信号"
    assert result["title"] == long_title


def test_external_urls_accept_only_http_protocols(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    items = service.normalize_quick_rows(
        [{"标题": "不安全链接", "链接": "javascript:alert(1)"}], source="新浪财经快讯"
    )
    assert items[0]["originalUrl"] == ""


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


def test_ai_review_policy_coalesces_changes_rate_limits_and_runs_safety_review(tmp_path):
    clock = [datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc)]
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: clock[0])
    candidate = {**_item(id="event-1"), "globalScore": 78, "independentSourceCount": 1}

    first = service._ai_review_plan([candidate], {})
    assert first["shouldRun"] is False
    assert first["reason"] == "coalescing"

    clock[0] += __import__("datetime").timedelta(minutes=6)
    due = service._ai_review_plan([candidate], first["metadata"])
    assert due["shouldRun"] is True
    assert due["reason"] == "candidate_changed"

    rate_limited_meta = {
        **due["metadata"],
        "lastCheckedAt": (clock[0] - __import__("datetime").timedelta(minutes=5)).isoformat(),
        "lastAttemptAt": (clock[0] - __import__("datetime").timedelta(minutes=5)).isoformat(),
    }
    limited = service._ai_review_plan([candidate], rate_limited_meta)
    assert limited["shouldRun"] is False
    assert limited["reason"] == "rate_limited"

    unchanged_meta = {
        **due["metadata"],
        "lastCandidateFingerprint": due["candidateFingerprint"],
        "lastCheckedAt": (clock[0] - __import__("datetime").timedelta(minutes=31)).isoformat(),
    }
    safety = service._ai_review_plan([candidate], unchanged_meta)
    assert safety["shouldRun"] is True
    assert safety["reason"] == "safety_review"


def test_ai_review_policy_bypasses_coalescing_for_urgent_official_event_and_at_close(tmp_path):
    clock = [datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc)]
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: clock[0])
    urgent = {
        **_item(id="official-1", sourceLevel="S", official=True),
        "globalScore": 94,
        "independentSourceCount": 1,
    }
    immediate = service._ai_review_plan([urgent], {})
    assert immediate["shouldRun"] is True
    assert immediate["reason"] == "urgent_change"

    clock[0] = datetime(2026, 9, 4, 7, 10, tzinfo=timezone.utc)  # 15:10 Beijing
    ordinary = {**_item(id="event-2"), "globalScore": 75, "independentSourceCount": 2}
    fingerprint = service._ai_candidate_fingerprint([ordinary])
    close = service._ai_review_plan([ordinary], {
        "lastCandidateFingerprint": fingerprint,
        "lastCheckedAt": datetime(2026, 9, 4, 6, 55, tzinfo=timezone.utc).isoformat(),
    })
    assert close["shouldRun"] is True
    assert close["reason"] == "post_close"


def test_ai_rate_limit_tracks_model_attempt_not_a_cache_only_safety_check(tmp_path):
    now = datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc)
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: now)
    urgent = {
        **_item(id="urgent", sourceLevel="S", official=True),
        "globalScore": 95, "independentSourceCount": 1,
    }
    plan = service._ai_review_plan([urgent], {
        "lastCandidateFingerprint": "older-candidates",
        "lastCheckedAt": (now - __import__("datetime").timedelta(minutes=1)).isoformat(),
        "lastAttemptAt": (now - __import__("datetime").timedelta(minutes=20)).isoformat(),
    })

    assert plan["shouldRun"] is True
    assert plan["reason"] == "urgent_change"


def test_post_close_review_does_not_wait_for_candidate_coalescing(tmp_path):
    now = datetime(2026, 9, 4, 7, 10, tzinfo=timezone.utc)
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: now)
    candidate = {**_item(id="new-at-close"), "globalScore": 75, "independentSourceCount": 1}

    plan = service._ai_review_plan([candidate], {
        "lastCandidateFingerprint": "before-close",
        "lastAttemptAt": (now - __import__("datetime").timedelta(minutes=20)).isoformat(),
    })

    assert plan["shouldRun"] is True
    assert plan["reason"] == "post_close"


def test_ai_candidate_discovery_includes_major_model_launch_for_market_linkage(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    model_release = {
        **_item(id="gpt", title="OpenAI发布GPT-6新模型", summary="新一代大模型已正式发布"),
        "globalScore": 55, "independentSourceCount": 1,
    }
    unrelated = {
        **_item(id="show", title="明星参加互联网综艺", summary="节目预告"),
        "globalScore": 55, "independentSourceCount": 1,
    }

    candidates = service._ai_review_candidates([model_release, unrelated])

    assert [item["id"] for item in candidates] == ["gpt"]


def test_ai_semantic_links_merge_independent_evidence_for_the_hot_list(tmp_path, monkeypatch):
    import chat
    import glm_config
    import json

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test"})
    monkeypatch.setattr(chat, "_call_llm", lambda *_args, **_kwargs: {"choices": [{"message": {"content": json.dumps([{
        "id": "release", "displayTitle": "GPT新模型发布带动A股软件板块走强",
        "digest": "模型发布与A股软件板块异动形成事件链。", "impactTags": ["AI应用", "A股软件"],
        "importanceScore": 92, "relatedEventIds": ["market-reaction"],
    }], ensure_ascii=False)}}]})
    base = {
        "summary": "", "publishedAt": NOW.isoformat(), "category": "产业", "sourceTier": 35,
        "sourceLevel": "A", "originalUrl": "https://example.test/news", "relatedStocks": [],
        "stale": False, "relatedSourceCount": 1, "independentSourceCount": 1,
        "hotScore": 70, "globalScore": 75, "importanceType": "industry_update",
    }
    release = {**base, "id": "release", "title": "OpenAI即将发布GPT新模型", "source": "新华社", "relatedSources": ["新华社"], "reports": [{**base, "title": "OpenAI即将发布GPT新模型", "source": "新华社"}]}
    reaction = {**base, "id": "market-reaction", "title": "A股软件股集体大涨", "source": "证券时报", "relatedSources": ["证券时报"], "reports": [{**base, "title": "A股软件股集体大涨", "source": "证券时报"}]}

    service._apply_ai_refinements([release, reaction])
    merged = service._merge_ai_related_events([release, reaction])

    assert len(merged) == 1
    assert merged[0]["displayTitle"] == "GPT新模型发布带动A股软件板块走强"
    assert merged[0]["independentSourceCount"] == 2
    assert merged[0]["aiImportance"] == 92


def test_scheduled_ai_reviews_preserve_the_accumulated_daily_budget(tmp_path, monkeypatch):
    import chat
    import glm_config
    import json

    clock = [datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc)]
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: clock[0])
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test"})

    def respond(_cfg, messages, use_tools):
        payload = json.loads(messages[-1]["content"].split("\n", 1)[1])
        return {"choices": [{"message": {"content": json.dumps([{
            "id": payload[0]["id"], "displayTitle": payload[0]["title"],
            "digest": "权威事件已进入审核。", "impactTags": [],
            "importanceScore": 90, "relatedEventIds": [],
        }], ensure_ascii=False)}}]}

    monkeypatch.setattr(chat, "_call_llm", respond)
    base = {
        **_item(sourceLevel="S", official=True), "globalScore": 95,
        "independentSourceCount": 1, "relatedSourceCount": 1,
        "relatedSources": ["新华社"], "independentSources": ["新华社"],
    }
    service._review_ai_if_due([{**base, "id": "first", "title": "央行发布利率决议"}])
    clock[0] += __import__("datetime").timedelta(minutes=20)
    service._review_ai_if_due([{**base, "id": "second", "title": "监管部门发布资本市场新规"}])

    assert service._read(service.ai_file)["_meta"]["candidateCount"] == 2


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


def test_glm_failure_does_not_consume_budget_or_make_candidate_permanently_cached(tmp_path, monkeypatch):
    import chat
    import glm_config
    import json

    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {"apiKey": "test"})
    calls = []

    def fake_call(_cfg, _messages, use_tools):
        calls.append(use_tools)
        if len(calls) == 1:
            raise RuntimeError("temporary outage")
        return {"choices": [{"message": {"content": json.dumps([{"id": "event-1", "digest": "恢复后的导读", "impactTags": []},], ensure_ascii=False)}}]}

    monkeypatch.setattr(chat, "_call_llm", fake_call)
    first = {**_item(id="event-1"), "relatedSourceCount": 2, "relatedSources": ["A", "B"], "hotScore": 80}
    service._apply_ai_refinements([first])
    second = {**first}
    service._apply_ai_refinements([second])

    assert len(calls) == 2
    assert second["aiDigest"] == "恢复后的导读"


def test_sqlite_failure_keeps_last_snapshot_and_ai_cache_failure_is_non_fatal(tmp_path, monkeypatch):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    original = service.normalize_quick_rows([{"标题": "缓存中的政策事件", "发布时间": "2026-08-31 15:55:00"}], source="新浪财经快讯")[0]
    service._compose([original], [], [])
    monkeypatch.setattr(service.store, "load_reports", lambda hours: (_ for _ in ()).throw(RuntimeError("db offline")))
    monkeypatch.setattr(service.store, "get_ai_cache", lambda key: (_ for _ in ()).throw(RuntimeError("cache offline")))

    result = service._compose([], [], [])

    assert result["feed"][0]["title"] == "缓存中的政策事件"


def test_due_market_check_reenriches_event_and_marks_checkpoint(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    event = {**_item(id="event-1"), "recheckDueAt": {"15m": "2026-08-31T07:59:00+00:00"}, "marketChecksCompleted": []}
    service.save_payload({"feed": [event], "urgent": [], "hot": [], "aShareHot": [], "candidates": [], "globalObservation": []})
    calls = []

    def enrich(row):
        calls.append(row["id"])
        return {**row, "aShareImpactScore": 61}

    service.market_enricher.enrich_event = enrich
    result = service.refresh_due_market_checks()

    assert calls == ["event-1"]
    assert result["feed"][0]["marketChecksCompleted"] == ["15m"]
    assert result["feed"][0]["aShareImpactScore"] == 61


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


def test_financial_news_manual_refresh_returns_latest_shared_snapshot(monkeypatch):
    refreshed = {
        "refreshing": True, "outcome": "started",
    }
    calls = []
    monkeypatch.setattr(app.financial_news_service, "request_refresh", lambda: calls.append("refresh") or refreshed)

    response = TestClient(app.app).post("/api/finance/news/refresh")

    assert response.status_code == 200
    assert response.json()["data"] == refreshed
    assert calls == ["refresh"]


def test_manual_refresh_returns_immediately_and_coalesces_concurrent_requests(tmp_path, monkeypatch):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    service.save_payload({"generatedAt": NOW.isoformat(), "globalHighlights": []})
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def slow_refresh():
        calls.append("refresh")
        entered.set()
        release.wait(2)
        return service.overview()

    monkeypatch.setattr(service, "refresh_all", slow_refresh)
    first = service.request_refresh()
    assert entered.wait(1)
    second = service.request_refresh()

    assert first["refreshing"] is True
    assert second["refreshing"] is True
    assert first["outcome"] == "started"
    assert second["outcome"] == "already_running"
    assert calls == ["refresh"]
    release.set()


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
    single = service.cluster_items([rows[0]])[0]
    assert event["urgencyScore"] == single["urgencyScore"]
    assert event["hotScore"] == single["hotScore"]


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
