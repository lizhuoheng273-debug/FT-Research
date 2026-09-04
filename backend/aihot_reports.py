"""Private HTML adapter for AI HOT weekly/monthly reports."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from aihot_report_parser import parse_report_html
from report_archive import ReportArchive


class AihotReportClient:
    def __init__(self, archive: ReportArchive | None = None, base_url: str = "https://aihot.virxact.com", timeout: float = 20):
        self.archive = archive or ReportArchive()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def _url(self, kind: str, period: str | None = None) -> str:
        root = "weekly" if kind == "weekly" else "monthly"
        return f"{self.base_url}/{root}" + (f"/{period}" if period else "")

    def fetch_period(self, kind: str, period: str | None = None, *, force: bool = False) -> dict[str, Any]:
        if kind not in {"weekly", "monthly"}:
            raise ValueError("周期类型必须是 weekly 或 monthly")
        url = self._url(kind, period)
        resolved_period = period or (datetime.now(timezone.utc).strftime("%Y-%m") if kind == "monthly" else datetime.now(timezone.utc).strftime("%G-W%V"))
        cached = self.archive.load_period(kind, resolved_period)
        if cached and not force:
            return cached
        try:
            candidates = [url]
            if period is None:
                candidates.append(self._url(kind, resolved_period))
            last_error: Exception | None = None
            for candidate in candidates:
                try:
                    response = self._session.get(candidate, timeout=self.timeout, headers={"Accept": "text/html"})
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    report = parse_report_html(response.text, kind=kind, period=resolved_period, source_url=candidate)
                    return self.archive.save_period(kind, resolved_period, report, fetched_at=datetime.now(timezone.utc).isoformat(), stale=False)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if last_error:
                raise last_error
            raise RuntimeError("周期报告没有可用来源")
        except Exception:
            if cached:
                return {**cached, "stale": True}
            raise

    def list_periods(self, kind: str, *, force: bool = False) -> list[dict[str, Any]]:
        cached = self.archive.list_periods(kind)
        if cached and not force:
            return cached
        known = {item["period"] for item in cached}
        try:
            response = self._session.get(self._url(kind), timeout=self.timeout, headers={"Accept": "text/html"})
            response.raise_for_status()
            pattern = r"/(?:weekly|monthly)/(\d{4}-(?:W\d{2}|\d{2}))"
            for period in re.findall(pattern, response.text):
                if period not in known:
                    cached.append({"kind": kind, "period": period, "title": ""})
                    known.add(period)
        except Exception:
            pass
        return sorted(cached, key=lambda item: item.get("period", ""), reverse=True)
