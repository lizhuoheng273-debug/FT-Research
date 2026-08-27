"""Background scheduler for daily FT-Research hotspot snapshots."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aihot_api import AihotClient
from report_archive import ReportArchive


SHANGHAI = ZoneInfo("Asia/Shanghai")


def snapshot_previous_day(archive: ReportArchive, client: AihotClient, now: datetime | None = None):
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    target = current.date() - timedelta(days=1)
    period = target.isoformat()
    if archive.load_daily(period):
        return archive.load_daily(period)
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
    return archive.save_daily(period, hot_topics=topics[:10], items=items, window_start=f"{period}T00:00:00+08:00", window_end=f"{current.date().isoformat()}T00:00:00+08:00")


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
