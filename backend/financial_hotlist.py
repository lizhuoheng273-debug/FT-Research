"""Cross-platform financial hot-list ingestion and deterministic ranking."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_name: str
    list_kind: str
    interval_seconds: int
    max_stale_seconds: int


SOURCE_SPECS = {
    "ths": SourceSpec("ths", "同花顺", "editorial", 300, 1800),
    "eastmoney": SourceSpec("eastmoney", "东方财富", "editorial", 300, 1800),
    "cls": SourceSpec("cls", "财联社", "editorial", 1800, 5400),
    "sina": SourceSpec("sina", "新浪财经", "editorial", 3600, 7200),
}
BEIJING = ZoneInfo("Asia/Shanghai")
SOURCE_HOSTS = {
    "ths": ("10jqka.com.cn",),
    "eastmoney": ("eastmoney.com",),
    "cls": ("cls.cn",),
    "sina": ("sina.com.cn",),
}
SOURCE_BASE_URLS = {
    "ths": "https://www.10jqka.com.cn/",
    "eastmoney": "https://finance.eastmoney.com/",
    "cls": "https://www.cls.cn/",
    "sina": "https://finance.sina.com.cn/",
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any, *, default_tz=timezone.utc) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), timezone.utc)
        except (ValueError, OSError):
            return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=default_tz).astimezone(timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def source_is_due(spec: SourceSpec, last_attempt_at: str | None, now: datetime) -> bool:
    previous = _parse_time(last_attempt_at)
    return previous is None or (now.astimezone(timezone.utc) - previous).total_seconds() >= spec.interval_seconds


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _safe_source_url(spec: SourceSpec, value: Any) -> str:
    url = _safe_url(value)
    hostname = (urlparse(url).hostname or "").lower()
    allowed = SOURCE_HOSTS.get(spec.source_id, ())
    return url if any(hostname == root or hostname.endswith(f".{root}") for root in allowed) else ""


def _absolute_source_url(spec: SourceSpec, value: Any) -> str:
    return urljoin(SOURCE_BASE_URLS[spec.source_id], str(value or "").strip())


def _entry(spec: SourceSpec, rank: int, title: Any, url: Any, fetched_at: datetime, *, summary: Any = "", published_at: Any = None, published_timezone=timezone.utc) -> dict[str, Any] | None:
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip()
    clean_url = _safe_source_url(spec, url)
    if not clean_title or not clean_url:
        return None
    published = _parse_time(published_at, default_tz=published_timezone)
    return {
        "sourceId": spec.source_id,
        "sourceName": spec.source_name,
        "listKind": spec.list_kind,
        "sourceRank": rank,
        "title": clean_title,
        "summary": re.sub(r"\s+", " ", str(summary or "")).strip()[:600],
        "publishedAt": _iso(published) if published else None,
        "originalUrl": clean_url,
        "fetchedAt": _iso(fetched_at),
    }


def _source_time(value: Any, fetched_at: datetime, *, default_tz=BEIJING) -> datetime | None:
    parsed = _parse_time(value, default_tz=default_tz)
    if parsed or not str(value or "").strip():
        return parsed
    text = re.sub(r"\s+", " ", str(value)).strip()
    match = re.search(r"(?:(\d{4})年)?\s*(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2}))?", text)
    if not match:
        return None
    local_now = fetched_at.astimezone(default_tz)
    year = int(match.group(1) or local_now.year)
    month, day = int(match.group(2)), int(match.group(3))
    if not match.group(1) and month > local_now.month + 6:
        year -= 1
    hour, minute = int(match.group(4) or 0), int(match.group(5) or 0)
    return datetime(year, month, day, hour, minute, tzinfo=default_tz).astimezone(timezone.utc)


def _first_list(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(keys)
    queue = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key in wanted and isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return []


def parse_sina_hotlist(payload: str | dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        text = payload.strip()
        text = re.sub(r"^var\s+data\s*=\s*", "", text)
        payload = json.loads(text[:-1] if text.endswith(";") else text)
    rows = _first_list(payload, ("data", "list"))
    spec = SOURCE_SPECS["sina"]
    output = []
    for row in rows:
        published = " ".join(filter(None, [str(row.get("create_date") or ""), str(row.get("create_time") or "")])).strip()
        item = _entry(spec, len(output) + 1, row.get("title"), row.get("url"), fetched_at, summary=row.get("summary"), published_at=published, published_timezone=BEIJING)
        if item:
            output.append(item)
        if len(output) == 10:
            break
    return output


def parse_sina_headline_html(payload: str, fetched_at: datetime) -> list[dict[str, Any]]:
    """Parse the homepage's 要闻 editor area, never the retired 7x24 ranking."""
    soup = BeautifulSoup(payload, "html.parser")
    target = soup.select_one("#fin_tabs0_c0")
    if target is None:
        return []
    spec = SOURCE_SPECS["sina"]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_link(link) -> None:
        if len(output) >= 10 or link.get("id") == "news_scroll_1":
            return
        if link.find_parent(id="news_scroll_1") is not None:
            return
        url = _absolute_source_url(spec, link.get("href"))
        if url in seen:
            return
        title = link.get_text(" ", strip=True)
        item = _entry(spec, len(output) + 1, title, url, fetched_at)
        if item:
            seen.add(url)
            output.append(item)

    headline_area = target.select_one("#blk_hdline_01")
    if headline_area is not None:
        for link in headline_area.select("a[href]"):
            append_link(link)
    ordinary_area = target.select_one("section.important-news-area") or target
    for link in ordinary_area.select("ul.m-list li a[href]"):
        append_link(link)
        if len(output) >= 10:
            break
    return output


