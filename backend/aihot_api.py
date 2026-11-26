"""AI HOT v1 adapter with ETag validation and last-good cache fallback."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from data_paths import cache_path

DEFAULT_BASE_URL = "https://aihot.virxact.com"
REPORT_BASE_URL = "https://aihot.news"
REPORT_PATHS = {
    "daily": ("dailies", "date", r"\d{4}-\d{2}-\d{2}", 120, 60),
    "weekly": ("weeklies", "week", r"\d{4}-W\d{2}", 52, 300),
    "monthly": ("monthlies", "month", r"\d{4}-\d{2}", 36, 300),
}
REPORT_WEB_PATHS = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
AIHOT_IMAGE_HOSTS = {"aihot.news", "aihot.virxact.com"}


def report_headline_image(html: bytes, page_url: str, headline: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    masthead = soup.select_one("#report-start")
    heading = masthead.find_next("h2") if masthead else None
    if not heading or " ".join(heading.stripped_strings).strip() != " ".join(headline.split()):
        # Inline links can split a headline without adding a visible space.
        if not heading or re.sub(r"\s+", "", heading.get_text()) != re.sub(r"\s+", "", headline):
            return None
    image = heading.parent.select_one("picture img[src]")
    if image is None:
        return None
    src = urljoin(page_url, image["src"])
    parsed = urlsplit(src)
    if parsed.hostname not in AIHOT_IMAGE_HOSTS or parsed.scheme != "https" or parsed.path != "/api/img-proxy":
        return None
    query = parse_qs(parsed.query)
    expiry = query.get("exp", [""])[0]
    if not expiry.isdecimal() or int(expiry) <= time.time() or not query.get("sig"):
        return None
    result = {"url": src, "alt": str(image.get("alt") or "")[:240]}
    figure = image.find_parent("figure")
    frame = image.parent.parent
    ratio = re.search(r"(?:^|;)\s*aspect-ratio\s*:\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?\s*(?:;|$)",
                      str(frame.get("style") or ""))
    if ratio:
        denominator = float(ratio[2] or 1)
        aspect = float(ratio[1]) / denominator if denominator else 0
        if 0.25 <= aspect <= 5:
            result["aspectRatio"] = aspect
    if figure and figure.parent is not heading.parent and "grid" in figure.parent.get("class", []):
        result["layout"] = "inline"
    elif figure:
        result["layout"] = "banner"
    for key in ("width", "height"):
        value = str(image.get(key) or "")
        if value.isdecimal() and 0 < int(value) <= 10000:
            result[key] = int(value)
    return result


def _element_to_markdown(root) -> tuple[str, list[dict[str, Any]]]:
    """Convert an AIHOT article body container into clean Markdown + h2/h3 TOC outline."""
    if root is None:
        return "", []
    blocks: list[str] = []
    outline: list[dict[str, Any]] = []
    sec_idx = 0
    for node in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"]):
        if node.name == "p" and node.find_parent(["li", "blockquote"]):
            continue
        if node.name == "pre":
            code = node.get_text("\n").strip()
            if code:
                blocks.append(f"```\n{code}\n```")
            continue
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not text:
            continue
        if node.name in {"h1", "h2"}:
            sec_idx += 1
            outline.append({"id": f"sec-{sec_idx}", "text": text[:60], "level": 2})
            blocks.append(f"## {text}")
        elif node.name in {"h3", "h4"}:
            sec_idx += 1
            outline.append({"id": f"sec-{sec_idx}", "text": text[:60], "level": 3})
            blocks.append(f"### {text}")
        elif node.name == "blockquote":
            blocks.append(f"> {text}")
        elif node.name == "li":
            blocks.append(f"- {text}")
        else:
            blocks.append(text)
    return "\n\n".join(blocks).strip(), outline


def parse_aihot_item_html(html: bytes, item_id: str, page_url: str, *, lang: str = "zh") -> dict[str, Any]:
    """Parse an AIHOT `/items/{id}` server-rendered page into structured JSON for in-site reading."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "html.parser")
    article = soup.select_one("article")
    if article is None:
        raise ValueError("AIHOT 详情页缺少正文结构")

    h1 = article.select_one("h1")
    title = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip() if h1 else ""
    if not title:
        raise ValueError("AIHOT 详情页缺少标题")

    original_title = ""
    if h1 is not None:
        next_el = h1.find_next_sibling()
        if next_el is not None and next_el.name == "p":
            cand = re.sub(r"\s+", " ", next_el.get_text(" ", strip=True)).strip()
            if cand and cand != title:
                original_title = cand

    header_meta = ""
    for div in article.find_all("div", recursive=False):
        txt = re.sub(r"\s+", " ", div.get_text(" ", strip=True)).strip()
        if txt and ("AI 评分" in txt or "·" in txt):
            header_meta = txt
            break

    score = None
    score_m = re.search(r"AI\s*评分\s*(\d{1,3})", soup.get_text(" ", strip=True))
    if score_m:
        score = int(score_m.group(1))

    pub_match = re.search(r"20\d{2}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?", header_meta or soup.get_text(" ", strip=True))
    published_at = pub_match.group(0) if pub_match else ""

    source_name = header_meta.split("·")[0].strip() if header_meta else ""
    original_url = ""
    # Prefer the explicit "来源：" footer link or sidebar "打开原文" link over inline article hyperlinks
    for p in article.find_all("p", recursive=False):
        if "来源" in p.get_text(" ", strip=True):
            for a in p.select("a[href]"):
                href = str(a.get("href") or "").strip()
                if href.startswith(("http://", "https://")) and "aihot." not in urlsplit(href).netloc:
                    original_url = href
                    if not source_name:
                        source_name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                    break
            if original_url:
                break
    if not original_url:
        for a in soup.select("aside a[href]"):
            href = str(a.get("href") or "").strip()
            if href.startswith(("http://", "https://")) and "aihot." not in urlsplit(href).netloc:
                original_url = href
                break
    if not original_url:
        for a in article.select("a[href]"):
            href = str(a.get("href") or "").strip()
            if href.startswith(("http://", "https://")) and "aihot." not in urlsplit(href).netloc:
                original_url = href
                if not source_name:
                    source_name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                break

    digest = ""
    reason = ""
    body_markdown = ""
    outline: list[dict[str, Any]] = []
    body_label = "正文"
    has_original_lang = False
    story_info: dict[str, str] | None = None

    for sec in article.find_all("section", recursive=False):
        sec_text = re.sub(r"\s+", " ", sec.get_text(" ", strip=True)).strip()
        if sec_text.startswith("AI 导读"):
            paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip() for p in sec.find_all("p")]
            paras = [p for p in paras if p and p != "AI 导读"]
            digest = "\n\n".join(paras) if paras else sec_text[len("AI 导读"):].strip()
        elif sec_text.startswith("推荐理由"):
            paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip() for p in sec.find_all("p")]
            paras = [p for p in paras if p and p != "推荐理由"]
            reason = " ".join(paras) if paras else sec_text[len("推荐理由"):].strip()
        elif sec_text.startswith("正文"):
            header_div = sec.find("div", recursive=False)
            if header_div:
                lbl = header_div.find("span")
                if lbl:
                    body_label = re.sub(r"\s+", " ", lbl.get_text(" ", strip=True)).strip() or "正文"
                for a in header_div.select("nav a[href]"):
                    if str(a.get("href") or "").rstrip("/").endswith("/original"):
                        has_original_lang = True
                body_divs = [c for c in sec.find_all("div", recursive=False) if c is not header_div]
                if body_divs:
                    body_markdown, outline = _element_to_markdown(body_divs[0])
            else:
                body_markdown, outline = _element_to_markdown(sec)
        elif sec_text.startswith("所属事件"):
            for a in sec.select("a[href]"):
                href = str(a.get("href") or "").strip()
                m_st = re.match(r"^/story/([A-Za-z0-9_-]+)$", href)
                if m_st:
                    st_title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                    if st_title and st_title != "查看完整事件":
                        story_info = {"storyId": m_st.group(1), "title": st_title}
                        break
                    if story_info is None:
                        story_info = {"storyId": m_st.group(1), "title": title}

    tags: list[str] = []
    daily_edition: dict[str, str] | None = None
    for a in article.select("a[href]"):
        href = str(a.get("href") or "").strip()
        txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        if href.startswith("/topics/") and txt and txt not in tags:
            tags.append(txt)
        m_daily = re.match(r"^/daily/(\d{4}-\d{2}-\d{2})$", href)
        if m_daily and not daily_edition:
            daily_edition = {"date": m_daily.group(1), "label": txt or m_daily.group(1)}

    return {
        "id": item_id,
        "title": title,
        "originalTitle": original_title,
        "sourceName": source_name or "AI HOT",
        "publishedAt": published_at,
        "score": score,
        "digest": digest,
        "reason": reason,
        "lang": lang,
        "bodyMode": "full" if len(body_markdown) >= 40 else "summary",
        "bodyLabel": body_label,
        "hasOriginalLang": has_original_lang,
        "bodyMarkdown": body_markdown,
        "outline": outline,
        "tags": tags,
        "originalUrl": original_url,
        "aihotUrl": page_url,
        "story": story_info,
        "dailyEdition": daily_edition,
    }


def normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    links = raw.get("links") or {}
    source = raw.get("source") or {}
    return {
        "id": str(raw.get("id") or hashlib.sha1(str(raw).encode()).hexdigest()[:16]),
        "title": raw.get("title") or raw.get("originalTitle") or "未命名事件",
        "summary": raw.get("summary") or "",
        "score": raw.get("score"),
        "reason": raw.get("reason") or "",
        "category": raw.get("category") or "",
        "publishedAt": raw.get("publishedAt") or raw.get("discoveredAt"),
        "source": source.get("name") if isinstance(source, dict) else str(source),
        "links": {
            "aihot": links.get("aihot"),
            "original": links.get("original"),
            "story": links.get("story"),
        },
    }


class AihotClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20, cache_dir: str | None = None):
        self.base_url = (base_url or os.environ.get("AIHOT_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._cache: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self._checked: dict[str, float] = {}
        self._image_lock = threading.Lock()
        self._image_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
        self._image_pending: set[str] = set()
        self._image_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="aihot-edition-image")
        self._cache_dir = Path(cache_dir or os.environ.get("AIHOT_CACHE_DIR", cache_path("aihot")))

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _load_disk(self, key: str) -> tuple[str | None, dict[str, Any]] | None:
        try:
            raw = json.loads(self._cache_path(key).read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("payload"), dict):
                return raw.get("etag"), raw["payload"]
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _save_disk(self, key: str, etag: str | None, payload: dict[str, Any]) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(key).write_text(json.dumps({"etag": etag, "payload": payload}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Cache is an optimization; a read-only deployment still works.
            pass

    def _get(self, path: str, params: dict[str, Any] | None = None, *, reuse_seconds: int = 0) -> dict[str, Any]:
        key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params or {}))
        etag, cached = self._cache.get(key, (None, None))
        if cached is None:
            disk = self._load_disk(key)
            if disk:
                etag, cached = disk
                self._cache[key] = disk
        headers = {"Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag
        if reuse_seconds and cached is not None and time.monotonic() - self._checked.get(key, float("-inf")) < reuse_seconds:
            return {**cached, "stale": False}
        try:
            response = self._session.get(self.base_url + path, params=params, headers=headers, timeout=self.timeout)
            if response.status_code == 304 and cached is not None:
                self._checked[key] = time.monotonic()
                return {**cached, "stale": False, "notModified": True}
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                self._cache[key] = (response.headers.get("ETag"), payload)
                self._checked[key] = time.monotonic()
                self._save_disk(key, response.headers.get("ETag"), payload)
                return {**payload, "stale": False}
            raise RuntimeError("AI HOT 返回格式不是 JSON 对象")
        except Exception:
            if cached is not None:
                return {**cached, "stale": True}
            raise

    def items(self, **params: Any) -> dict[str, Any]:
        payload = self._get("/api/v1/items", params or {"mode": "selected", "window": "24h", "limit": 50})
        payload["items"] = [normalize_item(x) for x in payload.get("items", [])]
        return payload

    def hot_topics(self, **params: Any) -> dict[str, Any]:
        payload = self._get("/api/v1/hot-topics", params)
        payload["items"] = [
            {
                **item,
                "source": (item.get("source") or {}).get("name") if isinstance(item.get("source"), dict) else item.get("source"),
            }
            for item in payload.get("items", [])
        ]
        return payload

    def story(self, public_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/stories/{public_id}")

    def daily(self, date: str | None = None) -> dict[str, Any]:
        return self._get("/api/v1/dailies/latest" if not date else f"/api/v1/dailies/{date}")

    def report_edition(self, kind: str, period: str = "latest") -> dict[str, Any]:
        path, field, pattern, _, ttl = REPORT_PATHS[kind]
        if period != "latest" and not re.fullmatch(pattern, period):
            raise ValueError("报告期格式不正确")
        payload = self._get(f"/api/v1/{path}/{period}", reuse_seconds=ttl)
        report = payload.get("report")
        if not isinstance(report, dict) or not re.fullmatch(pattern, str(report.get(field, ""))) or (
            period != "latest" and report[field] != period
        ):
            raise ValueError("AIHOT 报告响应异常")
        return {**payload, "period": report[field]}

    def report_editions(self, kind: str) -> dict[str, Any]:
        path, field, pattern, limit, ttl = REPORT_PATHS[kind]
        payload = self._get(f"/api/v1/{path}", {"limit": limit}, reuse_seconds=ttl)
        if not isinstance(payload.get("items"), list):
            raise ValueError("AIHOT 归档响应异常")
        return {**payload, "items": [
            {**row, "period": row[field]} for row in payload["items"]
            if isinstance(row, dict) and re.fullmatch(pattern, str(row.get(field, "")))
        ]}

    def edition_headline_image(self, kind: str, period: str) -> dict[str, Any]:
        _, _, pattern, _, _ = REPORT_PATHS[kind]
        if not re.fullmatch(pattern, period):
            raise ValueError("报告期格式不正确")
        key = f"{kind}:{period}"
        with self._image_lock:
            cached = self._image_cache.get(key)
            if cached and time.monotonic() < cached[0]:
                return {"image": cached[1], "pending": False}
            if key not in self._image_pending and len(self._image_pending) < 4:
                self._image_pending.add(key)
                self._image_workers.submit(self._refresh_edition_image, kind, period, key)
        return {"image": None, "pending": True}

    def _refresh_edition_image(self, kind, period, key):
        image = None
        try:
            report = self.report_edition(kind, period)["report"]
            headline = report.get("headline") or (report.get("lead") or {}).get("title")
            canonical = (report.get("links") or {}).get("aihot")
            url = urlsplit(str(canonical or ""))
            if (not headline or url.scheme != "https" or url.netloc not in AIHOT_IMAGE_HOSTS
                or url.path.rstrip("/") != f"/{REPORT_WEB_PATHS[kind]}/{period}"):
                return
            page_url = url._replace(query="", fragment="").geturl()
            with requests.get(page_url, headers={"Accept": "text/html", "User-Agent": "FT-Research/1.0"},
                              timeout=(3, 6), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return
                html = bytearray()
                for chunk in response.iter_content(32_768):
                    html.extend(chunk)
                    if len(html) > 1_500_000:
                        return
            image = report_headline_image(bytes(html), page_url, headline)
        except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
            pass
        finally:
            with self._image_lock:
                if len(self._image_cache) >= 128:
                    self._image_cache.pop(next(iter(self._image_cache)))
                ttl = min(1800, int(parse_qs(urlsplit(image["url"]).query)["exp"][0]) - time.time() - 10) if image else 300
                self._image_cache[key] = time.monotonic() + max(0, ttl), image
                self._image_pending.discard(key)

    def item_detail(self, item_id: str, *, lang: str = "zh") -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", item_id or ""):
            raise ValueError("条目 ID 格式不正确")
        norm_lang = "original" if lang == "original" else "zh"
        cache_key = f"/items/{item_id}?lang={norm_lang}"
        _, cached = self._cache.get(cache_key, (None, None))
        if cached is None:
            disk = self._load_disk(cache_key)
            if disk:
                _, cached = disk
                self._cache[cache_key] = disk
        if cached is not None and time.monotonic() - self._checked.get(cache_key, float("-inf")) < 900:
            return {**cached, "stale": False}
        suffix = "/original" if norm_lang == "original" else ""
        page_url = f"{self.base_url}/items/{item_id}{suffix}"
        try:
            response = self._session.get(
                page_url,
                headers={"Accept": "text/html", "User-Agent": "FT-Research/1.0"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = parse_aihot_item_html(response.content, item_id, page_url, lang=norm_lang)
            self._cache[cache_key] = (None, parsed)
            self._checked[cache_key] = time.monotonic()
            self._save_disk(cache_key, None, parsed)
            return {**parsed, "stale": False}
        except Exception:
            if cached is not None:
                return {**cached, "stale": True}
            raise

    def selected_snapshot(self) -> dict[str, Any]:
        return self._get("/api/v1/selected/snapshot")

    def selected_changes(self) -> dict[str, Any]:
        return self._get("/api/v1/selected/changes")
