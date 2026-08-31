"""Small standard-library SQLite store for rolling financial-news events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
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


class FinancialNewsStore:
    def __init__(self, path: str | Path, retention_hours: int = 72, now_fn: Callable[[], datetime] = _now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_hours = max(24, int(retention_hours))
        self.now_fn = now_fn
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
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
        """)
        self._conn.commit()

    def _prune(self) -> None:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(hours=self.retention_hours)).isoformat()
        self._conn.execute("DELETE FROM events WHERE COALESCE(latest_at, updated_at) < ?", (cutoff,))
        self._conn.execute("DELETE FROM reports WHERE COALESCE(published_at, last_seen_at) < ?", (cutoff,))
        self._conn.commit()

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
                    related_stocks_json, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    title=excluded.title, summary=excluded.summary,
                    published_at=COALESCE(excluded.published_at, reports.published_at),
                    source=excluded.source, source_tier=excluded.source_tier,
                    source_level=excluded.source_level, original_url=excluded.original_url,
                    normalized_url=excluded.normalized_url, category=excluded.category,
                    track=excluded.track, related_stocks_json=excluded.related_stocks_json,
                    last_seen_at=excluded.last_seen_at""",
                (
                    report_id, str(report.get("title") or "").strip(), str(report.get("summary") or ""),
                    _iso(report.get("publishedAt")), str(report.get("source") or "公开来源"),
                    int(report.get("sourceTier") or 8), str(report.get("sourceLevel") or ""),
                    original_url, normalized_url, str(report.get("category") or ""),
                    str(report.get("track") or ""), json.dumps(report.get("relatedStocks") or [], ensure_ascii=False),
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
        return result

    def load_reports(self, hours: int = 72) -> list[dict[str, Any]]:
        cutoff = (self.now_fn().astimezone(UTC) - timedelta(hours=max(24, int(hours)))).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM reports WHERE published_at IS NULL OR published_at >= ? ORDER BY published_at ASC, first_seen_at ASC", (cutoff,)
        ).fetchall()
        return [self._row_to_report(row) for row in rows]

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

    def get_ai_cache(self, content_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT payload_json FROM ai_cache WHERE content_hash = ?", (content_hash,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def put_ai_cache(self, content_hash: str, value: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO ai_cache(content_hash, payload_json, created_at) VALUES (?, ?, ?) ON CONFLICT(content_hash) DO UPDATE SET payload_json=excluded.payload_json",
            (content_hash, json.dumps(value, ensure_ascii=False), self.now_fn().astimezone(UTC).isoformat()),
        )
        self._conn.commit()

    def save_market_observation(self, observation_id: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO market_observations(observation_id, observed_at, payload_json) VALUES (?, ?, ?)",
            (observation_id, self.now_fn().astimezone(UTC).isoformat(), json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
