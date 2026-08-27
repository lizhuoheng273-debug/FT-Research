"""Local, git-ignored archive for FT-Research period reports."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReportArchive:
    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root or os.environ.get("FT_REPORTS_DIR", Path(__file__).parent / ".cache" / "ft-reports"))

    def _path(self, kind: str, period: str) -> Path:
        return self.root / kind / f"{period}.json"

    def _write_once(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        return payload

    def save_daily(
        self,
        period: str,
        *,
        hot_topics: list[dict[str, Any]],
        items: list[dict[str, Any]],
        generated_at: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "kind": "daily",
            "period": period,
            "generatedAt": generated_at or datetime.now(timezone.utc).isoformat(),
            "windowStart": window_start,
            "windowEnd": window_end,
            "hotTopics": hot_topics,
            "items": items,
            "source": {"provider": "FT-Research AI 热点资讯"},
        }
        return self._write_once(self._path("daily", period), payload)

    def load_daily(self, period: str) -> dict[str, Any] | None:
        path = self._path("daily", period)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None

    def save_period(self, kind: str, period: str, report: dict[str, Any], *, fetched_at: str | None = None, stale: bool = False) -> dict[str, Any]:
        payload = {
            "kind": kind,
            "period": period,
            "title": report.get("title", ""),
            "generatedAt": report.get("generatedAt"),
            "fetchedAt": fetched_at or datetime.now(timezone.utc).isoformat(),
            "stale": stale,
            "source": report.get("source", {}),
            "report": report,
        }
        path = self._path(kind, period)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        return payload

    def load_period(self, kind: str, period: str) -> dict[str, Any] | None:
        path = self._path(kind, period)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None

    def list_periods(self, kind: str) -> list[dict[str, Any]]:
        directory = self.root / kind
        if not directory.exists():
            return []
        output: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if kind == "daily":
                output.append({"kind": kind, "period": payload.get("period", path.stem), "hotCount": len(payload.get("hotTopics") or [])})
            else:
                output.append({"kind": kind, "period": payload.get("period", path.stem), "title": payload.get("title", "")})
        return output
