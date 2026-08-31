from datetime import datetime, timedelta, timezone

from financial_news_store import FinancialNewsStore


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def _report(**overrides):
    row = {
        "id": "ignored-by-store",
        "title": "AI 长剧带动内容板块关注",
        "summary": "上市公司披露相关进展",
        "publishedAt": "2026-08-31T07:00:00+00:00",
        "source": "财联社电报",
        "sourceTier": 35,
        "sourceLevel": "S",
        "originalUrl": "https://example.test/story/1",
        "category": "公司",
        "relatedStocks": ["300413"],
    }
    row.update(overrides)
    return row


def test_reports_from_early_refresh_survive_later_refresh(tmp_path):
    store = FinancialNewsStore(tmp_path / "news.db", now_fn=lambda: NOW)

    first_ids = store.upsert_reports([_report()])
    store.upsert_reports([_report(
        title="AI 长剧带动内容板块关注，上市公司回应",
        publishedAt="2026-08-31T07:55:00+00:00",
        originalUrl="https://example.test/story/2",
    )])

    rows = store.load_reports(hours=24)

    assert first_ids
    assert {row["originalUrl"] for row in rows} == {
        "https://example.test/story/1", "https://example.test/story/2"
    }


def test_same_original_url_is_idempotent_but_different_sources_remain_reports(tmp_path):
    store = FinancialNewsStore(tmp_path / "news.db", now_fn=lambda: NOW)

    store.upsert_reports([_report()])
    store.upsert_reports([_report(title="转载：AI 长剧带动内容板块关注", source="另一媒体")])

    rows = store.load_reports(hours=24)

    assert len(rows) == 1
    assert rows[0]["source"] == "另一媒体"


def test_events_keep_report_timeline_separate_from_event_payload(tmp_path):
    store = FinancialNewsStore(tmp_path / "news.db", now_fn=lambda: NOW)
    report_ids = store.upsert_reports([_report(), _report(
        title="AI 长剧带动内容板块关注，上市公司回应",
        publishedAt="2026-08-31T07:55:00+00:00",
        originalUrl="https://example.test/story/2",
        source="另一媒体",
    )])
    event = {
        "id": "event-ai-drama",
        "title": "AI 长剧带动内容板块关注",
        "firstReportAt": "2026-08-31T07:00:00+00:00",
        "latestAt": "2026-08-31T07:55:00+00:00",
        "relatedSourceCount": 2,
        "reports": [],
    }

    store.save_events([{**event, "reportIds": report_ids}])
    loaded = store.load_events(hours=24)

    assert loaded[0]["id"] == "event-ai-drama"
    assert [row["originalUrl"] for row in loaded[0]["reports"]] == [
        "https://example.test/story/1", "https://example.test/story/2"
    ]
    assert "reports" not in store._conn.execute(
        "SELECT payload_json FROM events WHERE event_id = ?", ("event-ai-drama",)
    ).fetchone()["payload_json"]


def test_retention_window_is_configurable_and_not_less_than_one_day(tmp_path):
    store = FinancialNewsStore(tmp_path / "news.db", retention_hours=48, now_fn=lambda: NOW)
    store.upsert_reports([
        _report(originalUrl="https://example.test/old", publishedAt="2026-08-29T07:59:00+00:00"),
        _report(originalUrl="https://example.test/recent", publishedAt="2026-08-30T08:01:00+00:00"),
    ])

    rows = store.load_reports(hours=72)

    assert [row["originalUrl"] for row in rows] == ["https://example.test/recent"]


def test_ai_cache_round_trips_by_content_hash(tmp_path):
    store = FinancialNewsStore(tmp_path / "news.db", now_fn=lambda: NOW)

    assert store.get_ai_cache("hash-1") is None
    store.put_ai_cache("hash-1", {"aiDigest": "事实导读", "createdAt": NOW.isoformat()})

    assert store.get_ai_cache("hash-1")["aiDigest"] == "事实导读"
