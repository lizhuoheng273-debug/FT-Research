"""Official public financial announcement connectors (metadata-only, cached).

Reads public announcement headlines, dates, and canonical links from the
domestic S-tier official portals already declared in
``financial_news_sources.json`` (`pbc`, `csrc`, `sse`, `szse`, `gov`, `miit`).
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from data_paths import cache_path
from source_registry import load_registry, source_grade, source_tier

SHANGHAI = timezone(timedelta(hours=8))
UTC = timezone.utc
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_SECONDS = 10
BATCH_TIMEOUT_SECONDS = 25
MAX_ITEMS_PER_SOURCE = 12


@dataclass(frozen=True)
class OfficialPortalSpec:
    source_id: str
    name: str
    url: str
    link_hints: tuple[str, ...] = ()
    category: str = "宏观政策"


OFFICIAL_PORTALS: tuple[OfficialPortalSpec, ...] = (
    OfficialPortalSpec(
        source_id="pbc",
        name="中国人民银行",
        url="https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        link_hints=("113469", "goutongjiaoliu", ".html", ".shtml"),
        category="宏观政策",
    ),
    OfficialPortalSpec(
        source_id="csrc",
        name="证监会",
        url="https://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
        link_hints=("csrc/", ".shtml", ".html"),
        category="宏观政策",
    ),
    OfficialPortalSpec(
        source_id="sse",
        name="上交所",
        url="https://www.sse.com.cn/news/newsrelease/",
        link_hints=("/news/", "/announcement/", ".shtml", ".html"),
        category="公司",
    ),
    OfficialPortalSpec(
        source_id="szse",
        name="深交所",
        url="https://www.szse.cn/aboutus/trends/news/",
        link_hints=("/trends/", "/news/", "/disclosure/", ".html", ".shtml"),
        category="公司",
    ),
    OfficialPortalSpec(
        source_id="gov",
        name="中国政府网",
        url="https://www.gov.cn/zhengce/index.htm",
        link_hints=("/zhengce/", "/yaowen/", ".htm", ".html"),
        category="宏观政策",
    ),
    OfficialPortalSpec(
        source_id="miit",
        name="工业和信息化部",
        url="https://www.miit.gov.cn/jgsj/index.html",
        link_hints=("/art/", "/zwgk/", "/jgsj/", ".html"),
        category="产业",
    ),
)

_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
_IGNORE_TITLES = {
    "首页", "更多", "查看更多", "更多>>", "上一页", "下一页", "尾页",
    "关于我们", "联系我们", "网站地图", "版权声明", "English", "RSS",
}


def _safe_http_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return ""


def _parse_date_text(text: str, *, now: datetime) -> datetime | None:
    match = _DATE_RE.search(text or "")
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        dt = datetime(year, month, day, 9, 0, tzinfo=SHANGHAI)
    except ValueError:
        return None
    if dt > now.astimezone(SHANGHAI) + timedelta(days=1):
        return None
    return dt.astimezone(UTC)


def parse_official_html(
    html: str,
    spec: OfficialPortalSpec,
    *,
    now: datetime | None = None,
    limit: int = MAX_ITEMS_PER_SOURCE,
) -> list[dict[str, Any]]:
    """Extract metadata-only announcements from an official portal HTML page."""
    current = now or datetime.now(UTC)
    soup = BeautifulSoup(html or "", "html.parser")
    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []
    for anchor in soup.find_all("a", href=True):
        href_raw = str(anchor.get("href") or "").strip()
        if not href_raw or href_raw.startswith(("javascript:", "#", "mailto:")):
            continue
        title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
        if len(title) < 8 or title in _IGNORE_TITLES:
            continue
        resolved = _safe_http_url(urljoin(spec.url, href_raw))
        if not resolved or resolved == spec.url or resolved in seen_urls:
            continue
        if spec.link_hints and not any(hint in resolved for hint in spec.link_hints):
            continue
        parent_text = re.sub(r"\s+", " ", anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
        published = _parse_date_text(parent_text, now=current) or _parse_date_text(resolved, now=current)
        if published is None:
            continue
        seen_urls.add(resolved)
        items.append({
            "title": title[:160],
            "summary": title[:240],
            "publishedAt": published.isoformat(),
            "source": spec.name,
            "originSource": spec.name,
            "originalUrl": resolved,
            "category": spec.category,
            "official": True,
            "rumor": False,
            "stale": False,
        })
        if len(items) >= limit:
            break
    return items


class OfficialNewsFetcher:
    """Fetches domestic S-tier official announcements with per-source fallback cache."""

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        portals: tuple[OfficialPortalSpec, ...] = OFFICIAL_PORTALS,
        http_get: Callable[[str], str] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        registry: dict[str, Any] | None = None,
    ):
        self.cache_dir = Path(cache_dir or cache_path("financial-news"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "official-sources.json"
        self.portals = portals
        self.http_get = http_get or self._default_http_get
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self.registry = registry or load_registry()

    @staticmethod
    def _default_http_get(url: str) -> str:
        response = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def _read_cache(self) -> dict[str, Any]:
        if not self.cache_file.exists():
            return {}
        try:
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_file.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.cache_file)

    def _fetch_one(self, spec: OfficialPortalSpec) -> tuple[OfficialPortalSpec, list[dict[str, Any]] | None, str | None]:
        try:
            html = self.http_get(spec.url)
            rows = parse_official_html(html, spec, now=self.now_fn())
            tier_score = source_tier(spec.name, self.registry)
            tier_grade = source_grade(spec.name, self.registry)
            for row in rows:
                row["sourceTier"] = tier_score
                row["sourceLevel"] = tier_grade
            return spec, rows, None
        except Exception as exc:  # noqa: BLE001
            return spec, None, str(exc)

    def load_cached(self) -> dict[str, Any]:
        cached = self._read_cache()
        if cached:
            return cached
        return {"generatedAt": None, "reports": [], "sourceStatus": []}

    def fetch(self) -> dict[str, Any]:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        previous = self._read_cache()
        prev_by_source: dict[str, list[dict[str, Any]]] = {}
        for row in previous.get("reports") or []:
            prev_by_source.setdefault(str(row.get("source") or ""), []).append(row)
        prev_status = {str(s.get("source") or ""): s for s in previous.get("sourceStatus") or []}

        reports: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        executor = ThreadPoolExecutor(max_workers=max(1, min(6, len(self.portals))))
        futures = {executor.submit(self._fetch_one, spec): spec for spec in self.portals}
        try:
            done, _ = wait(futures.keys(), timeout=BATCH_TIMEOUT_SECONDS)
            for future, spec in futures.items():
                if future in done:
                    _, rows, error = future.result()
                else:
                    rows, error = None, "请求超时"
                if rows is not None:
                    reports.extend(rows)
                    statuses.append({
                        "id": spec.source_id,
                        "source": spec.name,
                        "ok": True,
                        "count": len(rows),
                        "fetchedAt": now_iso,
                        "lastSuccessAt": now_iso,
                        "cache": "fresh",
                        "error": None,
                    })
                else:
                    cached_rows = [{**row, "stale": True} for row in prev_by_source.get(spec.name, [])]
                    reports.extend(cached_rows)
                    last_ok = (prev_status.get(spec.name) or {}).get("lastSuccessAt")
                    statuses.append({
                        "id": spec.source_id,
                        "source": spec.name,
                        "ok": False,
                        "count": len(cached_rows),
                        "fetchedAt": now_iso,
                        "lastSuccessAt": last_ok,
                        "cache": "stale" if cached_rows else "missing",
                        "error": error or "官方页面暂不可用",
                    })
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        payload = {"generatedAt": now_iso, "reports": reports, "sourceStatus": statuses}
        self._write_cache(payload)
        return payload
