from datetime import datetime

from fastapi.testclient import TestClient

import app
from aihot_report_parser import parse_report_html
from aihot_reports import AihotReportClient
from report_archive import ReportArchive
from report_scheduler import snapshot_previous_day


def test_daily_archive_roundtrip_and_index(tmp_path):
    archive = ReportArchive(tmp_path)
    saved = archive.save_daily(
        "2026-08-27",
        hot_topics=[{"rank": 1, "id": "event-1", "storyId": "story-1", "title": "热点"}],
        items=[{"id": "event-1", "title": "热点", "source": "来源"}],
        generated_at="2026-08-28T00:00:00+08:00",
    )
    assert saved["kind"] == "daily"
    assert archive.load_daily("2026-08-27")["hotTopics"][0]["storyId"] == "story-1"
    assert archive.list_periods("daily") == [{"kind": "daily", "period": "2026-08-27", "hotCount": 1, "headline": "热点"}]


def test_daily_archive_does_not_overwrite_existing_snapshot(tmp_path):
    archive = ReportArchive(tmp_path)
    archive.save_daily("2026-08-27", hot_topics=[{"rank": 1}], items=[])
    assert archive.save_daily("2026-08-27", hot_topics=[{"rank": 2}], items=[])["hotTopics"][0]["rank"] == 1


def test_parse_period_report_html_extracts_themes_media_and_links():
    html = """
    <main>
      <h1>AI HOT周报</h1><p data-period="2026-W34">2026-08-17 ~ 2026-08-23</p>
      <section data-lead><h2>本期主线</h2><p>基础设施与安全并进</p></section>
      <div data-stat="stories">18</div><div data-stat="reports">47</div>
      <section data-theme><h2>算力扩张</h2><p>基础设施投资加速。</p>
        <article data-story-id="story-1" data-published-at="2026-08-23T10:00:00Z"><h3>新模型发布</h3><p>摘要内容</p><span data-source>媒体 A</span><time datetime="2026-08-23T10:00:00Z">2026-08-23</time><a href="https://example.com/original">原文</a><a href="https://aihot.virxact.com/story/story-1">AI HOT</a></article>
      </section>
    </main>
    """
    report = parse_report_html(html, kind="weekly", period="2026-W34", source_url="https://aihot.virxact.com/weekly/2026-W34")
    assert report["title"] == "AI HOT周报"
    assert report["lead"] == "基础设施与安全并进"
    assert report["stats"] == {"stories": 18, "reports": 47}
    assert report["themes"][0]["title"] == "算力扩张"
    assert report["themes"][0]["stories"][0]["source"] == "媒体 A"
    assert report["themes"][0]["stories"][0]["links"]["original"] == "https://example.com/original"
    assert report["themes"][0]["stories"][0]["links"]["story"] == "https://aihot.virxact.com/story/story-1"
    assert report["themes"][0]["stories"][0]["publishedAt"] == "2026-08-23T10:00:00Z"


def test_report_endpoints_proxy_daily_and_period(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "report_archive", ReportArchive(tmp_path))
    app.report_archive.save_daily("2026-08-27", hot_topics=[{"rank": 1}], items=[])
    monkeypatch.setattr(app.aihot_reports, "fetch_period", lambda kind, period: {"kind": kind, "period": period, "report": {"title": "周报"}, "stale": False})
    client = TestClient(app.app)
    assert client.get("/api/ai/reports/index?kind=daily").json()["items"][0]["period"] == "2026-08-27"
    assert client.get("/api/ai/reports/daily/2026-08-27").json()["report"]["kind"] == "daily"
    assert client.get("/api/ai/reports/weekly/2026-W34").json()["report"]["title"] == "周报"


def test_snapshot_previous_day_uses_shanghai_calendar_and_is_idempotent(tmp_path):
    class Client:
        def items(self, **_):
            return {"items": [{"id": "event-1", "score": 90, "links": {"story": "https://aihot/story/story-1"}}]}
        def hot_topics(self, **_):
            return {"items": [{"rank": 1, "id": "event-1", "links": {"story": "https://aihot/story/story-1"}}]}

    archive = ReportArchive(tmp_path)
    now = datetime.fromisoformat("2026-08-28T08:00:00+08:00")
    first = snapshot_previous_day(archive, Client(), now)
    second = snapshot_previous_day(archive, Client(), now)
    assert first["period"] == second["period"] == "2026-08-27"
    assert first["hotTopics"][0]["storyId"] == "story-1"


def test_period_fetch_uses_cached_report_when_upstream_fails(tmp_path, monkeypatch):
    archive = ReportArchive(tmp_path)
    archive.save_period("weekly", "2026-W34", {"title": "已缓存周报", "themes": []})
    client = AihotReportClient(archive=archive, base_url="https://example.test")
    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    cached = client.fetch_period("weekly", "2026-W34")
    assert cached["report"]["title"] == "已缓存周报"
    assert cached["stale"] is True
