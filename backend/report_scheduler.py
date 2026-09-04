"""Background scheduler for daily FT-Research hotspot snapshots."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aihot_api import AihotClient
from report_archive import ReportArchive


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _text(value) -> str:
    return str(value or "").strip()


def _story_id(topic: dict) -> str:
    direct = _text(topic.get("storyId"))
    if direct:
        return direct
    return _text((topic.get("links") or {}).get("story")).rstrip("/").split("/")[-1]


def _daily_summaries(payload: dict) -> dict[str, str]:
    summaries: dict[str, str] = {}
    report = payload.get("report") or payload
    for section in report.get("sections") or []:
        for item in section.get("items") or []:
            item_id = _text((item.get("links") or {}).get("aihot")).rstrip("/").split("/")[-1]
            summary = _text(item.get("summary"))
            if item_id and summary:
                summaries[item_id] = summary
    return summaries


def _story_summary(topic: dict, payload: dict) -> str:
    story = payload.get("story") or payload
    reports = story.get("reports") or []
    topic_id = _text(topic.get("id"))
    for report in reports:
        if _text(report.get("id")) == topic_id and _text(report.get("summary")):
            return _text(report.get("summary"))
    if _text(story.get("latest")):
        return _text(story.get("latest"))
    for report in reports:
        if _text(report.get("summary")):
            return _text(report.get("summary"))
    return _text(story.get("digest"))


def _enrich_topic_summaries(client: AihotClient, period: str, topics: list[dict], items: list[dict]) -> list[dict]:
    item_summaries = {
        _text(item.get("id")): _text(item.get("summary"))
        for item in items
        if _text(item.get("id")) and _text(item.get("summary"))
    }
    enriched = [{**topic, "summary": _text(topic.get("summary")) or item_summaries.get(_text(topic.get("id")), "")} for topic in topics]
    missing = [topic for topic in enriched if not _text(topic.get("summary"))]
    if not missing:
        return enriched

    try:
        daily_summaries = _daily_summaries(client.daily(period))
    except Exception:
        daily_summaries = {}
    for topic in missing:
        topic["summary"] = daily_summaries.get(_text(topic.get("id")), "")

    for topic in enriched:
        if _text(topic.get("summary")):
            continue
        public_id = _story_id(topic)
        if not public_id:
            continue
        try:
            topic["summary"] = _story_summary(topic, client.story(public_id))
        except Exception:
            continue
    return enriched


def snapshot_previous_day(archive: ReportArchive, client: AihotClient, now: datetime | None = None):
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    target = current.date() - timedelta(days=1)
    period = target.isoformat()
    existing = archive.load_daily(period)
    if existing:
        topics = existing.get("hotTopics") or []
        if all(_text(topic.get("summary")) for topic in topics):
            return existing
        items = existing.get("items") or []
        enriched = _enrich_topic_summaries(client, period, topics, items)
        return archive.save_daily(
            period,
            hot_topics=enriched,
            items=items,
            generated_at=existing.get("generatedAt"),
            window_start=existing.get("windowStart"),
            window_end=existing.get("windowEnd"),
            overwrite=True,
        )

    feed = client.items(mode="selected", window="24h", limit=50)
    hot = client.hot_topics()
    items = feed.get("items", [])
    by_id = {item.get("id"): item for item in items}
    topics = []
    for topic in hot.get("items", []):
        item = by_id.get(topic.get("id"))
        topic_copy = {**topic, "storyId": str(topic.get("links", {}).get("story", "")).rstrip("/").split("/")[-1] or topic.get("id")}
        if item:
            topic_copy["score"] = item.get("score")
            topic_copy["reason"] = item.get("reason")
        topics.append(topic_copy)
    if not topics:
        topics = [{**item, "rank": index, "storyId": str(item.get("links", {}).get("story", "")).rstrip("/").split("/")[-1] or item.get("id")} for index, item in enumerate(sorted(items, key=lambda row: row.get("score") or 0, reverse=True)[:10], 1)]
    topics = _enrich_topic_summaries(client, period, topics[:10], items)
    return archive.save_daily(period, hot_topics=topics, items=items, window_start=f"{period}T00:00:00+08:00", window_end=f"{current.date().isoformat()}T00:00:00+08:00")


class DailyReportScheduler:
    def __init__(self, archive: ReportArchive | None = None, client: AihotClient | None = None):
        self.archive = archive or ReportArchive()
        self.client = client or AihotClient()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._run, name="ft-report-scheduler", daemon=True).start()

    def _run(self):
        # Catch up after a restart that happened after the scheduled 08:00 run.
        try:
            snapshot_previous_day(self.archive, self.client)
        except Exception:
            pass
        while True:
            now = datetime.now(SHANGHAI)
            if now.hour == 8 and now.minute == 0:
                try:
                    snapshot_previous_day(self.archive, self.client, now)
                except Exception:
                    pass
            time.sleep(60)
