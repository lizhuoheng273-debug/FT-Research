"""Financial-news priority layer.

Quick feeds answer "what just happened"; the existing RSS radar answers
"what is being reported by several independent sources".  Scores are fully
deterministic and explainable.  GLM is only used to refine new multi-source
events that enter the top ten and its output is cached by content hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import newsradar

BEIJING = timezone(timedelta(hours=8))
QUICK_INTERVAL_SECONDS = 180
RSS_INTERVAL_SECONDS = 1800
_POLICY_WORDS = ("国务院", "央行", "证监会", "交易所", "监管", "政策", "新规", "财政部", "商务部", "发改委", "公告", "停牌", "复牌", "退市")
_OVERSEAS_WORDS = ("美联储", "美国", "欧洲", "日本", "港股", "美股", "纳斯达克", "全球")
_SOURCE_TIERS = {
    "财联社电报": 35,
    "同花顺快讯": 28,
    "东方财富快讯": 24,
    "新浪财经快讯": 22,
    "新华社": 35,
    "中国政府网": 35,
    "证监会": 35,
    "上交所": 35,
    "深交所": 35,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any, *, date_value: Any = "") -> datetime | None:
    text = str(value or "").strip()
    date_text = str(date_value or "").strip()
    if date_text and text and len(text) <= 10:
        text = f"{date_text} {text}"
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        except (ValueError, OSError):
            return None
    text = text.replace("/", "-").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                if fmt.startswith("%m"):
                    parsed = parsed.replace(year=_now().astimezone(BEIJING).year)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(timezone.utc)


def _age_minutes(item: dict[str, Any], now: datetime) -> float:
    parsed = _parse_datetime(item.get("publishedAt"))
    if not parsed:
        return 10_000
    minutes = (now.astimezone(timezone.utc) - parsed).total_seconds() / 60
    # Scheduled event dates occasionally leak into RSS pubDate.  A timestamp
    # more than five minutes in the future is not breaking news.
    return 10_000 if minutes < -5 else max(0.0, minutes)


def _event_type_points(item: dict[str, Any]) -> tuple[int, str | None]:
    blob = f"{item.get('title', '')} {item.get('summary', '')}"
    hit = next((word for word in _POLICY_WORDS if word in blob), None)
    return (20, f"{hit}等重要信息") if hit else (0, None)


def urgency_score(item: dict[str, Any], *, now: datetime | None = None, related_source_count: int = 1) -> tuple[int, list[str]]:
    current = now or _now()
    source_points = max(0, min(35, int(item.get("sourceTier") or 0)))
    age = _age_minutes(item, current)
    if age <= 10:
        recency = 35
    elif age <= 30:
        recency = 30
    elif age <= 120:
        recency = 24
    elif age <= 360:
        recency = 16
    elif age <= 1440:
        recency = 8
    else:
        recency = 0
    type_points, type_reason = _event_type_points(item)
    corroboration = 10 if related_source_count >= 3 else 6 if related_source_count == 2 else 0
    reasons = [f"{related_source_count} 个独立来源"]
    if type_reason:
        reasons.append(type_reason)
    reasons.append("发布时间尚未到达" if age >= 10_000 else "10 分钟内更新" if age <= 10 else f"{max(1, round(age))} 分钟前更新")
    return min(100, source_points + recency + type_points + corroboration), reasons


def hot_score(
    item: dict[str, Any], *, now: datetime | None = None, related_source_count: int = 1,
    category_count: int = 1, update_count: int = 1,
) -> tuple[int, list[str]]:
    current = now or _now()
    source_points = {1: 0, 2: 15, 3: 25, 4: 32}.get(min(related_source_count, 5), 40)
    authority = round(max(0, min(35, int(item.get("sourceTier") or 0))) * 20 / 35)
    age = _age_minutes(item, current)
    recency = 25 if age <= 60 else 20 if age <= 360 else 12 if age <= 1440 else 5 if age <= 4320 else 0
    breadth = 10 if category_count >= 2 else 0
    continuity = 5 if update_count >= 3 else 3 if update_count == 2 else 0
    reasons = [f"{related_source_count} 个独立来源", "高权威来源" if authority >= 16 else "公开来源"]
    if breadth:
        reasons.append(f"覆盖 {category_count} 个赛道")
    if continuity:
        reasons.append("事件持续更新")
    return min(100, source_points + authority + recency + breadth + continuity), reasons


def _normalized_title(title: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", (title or "").lower())


def _bigrams(text: str) -> set[str]:
    return {text[index:index + 2] for index in range(max(0, len(text) - 1))} or {text}


def _similar(a: str, b: str) -> bool:
    left, right = _normalized_title(a), _normalized_title(b)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    aa, bb = _bigrams(left), _bigrams(right)
    return len(aa & bb) / max(1, len(aa | bb)) >= 0.62


def _stable_id(title: str) -> str:
    return hashlib.sha1(_normalized_title(title).encode("utf-8")).hexdigest()[:16]


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return ""


class FinancialNewsService:
    def __init__(self, cache_dir: str | Path | None = None, now_fn: Callable[[], datetime] = _now):
        self.cache_dir = Path(cache_dir or os.environ.get("FINANCIAL_NEWS_CACHE_DIR", Path(__file__).parent / ".cache" / "financial-news"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_file = self.cache_dir / "snapshot.json"
        self.quick_file = self.cache_dir / "quick.json"
        self.ai_file = self.cache_dir / "ai-refinements.json"
        self.now_fn = now_fn
        self._lock = threading.Lock()
        self.quick_fetchers: dict[str, Callable[[], Any]] = self._default_fetchers()

    @staticmethod
    def _default_fetchers() -> dict[str, Callable[[], Any]]:
        try:
            import akshare as ak
        except ImportError:
            return {}
        return {
            "财联社电报": lambda: ak.stock_info_global_cls(symbol="重点"),
            "同花顺快讯": ak.stock_info_global_ths,
            "东方财富快讯": ak.stock_info_global_em,
            "新浪财经快讯": ak.stock_info_global_sina,
        }

    def normalize_quick_rows(self, rows: Any, *, source: str) -> list[dict[str, Any]]:
        if hasattr(rows, "to_dict"):
            rows = rows.to_dict("records")
        output: list[dict[str, Any]] = []
        for raw in rows or []:
            row = dict(raw)
            title = str(_pick(row, "标题", "title", "摘要")).strip()
            if not title:
                continue
            summary = str(_pick(row, "内容", "摘要", "digest", "content", "summary")).strip()
            date_value = _pick(row, "发布日期", "date")
            published = _parse_datetime(_pick(row, "发布时间", "时间", "rtime", "ctime"), date_value=date_value)
            level = str(_pick(row, "等级", "level") or ("A" if source == "财联社电报" else ""))
            url = str(_pick(row, "链接", "url", "新闻链接")).strip()
            output.append({
                "id": _stable_id(f"{source}:{title}"), "title": title, "summary": summary,
                "publishedAt": (published or self.now_fn()).isoformat(), "category": self.classify(title, summary),
                "source": source, "sourceTier": _SOURCE_TIERS.get(source, 18), "sourceLevel": level,
                "originalUrl": url, "relatedStocks": self.related_stocks(title, summary), "stale": False,
            })
        return output

    @staticmethod
    def classify(title: str, summary: str = "", track: str = "") -> str:
        blob = f"{title} {summary} {track}"
        if any(word in blob for word in ("公司", "股份", "业绩", "股东", "董事会", "中标", "减持", "增持")):
            return "公司"
        if any(word in blob for word in _POLICY_WORDS):
            return "宏观政策"
        if any(word in blob for word in _OVERSEAS_WORDS):
            return "海外"
        return "产业"

    @staticmethod
    def related_stocks(title: str, summary: str = "") -> list[str]:
        return sorted(set(re.findall(r"(?<!\d)[0368]\d{5}(?!\d)", f"{title} {summary}")))

    def normalize_radar(self, radar: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for industry in radar.get("industries") or []:
            track = str(industry.get("name") or "")
            for raw in industry.get("items") or []:
                title = str(raw.get("zh") or raw.get("title") or "").strip()
                if not title:
                    continue
                published = datetime.fromtimestamp(raw.get("ts"), tz=timezone.utc) if raw.get("ts") else _parse_datetime(raw.get("time"))
                # Some RSS sources publish scheduled-event timestamps weeks in
                # advance.  Those records belong in a calendar, not in the
                # latest-news feed, where they would otherwise sort first.
                if published and published > self.now_fn() + timedelta(minutes=5):
                    continue
                source = str(raw.get("source") or "公开来源")
                tier = next((value for name, value in _SOURCE_TIERS.items() if name in source), 18)
                output.append({
                    "id": _stable_id(f"{source}:{title}"), "title": title,
                    "summary": str(raw.get("summary") or ""), "publishedAt": (published or self.now_fn()).isoformat(),
                    "category": self.classify(title, str(raw.get("summary") or ""), track), "track": track,
                    "source": source, "sourceTier": tier, "sourceLevel": "", "originalUrl": str(raw.get("url") or ""),
                    "relatedStocks": self.related_stocks(title, str(raw.get("summary") or "")), "stale": False,
                })
        return output

    def cluster_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[list[dict[str, Any]]] = []
        ordered = sorted(items, key=lambda item: item.get("publishedAt") or "", reverse=True)
        for item in ordered:
            published = _parse_datetime(item.get("publishedAt"))
            target = None
            for group in groups:
                group_time = _parse_datetime(group[0].get("publishedAt"))
                close_in_time = not published or not group_time or abs((published - group_time).total_seconds()) <= 86400
                if close_in_time and _similar(item.get("title", ""), group[0].get("title", "")):
                    target = group
                    break
            if target is None:
                groups.append([item])
            else:
                target.append(item)

        events: list[dict[str, Any]] = []
        for group in groups:
            reports = sorted(group, key=lambda item: item.get("publishedAt") or "", reverse=True)
            lead = max(reports, key=lambda item: (int(item.get("sourceTier") or 0), item.get("publishedAt") or ""))
            sources = sorted({str(item.get("source") or "公开来源") for item in reports})
            categories = {str(item.get("category") or "产业") for item in reports}
            urgency, urgency_reasons = urgency_score(lead, now=self.now_fn(), related_source_count=len(sources))
            heat, heat_reasons = hot_score(
                lead, now=self.now_fn(), related_source_count=len(sources), category_count=len(categories), update_count=len(reports),
            )
            event = {
                **lead, "id": _stable_id(lead["title"]), "urgencyScore": urgency, "hotScore": heat,
                "scoreReasons": list(dict.fromkeys(urgency_reasons + heat_reasons)),
                "relatedSourceCount": len(sources), "relatedSources": sources,
                "relatedStocks": sorted({code for report in reports for code in report.get("relatedStocks", [])}),
                "reports": reports, "firstReportAt": reports[-1].get("publishedAt"),
                "latestAt": reports[0].get("publishedAt"), "status": "持续更新" if len(reports) > 1 else "最新",
            }
            events.append(event)
        return events

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def save_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        complete = {"stale": False, "sourceStatus": [], **payload}
        self._write(self.snapshot_file, complete)
        return complete

    def _apply_ai_refinements(self, events: list[dict[str, Any]]) -> None:
        cache = self._read(self.ai_file) or {}
        changed = False
        candidates = [event for event in sorted(events, key=lambda row: row["hotScore"], reverse=True)[:10] if event["relatedSourceCount"] > 1]
        def fingerprint(event: dict[str, Any]) -> str:
            material = json.dumps({"title": event.get("title"), "summary": event.get("summary"), "sources": event.get("relatedSources")}, ensure_ascii=False, sort_keys=True)
            return hashlib.sha1(material.encode("utf-8")).hexdigest()
        missing = [event for event in candidates if cache.get(event["id"], {}).get("_fingerprint") != fingerprint(event)]
        if missing:
            try:
                import chat
                import glm_config
                cfg = glm_config.load_glm_config()
                if cfg.get("apiKey"):
                    compact = [{"id": e["id"], "title": e["title"], "summary": e.get("summary", ""), "sources": e["relatedSources"]} for e in missing]
                    prompt = "请为这些金融资讯事件返回严格 JSON 数组，每项仅含 id、digest（不超过60字）、impactTags（最多3个客观范围标签），不预测涨跌：\n" + json.dumps(compact, ensure_ascii=False)
                    data = chat._call_llm(cfg, [{"role": "user", "content": prompt}], use_tools=False)
                    content = data["choices"][0]["message"].get("content") or "[]"
                    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I).strip()
                    for row in json.loads(content):
                        if row.get("id"):
                            matching = next((event for event in missing if event["id"] == row["id"]), None)
                            cache[row["id"]] = {
                                "aiDigest": str(row.get("digest") or ""), "impactTags": list(row.get("impactTags") or [])[:3],
                                "_fingerprint": fingerprint(matching) if matching else "",
                            }
                            changed = True
            except Exception:
                pass
        if changed:
            self._write(self.ai_file, cache)
        for event in events:
            refinement = {key: value for key, value in cache.get(event["id"], {}).items() if not key.startswith("_")}
            event.update(refinement)

    def _compose(self, quick: list[dict[str, Any]], radar: list[dict[str, Any]], source_status: list[dict[str, Any]]) -> dict[str, Any]:
        events = self.cluster_items(quick + radar)
        self._apply_ai_refinements(events)
        urgent = sorted([event for event in events if event["urgencyScore"] > 0], key=lambda row: (row["urgencyScore"], row.get("publishedAt", "")), reverse=True)[:10]
        hot = sorted(events, key=lambda row: (row["hotScore"], row["relatedSourceCount"], row.get("publishedAt", "")), reverse=True)[:10]
        feed = sorted(events, key=lambda row: row.get("publishedAt") or "", reverse=True)
        return self.save_payload({
            "generatedAt": self.now_fn().isoformat(), "urgent": urgent, "hot": hot, "feed": feed,
            "sourceStatus": source_status,
        })

    def refresh_quick(self) -> dict[str, Any]:
        with self._lock:
            quick: list[dict[str, Any]] = []
            status: list[dict[str, Any]] = []
            for source, fetcher in self.quick_fetchers.items():
                try:
                    rows = self.normalize_quick_rows(fetcher(), source=source)
                    quick.extend(rows)
                    status.append({"source": source, "ok": True, "count": len(rows), "fetchedAt": self.now_fn().isoformat()})
                except Exception as exc:
                    status.append({"source": source, "ok": False, "error": str(exc)[:160], "fetchedAt": self.now_fn().isoformat()})
            if not quick:
                cached = self._read(self.snapshot_file)
                if cached:
                    return {**cached, "stale": True, "sourceStatus": status}
                return self.empty(stale=True, source_status=status)
            self._write(self.quick_file, {"items": quick, "sourceStatus": status, "generatedAt": self.now_fn().isoformat()})
            radar = self.normalize_radar(newsradar.get_radar(force=False))
            return self._compose(quick, radar, status)

    def refresh_rss(self) -> dict[str, Any]:
        with self._lock:
            try:
                radar_payload = newsradar.fetch_radar()
                radar_status = [{"source": "RSS 资讯雷达", "ok": True, "count": sum(len(x.get("items") or []) for x in radar_payload.get("industries") or []), "fetchedAt": self.now_fn().isoformat()}]
            except Exception as exc:
                radar_payload = newsradar.get_radar(force=False)
                radar_status = [{"source": "RSS 资讯雷达", "ok": False, "error": str(exc)[:160], "fetchedAt": self.now_fn().isoformat()}]
            quick_cache = self._read(self.quick_file) or {}
            quick = list(quick_cache.get("items") or [])
            status = list(quick_cache.get("sourceStatus") or []) + radar_status
            if not quick and not any(ind.get("items") for ind in radar_payload.get("industries") or []):
                cached = self._read(self.snapshot_file)
                if cached:
                    return {**cached, "stale": True, "sourceStatus": status}
            return self._compose(quick, self.normalize_radar(radar_payload), status)

    def empty(self, *, stale: bool = False, source_status: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {"generatedAt": None, "stale": stale, "urgent": [], "hot": [], "feed": [], "sourceStatus": source_status or []}

    def overview(self) -> dict[str, Any]:
        return self._read(self.snapshot_file) or self.empty()

    def feed(self, *, category: str = "all", source: str = "", limit: int = 60) -> list[dict[str, Any]]:
        rows = list(self.overview().get("feed") or [])
        if category and category != "all":
            rows = [row for row in rows if row.get("category") == category or row.get("track") == category]
        if source:
            rows = [row for row in rows if source in row.get("relatedSources", [])]
        return rows[:max(1, min(limit, 200))]

    def event(self, event_id: str) -> dict[str, Any] | None:
        return next((row for row in self.overview().get("feed") or [] if row.get("id") == event_id), None)

    def status(self) -> dict[str, Any]:
        payload = self.overview()
        return {
            "quickIntervalSeconds": QUICK_INTERVAL_SECONDS, "rssIntervalSeconds": RSS_INTERVAL_SECONDS,
            "generatedAt": payload.get("generatedAt"), "stale": payload.get("stale", False),
            "sources": payload.get("sourceStatus") or [],
        }


class FinancialNewsScheduler:
    def __init__(self, service: FinancialNewsService):
        self.service = service
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        def run() -> None:
            next_quick = next_rss = 0.0
            while True:
                current = time.monotonic()
                if current >= next_quick:
                    self.service.refresh_quick()
                    next_quick = current + QUICK_INTERVAL_SECONDS
                if current >= next_rss:
                    self.service.refresh_rss()
                    next_rss = current + RSS_INTERVAL_SECONDS
                time.sleep(5)

        threading.Thread(target=run, name="financial-news-scheduler", daemon=True).start()
