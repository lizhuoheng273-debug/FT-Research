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


def test_parse_aihot_period_classes_and_relative_item_links():
    html = """
    <h1>AI HOT周报</h1>
    <section class="period-lead"><h2 class="period-lead-headline">基础设施与安全并进</h2><p class="period-lead-overview">本周主线摘要</p></section>
    <section class="period-stats"><div class="period-stat"><div class="period-stat-value">47</div><div class="period-stat-label">独立事件</div></div></section>
    <section class="daily-section"><h2 class="daily-section-title">算力扩张</h2><p class="period-theme-intro">主题摘要</p><div class="period-stories"><article class="period-story"><h3 class="period-story-title"><a href="/items/event-1">事件标题</a></h3><span class="period-story-source">媒体 A</span></article></div></section>
    <section class="daily-section"><h2 class="daily-section-title">往期 AI 周报</h2><div class="period-stories"><article class="period-story"><h3 class="period-story-title">旧报告</h3></article></div></section>
    """
    report = parse_report_html(html, kind="weekly", period="2026-W34", source_url="https://aihot.virxact.com/weekly")
    assert report["lead"] == "本周主线摘要"
    assert report["stats"] == {"独立事件": 47}
    assert report["themes"][0]["title"] == "算力扩张"
    assert len(report["themes"]) == 1
    story = report["themes"][0]["stories"][0]
    assert story["title"] == "事件标题"
    assert story["source"] == "媒体 A"
    assert story["links"]["original"] == "https://aihot.virxact.com/items/event-1"


def test_report_endpoints_proxy_daily_and_period(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "report_archive", ReportArchive(tmp_path))
    app.report_archive.save_daily("2026-08-27", hot_topics=[{"rank": 1}], items=[])
    monkeypatch.setattr(app.aihot_reports, "fetch_period", lambda kind, period, force=False: {"kind": kind, "period": period, "report": {"title": "周报"}, "stale": False})
    client = TestClient(app.app)
    assert client.get("/api/ai/reports/index?kind=daily").json()["items"][0]["period"] == "2026-08-27"
    assert client.get("/api/ai/reports/daily/2026-08-27").json()["report"]["kind"] == "daily"
    assert client.get("/api/ai/reports/weekly/2026-W34").json()["report"]["title"] == "周报"


def test_period_report_route_forwards_explicit_refresh(monkeypatch):
    calls = []

    def fetch_period(kind, period, force=False):
        calls.append((kind, period, force))
        return {"kind": kind, "period": period, "report": {"title": "周报"}, "stale": False}

    monkeypatch.setattr(app.aihot_reports, "fetch_period", fetch_period)
    client = TestClient(app.app)

    response = client.get("/api/ai/reports/weekly/2026-W34?refresh=true")

    assert response.status_code == 200
    assert calls == [("weekly", "2026-W34", True)]


def test_period_client_prefers_cached_report_without_upstream_request(tmp_path, monkeypatch):
    archive = ReportArchive(tmp_path)
    cached = archive.save_period("weekly", "2026-W34", {"title": "已缓存周报", "themes": []})
    client = AihotReportClient(archive=archive, base_url="https://example.test")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("cached report should not request upstream")

    monkeypatch.setattr(client._session, "get", unexpected_request)

    assert client.fetch_period("weekly", "2026-W34") == cached


def test_period_client_force_refreshes_cached_report(tmp_path, monkeypatch):
    archive = ReportArchive(tmp_path)
    archive.save_period("weekly", "2026-W34", {"title": "已缓存周报", "themes": []})
    client = AihotReportClient(archive=archive, base_url="https://example.test")

    class Response:
        text = "<main><h1>远端周报</h1></main>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: Response())

    refreshed = client.fetch_period("weekly", "2026-W34", force=True)

    assert refreshed["report"]["title"] == "远端周报"
    assert refreshed["stale"] is False


def test_period_index_prefers_cached_periods_without_upstream_request(tmp_path, monkeypatch):
    archive = ReportArchive(tmp_path)
    archive.save_period("monthly", "2026-08", {"title": "已缓存月报", "themes": []})
    client = AihotReportClient(archive=archive, base_url="https://example.test")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("cached period index should not request upstream")

    monkeypatch.setattr(client._session, "get", unexpected_request)

    assert client.list_periods("monthly") == [{"kind": "monthly", "period": "2026-08", "title": "已缓存月报"}]


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


def test_snapshot_previous_day_enriches_every_topic_with_a_real_story_summary(tmp_path):
    class Client:
        def items(self, **_):
            return {
                "items": [
                    {
                        "id": "event-1",
                        "title": "事件一",
                        "summary": "精选资讯中的摘要",
                        "links": {"story": "https://aihot/story/story-1"},
                    }
                ]
            }

        def hot_topics(self, **_):
            return {
                "items": [
                    {"rank": 1, "id": "event-1", "title": "事件一", "links": {"story": "https://aihot/story/story-1"}},
                    {"rank": 2, "id": "event-2", "title": "事件二", "links": {"story": "https://aihot/story/story-2"}},
                ]
            }

        def daily(self, _period):
            return {"report": {"sections": []}}

        def story(self, public_id):
            assert public_id == "story-2"
            return {
                "story": {
                    "latest": "事件二的最新进展",
                    "digest": "事件二的长篇综合摘要",
                    "reports": [],
                }
            }

    archive = ReportArchive(tmp_path)
    now = datetime.fromisoformat("2026-08-28T08:00:00+08:00")

    report = snapshot_previous_day(archive, Client(), now)

    assert [topic["summary"] for topic in report["hotTopics"]] == [
        "精选资讯中的摘要",
        "事件二的最新进展",
    ]


def test_snapshot_previous_day_repairs_an_existing_incomplete_snapshot(tmp_path):
    class Client:
        def daily(self, _period):
            return {
                "report": {
                    "sections": [
                        {
                            "items": [
                                {
                                    "title": "事件一",
                                    "summary": "日报中的真实摘要",
                                    "links": {"aihot": "https://aihot.virxact.com/items/event-1"},
                                }
                            ]
                        }
                    ]
                }
            }

        def story(self, _public_id):
            raise AssertionError("daily report summary should avoid a story request")

    archive = ReportArchive(tmp_path)
    archive.save_daily(
        "2026-08-27",
        hot_topics=[{"rank": 1, "id": "event-1", "title": "事件一", "storyId": "story-1"}],
        items=[],
    )
    now = datetime.fromisoformat("2026-08-28T08:00:00+08:00")

    repaired = snapshot_previous_day(archive, Client(), now)

    assert repaired["hotTopics"][0]["summary"] == "日报中的真实摘要"
    assert archive.load_daily("2026-08-27")["hotTopics"][0]["summary"] == "日报中的真实摘要"


def test_period_fetch_uses_cached_report_when_upstream_fails(tmp_path, monkeypatch):
    archive = ReportArchive(tmp_path)
    archive.save_period("weekly", "2026-W34", {"title": "已缓存周报", "themes": []})
    client = AihotReportClient(archive=archive, base_url="https://example.test")
    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    cached = client.fetch_period("weekly", "2026-W34", force=True)
    assert cached["report"]["title"] == "已缓存周报"
    assert cached["stale"] is True


def test_period_client_uses_html_headers_for_aihot_pages(tmp_path):
    client = AihotReportClient(archive=ReportArchive(tmp_path))
    assert client._session.headers["User-Agent"].startswith("Mozilla/5.0")
    assert "zh-CN" in client._session.headers["Accept-Language"]