def parse_eastmoney_editorial(payload: dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    rows = _first_list(payload, ("list", "data"))
    spec = SOURCE_SPECS["eastmoney"]
    output = []
    for row in rows:
        item = _entry(
            spec, len(output) + 1, row.get("title") or row.get("newsTitle"),
            row.get("url") or row.get("newsUrl"), fetched_at,
            summary=row.get("digest") or row.get("summary"),
            published_at=row.get("showTime") or row.get("publishTime"),
            published_timezone=BEIJING,
        )
        if item:
            output.append(item)
        if len(output) == 10:
            break
    return output


def parse_eastmoney_editorial_html(payload: str, fetched_at: datetime) -> list[dict[str, Any]]:
    """Parse only the 资讯精华 container from finance.eastmoney.com/yaowen.html."""
    soup = BeautifulSoup(payload, "html.parser")
    target = soup.select_one("#artitileList1")
    if target is None:
        return []
    spec = SOURCE_SPECS["eastmoney"]
    output: list[dict[str, Any]] = []
    for row in target.select("li"):
        link = row.select_one("p.title a[href]") or row.select_one("a[href]")
        if link is None:
            continue
        info = row.select_one("p.info")
        time_node = row.select_one("p.time")
        published = _source_time(time_node.get_text(" ", strip=True) if time_node else "", fetched_at)
        item = _entry(
            spec, len(output) + 1, link.get_text(" ", strip=True), _absolute_source_url(spec, link.get("href")), fetched_at,
            summary=(info.get("title") if info and info.get("title") else info.get_text(" ", strip=True) if info else ""),
            published_at=published,
        )
        if item:
            output.append(item)
        if len(output) >= 10:
            break
    return output


def parse_cls_hotlist(payload: dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    rows = _first_list(payload, ("roll_data", "list", "data"))
    rows.sort(key=lambda row: float(row.get("reading_num") or row.get("readingNum") or 0), reverse=True)
    spec = SOURCE_SPECS["cls"]
    output = []
    for row in rows:
        item = _entry(
            spec, len(output) + 1, row.get("title") or row.get("subject"),
            row.get("shareurl") or row.get("share_url") or row.get("url"), fetched_at,
            summary=row.get("brief") or row.get("content"), published_at=row.get("ctime") or row.get("time"),
        )
        if item:
            output.append(item)
        if len(output) == 10:
            break
    return output


def parse_cls_headline_html(payload: str, fetched_at: datetime) -> list[dict[str, Any]]:
    """Parse the CLS homepage editorial block; /v1/roll is deliberately out of scope."""
    soup = BeautifulSoup(payload, "html.parser")
    lead = next((node for node in soup.find_all("span")
                 if node.get_text(" ", strip=True) == "头条"
                 and node.find_next_sibling("a", href=True)), None)
    if lead is None:
        return []
    root = next((ancestor for ancestor in lead.parents if "w-420" in str(ancestor.get("class") or "")), lead.parent)
    spec = SOURCE_SPECS["cls"]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in root.select("a[href]"):
        url = _absolute_source_url(spec, link.get("href"))
        if not re.fullmatch(r"/detail/\d+", urlparse(url).path) or url in seen:
            continue
        title = re.sub(r"^\s*[•·]\s*", "", link.get_text(" ", strip=True)).strip()
        item = _entry(spec, len(output) + 1, title, url, fetched_at)
        if item:
            seen.add(url)
            output.append(item)
        if len(output) >= 10:
            break
    return output


def parse_ths_editorial(payload: str, fetched_at: datetime) -> list[dict[str, Any]]:
    soup = BeautifulSoup(payload, "html.parser")
    cards = [link for link in soup.find_all("a", href=True) if link.find(["h2", "h3", "h4"])]
    links = cards or soup.find_all("a", href=True)
    spec = SOURCE_SPECS["ths"]
    output = []
    seen: set[str] = set()
    for link in links:
        heading = link.find(["h2", "h3", "h4"])
        summary_node = link.find("p")
        title = heading.get_text(" ", strip=True) if heading else link.get_text(" ", strip=True)
        url = _safe_url(link.get("href"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        item = _entry(spec, len(output) + 1, title, url, fetched_at, summary=summary_node.get_text(" ", strip=True) if summary_node else "")
        if item:
            output.append(item)
        if len(output) == 10:
            break
    return output


def parse_ths_headline_html(payload: str, fetched_at: datetime) -> list[dict[str, Any]]:
    """Parse links from the active 首页头条 tab only."""
    soup = BeautifulSoup(payload, "html.parser")
    active_tab = next((tab for tab in soup.select("[role='tab'][aria-selected='true'], [role='tab'][data-state='active']") if tab.get_text(" ", strip=True) == "头条"), None)
    if active_tab is None:
        return []
    card = active_tab.find_parent(attrs={"data-slot": "card"})
    if card is None:
        return []
    spec = SOURCE_SPECS["ths"]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in card.select("a[href]"):
        url = _absolute_source_url(spec, link.get("href"))
        if url in seen:
            continue
        heading = link.find(["h1", "h2", "h3", "h4"])
        title = heading.get_text(" ", strip=True) if heading else link.get("data-title") or link.get_text(" ", strip=True)
        summary_node = link.find("p")
        item = _entry(spec, len(output) + 1, title, url, fetched_at, summary=summary_node.get_text(" ", strip=True) if summary_node else "")
        if item:
            seen.add(url)
            output.append(item)
        if len(output) >= 10:
            break
    return output


def _normalized(title: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())


def _bigrams(text: str) -> set[str]:
    return {text[index:index + 2] for index in range(max(1, len(text) - 1))}


def _same_event(left: str, right: str) -> bool:
    a, b = _normalized(left), _normalized(right)
    if not a or not b:
        return False
    if a == b or ((a in b or b in a) and min(len(a), len(b)) / max(len(a), len(b)) >= 0.45):
        return True
    aa, bb = _bigrams(a), _bigrams(b)
    similarity = len(aa & bb) / max(1, len(aa | bb))
    latin_left = {token.replace("-", "") for token in re.findall(r"[a-z]+(?:-\d+)?", left.lower()) if len(token.replace("-", "")) >= 4}
    latin_right = {token.replace("-", "") for token in re.findall(r"[a-z]+(?:-\d+)?", right.lower()) if len(token.replace("-", "")) >= 4}
    return similarity >= 0.42 or (bool(latin_left & latin_right) and similarity >= 0.18)


_FINANCIAL_TERMS = (
    "股", "证券", "基金", "债", "期货", "汇率", "外汇", "人民币", "美元", "日元", "欧元",
    "黄金", "原油", "商品", "央行", "美联储", "利率", "降息", "加息", "通胀", "就业", "GDP",
    "经济", "金融", "财经", "财政", "监管", "证监会", "交易所", "上市", "IPO", "并购", "收购", "财报",
    "营收", "利润", "市值", "关税", "贸易", "芯片", "半导体", "人工智能", "大模型", "OpenAI",
    "GPT", "英伟达", "NVIDIA", "苹果", "微软", "谷歌", "特斯拉", "产业", "政策", "公司",
    "业绩", "销量", "订单", "产能", "分红", "回购", "减持", "增持", "中标", "签约",
)


def is_financial_headline(title: str) -> bool:
    return any(term.lower() in title.lower() for term in _FINANCIAL_TERMS)


def aggregate_hot_rank(entries: list[dict[str, Any]], *, now: datetime, previous_events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for entry in entries:
        if not is_financial_headline(str(entry.get("title") or "")):
            continue
        target = next((group for group in groups if _same_event(entry["title"], group[0]["title"])), None)
        if target is None:
            groups.append([entry])
        else:
            target.append(entry)

    events = []
    consumed_previous_ids: set[str] = set()
    for group in groups:
        by_source: dict[str, dict[str, Any]] = {}
        for placement in group:
            current = by_source.get(placement["sourceId"])
            if current is None or int(placement["sourceRank"]) < int(current["sourceRank"]):
                by_source[placement["sourceId"]] = placement
        placements = sorted(by_source.values(), key=lambda row: (int(row["sourceRank"]), row["sourceId"]))
        lead = placements[0]
        score = sum(max(0, 11 - int(row["sourceRank"])) for row in placements)
        published = max((row.get("publishedAt") or "" for row in placements), default="") or None
        occurred_at = _parse_time(published or lead.get("fetchedAt")) or now.astimezone(timezone.utc)
        day_bucket = occurred_at.astimezone(BEIJING).date().isoformat()
        previous = next((event for event in previous_events or []
            if str(event.get("id") or "") not in consumed_previous_ids
            and str(event.get("eventDay") or "") == day_bucket
            and any(_same_event(str(row.get("title") or ""), str(event.get("title") or "")) for row in placements)), None)
        identity = f"{day_bucket}|{min(_normalized(row['title']) for row in placements)}"
        event_id = str(previous.get("id")) if previous and previous.get("id") else hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        if previous:
            consumed_previous_ids.add(event_id)
        events.append({
            "id": event_id,
            "eventDay": day_bucket,
            "rank": 0,
            "title": lead["title"],
            "platformCount": len(placements),
            "rankScore": score,
            "bestSourceRank": int(lead["sourceRank"]),
            "publishedAt": published,
            "originalUrl": lead["originalUrl"],
            "placements": placements,
            "aiDigestStatus": "pending",
            "stale": any(bool(row.get("stale")) for row in placements),
        })
    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, float]:
        published_at = _parse_time(row.get("publishedAt"))
        return (-row["platformCount"], -row["rankScore"], row["bestSourceRank"], -(published_at.timestamp() if published_at else 0.0))

    events.sort(key=sort_key)
    for index, event in enumerate(events[:10], 1):
        event["rank"] = index
    return events[:10]


class HotlistCollector:
    """Persist per-source ranked snapshots and aggregate only fresh evidence."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        fetch_fn: Callable[[str], list[dict[str, Any]]] | None = None,
    ):
        self.path = Path(cache_dir) / "platform-hotlists.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.now_fn = now_fn
        self.fetch_fn = fetch_fn or self._fetch_source

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, payload: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _get(url: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FT-Research/1.0)", "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        return response

    def _fetch_source(self, source_id: str) -> list[dict[str, Any]]:
        fetched_at = self.now_fn()
        if source_id == "ths":
            response = self._get("https://www.10jqka.com.cn/")
            response.encoding = "utf-8"
            return parse_ths_headline_html(response.text, fetched_at)
        if source_id == "eastmoney":
            response = self._get("https://finance.eastmoney.com/yaowen.html")
            response.encoding = response.apparent_encoding or "utf-8"
            return parse_eastmoney_editorial_html(response.text, fetched_at)
        if source_id == "cls":
            response = self._get("https://www.cls.cn/")
            response.encoding = response.apparent_encoding or "utf-8"
            return parse_cls_headline_html(response.text, fetched_at)
        if source_id == "sina":
            response = self._get("https://finance.sina.com.cn/")
            response.encoding = response.apparent_encoding or "gb18030"
            return parse_sina_headline_html(response.text, fetched_at)
        raise KeyError(source_id)

    def refresh_due(self, *, force: bool = False) -> dict[str, Any]:
        payload = self._read()
        sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
        now = self.now_fn().astimezone(timezone.utc)
        changed = False
        for source_id, spec in SOURCE_SPECS.items():
            state = dict(sources.get(source_id) or {})
            if not force and not source_is_due(spec, state.get("lastAttemptAt"), now):
                continue
            state["lastAttemptAt"] = _iso(now)
            try:
                entries = self.fetch_fn(source_id)
                if not entries:
                    raise ValueError("榜单没有返回有效条目")
                state.update({"entries": entries[:10], "lastSuccessAt": _iso(now), "error": None})
                changed = True
            except Exception as exc:  # each source degrades independently
                state["error"] = str(exc)[:240]
            sources[source_id] = state
        payload["sources"] = sources
        if changed or not payload.get("generatedAt"):
            payload["generatedAt"] = _iso(now)
        self._write(payload)
        result = self.overview()
        payload["events"] = result["hotRank"]
        self._write(payload)
        return result

    def overview(self) -> dict[str, Any]:
        payload = self._read()
        sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
        now = self.now_fn().astimezone(timezone.utc)
        entries: list[dict[str, Any]] = []
        cached_entries: list[dict[str, Any]] = []
        status = []
        for source_id, spec in SOURCE_SPECS.items():
            state = dict(sources.get(source_id) or {})
            last_success = _parse_time(state.get("lastSuccessAt"))
            age = None if last_success is None else max(0, (now - last_success).total_seconds())
            fresh = age is not None and age <= spec.max_stale_seconds
            if fresh:
                entries.extend({**row, "stale": bool(state.get("error"))} for row in state.get("entries") or [] if isinstance(row, dict))
            cached_entries.extend({**row, "stale": True} for row in state.get("entries") or [] if isinstance(row, dict))
            status.append({
                "sourceId": source_id,
                "source": spec.source_name,
                "listKind": spec.list_kind,
                "intervalSeconds": spec.interval_seconds,
                "ok": fresh and not state.get("error"),
                "count": len(state.get("entries") or []),
                "lastSuccessAt": state.get("lastSuccessAt"),
                "lastAttemptAt": state.get("lastAttemptAt"),
                "error": state.get("error"),
                "cache": "stale" if state.get("error") and state.get("entries") else "fresh" if fresh else "stale" if state.get("entries") else "missing",
            })
        # If every live source is unavailable, keep the last successful board
        # visible and label it as cached instead of presenting a blank page.
        visible_entries = entries or cached_entries
        return {
            "hotRank": aggregate_hot_rank(visible_entries, now=now, previous_events=payload.get("events") if isinstance(payload.get("events"), list) else []),
            "generatedAt": payload.get("generatedAt"),
            "sourceStatus": status,
            "stale": not all(row["cache"] == "fresh" for row in status),
        }
