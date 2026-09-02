"""安全的 RSS/Atom 抓取、解析与逐媒体缓存。

该模块只保存客观 feed 字段，不生成摘要、不保存用户订阅关系。缓存文件属于运行时
产物，路径固定在 ``backend/.cache/rss``，API 只读这些缓存。
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


HERE = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = HERE / ".cache" / "rss"
MAX_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 4
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 12
MAX_ITEMS = 50
CACHE_TTL_SECONDS = 1800
MAX_CONCURRENT_REFRESHES = 4
TOTAL_FETCH_TIMEOUT = CONNECT_TIMEOUT + READ_TIMEOUT
logger = logging.getLogger(__name__)


DEFAULT_SOURCE_DEFS: tuple[dict[str, object], ...] = (
    {"id": "ithome", "name": "IT之家", "url": "https://www.ithome.com/rss/", "homepage": "https://www.ithome.com", "category": "tech", "region": "cn", "priority": 1},
    {"id": "qbitai", "name": "量子位", "url": "https://www.qbitai.com/feed", "homepage": "https://www.qbitai.com", "category": "ai", "region": "cn", "priority": 2},
    {"id": "jiqizhixin", "name": "机器之心", "url": "https://wechat2rss.xlab.app/feed/51e92aad2728acdd1fda7314be32b16639353001.xml", "homepage": "https://www.jiqizhixin.com", "category": "ai", "region": "cn", "priority": 3},
    {"id": "zhidx", "name": "智东西", "url": "https://zhidx.com/rss", "homepage": "https://zhidx.com", "category": "ai", "region": "cn", "priority": 4},
    {"id": "xinzhiyuan", "name": "新智元", "url": "https://wechat2rss.xlab.app/feed/ede30346413ea70dbef5d485ea5cbb95cca446e7.xml", "homepage": "https://www.aixinzhiyuan.com", "category": "ai", "region": "cn", "priority": 5},
    {"id": "tmtpost", "name": "钛媒体", "url": "https://www.tmtpost.com/rss.xml", "homepage": "https://www.tmtpost.com", "category": "tech", "region": "cn", "priority": 7},
    {"id": "huxiu", "name": "虎嗅", "url": "https://rss.huxiu.com/", "homepage": "https://www.huxiu.com", "category": "tech", "region": "cn", "priority": 8},
    {"id": "solidot", "name": "Solidot", "url": "https://www.solidot.org/index.rss", "homepage": "https://www.solidot.org", "category": "science", "region": "cn", "priority": 10},
    {"id": "baijingapp", "name": "白鲸出海", "url": "https://www.baijingapp.com/feed", "homepage": "https://www.baijingapp.com", "category": "tech", "region": "cn", "priority": 11},
    {"id": "williamlong", "name": "月光博客", "url": "https://www.williamlong.info/rss.xml", "homepage": "https://www.williamlong.info", "category": "tech", "region": "cn", "priority": 12},
)

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "spm", "fbclid", "gclid", "msclkid"}


class RssSecurityError(ValueError):
    """The user supplied a URL that is not safe to fetch."""


class RssFetchError(RuntimeError):
    """The URL passed validation but could not be fetched or parsed."""


@dataclass(frozen=True)
class RssItem:
    id: str
    title: str
    summary: str
    publishedAt: str | None
    originalUrl: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "title": self.title, "summary": self.summary, "publishedAt": self.publishedAt, "originalUrl": self.originalUrl}


@dataclass(frozen=True)
class ParsedFeed:
    name: str
    items: tuple[RssItem, ...]


def normalize_url(value: str) -> str:
    parts = urlsplit((value or "").strip())
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(kept), ""))


def _host_is_blocked(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified)


def validate_public_url(value: str, *, resolve_dns: bool = True) -> str:
    """Validate a URL before every request and return its normalized form."""
    raw = (value or "").strip()
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise RssSecurityError("RSS URL 格式无效") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise RssSecurityError("RSS 只支持 HTTP/HTTPS URL")
    if parts.username or parts.password:
        raise RssSecurityError("RSS URL 不允许包含账号或密码")
    if not parts.hostname or _host_is_blocked(parts.hostname):
        raise RssSecurityError("RSS URL 不允许访问本机、内网或云元数据地址")
    if resolve_dns:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise RssSecurityError("RSS 域名无法解析") from exc
        if not addresses or any(_host_is_blocked(address) for address in addresses):
            raise RssSecurityError("RSS 域名解析到了不允许访问的地址")
    return normalize_url(raw)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "svg", "iframe", "object"}:
            self._skip += 1
        elif not self._skip and tag.lower() in {"br", "p", "div", "li", "article"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "svg", "iframe", "object"} and self._skip:
            self._skip -= 1
        elif not self._skip and tag.lower() in {"p", "div", "li", "article"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def clean_summary(value: str, limit: int = 240) -> str:
    text = html.unescape(value or "")
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit].rstrip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _date_key(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0


def _item_id(title: str, url: str, published: str | None, guid: str) -> str:
    seed = guid.strip() or f"{normalize_url(url)}|{title.strip()}|{published or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def parse_feed(raw: bytes, *, source_url: str) -> ParsedFeed:
    if len(raw) > MAX_BYTES:
        raise RssFetchError("RSS 响应超过 4 MB 限制")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RssFetchError("RSS/Atom XML 解析失败") from exc
    feed_name = ""
    entries: list[ET.Element] = []
    for node in root.iter():
        name = _local(node.tag)
        if name == "title" and not feed_name and node.text:
            feed_name = clean_summary(node.text, 100)
        elif name in {"item", "entry"}:
            entries.append(node)
    items: list[RssItem] = []
    for entry in entries[:MAX_ITEMS]:
        title = ""
        url = ""
        summary = ""
        date_value = ""
        guid = ""
        for child in list(entry):
            name = _local(child.tag)
            value = (child.text or "").strip()
            if name == "title" and not title:
                title = clean_summary(value, 220)
            elif name == "link" and not url:
                url = (child.attrib.get("href") or value).strip()
            elif name in {"guid", "id"} and not guid:
                guid = value
            elif name in {"pubdate", "published", "updated", "date", "modified"} and not date_value:
                date_value = value
            elif name in {"description", "summary", "content", "encoded"} and not summary:
                summary = clean_summary(value)
        if not title:
            continue
        if not url:
            url = source_url
        if not url.lower().startswith(("http://", "https://")):
            continue
        published = _parse_date(date_value)
        items.append(RssItem(_item_id(title, url, published, guid), title, summary, published, url))
    items.sort(key=lambda item: _date_key(item.publishedAt), reverse=True)
    if not feed_name:
        feed_name = urlsplit(source_url).hostname or "RSS 媒体"
    return ParsedFeed(feed_name, tuple(items))


def _set_response_read_timeout(response: object, timeout: float) -> bool:
    """Set urllib's underlying socket timeout without assuming one wrapper shape."""
    candidates = [response]
    for attrs in (("fp",), ("fp", "raw"), ("fp", "raw", "_sock"), ("raw",), ("raw", "_sock"), ("_sock",)):
        current = response
        for attr in attrs:
            current = getattr(current, attr, None)
            if current is None:
                break
        if current is not None:
            candidates.append(current)
    for candidate in candidates:
        settimeout = getattr(candidate, "settimeout", None)
        if callable(settimeout):
            try:
                settimeout(timeout)
                return True
            except OSError:
                continue
    return False


