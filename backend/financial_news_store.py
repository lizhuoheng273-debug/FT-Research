"""Small standard-library SQLite store for rolling financial-news events."""

from __future__ import annotations

import functools
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def _iso(value: Any) -> str | None:
    parsed = _parse(value)
    return parsed.isoformat() if parsed else None


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
        query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                 if key.lower() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "spm", "fbclid", "gclid"}]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return text.lower()


def _report_key(report: dict[str, Any]) -> str:
    url = _normalize_url(report.get("originalUrl") or report.get("url"))
    if url:
        material = f"url:{url}"
    else:
        material = json.dumps({
            "source": report.get("source", ""),
            "title": report.get("title", ""),
            "publishedAt": _iso(report.get("publishedAt")),
        }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class FinancialNewsStore:
    def __init__(self, path: str | Path, retention_hours: int = 72, now_fn: Callable[[], datetime] = _now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_hours = max(24, int(retention_hours))
        self.now_fn = now_fn
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=15000")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            source TEXT NOT NULL,
            source_tier INTEGER NOT NULL DEFAULT 8,
            source_level TEXT NOT NULL DEFAULT '',
            original_url TEXT NOT NULL DEFAULT '',
            normalized_url TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            track TEXT NOT NULL DEFAULT '',
            related_stocks_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS reports_published_idx ON reports(published_at);
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            first_report_at TEXT,
            latest_at TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_latest_idx ON events(latest_at);
        CREATE TABLE IF NOT EXISTS event_reports (
            event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
            report_id TEXT NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
            PRIMARY KEY (event_id, report_id)
        );
        CREATE TABLE IF NOT EXISTS ai_cache (
            content_hash TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_observations (
            observation_id TEXT PRIMARY KEY,
            observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracked_stories (
            story_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            bucket TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            overview_json TEXT NOT NULL DEFAULT '{}',
            overview_inputs_hash TEXT NOT NULL DEFAULT '',
            first_report_at TEXT,
            latest_at TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS tracked_stories_latest_idx ON tracked_stories(latest_at);
        CREATE TABLE IF NOT EXISTS story_milestones (
            milestone_id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL REFERENCES tracked_stories(story_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            representative_report_key TEXT NOT NULL DEFAULT '',
            market_note TEXT NOT NULL DEFAULT '',
            report_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS story_milestones_story_idx ON story_milestones(story_id, occurred_at);
        CREATE TABLE IF NOT EXISTS milestone_reports (
            milestone_id TEXT NOT NULL REFERENCES story_milestones(milestone_id) ON DELETE CASCADE,
            story_id TEXT NOT NULL REFERENCES tracked_stories(story_id) ON DELETE CASCADE,
            report_key TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'report',
            PRIMARY KEY (milestone_id, report_key)
        );
        CREATE INDEX IF NOT EXISTS milestone_reports_report_idx ON milestone_reports(report_key);
        CREATE TABLE IF NOT EXISTS story_signals (
            story_id TEXT NOT NULL REFERENCES tracked_stories(story_id) ON DELETE CASCADE,
            participant_key TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_tier TEXT NOT NULL DEFAULT 'C',
            kind TEXT NOT NULL DEFAULT 'editorial',
            observed_at TEXT NOT NULL,
            PRIMARY KEY (story_id, participant_key, observed_at)
        );
        CREATE INDEX IF NOT EXISTS story_signals_story_idx ON story_signals(story_id, observed_at);
        CREATE TABLE IF NOT EXISTS story_heat_hourly (
            story_id TEXT NOT NULL REFERENCES tracked_stories(story_id) ON DELETE CASCADE,
            hour_key TEXT NOT NULL,
            heat REAL NOT NULL DEFAULT 0,
            participants INTEGER NOT NULL DEFAULT 0,
            milestone_label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (story_id, hour_key)
        );
        CREATE TABLE IF NOT EXISTS daily_editions (
            edition_key TEXT PRIMARY KEY,
            edition_date TEXT NOT NULL,
            edition_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS daily_editions_date_idx ON daily_editions(edition_date, edition_type);
        """)
        self._conn.execute("PRAGMA foreign_keys = ON")
        try:
            self._conn.execute("ALTER TABLE reports ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'" )
        except sqlite3.OperationalError:
            pass
        self._conn.commit()

    @_locked
    def _prune(self) -> None:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(hours=self.retention_hours)).isoformat()
        tracked_cutoff = (self.now_fn().astimezone(UTC) - timedelta(days=30)).isoformat()
        self._conn.execute("DELETE FROM events WHERE COALESCE(latest_at, updated_at) < ?", (cutoff,))
        self._conn.execute("DELETE FROM tracked_stories WHERE COALESCE(latest_at, updated_at) < ?", (tracked_cutoff,))
        self._conn.execute(
            """DELETE FROM reports
            WHERE COALESCE(published_at, last_seen_at) < ?
              AND report_id NOT IN (SELECT report_key FROM milestone_reports)""",
            (cutoff,),
        )
        self._conn.commit()

    @_locked
    def upsert_reports(self, reports: list[dict[str, Any]]) -> list[str]:
        observed = self.now_fn().astimezone(UTC).isoformat()
        ids: list[str] = []
        for report in reports:
            report_id = _report_key(report)
            original_url = str(report.get("originalUrl") or report.get("url") or "").strip()
            normalized_url = _normalize_url(original_url)
            self._conn.execute(
                """INSERT INTO reports (
                    report_id, title, summary, published_at, source, source_tier,
                    source_level, original_url, normalized_url, category, track,
                    related_stocks_json, metadata_json, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    title=CASE WHEN reports.metadata_json LIKE '%"translatedZh": true%' THEN reports.title ELSE excluded.title END,
                    summary=CASE WHEN reports.metadata_json LIKE '%"translatedZh": true%' THEN reports.summary ELSE excluded.summary END,
                    published_at=COALESCE(excluded.published_at, reports.published_at),
                    source=excluded.source, source_tier=excluded.source_tier,
                    source_level=excluded.source_level, original_url=excluded.original_url,
                    normalized_url=excluded.normalized_url, category=excluded.category,
                    track=excluded.track, related_stocks_json=excluded.related_stocks_json,
                    metadata_json=CASE WHEN reports.metadata_json LIKE '%"translatedZh": true%' THEN reports.metadata_json ELSE excluded.metadata_json END,
                    last_seen_at=excluded.last_seen_at""",
                (
                    report_id, str(report.get("title") or "").strip(), str(report.get("summary") or ""),
                    _iso(report.get("publishedAt")), str(report.get("source") or "公开来源"),
                    int(report.get("sourceTier") or 8), str(report.get("sourceLevel") or ""),
                    original_url, normalized_url, str(report.get("category") or ""),
                    str(report.get("track") or ""), json.dumps(report.get("relatedStocks") or [], ensure_ascii=False),
                    json.dumps({key: report.get(key) for key in ("importanceType", "official", "rumor", "relatedConcepts", "conceptEvidence", "originSource", "stale") if key in report}, ensure_ascii=False),
                    observed, observed,
                ),
            )
            ids.append(report_id)
        self._conn.commit()
        self._prune()
        return ids

    def _row_to_report(self, row: sqlite3.Row) -> dict[str, Any]:
        result = {
            "id": row["report_id"], "title": row["title"], "summary": row["summary"],
            "publishedAt": row["published_at"], "source": row["source"],
            "sourceTier": row["source_tier"], "sourceLevel": row["source_level"],
            "originalUrl": row["original_url"], "category": row["category"], "track": row["track"],
            "relatedStocks": json.loads(row["related_stocks_json"] or "[]"), "stale": False,
        }
        try:
            result.update(json.loads(row["metadata_json"] or "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        return result

    @_locked
    def load_reports(self, hours: int = 72) -> list[dict[str, Any]]:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(hours=max(24, int(hours)))).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM reports WHERE published_at IS NULL OR published_at >= ? ORDER BY published_at ASC, first_seen_at ASC", (cutoff,)
        ).fetchall()
        return [self._row_to_report(row) for row in rows]

    @_locked
    def save_events(self, events: list[dict[str, Any]]) -> None:
        updated = self.now_fn().astimezone(UTC).isoformat()
        for event in events:
            event_id = str(event.get("id") or "").strip()
            if not event_id:
                continue
            report_ids = [str(value) for value in event.get("reportIds") or [] if value]
            payload = {key: value for key, value in event.items() if key not in {"reports", "reportIds"}}
            self._conn.execute(
                """INSERT INTO events(event_id, first_report_at, latest_at, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET first_report_at=excluded.first_report_at,
                latest_at=excluded.latest_at, payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
                (event_id, _iso(event.get("firstReportAt")), _iso(event.get("latestAt") or event.get("publishedAt")), json.dumps(payload, ensure_ascii=False), updated),
            )
            self._conn.execute("DELETE FROM event_reports WHERE event_id = ?", (event_id,))
            for report_id in report_ids:
                self._conn.execute("INSERT OR IGNORE INTO event_reports(event_id, report_id) VALUES (?, ?)", (event_id, report_id))
        self._conn.commit()
        self._prune()

    @_locked
    def load_events(self, hours: int = 72) -> list[dict[str, Any]]:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(hours=max(24, int(hours)))).isoformat()
        events = self._conn.execute(
            "SELECT * FROM events WHERE latest_at IS NULL OR latest_at >= ? ORDER BY latest_at DESC, updated_at DESC", (cutoff,)
        ).fetchall()
        output: list[dict[str, Any]] = []
        for event_row in events:
            event = json.loads(event_row["payload_json"] or "{}")
            report_rows = self._conn.execute(
                """SELECT r.* FROM reports r JOIN event_reports er ON er.report_id = r.report_id
                WHERE er.event_id = ? ORDER BY r.published_at ASC, r.first_seen_at ASC""", (event_row["event_id"],)
            ).fetchall()
            event["reports"] = [self._row_to_report(row) for row in report_rows]
            output.append(event)
        return output

    @_locked
    def get_ai_cache(self, content_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload_json FROM ai_cache WHERE content_hash = ?", (content_hash,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    @_locked
    def put_ai_cache(self, content_hash: str, value: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO ai_cache(content_hash, payload_json, created_at) VALUES (?, ?, ?) ON CONFLICT(content_hash) DO UPDATE SET payload_json=excluded.payload_json",
            (content_hash, json.dumps(value, ensure_ascii=False), self.now_fn().astimezone(UTC).isoformat()),
        )
        self._conn.commit()

    @_locked
    def save_market_observation(self, observation_id: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO market_observations(observation_id, observed_at, payload_json) VALUES (?, ?, ?)",
            (observation_id, self.now_fn().astimezone(UTC).isoformat(), json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    @_locked
    def upsert_tracked_story(
        self,
        *,
        story_id: str,
        title: str,
        bucket: str,
        status: str = "active",
        overview: dict[str, Any] | None = None,
        overview_inputs_hash: str = "",
        first_report_at: str | None = None,
        latest_at: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        first_iso = _iso(first_report_at) or now_iso
        latest_iso = _iso(latest_at) or first_iso
        self._conn.execute(
            """INSERT INTO tracked_stories (
                story_id, title, bucket, status, overview_json, overview_inputs_hash,
                first_report_at, latest_at, tags_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(story_id) DO UPDATE SET
                title=excluded.title,
                bucket=excluded.bucket,
                status=excluded.status,
                overview_json=CASE WHEN excluded.overview_json != '{}' THEN excluded.overview_json ELSE tracked_stories.overview_json END,
                overview_inputs_hash=CASE WHEN excluded.overview_inputs_hash != '' THEN excluded.overview_inputs_hash ELSE tracked_stories.overview_inputs_hash END,
                first_report_at=MIN(COALESCE(tracked_stories.first_report_at, excluded.first_report_at), excluded.first_report_at),
                latest_at=MAX(COALESCE(tracked_stories.latest_at, excluded.latest_at), excluded.latest_at),
                tags_json=CASE WHEN excluded.tags_json != '[]' THEN excluded.tags_json ELSE tracked_stories.tags_json END,
                updated_at=excluded.updated_at""",
            (
                story_id,
                title,
                bucket,
                status,
                json.dumps(overview or {}, ensure_ascii=False),
                overview_inputs_hash,
                first_iso,
                latest_iso,
                json.dumps(tags or [], ensure_ascii=False),
                now_iso,
            ),
        )
        self._conn.commit()

    @_locked
    def update_tracked_overview(self, story_id: str, overview: dict[str, Any], inputs_hash: str) -> None:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        self._conn.execute(
            "UPDATE tracked_stories SET overview_json = ?, overview_inputs_hash = ?, updated_at = ? WHERE story_id = ?",
            (json.dumps(overview, ensure_ascii=False), inputs_hash, now_iso, story_id),
        )
        self._conn.commit()

    @_locked
    def upsert_milestone(
        self,
        *,
        milestone_id: str,
        story_id: str,
        title: str,
        occurred_at: str | None,
        representative_report_key: str,
        market_note: str = "",
        report_count: int = 1,
    ) -> None:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        occurred_iso = _iso(occurred_at) or now_iso
        self._conn.execute(
            """INSERT INTO story_milestones (
                milestone_id, story_id, title, occurred_at, representative_report_key,
                market_note, report_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(milestone_id) DO UPDATE SET
                title=excluded.title,
                occurred_at=MIN(story_milestones.occurred_at, excluded.occurred_at),
                representative_report_key=excluded.representative_report_key,
                market_note=CASE WHEN excluded.market_note != '' THEN excluded.market_note ELSE story_milestones.market_note END,
                report_count=excluded.report_count""",
            (milestone_id, story_id, title, occurred_iso, representative_report_key, market_note, int(report_count), now_iso),
        )
        self._conn.commit()

    @_locked
    def link_milestone_report(self, *, milestone_id: str, story_id: str, report_key: str, role: str = "report") -> None:
        self._conn.execute(
            """INSERT INTO milestone_reports (milestone_id, story_id, report_key, role)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(milestone_id, report_key) DO UPDATE SET role=excluded.role""",
            (milestone_id, story_id, report_key, role),
        )
        self._conn.execute(
            "UPDATE story_milestones SET report_count = (SELECT COUNT(*) FROM milestone_reports WHERE milestone_id = ?) WHERE milestone_id = ?",
            (milestone_id, milestone_id),
        )
        self._conn.commit()

    @_locked
    def record_signal(
        self,
        *,
        story_id: str,
        participant_key: str,
        source_name: str,
        source_tier: str = "C",
        kind: str = "editorial",
        observed_at: str | None = None,
    ) -> None:
        observed_iso = _iso(observed_at) or self.now_fn().astimezone(UTC).isoformat()
        self._conn.execute(
            """INSERT OR IGNORE INTO story_signals (
                story_id, participant_key, source_name, source_tier, kind, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (story_id, participant_key, source_name, source_tier, kind, observed_iso),
        )
        self._conn.commit()

    @_locked
    def upsert_heat_snapshot(
        self,
        *,
        story_id: str,
        hour_key: str,
        heat: float,
        participants: int,
        milestone_label: str = "",
    ) -> None:
        self._conn.execute(
            """INSERT INTO story_heat_hourly (story_id, hour_key, heat, participants, milestone_label)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(story_id, hour_key) DO UPDATE SET
                heat=excluded.heat,
                participants=excluded.participants,
                milestone_label=CASE WHEN excluded.milestone_label != '' THEN excluded.milestone_label ELSE story_heat_hourly.milestone_label END""",
            (story_id, hour_key, float(heat), int(participants), milestone_label),
        )
        self._conn.commit()

    @_locked
    def list_active_stories(self, days: int = 30) -> list[dict[str, Any]]:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(days=max(1, int(days)))).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM tracked_stories WHERE COALESCE(latest_at, updated_at) >= ? ORDER BY latest_at DESC",
            (cutoff,),
        ).fetchall()
        stories: list[dict[str, Any]] = []
        for row in rows:
            story = self._hydrate_tracked_story(row, include_reports=True)
            stories.append(story)
        return stories

    def _hydrate_tracked_story(self, row: sqlite3.Row, *, include_reports: bool = True) -> dict[str, Any]:
        story_id = row["story_id"]
        milestone_rows = self._conn.execute(
            "SELECT * FROM story_milestones WHERE story_id = ? ORDER BY occurred_at DESC",
            (story_id,),
        ).fetchall()
        milestones: list[dict[str, Any]] = []
        all_reports: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for m_row in milestone_rows:
            reports: list[dict[str, Any]] = []
            if include_reports:
                rep_rows = self._conn.execute(
                    """SELECT r.*, mr.role AS link_role
                    FROM milestone_reports mr
                    JOIN reports r ON r.report_id = mr.report_key
                    WHERE mr.milestone_id = ?
                    ORDER BY COALESCE(r.published_at, r.first_seen_at) DESC""",
                    (m_row["milestone_id"],),
                ).fetchall()
                for rr in rep_rows:
                    rep = self._row_to_report(rr)
                    rep["reportKey"] = rep["id"]
                    rep["role"] = rr["link_role"]
                    reports.append(rep)
                    if rep["id"] not in seen_keys:
                        seen_keys.add(rep["id"])
                        all_reports.append(rep)
            milestones.append({
                "milestoneId": m_row["milestone_id"],
                "storyId": story_id,
                "title": m_row["title"],
                "occurredAt": m_row["occurred_at"],
                "representativeReportKey": m_row["representative_report_key"],
                "marketNote": m_row["market_note"],
                "reportCount": max(int(m_row["report_count"] or 0), len(reports)),
                "reports": reports,
            })
        signal_rows = self._conn.execute(
            "SELECT * FROM story_signals WHERE story_id = ? ORDER BY observed_at DESC",
            (story_id,),
        ).fetchall()
        heat_rows = self._conn.execute(
            "SELECT * FROM story_heat_hourly WHERE story_id = ? ORDER BY hour_key ASC",
            (story_id,),
        ).fetchall()
        try:
            overview = json.loads(row["overview_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            overview = {}
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []
        return {
            "storyId": story_id,
            "title": row["title"],
            "bucket": row["bucket"],
            "status": row["status"],
            "overview": overview,
            "overviewInputsHash": row["overview_inputs_hash"],
            "firstReportAt": row["first_report_at"],
            "latestAt": row["latest_at"],
            "tags": tags,
            "milestones": milestones,
            "reports": all_reports,
            "signals": [dict(s) for s in signal_rows],
            "heatSeries": [
                {
                    "hourKey": h["hour_key"],
                    "heat": h["heat"],
                    "participants": h["participants"],
                    "milestoneLabel": h["milestone_label"],
                }
                for h in heat_rows
            ],
        }

    @_locked
    def get_tracked_story(self, story_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM tracked_stories WHERE story_id = ?", (story_id,)).fetchone()
        if not row:
            return None
        return self._hydrate_tracked_story(row, include_reports=True)

    @_locked
    def get_report_detail(self, report_key: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM reports WHERE report_id = ?", (report_key,)).fetchone()
        if not row:
            return None
        report = self._row_to_report(row)
        report["reportKey"] = report["id"]
        link = self._conn.execute(
            "SELECT story_id, milestone_id, role FROM milestone_reports WHERE report_key = ? LIMIT 1",
            (report_key,),
        ).fetchone()
        if link:
            report["storyId"] = link["story_id"]
            report["milestoneId"] = link["milestone_id"]
            report["role"] = link["role"]
        return report

    @_locked
    def apply_report_translation(self, report_key: str, *, title_zh: str = "", summary_zh: str = "") -> None:
        """Persist validated GLM Chinese translations to reports, milestones, and tracked stories."""
        if not title_zh and not summary_zh:
            return
        row = self._conn.execute(
            "SELECT title, summary, metadata_json FROM reports WHERE report_id = ?",
            (report_key,),
        ).fetchone()
        if not row:
            return
        old_title = row["title"]
        old_summary = row["summary"]
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        if title_zh and not meta.get("originalTitle"):
            meta["originalTitle"] = old_title
        meta["translatedZh"] = True
        new_title = title_zh or old_title
        new_summary = summary_zh or old_summary
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        self._conn.execute(
            "UPDATE reports SET title = ?, summary = ?, metadata_json = ? WHERE report_id = ?",
            (new_title, new_summary, json.dumps(meta, ensure_ascii=False), report_key),
        )
        if title_zh:
            self._conn.execute(
                "UPDATE story_milestones SET title = ? WHERE representative_report_key = ?",
                (title_zh, report_key),
            )
            linked = self._conn.execute(
                "SELECT DISTINCT story_id FROM milestone_reports WHERE report_key = ?",
                (report_key,),
            ).fetchall()
            for link in linked:
                self._conn.execute(
                    "UPDATE tracked_stories SET title = ?, updated_at = ? WHERE story_id = ? AND (title = ? OR story_id IN (SELECT story_id FROM story_milestones WHERE representative_report_key = ?))",
                    (title_zh, now_iso, link["story_id"], old_title, report_key),
                )
        self._conn.commit()

    @_locked
    def merge_tracked_stories(self, *, target_story_id: str, duplicate_story_id: str) -> None:
        """Fold a duplicate cross-outlet tracked story into the surviving story."""
        if not target_story_id or not duplicate_story_id or target_story_id == duplicate_story_id:
            return
        target = self._conn.execute("SELECT * FROM tracked_stories WHERE story_id = ?", (target_story_id,)).fetchone()
        dup = self._conn.execute("SELECT * FROM tracked_stories WHERE story_id = ?", (duplicate_story_id,)).fetchone()
        if not target or not dup:
            return
        target_ms = self._conn.execute(
            "SELECT milestone_id FROM story_milestones WHERE story_id = ? ORDER BY occurred_at DESC LIMIT 1",
            (target_story_id,),
        ).fetchone()
        if not target_ms:
            return
        target_mid = target_ms["milestone_id"]
        dup_links = self._conn.execute(
            "SELECT report_key, role FROM milestone_reports WHERE story_id = ?",
            (duplicate_story_id,),
        ).fetchall()
        for link in dup_links:
            self._conn.execute(
                """INSERT INTO milestone_reports (milestone_id, story_id, report_key, role)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(milestone_id, report_key) DO NOTHING""",
                (target_mid, target_story_id, link["report_key"], link["role"]),
            )
        dup_signals = self._conn.execute(
            "SELECT participant_key, source_name, source_tier, kind, observed_at FROM story_signals WHERE story_id = ?",
            (duplicate_story_id,),
        ).fetchall()
        for sig in dup_signals:
            self._conn.execute(
                """INSERT OR IGNORE INTO story_signals (
                    story_id, participant_key, source_name, source_tier, kind, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (target_story_id, sig["participant_key"], sig["source_name"], sig["source_tier"], sig["kind"], sig["observed_at"]),
            )
        self._conn.execute(
            "UPDATE story_milestones SET report_count = (SELECT COUNT(*) FROM milestone_reports WHERE milestone_id = ?) WHERE milestone_id = ?",
            (target_mid, target_mid),
        )
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        self._conn.execute(
            """UPDATE tracked_stories
            SET first_report_at = MIN(COALESCE(first_report_at, ?), COALESCE(?, first_report_at)),
                latest_at = MAX(COALESCE(latest_at, ?), COALESCE(?, latest_at)),
                updated_at = ?
            WHERE story_id = ?""",
            (dup["first_report_at"], dup["first_report_at"], dup["latest_at"], dup["latest_at"], now_iso, target_story_id),
        )
        self._conn.execute("DELETE FROM tracked_stories WHERE story_id = ?", (duplicate_story_id,))
        self._conn.commit()

    @_locked
    def save_daily_edition(
        self,
        *,
        edition_key: str,
        edition_date: str,
        edition_type: str,
        payload: dict[str, Any],
        snapshot_hash: str = "",
        prompt_version: str = "",
    ) -> None:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        self._conn.execute(
            """INSERT INTO daily_editions (
                edition_key, edition_date, edition_type, payload_json, snapshot_hash,
                prompt_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edition_key) DO UPDATE SET
                payload_json=excluded.payload_json,
                snapshot_hash=excluded.snapshot_hash,
                prompt_version=excluded.prompt_version,
                updated_at=excluded.updated_at""",
            (
                edition_key,
                edition_date,
                edition_type,
                json.dumps(payload, ensure_ascii=False),
                snapshot_hash,
                prompt_version,
                now_iso,
                now_iso,
            ),
        )
        self._conn.commit()

    @_locked
    def get_daily_edition(self, edition_key: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload_json FROM daily_editions WHERE edition_key = ?", (edition_key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    @_locked
    def delete_daily_edition(self, edition_key: str) -> None:
        self._conn.execute("DELETE FROM daily_editions WHERE edition_key = ?", (edition_key,))
        self._conn.commit()

    @_locked
    def get_latest_daily_edition(self, edition_type: str | None = None) -> dict[str, Any] | None:
        if edition_type in {"morning", "evening"}:
            row = self._conn.execute(
                "SELECT payload_json FROM daily_editions WHERE edition_type = ? ORDER BY edition_date DESC, updated_at DESC LIMIT 1",
                (edition_type,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT payload_json FROM daily_editions
                ORDER BY edition_date DESC, CASE edition_type WHEN 'evening' THEN 2 ELSE 1 END DESC, updated_at DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    @_locked
    def list_daily_editions(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT edition_key, edition_date, edition_type, payload_json, updated_at
            FROM daily_editions
            ORDER BY edition_date DESC, CASE edition_type WHEN 'evening' THEN 2 ELSE 1 END DESC
            LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        editions: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {}
            lead = payload.get("lead") or {}
            editions.append({
                "editionKey": row["edition_key"],
                "editionDate": row["edition_date"],
                "editionType": row["edition_type"],
                "publishTimeLabel": payload.get("publishTimeLabel") or ("08:00 早报" if row["edition_type"] == "morning" else "18:00 晚报"),
                "leadTitle": lead.get("title") or payload.get("headline") or row["edition_key"],
                "updatedAt": row["updated_at"],
            })
        return editions

    @_locked
    def prune_tracked(self, days: int = 30) -> None:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(days=max(1, int(days)))).isoformat()
        self._conn.execute("DELETE FROM tracked_stories WHERE COALESCE(latest_at, updated_at) < ?", (cutoff,))
        self._conn.commit()

    @_locked
    def close(self) -> None:
        self._conn.close()