def _bounded_response_read(response: object, reader: Callable[[int], bytes], size: int, timeout: float) -> bytes:
    """Read one bounded chunk; closing a fallback response interrupts its reader."""
    if _set_response_read_timeout(response, timeout):
        return reader(size)
    completed = threading.Event()
    result: list[bytes] = []
    errors: list[BaseException] = []

    def read_once() -> None:
        try:
            result.append(reader(size))
        except BaseException as exc:  # the caller normalizes the network boundary
            errors.append(exc)
        finally:
            completed.set()

    threading.Thread(target=read_once, name="rss-bounded-read", daemon=True).start()
    if not completed.wait(timeout):
        close = getattr(response, "close", None)
        if callable(close):
            close()
        raise RssFetchError("RSS 响应读取超时")
    if errors:
        raise errors[0]
    return result[0]


def fetch_url(url: str) -> bytes:
    normalized = validate_public_url(url)
    request = urllib.request.Request(normalized, headers={"User-Agent": "FT-Research RSS Reader/1.0", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.1"})
    opener = urllib.request.build_opener(SafeRedirectHandler())
    deadline = time.monotonic() + TOTAL_FETCH_TIMEOUT
    try:
        with opener.open(request, timeout=min(CONNECT_TIMEOUT, max(0.01, deadline - time.monotonic()))) as response:
            content_length = int(response.headers.get("Content-Length", "0") or 0)
            if content_length > MAX_BYTES:
                raise RssFetchError("RSS 响应超过 4 MB 限制")
            chunks: list[bytes] = []
            size = 0
            while size <= MAX_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RssFetchError("RSS 下载总时限已到")
                reader = getattr(response, "read1", response.read)
                chunk = _bounded_response_read(response, reader, min(64 * 1024, MAX_BYTES + 1 - size), min(READ_TIMEOUT, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise RssFetchError("RSS 响应超过 4 MB 限制")
            return b"".join(chunks)
    except (RssFetchError, RssSecurityError):
        raise
    except Exception as exc:  # noqa: BLE001 - normalize network/parser boundary
        raise RssFetchError(f"RSS 抓取失败：{exc}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RssCatalog:
    def __init__(self, cache_dir: str | Path | None = None, fetcher: Callable[[str], bytes] | None = None, *, validate_dns: bool = True) -> None:
        self.cache_dir = Path(cache_dir or os.environ.get("VR_RSS_CACHE_DIR", DEFAULT_CACHE_DIR))
        self.fetcher = fetcher or fetch_url
        self.validate_dns = validate_dns
        self.source_defs = [dict(item) for item in DEFAULT_SOURCE_DEFS]
        self._cache_lock = threading.RLock()
        self._source_locks_lock = threading.Lock()
        self._source_locks: dict[str, threading.Lock] = {}
        self._refresh_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REFRESHES)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(normalize_url(url).encode('utf-8')).hexdigest()}.json"

    def _read_cache(self, url: str) -> dict[str, object] | None:
        try:
            value = json.loads(self._cache_path(url).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def _write_cache(self, url: str, value: dict[str, object]) -> None:
        # The legacy radar and RSS scheduler share this catalog and may finish
        # the same source together. Keep their atomic replacement serialized.
        with self._cache_lock:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(url)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)

    def _source_lock(self, url: str) -> threading.Lock:
        """Return the URL-scoped lock held from fetch through cache persistence."""
        key = normalize_url(url)
        with self._source_locks_lock:
            return self._source_locks.setdefault(key, threading.Lock())

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, RssSecurityError):
            return "security"
        if isinstance(error, TimeoutError) or "timeout" in str(error).lower() or "timed out" in str(error).lower():
            return "timeout"
        if isinstance(error, urllib.error.HTTPError):
            return "http"
        if "http error" in str(error).lower():
            return "http"
        if isinstance(error, RssFetchError) and "解析" in str(error):
            return "parse"
        return "unknown"

    def _record_failure(self, source: dict[str, object], error: str, error_code: str) -> None:
        try:
            with self._cache_lock:
                url = str(source["url"])
                cached = self._read_cache(url) or {"source": source, "items": [], "lastSuccessAt": None}
                self._write_cache(url, {**cached, "lastError": error, "lastErrorCode": error_code, "lastAttemptAt": _now()})
        except OSError:
            logger.warning("Could not persist RSS failure state for %s", source.get("id"))

    @staticmethod
    def _public_snapshot(source: dict[str, object], *, items: Iterable[dict[str, object]], last_success: str | None, last_attempt: str | None, stale: bool, stale_reason: str | None, error: str | None, error_code: str | None) -> dict[str, object]:
        return {"id": source["id"], "name": source["name"], "category": source.get("category", "tech"), "region": source.get("region", "custom"), "priority": source.get("priority", 100), "homepage": source.get("homepage", ""), "lastSuccessAt": last_success, "lastAttemptAt": last_attempt, "stale": stale, "staleReason": stale_reason, "error": error, "errorCode": error_code, "items": list(items)[:3]}

    def _read_snapshot(self, source: dict[str, object], *, stale: bool = False, error: str | None = None) -> dict[str, object]:
        cached = self._read_cache(str(source["url"]))
        if cached and isinstance(cached.get("items"), list):
            last_success = cached.get("lastSuccessAt") if isinstance(cached.get("lastSuccessAt"), str) else None
            last_error = error or cached.get("lastError")
            last_attempt = cached.get("lastAttemptAt") if isinstance(cached.get("lastAttemptAt"), str) else last_success
            error_code = cached.get("lastErrorCode") if isinstance(cached.get("lastErrorCode"), str) else None
            expired = bool(last_success) and (_date_key(_now()) - _date_key(last_success) >= CACHE_TTL_SECONDS)
            return self._public_snapshot(source, items=cached["items"], last_success=last_success,
                                         last_attempt=last_attempt, stale=bool(last_success) and bool(stale or expired or last_error),
                                         stale_reason="fetch_failed" if last_error else ("ttl" if expired else None),
                                         error=str(last_error) if last_error else (None if last_success else "尚未成功抓取"),
                                         error_code=error_code)
        return self._public_snapshot(source, items=[], last_success=None, last_attempt=None, stale=False,
                                     stale_reason="fetch_failed" if error else None, error=error or "尚未成功抓取", error_code=None)

    def refresh(self, source: dict[str, object]) -> dict[str, object]:
        url = str(source["url"])
        # The lock intentionally includes fetch + write. A slow failure must not
        # finish after a newer successful refresh and overwrite its cache.
        with self._source_lock(url), self._refresh_slots:
            try:
                validate_public_url(url, resolve_dns=self.validate_dns)
                parsed = parse_feed(self.fetcher(url), source_url=url)
                now = _now()
                cache_value = {"source": {key: source.get(key) for key in ("id", "name", "category", "region", "priority", "homepage", "url")}, "lastSuccessAt": now, "lastAttemptAt": now, "items": [item.as_dict() for item in parsed.items]}
                self._write_cache(url, cache_value)
                resolved_source = {**source, "name": source.get("name") or parsed.name}
                return self._public_snapshot(resolved_source, items=cache_value["items"], last_success=now, last_attempt=now, stale=False, stale_reason=None, error=None, error_code=None)
            except Exception as exc:  # noqa: BLE001 - stale fallback is the public contract
                error_code = self._error_code(exc)
                self._record_failure(source, str(exc), error_code)
                snapshot = self._read_snapshot(source, stale=True, error=str(exc))
                snapshot["errorCode"] = error_code
                return snapshot

    def refresh_identity(self, source_id: str, custom_url: str | None = None) -> str:
        """Validate identity before the HTTP route applies its cooldown.

        Custom domains get syntax/IP checks here but DNS stays in the admitted
        refresh path, so rejected repeat clicks do not perform DNS work.
        """
        builtin = next((source for source in self.source_defs if source["id"] == source_id), None)
        if builtin:
            if custom_url is not None:
                raise ValueError("内置信源不能指定 URL")
            return source_id
        if not custom_url:
            raise KeyError(source_id)
        normalized = validate_public_url(custom_url, resolve_dns=False)
        expected_id = f"custom-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"
        if source_id != expected_id:
            raise KeyError(source_id)
        return expected_id

    def source_for_refresh(self, source_id: str, custom_url: str | None = None) -> dict[str, object]:
        """Resolve a caller's id without ever accepting an alternate built-in URL."""
        builtin = next((source for source in self.source_defs if source["id"] == source_id), None)
        if builtin:
            self.refresh_identity(source_id, custom_url)
            return dict(builtin)
        self.refresh_identity(source_id, custom_url)
        assert custom_url is not None
        normalized = validate_public_url(custom_url, resolve_dns=self.validate_dns)
        expected_id = f"custom-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"
        if source_id != expected_id:
            raise KeyError(source_id)
        cached = self._read_cache(normalized) or {}
        cached_source = cached.get("source") if isinstance(cached.get("source"), dict) else {}
        return {"id": expected_id, "name": cached_source.get("name") or "自定义媒体", "url": normalized,
                "category": cached_source.get("category") or "tech", "region": "custom",
                "priority": cached_source.get("priority") or 100,
                "homepage": cached_source.get("homepage") or f"{urlsplit(normalized).scheme}://{urlsplit(normalized).netloc}"}

    def refresh_source(self, source_id: str, custom_url: str | None = None) -> dict[str, object]:
        source = self.source_for_refresh(source_id, custom_url)
        snapshot = self.refresh(source)
        return {"source": snapshot, "outcome": "updated" if snapshot["error"] is None else "cached"}

    def resolve(self, url: str, *, source: dict[str, object] | None = None) -> dict[str, object]:
        normalized = validate_public_url(url, resolve_dns=self.validate_dns)
        base = dict(source or {})
        base.setdefault("id", f"custom-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}")
        base.setdefault("url", normalized)
        base.setdefault("category", "tech")
        base.setdefault("region", "custom")
        base.setdefault("priority", 100)
        base.setdefault("homepage", f"{urlsplit(normalized).scheme}://{urlsplit(normalized).netloc}")
        raw = self.fetcher(normalized)
        parsed = parse_feed(raw, source_url=normalized)
        base["name"] = parsed.name
        now = _now()
        self._write_cache(normalized, {"source": base, "lastSuccessAt": now, "items": [item.as_dict() for item in parsed.items]})
        return self._public_snapshot(base, items=[item.as_dict() for item in parsed.items], last_success=now, last_attempt=now, stale=False, stale_reason=None, error=None, error_code=None)

    def sources(self, urls: Iterable[str] | None = None) -> list[dict[str, object]]:
        sources = [self._read_snapshot(source) for source in self.source_defs]
        for url in urls or ():
            try:
                # This path never fetches the URL. DNS outages must not prevent
                # reading a previously validated subscription's local cache.
                normalized = validate_public_url(url, resolve_dns=False)
            except RssSecurityError as exc:
                sources.append(self._public_snapshot({"id": f"custom-{hashlib.sha256(str(url).encode()).hexdigest()[:16]}", "name": "自定义媒体", "url": str(url), "category": "tech", "region": "custom", "priority": 100, "homepage": ""}, items=[], last_success=None, last_attempt=None, stale=False, stale_reason="fetch_failed", error=str(exc), error_code="security"))
                continue
            cached = self._read_cache(normalized)
            if cached and isinstance(cached.get("source"), dict):
                sources.append(self._read_snapshot({**cached["source"], "url": normalized}))
        return sorted(sources, key=lambda item: int(item.get("priority", 100)))

    def record_radar_result(self, source: dict[str, object], items: list[dict[str, object]] | None) -> None:
        """Bootstrap only: filtered radar data must never overwrite RSS snapshots."""
        if not items:
            return
        source_url = str(source.get("url", ""))
        if not source_url or not any(normalize_url(source_url) == normalize_url(str(item["url"])) for item in self.source_defs):
            return
        converted = []
        for item in items:
            converted.append({"id": str(item.get("id") or hashlib.sha256(str(item).encode()).hexdigest()[:20]), "title": item.get("title", ""), "summary": item.get("summary", ""), "publishedAt": item.get("publishedAt") or item.get("time"), "originalUrl": item.get("originalUrl") or item.get("url", "")})
        now = _now()
        with self._cache_lock:
            if self._read_cache(source_url) is None:
                self._write_cache(source_url, {"source": source, "lastSuccessAt": now, "items": converted})

    def refresh_builtins(self) -> list[dict[str, object]]:
        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(self.refresh, self.source_defs))

    def start_scheduler(self, interval: int = 1800) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def run() -> None:
            # Keep each URL on its own cadence. A slow source occupies one
            # worker but never delays another source's next 30-minute check.
            due_at = {normalize_url(str(source["url"])): 0.0 for source in self.source_defs}
            in_flight: dict[str, object] = {}
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REFRESHES, thread_name_prefix="rss-source-refresh") as executor:
                while not self._stop.is_set():
                    now = time.monotonic()
                    for key, future in list(in_flight.items()):
                        if future.done():  # type: ignore[union-attr]
                            try:
                                future.result()  # type: ignore[union-attr]
                            except Exception as exc:
                                # refresh normally converts fetch errors to a stale snapshot;
                                # this only guards unexpected worker failures. Avoid formatting a
                                # full traceback in the scheduler loop, which would delay the
                                # next due source on slow console handlers.
                                logger.warning("RSS refresh worker failed for %s: %s", key, exc)
                            del in_flight[key]
                            due_at[key] = time.monotonic() + interval
                    for source in self.source_defs:
                        key = normalize_url(str(source["url"]))
                        if key not in in_flight and now >= due_at.get(key, 0.0):
                            in_flight[key] = executor.submit(self.refresh, source)
                    remaining = [value - time.monotonic() for key, value in due_at.items() if key not in in_flight]
                    # Poll pending workers briefly so their next deadline is
                    # anchored to completion rather than an unrelated slow URL.
                    self._stop.wait(max(0.01, min(0.05, min(remaining, default=0.05))))
        self._thread = threading.Thread(target=run, name="rss-catalog-refresh", daemon=True)
        self._thread.start()

    def stop_scheduler(self) -> None:
        self._stop.set()


rss_catalog = RssCatalog()
