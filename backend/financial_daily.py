"""Dual-edition Financial Daily engine with 30-day 3-tier event tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from data_paths import cache_path
from financial_editorial import financial_topic, headline, independent_sources, is_roundup, origin_owner
from financial_news_store import FinancialNewsStore, _normalize_url, _parse, _report_key
from financial_official import OfficialNewsFetcher
from source_registry import load_registry, source_grade, source_tier

logger = logging.getLogger(__name__)

UTC = timezone.utc
SHANGHAI = timezone(timedelta(hours=8))
PROMPT_VERSION = "financial-daily-v1"
TRACKED_WINDOW_DAYS = 30
EDITION_MEMORY_DAYS = 7

FINANCE_BUCKETS: tuple[dict[str, str], ...] = (
    {"key": "macro", "code": "01", "name": "宏观与政策", "note": "聚焦央行、财政、通胀与重要监管落地"},
    {"key": "china", "code": "02", "name": "国内与 A 股", "note": "聚焦交易所监管、行业动态与龙头公告"},
    {"key": "global", "code": "03", "name": "海外与重点公司", "note": "聚焦美港股核心财报、指引与跨国大事"},
    {"key": "tech", "code": "04", "name": "产业与科技", "note": "聚焦 AI 算力、半导体、新能源与医药进展"},
    {"key": "commodities", "code": "05", "name": "大宗与汇率", "note": "聚焦原油、黄金、美债与主要汇率波动"},
)
_BUCKET_BY_KEY = {row["key"]: row for row in FINANCE_BUCKETS}

_NON_ADVISORY_RE = re.compile(r"买入建议|强烈推荐|目标价|必涨|抄底|建议买入|建议卖出|重仓买入|坚决看多|逢低买入")
_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?")

_ASHARE_WRAP_RE = re.compile(r"A股(?:午评|收评|早评|三大股指|开盘|收盘)|沪指|深成指|创业板指|科创50|北证50", re.I)
_NOISE_RE = re.compile(
    r"在互动平台表示|互动平台回复|投资者互动平台|互动易回复|回复投资者提问|董秘回复|"
    r"盘前必读|早盘必读|操盘必读|午间公告一览|晚间公告一览|热点前瞻|一周综述|每日复盘汇总",
    re.I,
)
_CLICKBAIT_RE = re.compile(
    r"100%！|刚刚！.*突发|突发！.*大消息|重磅！.*大消息|发生了什么？|惊天|炸裂|史诗级|太猛了|暴涨预警|华尔街之狼",
    re.I,
)
_MACRO_RE = re.compile(
    r"央行|美联储|欧央行|利率|降息|加息|降准|LPR|MLF|逆回购|财政部|发改委|国新办|国务院|"
    r"通胀|CPI|PPI|PCE|PMI|GDP|非农|失业率|关税|贸易|国债|货币政策|fomc|fed|ecb|inflation|tariff|treasury|"
    r"对外直接投资|外贸|进出口|社融|M2|社会消费品零售|工业增加值",
    re.I,
)
_COMMODITY_FX_RE = re.compile(
    r"原油|油价|布伦特|WTI|黄金|白银|铜价|铝|碳酸锂|天然气|煤炭|铁矿石|"
    r"汇率|人民币汇率|离岸人民币|在岸人民币|美元兑人民币|人民币兑美元|中间价|外汇|"
    r"美元指数|欧元|日元|美债收益率|brent|crude|oil price|gold|copper|forex|currency",
    re.I,
)
_TECH_RE = re.compile(
    r"AI|人工智能|大模型|算力|芯片|半导体|晶圆|光刻|液冷|光模块|储能|电池|光伏|创新药|生物医药|"
    r"机器人|自动驾驶|火箭|航天|semiconductor|foundry|chip|2nm|data cent(?:er|re)|inference|gpu",
    re.I,
)
_CHINA_RE = re.compile(
    r"A股|沪指|深成指|创业板|科创板|北交所|上交所|深交所|证监会|巨潮|互动易|两融|涨停|跌停|"
    r"并购重组|分红|回购|排产|中标|央企|国企|\b[0368]\d{5}\b",
    re.I,
)
_GLOBAL_RE = re.compile(
    r"美股|纳指|标普|道指|港股|恒生|SEC|港交所|Form\s*8-K|财报|营收|净利润|季度业绩|交付目标|"
    r"苹果|微软|英伟达|谷歌|亚马逊|特斯拉|Meta|Apple|Nvidia|Microsoft|Amazon|Google|Tesla|SEC",
    re.I,
)

_ENTITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pboc", ("中国人民银行", "中国央行", "央行", "pboc")),
    ("fed", ("美联储", "federal reserve", "fomc", "fed")),
    ("ecb", ("欧央行", "欧洲央行", "ecb", "european central bank")),
    ("boj", ("日本央行", "日央行", "bank of japan", "boj")),
    ("csrc", ("证监会", "csrc")),
    ("sse", ("上交所", "上海证券交易所", "sse")),
    ("szse", ("深交所", "深圳证券交易所", "szse")),
    ("ndrc", ("发改委", "国家发展改革委", "ndrc")),
    ("mof", ("财政部",)),
    ("miit", ("工信部", "工业和信息化部", "miit")),
    ("sec", ("sec", "form 8-k", "form 10-k")),
    ("trump", ("特朗普", "trump", "donald trump")),
    ("tariff", ("关税", "tariff", "tariffs")),
    ("huawei", ("华为", "huawei")),
    ("us_trade", ("美国商务部", "贸易战", "trading partners", "major economies")),
    ("nvidia", ("英伟达", "nvidia", "nvda")),
    ("apple", ("苹果", "apple", "aapl")),
    ("microsoft", ("微软", "microsoft", "msft")),
    ("google", ("谷歌", "alphabet", "google", "googl")),
    ("amazon", ("亚马逊", "amazon", "amzn")),
    ("meta", ("meta", "facebook")),
    ("tesla", ("特斯拉", "tesla", "tsla")),
    ("tsmc", ("台积电", "tsmc")),
    ("alibaba", ("阿里巴巴", "阿里", "alibaba", "baba")),
    ("tencent", ("腾讯", "tencent")),
    ("bytedance", ("字节跳动", "bytedance", "tiktok")),
    ("openai", ("openai", "chatgpt")),
    ("xiaomi", ("小米", "xiaomi")),
    ("byd", ("比亚迪", "byd")),
    ("catl", ("宁德时代", "catl")),
    ("gold", ("黄金", "金价", "gold")),
    ("oil", ("原油", "布伦特", "wti", "brent", "crude")),
    ("boe", ("英国央行", "bank of england", "boe")),
    ("rrr", ("降准", "存款准备金率", "rrr")),
    ("cpi", ("cpi", "通胀", "inflation", "pce")),
    ("pmi", ("pmi", "制造业pmi")),
)

_S_SOURCES = {"中国人民银行", "证监会", "上交所", "深交所", "巨潮资讯", "互动易", "SEC", "Federal Reserve", "European Central Bank", "中国政府网", "工业和信息化部"}
_A_SOURCES = {
    "财联社电报", "财联社", "同花顺快讯", "东方财富快讯", "新浪财经快讯",
    "新华社", "中新网财经", "BBC财经", "Guardian Business", "CNBC",
    "Financial Times", "WSJ Markets", "华尔街见闻", "MarketWatch",
    "Seeking Alpha", "经济观察网", "东方财富 RSS",
}
_QUICK_SOURCES = {"财联社电报", "同花顺快讯", "东方财富快讯", "新浪财经快讯"}
_FINANCE_INDUSTRY_HINTS = {"macro", "semi", "energy", "ai", "auto", "bio", "tech"}


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("http://", "https://")) else ""


def _normalized(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def _bigrams(text: str) -> set[str]:
    norm = _normalized(text)
    if len(norm) < 2:
        return {norm} if norm else set()
    return {norm[i:i + 2] for i in range(len(norm) - 1)}


def _dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return (2.0 * len(a & b)) / (len(a) + len(b))


def extract_entities(title: str, summary: str = "") -> set[str]:
    blob = f"{title} {summary[:400]}".lower()
    found: set[str] = set()
    for canonical, aliases in _ENTITY_ALIASES:
        if any(alias in blob for alias in aliases):
            found.add(canonical)
    for code in re.findall(r"(?<!\d)[0368]\d{5}(?!\d)", blob):
        found.add(f"stk:{code}")
    for num in re.findall(r"\d+(?:\.\d+)?%|\d+bp|\d+nm", blob):
        found.add(f"num:{num}")
    return found


def classify_bucket(title: str, summary: str = "", track: str = "", source: str = "") -> str:
    blob = f"{title} {summary[:300]}"
    if _ASHARE_WRAP_RE.search(title):
        return "china"
    if _COMMODITY_FX_RE.search(blob):
        return "commodities"
    if _MACRO_RE.search(blob) or source in {"中国人民银行", "Federal Reserve", "European Central Bank", "中国政府网", "国家统计局"}:
        return "macro"
    if _TECH_RE.search(blob) or track in {"AI / 大模型", "半导体 / 芯片", "生物医药 / 健康", "机器人 / 自动化", "航天 / 太空"}:
        return "tech"
    if _CHINA_RE.search(blob) or source in {"证监会", "上交所", "深交所", "巨潮资讯", "互动易"}:
        return "china"
    if _GLOBAL_RE.search(blob) or source in {"SEC", "CNBC", "Financial Times", "WSJ Markets", "MarketWatch", "Seeking Alpha", "Guardian Business", "BBC财经"}:
        return "global"
    if track in {"汽车 / 新能源车", "能源 / 新能源"}:
        return "tech"
    return "china"


def _effective_grade(report: dict[str, Any], registry: dict[str, Any]) -> str:
    source = str(report.get("source") or "")
    if report.get("official") or source in _S_SOURCES:
        return "S"
    grade = str(report.get("sourceLevel") or source_grade(source, registry) or "C").upper()
    if grade in {"S", "A", "B", "C"}:
        return grade
    if source in _A_SOURCES:
        return "A"
    return "C"


def _has_market_relevance(report: dict[str, Any]) -> bool:
    title = str(report.get("title") or "")
    summary = str(report.get("summary") or "")
    if not title or is_roundup(title):
        return False
    if _NOISE_RE.search(title) or _NOISE_RE.search(summary[:200]):
        return False
    if financial_topic(report) is not None:
        return True
    blob = f"{title} {summary[:300]}"
    return bool(_MACRO_RE.search(blob) or _COMMODITY_FX_RE.search(blob) or _TECH_RE.search(blob) or _CHINA_RE.search(blob) or _GLOBAL_RE.search(blob))


def _passes_guardrails(text: str, source_corpus: str) -> bool:
    if not text or _NON_ADVISORY_RE.search(text):
        return False
    generated_nums = set(_NUMERIC_TOKEN_RE.findall(text))
    allowed_nums = set(_NUMERIC_TOKEN_RE.findall(source_corpus))
    return not bool(generated_nums - allowed_nums)


def _format_beijing(iso_value: str | None) -> str:
    dt = _parse(iso_value)
    if not dt:
        return "时间待定"
    return dt.astimezone(SHANGHAI).strftime("%m月%d日 %H:%M")


def _relative_time(iso_value: str | None, now: datetime) -> str:
    dt = _parse(iso_value)
    if not dt:
        return "近期"
    diff = max(0, int((now.astimezone(UTC) - dt.astimezone(UTC)).total_seconds()))
    if diff < 3600:
        return f"{max(1, diff // 60)} 分钟前"
    if diff < 86400:
        return f"{diff // 3600} 小时前"
    return f"{diff // 86400} 天前"


class FinancialDailyService:
    """Orchestrates unified financial ingestion, 30-day event tracking, and dual editions."""

    def __init__(
        self,
        news_service: Any,
        *,
        official_fetcher: OfficialNewsFetcher | None = None,
        market_review_service: Any = None,
        global_indices_fn: Callable[[], list[dict[str, Any]]] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        llm_call: Callable[[list[dict[str, str]]], Any] | None = None,
        config_loader: Callable[[], dict[str, str]] | None = None,
    ):
        self.news_service = news_service
        self.store: FinancialNewsStore = news_service.store
        self.registry: dict[str, Any] = getattr(news_service, "registry", None) or load_registry()
        self.official_fetcher = official_fetcher or OfficialNewsFetcher(
            cache_dir=getattr(news_service, "cache_dir", cache_path("financial-news")),
            registry=self.registry,
        )
        self.market_review_service = market_review_service
        self.global_indices_fn = global_indices_fn
        self.now_fn = now_fn or (lambda: datetime.now(SHANGHAI))
        self.llm_call = llm_call
        self.config_loader = config_loader
        self._lock = threading.RLock()

    def _call_llm_json(self, system_prompt: str, user_prompt: str) -> Any:
        if self.llm_call is not None:
            raw = self.llm_call([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
        else:
            import chat
            import glm_config
            loader = self.config_loader or glm_config.load_glm_config
            cfg = loader()
            if not cfg.get("apiKey"):
                return None
            resp = chat._call_llm(
                cfg,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                use_tools=False,
                timeout_seconds=120,
            )
            raw = resp["choices"][0]["message"].get("content") or ""
        if isinstance(raw, (dict, list)):
            return raw
        cleaned = re.sub(r"^```(?:json)?|```$", "", str(raw).strip(), flags=re.I | re.M).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            candidates: list[tuple[int, str]] = []
            for start_ch, end_ch in (("[", "]"), ("{", "}")):
                start = cleaned.find(start_ch)
                end = cleaned.rfind(end_ch)
                if start != -1 and end > start:
                    candidates.append((start, end_ch))
            candidates.sort(key=lambda item: item[0])
            for start, end_ch in candidates:
                end = cleaned.rfind(end_ch)
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    continue
            raise

    def _hotlist_index(self) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        overview = self.news_service.overview() or {}
        hot_rank = overview.get("hotRank") or []
        hot_status = overview.get("hotRankSourceStatus") or []
        by_norm_title: dict[str, dict[str, Any]] = {}
        for row in hot_rank:
            info = {
                "rank": int(row.get("rank") or 10),
                "platformCount": int(row.get("platformCount") or 1),
                "rankScore": float(row.get("rankScore") or 0),
                "placements": row.get("placements") or [],
            }
            norm = _normalized(headline(str(row.get("title") or "")))
            if norm:
                by_norm_title[norm] = info
            for pl in info["placements"]:
                pl_norm = _normalized(headline(str(pl.get("title") or "")))
                if pl_norm:
                    by_norm_title[pl_norm] = info
        return by_norm_title, hot_status

    def _collect_unified_pool(self, *, refresh_upstream: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if refresh_upstream:
            try:
                self.news_service.refresh_hotlists(force=True)
            except Exception:  # noqa: BLE001
                logger.exception("hotlist refresh failed during daily refresh")
            try:
                self.news_service.refresh_rss()
            except Exception:  # noqa: BLE001
                logger.exception("rss refresh failed during daily refresh")
            try:
                self.news_service.refresh_quick()
            except Exception:  # noqa: BLE001
                logger.exception("quick refresh failed during daily refresh")
            official_payload = self.official_fetcher.fetch()
        else:
            official_payload = self.official_fetcher.load_cached()
            if not official_payload.get("reports"):
                try:
                    official_payload = self.official_fetcher.fetch()
                except Exception:  # noqa: BLE001
                    official_payload = {"reports": [], "sourceStatus": []}

        # Gather existing rolling reports from SQLite + official HTML reports + hotlist items
        rolling_reports = self.store.load_reports(hours=72)
        official_reports = list(official_payload.get("reports") or [])
        hot_by_title, hot_status = self._hotlist_index()

        # Also materialize hotlist items as candidate reports if missing from rolling pool
        hotlist_reports: list[dict[str, Any]] = []
        overview = self.news_service.overview() or {}
        for item in overview.get("hotRank") or []:
            for pl in item.get("placements") or []:
                url = _safe_http_url(pl.get("originalUrl"))
                title = str(pl.get("title") or item.get("title") or "").strip()
                if not url or not title:
                    continue
                src_name = str(pl.get("sourceName") or "平台头条")
                hotlist_reports.append({
                    "title": title,
                    "summary": str(pl.get("summary") or title),
                    "publishedAt": pl.get("publishedAt") or item.get("publishedAt"),
                    "source": src_name,
                    "sourceTier": source_tier(src_name, self.registry),
                    "sourceLevel": source_grade(src_name, self.registry),
                    "originalUrl": url,
                    "category": classify_bucket(title),
                    "official": False,
                    "rumor": False,
                    "stale": bool(item.get("stale")),
                })

        combined_raw = official_reports + rolling_reports + hotlist_reports
        deduped: dict[str, dict[str, Any]] = {}
        for raw in combined_raw:
            url = _safe_http_url(raw.get("originalUrl") or raw.get("url"))
            title = str(raw.get("title") or "").strip()
            if not title or not url:
                continue
            item = dict(raw)
            item["originalUrl"] = url
            item["title"] = title
            item["summary"] = str(item.get("summary") or title).strip()
            item["source"] = str(item.get("source") or "公开来源").strip()
            item["sourceLevel"] = _effective_grade(item, self.registry)
            item["sourceTier"] = int(item.get("sourceTier") or source_tier(item["source"], self.registry))
            item["bucket"] = classify_bucket(title, item["summary"], str(item.get("track") or ""), item["source"])
            rkey = _report_key(item)
            item["reportKey"] = rkey
            item["id"] = rkey

            # Attach hotlist signal if matched
            norm = _normalized(headline(title))
            hot_info = hot_by_title.get(norm)
            if not hot_info and norm:
                bg = _bigrams(norm)
                for h_norm, h_val in hot_by_title.items():
                    if _dice(bg, _bigrams(h_norm)) >= 0.72:
                        hot_info = h_val
                        break
            if hot_info:
                item["hotlistSignal"] = hot_info

            if rkey not in deduped or (item.get("official") and not deduped[rkey].get("official")):
                deduped[rkey] = item

        # Persist merged reports into SQLite so Level 2 detail queries always find them
        reports_list = list(deduped.values())
        if reports_list:
            self.store.upsert_reports(reports_list)

        # Combine source health statuses
        news_status = list(overview.get("sourceStatus") or [])
        all_statuses = list(official_payload.get("sourceStatus") or []) + list(hot_status) + news_status
        return reports_list, all_statuses

    def admit_report(self, report: dict[str, Any], *, corroborating_count: int = 1, matches_active_story: bool = False) -> bool:
        if not _safe_http_url(report.get("originalUrl")):
            return False
        if not _has_market_relevance(report):
            return False
        if _CLICKBAIT_RE.search(str(report.get("title") or "")) and not report.get("official") and corroborating_count < 2:
            return False
        grade = str(report.get("sourceLevel") or "C").upper()
        if report.get("official") or grade == "S":
            return True
        if grade == "A" and str(report.get("source") or "") not in _QUICK_SOURCES:
            return True
        if report.get("hotlistSignal") or matches_active_story:
            return True
        return corroborating_count >= 2

    def _recall_candidates(
        self,
        report: dict[str, Any],
        active_stories: list[dict[str, Any]],
        *,
        allow_weak: bool = False,
    ) -> list[dict[str, Any]]:
        entities = extract_entities(report["title"], report.get("summary", ""))
        bg = _bigrams(headline(report["title"]))
        scored: list[tuple[float, dict[str, Any]]] = []
        for story in active_stories:
            story_entities = extract_entities(story["title"])
            for m in story.get("milestones") or []:
                story_entities |= extract_entities(m.get("title") or "")
            ent_overlap = len(entities & story_entities)
            title_sim = _dice(bg, _bigrams(headline(story["title"])))
            for m in story.get("milestones") or []:
                title_sim = max(title_sim, _dice(bg, _bigrams(headline(m.get("title") or ""))))
            score = ent_overlap * 0.35 + title_sim
            strong_match = ent_overlap >= 2 or title_sim >= 0.34 or (ent_overlap >= 1 and title_sim >= 0.2)
            weak_match = allow_weak and ent_overlap >= 1 and story.get("bucket") == report.get("bucket")
            if strong_match or weak_match:
                scored.append((score, story))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [story for _, story in scored[:6]]

    def _classify_story_links(
        self,
        new_reports: list[dict[str, Any]],
        active_stories: list[dict[str, Any]],
        *,
        allow_llm: bool,
    ) -> dict[str, dict[str, Any]]:
        """Decide SAME_NODE / NEW_NODE / NEW_STORY for candidate reports."""
        decisions: dict[str, dict[str, Any]] = {}
        batch_for_llm: list[dict[str, Any]] = []

        for rep in new_reports:
            candidates = self._recall_candidates(rep, active_stories, allow_weak=allow_llm)
            if not candidates:
                decisions[rep["reportKey"]] = {"action": "NEW_STORY"}
                continue

            rep_bg = _bigrams(headline(rep["title"]))
            rep_dt = _parse(rep.get("publishedAt"))
            best_story = candidates[0]
            best_ms = None
            best_sim = 0.0
            for ms in best_story.get("milestones") or []:
                sim = _dice(rep_bg, _bigrams(headline(ms.get("title") or "")))
                if sim > best_sim:
                    best_sim = sim
                    best_ms = ms

            if best_ms and best_sim >= 0.62:
                ms_dt = _parse(best_ms.get("occurredAt"))
                if not rep_dt or not ms_dt or abs((rep_dt - ms_dt).total_seconds()) <= 18 * 3600:
                    decisions[rep["reportKey"]] = {
                        "action": "SAME_NODE",
                        "storyId": best_story["storyId"],
                        "milestoneId": best_ms["milestoneId"],
                    }
                    continue

            if allow_llm:
                batch_for_llm.append({
                    "reportKey": rep["reportKey"],
                    "title": rep["title"],
                    "summary": rep["summary"][:240],
                    "publishedAt": rep.get("publishedAt"),
                    "candidates": [
                        {
                            "storyId": st["storyId"],
                            "title": st["title"],
                            "milestones": [
                                {"milestoneId": m["milestoneId"], "title": m["title"], "occurredAt": m["occurredAt"]}
                                for m in (st.get("milestones") or [])[:4]
                            ],
                        }
                        for st in candidates[:4]
                    ],
                })
            else:
                # Deterministic fallback: shared entity/topic with >12h delta or distinct title -> NEW_NODE
                if best_ms and best_sim >= 0.34:
                    decisions[rep["reportKey"]] = {
                        "action": "NEW_NODE",
                        "storyId": best_story["storyId"],
                    }
                else:
                    decisions[rep["reportKey"]] = {"action": "NEW_STORY"}

        if allow_llm and batch_for_llm:
            try:
                rows = self._call_llm_json(
                    "你是财经事件归类助手。只根据提供标题、摘要和候选事件返回 JSON 数组，不得编造 ID。",
                    (
                        "请判断每条新报道属于已有事件的同节点补充(SAME_NODE)、同事件新进展节点(NEW_NODE)，还是全新事件(NEW_STORY)。"
                        "返回严格 JSON 数组，每项字段：reportKey, action (SAME_NODE|NEW_NODE|NEW_STORY), storyId(可选), milestoneId(仅SAME_NODE必填)：\n"
                        + json.dumps(batch_for_llm[:25], ensure_ascii=False)
                    ),
                )
                valid_stories = {st["storyId"]: {m["milestoneId"] for m in st.get("milestones") or []} for st in active_stories}
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        rkey = str(row.get("reportKey") or "")
                        action = str(row.get("action") or "")
                        sid = str(row.get("storyId") or "")
                        mid = str(row.get("milestoneId") or "")
                        if rkey and action == "SAME_NODE" and sid in valid_stories and mid in valid_stories[sid]:
                            decisions[rkey] = {"action": "SAME_NODE", "storyId": sid, "milestoneId": mid}
                        elif rkey and action == "NEW_NODE" and sid in valid_stories:
                            decisions[rkey] = {"action": "NEW_NODE", "storyId": sid}
                        elif rkey and action == "NEW_STORY":
                            decisions[rkey] = {"action": "NEW_STORY"}
            except Exception:  # noqa: BLE001
                logger.exception("batch story linking llm failed; falling back to deterministic rules")

        for rep in new_reports:
            if rep["reportKey"] not in decisions:
                candidates = self._recall_candidates(rep, active_stories)
                if candidates:
                    decisions[rep["reportKey"]] = {"action": "NEW_NODE", "storyId": candidates[0]["storyId"]}
                else:
                    decisions[rep["reportKey"]] = {"action": "NEW_STORY"}
        return decisions

    def ingest_to_stories(self, reports: list[dict[str, Any]], *, allow_llm: bool = False) -> list[dict[str, Any]]:
        """Admit and cluster financial reports into 30-day 3-tier tracked stories."""
        with self._lock:
            now_dt = self.now_fn().astimezone(UTC)
            active_stories = self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)
            known_report_keys = {
                rep["reportKey"]
                for st in active_stories
                for rep in st.get("reports") or []
            }

            # Count independent source corroboration across the incoming batch
            title_groups: dict[str, list[dict[str, Any]]] = {}
            for rep in reports:
                norm = _normalized(headline(rep["title"]))
                title_groups.setdefault(norm, []).append(rep)

            admitted: list[dict[str, Any]] = []
            for rep in sorted(reports, key=lambda r: r.get("publishedAt") or "", reverse=True):
                norm = _normalized(headline(rep["title"]))
                peers = title_groups.get(norm) or [rep]
                indep_count = len(independent_sources(peers))
                matches_active = bool(self._recall_candidates(rep, active_stories))
                if not self.admit_report(rep, corroborating_count=indep_count, matches_active_story=matches_active):
                    continue
                if rep["reportKey"] in known_report_keys:
                    # Still refresh heat signal if newly seen
                    continue
                admitted.append(rep)

            if admitted:
                decisions = self._classify_story_links(admitted, active_stories, allow_llm=allow_llm)
                for rep in admitted:
                    rkey = rep["reportKey"]
                    dec = decisions.get(rkey) or {"action": "NEW_STORY"}
                    action = dec["action"]
                    sid = str(dec.get("storyId") or "")
                    published_iso = rep.get("publishedAt") or now_dt.isoformat()
                    owner = origin_owner(rep)
                    grade = _effective_grade(rep, self.registry)
                    role = "primary" if rep.get("official") or grade == "S" else "report"

                    if action == "SAME_NODE" and dec.get("storyId") and dec.get("milestoneId"):
                        sid = dec["storyId"]
                        mid = dec["milestoneId"]
                        self.store.link_milestone_report(milestone_id=mid, story_id=sid, report_key=rkey, role=role)
                        self.store.upsert_tracked_story(
                            story_id=sid,
                            title=next((s["title"] for s in active_stories if s["storyId"] == sid), rep["title"]),
                            bucket=rep["bucket"],
                            latest_at=published_iso,
                        )
                    elif action == "NEW_NODE" and dec.get("storyId"):
                        sid = dec["storyId"]
                        mid = "ms-" + hashlib.sha1(f"{sid}:{rkey}".encode("utf-8")).hexdigest()[:12]
                        self.store.upsert_milestone(
                            milestone_id=mid,
                            story_id=sid,
                            title=headline(rep["title"]),
                            occurred_at=published_iso,
                            representative_report_key=rkey,
                            market_note="",
                            report_count=1,
                        )
                        self.store.link_milestone_report(milestone_id=mid, story_id=sid, report_key=rkey, role=role)
                        self.store.upsert_tracked_story(
                            story_id=sid,
                            title=headline(rep["title"]) if grade == "S" else next((s["title"] for s in active_stories if s["storyId"] == sid), rep["title"]),
                            bucket=rep["bucket"],
                            latest_at=published_iso,
                        )
                    else:
                        sid = "st-" + hashlib.sha1(f"{rep['bucket']}:{headline(rep['title'])}".encode("utf-8")).hexdigest()[:12]
                        mid = "ms-" + hashlib.sha1(f"{sid}:{rkey}".encode("utf-8")).hexdigest()[:12]
                        tags = list(dict.fromkeys([_BUCKET_BY_KEY[rep["bucket"]]["name"], *(f"股票 {c}" for c in rep.get("relatedStocks") or [])]))[:4]
                        self.store.upsert_tracked_story(
                            story_id=sid,
                            title=headline(rep["title"]),
                            bucket=rep["bucket"],
                            first_report_at=published_iso,
                            latest_at=published_iso,
                            tags=tags,
                        )
                        self.store.upsert_milestone(
                            milestone_id=mid,
                            story_id=sid,
                            title=headline(rep["title"]),
                            occurred_at=published_iso,
                            representative_report_key=rkey,
                            market_note="",
                            report_count=1,
                        )
                        self.store.link_milestone_report(milestone_id=mid, story_id=sid, report_key=rkey, role=role)
                        # Refresh active_stories in memory so subsequent reports in same batch can cluster onto it
                        new_st = self.store.get_tracked_story(sid)
                        if new_st:
                            active_stories.insert(0, new_st)

                    self.store.record_signal(
                        story_id=dec.get("storyId") or sid,
                        participant_key=owner.lower(),
                        source_name=owner,
                        source_tier=grade,
                        kind="official" if rep.get("official") else "editorial",
                        observed_at=published_iso,
                    )

            self.store.prune_tracked(days=TRACKED_WINDOW_DAYS)
            return self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)

    def compute_heat_and_why_hot(self, story: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or self.now_fn()).astimezone(UTC)
        signals = story.get("signals") or []
        latest_by_participant: dict[str, tuple[datetime, dict[str, Any]]] = {}
        first_by_participant: dict[str, datetime] = {}

        for sig in signals:
            pkey = str(sig.get("participant_key") or sig.get("source_name") or "").lower()
            obs = _parse(sig.get("observed_at"))
            if not pkey or not obs:
                continue
            age_hours = (current - obs).total_seconds() / 3600.0
            if age_hours < -0.25 or age_hours > 48.0:
                continue
            prev = latest_by_participant.get(pkey)
            if prev is None or obs > prev[0]:
                latest_by_participant[pkey] = (obs, sig)
            prev_first = first_by_participant.get(pkey)
            if prev_first is None or obs < prev_first:
                first_by_participant[pkey] = obs

        heat_sum = 0.0
        official_sources: set[str] = set()
        new_6h = 0
        for pkey, (obs, sig) in latest_by_participant.items():
            age_h = max(0.0, (current - obs).total_seconds() / 3600.0)
            heat_sum += 0.5 ** (age_h / 24.0)
            if sig.get("source_tier") == "S" or sig.get("kind") == "official":
                official_sources.add(str(sig.get("source_name") or pkey))
            first_obs = first_by_participant.get(pkey)
            if first_obs and (current - first_obs).total_seconds() <= 6 * 3600:
                new_6h += 1

        participants_48h = len(latest_by_participant)
        heat_index = round(heat_sum * 100.0) / 10.0

        badges: list[str] = []
        if official_sources:
            badges.append(f"{len(official_sources)} 家官方机构")
        badges.append(f"{participants_48h} 个独立信源")

        return {
            "heatIndex": heat_index,
            "participants48h": participants_48h,
            "newParticipants6h": new_6h,
            "officialCount": len(official_sources),
            "headline": f"过去 48 小时，有 {participants_48h} 个独立信源报道或跟进了这件事，最近 6 小时新增 {new_6h} 个。",
            "detail": "统计已剔除同源重复转载，按发布时间与信源权威度客观计算。" if participants_48h else "当前处于早期收录阶段，暂无多源持续发酵。",
            "badges": badges,
        }

    def record_hourly_heat_snapshots(self) -> None:
        current = self.now_fn().astimezone(SHANGHAI)
        hour_key = current.strftime("%Y-%m-%d %H:00")
        for story in self.store.list_active_stories(days=TRACKED_WINDOW_DAYS):
            stats = self.compute_heat_and_why_hot(story, now=current.astimezone(UTC))
            if stats["participants48h"] <= 0:
                continue
            latest_ms = (story.get("milestones") or [{}])[0]
            ms_dt = _parse(latest_ms.get("occurredAt"))
            ms_label = ""
            if ms_dt and abs((current.astimezone(UTC) - ms_dt).total_seconds()) <= 3600:
                ms_label = str(latest_ms.get("title") or "")[:32]
            self.store.upsert_heat_snapshot(
                story_id=story["storyId"],
                hour_key=hour_key,
                heat=stats["heatIndex"],
                participants=stats["participants48h"],
                milestone_label=ms_label,
            )

    def _build_heat_series(self, story: dict[str, Any]) -> list[dict[str, Any]]:
        stored = story.get("heatSeries") or []
        if len(stored) >= 2:
            return [
                {
                    "label": row["hourKey"][5:16],
                    "value": round(float(row["heat"]), 1),
                    "participants": row["participants"],
                    "milestone": row["milestoneLabel"],
                }
                for row in stored[-14:]
            ]
        # Construct deterministic day-level heat curve from milestone & signal timestamps
        by_day: dict[str, dict[str, Any]] = {}
        for m in reversed(story.get("milestones") or []):
            dt = _parse(m.get("occurredAt"))
            if not dt:
                continue
            day = dt.astimezone(SHANGHAI).strftime("%m/%d")
            entry = by_day.setdefault(day, {"label": day, "value": 0, "participants": 0, "milestone": ""})
            entry["value"] += max(12, int(m.get("reportCount") or 1) * 14)
            entry["participants"] += max(1, int(m.get("reportCount") or 1))
            if not entry["milestone"]:
                entry["milestone"] = str(m.get("title") or "")[:26]
        for sig in story.get("signals") or []:
            dt = _parse(sig.get("observed_at"))
            if not dt:
                continue
            day = dt.astimezone(SHANGHAI).strftime("%m/%d")
            if day in by_day:
                by_day[day]["value"] += 8
        return list(by_day.values())[-7:]

    def _prepare_event_overview(self, story: dict[str, Any], *, allow_llm: bool) -> tuple[dict[str, Any], str, bool]:
        milestones = story.get("milestones") or []
        reports = story.get("reports") or []
        corpus_material = [
            {
                "id": r.get("reportKey"),
                "title": r.get("title"),
                "summary": (r.get("summary") or "")[:240],
                "source": r.get("source"),
                "publishedAt": r.get("publishedAt"),
            }
            for r in reports[:24]
        ]
        inputs_hash = hashlib.sha1(json.dumps(corpus_material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        existing_overview = story.get("overview") or {}
        if existing_overview.get("paragraphs") and story.get("overviewInputsHash") == inputs_hash:
            return existing_overview, inputs_hash, False

        latest_ms = milestones[0] if milestones else {}
        latest_line = f"{_format_beijing(latest_ms.get('occurredAt'))} · {latest_ms.get('title', story['title'])}" if latest_ms else ""
        fallback = {
            "paragraphs": [
                str(r.get("summary") or r.get("title"))
                for r in sorted(reports, key=lambda item: item.get("publishedAt") or "", reverse=True)[:2]
                if r.get("summary") or r.get("title")
            ] or [story["title"]],
            "latestMilestoneSummary": latest_line,
            "generatedBy": "rule",
        }

        if not allow_llm or not reports:
            return fallback, inputs_hash, True

        source_corpus = " ".join(f"{r.get('title', '')} {r.get('summary', '')}" for r in reports)
        prev_paragraphs = existing_overview.get("paragraphs") or []
        try:
            prompt_payload = {
                "eventTitle": story["title"],
                "previousOverview": prev_paragraphs if prev_paragraphs else None,
                "milestones": [{"time": _format_beijing(m.get("occurredAt")), "title": m.get("title")} for m in milestones[:8]],
                "reports": corpus_material[:15],
            }
            res = self._call_llm_json(
                "你是客观财经编辑。只能概括输入报道中已核实的事实，不得补充外部数字、原因或投资建议。",
                (
                    "请为该财经事件生成「先了解这件事」的客观概览，返回严格 JSON 对象："
                    '{"paragraphs": ["100-180字事实总结段1", "可选补充段2"], "latestMilestoneSummary": "一句最新进展"}。'
                    "不得出现输入里没有的数字，不得预测涨跌或给出买卖建议：\n"
                    + json.dumps(prompt_payload, ensure_ascii=False)
                ),
            )
            if isinstance(res, dict) and isinstance(res.get("paragraphs"), list):
                paras = [str(p).strip() for p in res["paragraphs"] if isinstance(p, str) and p.strip()][:3]
                latest_sum = str(res.get("latestMilestoneSummary") or latest_line).strip()
                joined = " ".join(paras + [latest_sum])
                if paras and _passes_guardrails(joined, source_corpus):
                    overview = {"paragraphs": paras, "latestMilestoneSummary": latest_sum, "generatedBy": "glm"}
                    return overview, inputs_hash, True
        except Exception:  # noqa: BLE001
            logger.exception("event overview generation failed; using factual fallback")

        return fallback, inputs_hash, True

    def _ensure_event_overview(self, story: dict[str, Any], *, allow_llm: bool) -> dict[str, Any]:
        overview, inputs_hash, changed = self._prepare_event_overview(story, allow_llm=allow_llm)
        if changed:
            self.store.update_tracked_overview(story["storyId"], overview, inputs_hash)
        return overview

    def _rule_candidate_score(self, story: dict[str, Any], rep: dict[str, Any], now_dt: datetime) -> float:
        grade = _effective_grade(rep, self.registry)
        grade_pts = {"S": 35.0, "A": 26.0, "B": 16.0, "C": 8.0}.get(grade, 8.0)
        pub = _parse(rep.get("publishedAt"))
        age_h = max(0.0, (now_dt - pub).total_seconds() / 3600.0) if pub else 24.0
        recency_pts = max(0.0, 25.0 - age_h * 1.1)
        indep_count = len(independent_sources(story.get("reports") or [rep]))
        hot_bonus = 12.0 if rep.get("hotlistSignal") else 0.0
        clickbait_penalty = -25.0 if _CLICKBAIT_RE.search(str(rep.get("title") or "")) else 0.0
        return grade_pts + recency_pts + min(20.0, indep_count * 5.0) + hot_bonus + clickbait_penalty

    def _rerank_with_glm(self, candidates: list[dict[str, Any]], *, allow_llm: bool) -> tuple[dict[str, dict[str, Any]], bool]:
        scores: dict[str, dict[str, Any]] = {}
        cand_by_key: dict[str, dict[str, Any]] = {}
        for c in candidates:
            cand_by_key[c["reportKey"]] = c
            grade = c["sourceTierGrade"]
            ev_default = 5.0 if (c["official"] or grade == "S") else 3.5 if grade == "A" else 2.0
            br_default = 4.0 if c["bucket"] in {"macro", "commodities"} else 3.2
            nv_default = 4.0 if c["isNewMilestone"] else 2.5
            scores[c["reportKey"]] = {
                "breadth": br_default,
                "novelty": nv_default,
                "evidence": ev_default,
                "bucket": c["bucket"],
                "duplicateOf": "",
                "titleZh": "",
                "summaryZh": "",
            }

        if not allow_llm or not candidates:
            return scores, False

        compact = [
            {
                "reportKey": c["reportKey"],
                "bucket": c["bucket"],
                "title": c["title"][:120],
                "summary": c["summary"][:260],
                "source": c["sourceName"],
                "grade": c["sourceTierGrade"],
                "independentSources": c["independentCount"],
                "onHotlist": bool(c.get("hotlistSignal")),
            }
            for c in candidates[:60]
        ]
        llm_used = False
        try:
            rows = self._call_llm_json(
                "你是客观金融日报主编。只输出严格 JSON 数组，严格基于事实评估广度、增量与证据强度，翻译英文资讯，并识别跨媒体重复事件，严禁编造或给出投资建议。",
                (
                    "请为以下候选财经资讯逐条打分（breadth/novelty/evidence 各 0-5 分，可带一位小数），确认最贴切的板块 bucket"
                    "（macro|china|global|tech|commodities），并补充可选字段："
                    "duplicateOf（若与本批次另一条报道讲述同一具体新闻事件，填写更权威或更早那条的 reportKey，否则不填）、"
                    "titleZh（若原标题主要为英文则必填，译为客观简练中文标题并原样保留数字，不要换算单位或给出投资建议）、"
                    "summaryZh（若原摘要主要为英文则必填，译为客观一句中文事实摘要<=90字并原样保留数字）。"
                    "返回严格 JSON 数组，每项字段：reportKey, breadth, novelty, evidence, bucket, duplicateOf(可选), titleZh(可选), summaryZh(可选)：\n"
                    + json.dumps(compact, ensure_ascii=False)
                ),
            )
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    rkey = str(row.get("reportKey") or "")
                    if rkey not in scores:
                        continue
                    try:
                        breadth = max(0.0, min(5.0, float(row.get("breadth"))))
                        novelty = max(0.0, min(5.0, float(row.get("novelty"))))
                        evidence = max(0.0, min(5.0, float(row.get("evidence"))))
                    except (TypeError, ValueError):
                        continue
                    bucket = str(row.get("bucket") or scores[rkey]["bucket"])
                    if bucket not in _BUCKET_BY_KEY:
                        bucket = scores[rkey]["bucket"]
                    dup_of = str(row.get("duplicateOf") or "").strip()
                    if dup_of == rkey or dup_of not in cand_by_key:
                        dup_of = ""
                    cand = cand_by_key[rkey]
                    source_corpus = f"{cand['title']} {cand['summary']}"
                    title_zh = str(row.get("titleZh") or "").strip()
                    if title_zh and not _passes_guardrails(title_zh, source_corpus):
                        title_zh = ""
                    summary_zh = str(row.get("summaryZh") or "").strip()
                    if summary_zh and not _passes_guardrails(summary_zh, source_corpus):
                        summary_zh = ""
                    scores[rkey] = {
                        "breadth": breadth,
                        "novelty": novelty,
                        "evidence": evidence,
                        "bucket": bucket,
                        "duplicateOf": dup_of,
                        "titleZh": title_zh[:160] if title_zh else "",
                        "summaryZh": summary_zh[:220] if summary_zh else "",
                    }
                    llm_used = True
        except Exception:  # noqa: BLE001
            logger.exception("glm editorial rerank failed; using deterministic scores")
        return scores, llm_used

    def _build_market_strip(self, edition_type: str) -> dict[str, Any]:
        if edition_type == "evening" and self.market_review_service is not None:
            try:
                review = self.market_review_service.get_review() or {}
                indices = review.get("indices") or []
                liq = review.get("liquidity") or {}
                items = [
                    {
                        "name": row.get("name"),
                        "value": str(row.get("price") if row.get("price") is not None else "数据缺失"),
                        "change": (
                            f"{'+' if float(row['changePct']) > 0 else ''}{row['changePct']}%"
                            if row.get("changePct") is not None else "暂无"
                        ),
                        "direction": "up" if (row.get("changePct") or 0) > 0 else ("down" if (row.get("changePct") or 0) < 0 else "flat"),
                    }
                    for row in indices[:3]
                ]
                amt = liq.get("todayAmountYuan")
                chg_pct = liq.get("changePct")
                if amt is not None:
                    trillion = amt / 1e12
                    items.append({
                        "name": "两市成交额",
                        "value": f"{trillion:.2f} 万亿" if trillion >= 1 else f"{amt / 1e8:.0f} 亿",
                        "change": f"较前日 {'+' if (chg_pct or 0) > 0 else ''}{chg_pct}%" if chg_pct is not None else "成交额",
                        "direction": "flat",
                    })
                if items:
                    return {
                        "title": "当日收盘客观速览（联动每日复盘）",
                        "note": f"交易日 {review.get('tradingDate') or '最新'}",
                        "items": items,
                        "partial": bool(review.get("partial") or review.get("stale")),
                    }
            except Exception:  # noqa: BLE001
                logger.exception("failed to read market_review snapshot for evening daily")

        if edition_type == "morning" and self.global_indices_fn is not None:
            try:
                rows = self.global_indices_fn() or []
                items = [
                    {
                        "name": row.get("name"),
                        "value": str(row.get("price") if row.get("price") is not None else "暂缺"),
                        "change": (
                            f"{'+' if float(row['change_pct']) > 0 else ''}{row['change_pct']}%"
                            if row.get("change_pct") is not None else "数据暂缺"
                        ),
                        "direction": "up" if (row.get("change_pct") or 0) > 0 else ("down" if (row.get("change_pct") or 0) < 0 else "flat"),
                    }
                    for row in rows[:4]
                ]
                if items:
                    return {"title": "隔夜海外市场客观速览", "note": "截至早间出刊", "items": items, "partial": False}
            except Exception:  # noqa: BLE001
                logger.exception("failed to read global indices for morning daily")

        return {
            "title": "隔夜海外市场客观速览" if edition_type == "morning" else "当日收盘客观速览",
            "note": "部分行情快照暂未就绪，已跳过未核验数值",
            "items": [],
            "partial": True,
        }

    def _compose_overview(self, edition_type: str, lead: dict[str, Any] | None, picks: list[dict[str, Any]], *, allow_llm: bool) -> str:
        if not lead:
            return "本期暂无达到发布门槛的实质性金融要闻，仅展示已核验的未来官方日程与来源状态。"
        label = "早报" if edition_type == "morning" else "晚报"
        parts = [f"本期{label}头条关注「{lead['title']}」"]
        if picks:
            parts.append("；其余版面重点涵盖" + "、".join(p["sectionName"] + "方向的「" + p["title"] + "」" for p in picks[:3]))
        fallback = "".join(parts) + "。"
        if not allow_llm:
            return fallback

        corpus = " ".join([lead["title"], lead["summary"], *(p["title"] + " " + p["summary"] for p in picks)])
        try:
            res = self._call_llm_json(
                "你是金融日报主编，只用两三句客观白话导读本期主线。不得编造数字，不得预测涨跌，不得给出买卖建议。",
                (
                    "根据以下本期头条和3条看点，写出120-180字客观「本期导读」，返回 JSON {\"overview\": \"...\"}：\n"
                    + json.dumps({"lead": lead, "picks": picks}, ensure_ascii=False)
                ),
            )
            if isinstance(res, dict) and isinstance(res.get("overview"), str):
                text = res["overview"].strip()
                if text and len(text) <= 260 and _passes_guardrails(text, corpus):
                    return text
        except Exception:  # noqa: BLE001
            logger.exception("edition overview llm failed; using factual fallback")
        return fallback

    def compose_edition(
        self,
        *,
        edition_date: str | None = None,
        edition_type: str | None = None,
        refresh_upstream: bool = False,
        allow_llm: bool = True,
    ) -> dict[str, Any]:
        """Run 2-stage funnel + strict newspaper layout and persist edition archive."""
        with self._lock:
            now_bj = self.now_fn().astimezone(SHANGHAI)
            now_utc = now_bj.astimezone(UTC)
            target_date = edition_date or now_bj.strftime("%Y-%m-%d")
            target_type = edition_type if edition_type in {"morning", "evening"} else ("evening" if now_bj.hour >= 18 else "morning")
            edition_key = f"{target_date}-{target_type}"

            reports, source_statuses = self._collect_unified_pool(refresh_upstream=refresh_upstream)
            stories = self.ingest_to_stories(reports, allow_llm=allow_llm)

            # Collect milestone IDs already cited in prior 7 days to prevent stale repeats
            prior_milestone_ids: set[str] = set()
            for meta in self.store.list_daily_editions(limit=16):
                if meta["editionKey"] == edition_key:
                    continue
                prior_ed = self.store.get_daily_edition(meta["editionKey"])
                if not prior_ed:
                    continue
                if prior_ed.get("lead", {}) and prior_ed["lead"].get("milestoneId"):
                    prior_milestone_ids.add(prior_ed["lead"]["milestoneId"])
                for sec in prior_ed.get("sections") or []:
                    for st in sec.get("items") or []:
                        if st.get("milestoneId"):
                            prior_milestone_ids.add(st["milestoneId"])

            # Stage A: 5-bucket rule recall (up to 15 per bucket)
            bucket_pools: dict[str, list[dict[str, Any]]] = {row["key"]: [] for row in FINANCE_BUCKETS}
            for story in stories:
                milestones = story.get("milestones") or []
                if not milestones:
                    continue
                latest_ms = milestones[0]
                is_new_ms = latest_ms["milestoneId"] not in prior_milestone_ids
                ms_dt = _parse(latest_ms.get("occurredAt"))
                age_hours = ((now_utc - ms_dt).total_seconds() / 3600.0) if ms_dt else 24.0
                if age_hours > 48.0:
                    continue
                if not is_new_ms and age_hours > 18.0:
                    continue
                rep = next(
                    (r for r in (latest_ms.get("reports") or []) if r.get("reportKey") == latest_ms.get("representativeReportKey")),
                    (latest_ms.get("reports") or [None])[0],
                )
                if not rep or not _safe_http_url(rep.get("originalUrl")):
                    continue
                indep_count = len(independent_sources(story.get("reports") or [rep]))
                grade = _effective_grade(rep, self.registry)
                cand = {
                    "reportKey": rep["reportKey"],
                    "storyId": story["storyId"],
                    "milestoneId": latest_ms["milestoneId"],
                    "milestoneCount": len(milestones),
                    "reportCount": len(story.get("reports") or []),
                    "bucket": story.get("bucket") if story.get("bucket") in _BUCKET_BY_KEY else classify_bucket(rep["title"], rep.get("summary", ""), str(rep.get("track") or ""), rep["source"]),
                    "title": rep["title"],
                    "summary": str(rep.get("summary") or rep["title"])[:220],
                    "tags": story.get("tags") or [_BUCKET_BY_KEY[story.get("bucket", "china")]["name"]],
                    "sourceName": rep["source"],
                    "sourceTierGrade": grade,
                    "official": bool(rep.get("official") or grade == "S"),
                    "publishedAt": rep.get("publishedAt"),
                    "relativeTime": _relative_time(rep.get("publishedAt"), now_utc),
                    "originalUrl": rep["originalUrl"],
                    "hotlistSignal": rep.get("hotlistSignal"),
                    "independentCount": indep_count,
                    "isNewMilestone": is_new_ms,
                    "_ruleScore": self._rule_candidate_score(story, rep, now_utc),
                }
                bucket_pools[cand["bucket"]].append(cand)

            recalled: list[dict[str, Any]] = []
            for key in bucket_pools:
                bucket_pools[key].sort(key=lambda item: item["_ruleScore"], reverse=True)
                recalled.extend(bucket_pools[key][:10])

            # Stage B: 4-axis rerank + cross-outlet duplicate folding + English -> Chinese translation
            rerank_map, llm_rerank_used = self._rerank_with_glm(recalled, allow_llm=allow_llm)
            by_key = {c["reportKey"]: c for c in recalled}
            dropped_keys: set[str] = set()
            for cand in recalled:
                rk = rerank_map.get(cand["reportKey"]) or {}
                dup_target = str(rk.get("duplicateOf") or "").strip()
                if dup_target and dup_target != cand["reportKey"] and dup_target in by_key:
                    # Avoid mutual/cyclic drops: resolve up to 2 hops and never drop if target is already dropped
                    if dup_target not in dropped_keys and cand["reportKey"] not in dropped_keys:
                        by_key[dup_target]["independentCount"] += 1
                        dropped_keys.add(cand["reportKey"])

            filtered_recalled: list[dict[str, Any]] = []
            for cand in recalled:
                if cand["reportKey"] in dropped_keys:
                    continue
                rk = rerank_map.get(cand["reportKey"]) or {"breadth": 3.0, "novelty": 3.0, "evidence": 3.0, "bucket": cand["bucket"]}
                cand["bucket"] = rk["bucket"]
                if rk.get("titleZh"):
                    cand["originalTitle"] = cand["title"]
                    cand["title"] = rk["titleZh"]
                if rk.get("summaryZh"):
                    cand["summary"] = rk["summaryZh"]
                hot_pts = 5.0 if cand.get("hotlistSignal") else min(5.0, float(cand["independentCount"]))
                cand["finalScore"] = round(
                    rk["breadth"] * 0.35 * 20.0
                    + rk["novelty"] * 0.35 * 20.0
                    + rk["evidence"] * 0.20 * 20.0
                    + hot_pts * 0.10 * 20.0,
                    2,
                )
                cand["evidenceScore"] = rk["evidence"]
                filtered_recalled.append(cand)
            recalled = filtered_recalled

            recalled.sort(key=lambda item: (item["finalScore"], item["official"], item["independentCount"]), reverse=True)

            # Stage C: 1 Lead + 5 Sections (2-4 per section) + 3 Key Picks strictly from Sections
            lead = None
            if recalled:
                lead = next((c for c in recalled if c["evidenceScore"] >= 3.5 or c["official"] or c["sourceTierGrade"] == "S"), recalled[0])

            lead_key = lead["reportKey"] if lead else None
            lead_story_id = lead["storyId"] if lead else None
            source_counts: dict[str, int] = {}
            if lead:
                source_counts[lead["sourceName"]] = 1

            sections_out: list[dict[str, Any]] = []
            all_section_items: list[dict[str, Any]] = []
            used_story_ids: set[str] = {lead_story_id} if lead_story_id else set()

            for meta in FINANCE_BUCKETS:
                b_candidates = [
                    c for c in recalled
                    if c["bucket"] == meta["key"] and c["reportKey"] != lead_key and c["storyId"] not in used_story_ids
                ]
                chosen: list[dict[str, Any]] = []
                for c in b_candidates:
                    if source_counts.get(c["sourceName"], 0) >= 3:
                        continue
                    source_counts[c["sourceName"]] = source_counts.get(c["sourceName"], 0) + 1
                    used_story_ids.add(c["storyId"])
                    chosen.append({
                        **{k: v for k, v in c.items() if not k.startswith("_")},
                        "sectionCode": meta["code"],
                        "sectionName": meta["name"],
                    })
                    if len(chosen) >= 4:
                        break
                all_section_items.extend(chosen)
                sections_out.append({
                    "key": meta["key"],
                    "code": meta["code"],
                    "name": meta["name"],
                    "note": meta["note"],
                    "items": chosen,
                })

            # Pick 3 keyPicks strictly from sections, preferring 1 per distinct bucket first
            picks_pool = sorted(all_section_items, key=lambda item: item["finalScore"], reverse=True)
            key_picks: list[dict[str, Any]] = []
            seen_pick_buckets: set[str] = set()
            for item in picks_pool:
                if item["bucket"] in seen_pick_buckets:
                    continue
                seen_pick_buckets.add(item["bucket"])
                key_picks.append({
                    "reportKey": item["reportKey"],
                    "storyId": item["storyId"],
                    "sectionCode": item["sectionCode"],
                    "sectionName": item["sectionName"],
                    "title": item["title"],
                    "summary": item["summary"],
                })
                if len(key_picks) >= 3:
                    break
            if len(key_picks) < 3:
                picked_keys = {p["reportKey"] for p in key_picks}
                for item in picks_pool:
                    if item["reportKey"] in picked_keys:
                        continue
                    key_picks.append({
                        "reportKey": item["reportKey"],
                        "storyId": item["storyId"],
                        "sectionCode": item["sectionCode"],
                        "sectionName": item["sectionName"],
                        "title": item["title"],
                        "summary": item["summary"],
                    })
                    if len(key_picks) >= 3:
                        break

            # Precompute event overviews for lead + selected stories (prioritize lead/keyPicks + multi-report for GLM)
            selected_story_ids = ({lead["storyId"]} if lead else set()) | {item["storyId"] for item in all_section_items}
            priority_story_ids = ({lead["storyId"]} if lead else set()) | {item["storyId"] for item in key_picks}
            story_by_id = {st["storyId"]: st for st in stories}
            ordered_sids = [sid for sid in priority_story_ids if sid in selected_story_ids] + [
                sid for sid in selected_story_ids if sid not in priority_story_ids
            ]
            llm_story_set: set[str] = set()
            if allow_llm:
                for sid in ordered_sids:
                    st = story_by_id.get(sid)
                    if not st:
                        continue
                    if sid in priority_story_ids or len(st.get("reports") or []) >= 2:
                        llm_story_set.add(sid)
                    if len(llm_story_set) >= 6:
                        break
            prep_tasks = [(sid, story_by_id[sid], sid in llm_story_set) for sid in ordered_sids if sid in story_by_id]
            if prep_tasks:
                if allow_llm and llm_story_set:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        ov_results = list(pool.map(lambda args: (args[0], self._prepare_event_overview(args[1], allow_llm=args[2])), prep_tasks))
                else:
                    ov_results = [(sid, self._prepare_event_overview(st, allow_llm=False)) for sid, st, _ in prep_tasks]
                for sid, (ov, inputs_hash, changed) in ov_results:
                    if changed:
                        self.store.update_tracked_overview(sid, ov, inputs_hash)

            # Urgent live breaking banner (S-tier official within 4h)
            urgent_banner = None
            for cand in recalled:
                if not cand["official"]:
                    continue
                pub = _parse(cand.get("publishedAt"))
                if pub and (now_utc - pub).total_seconds() <= 4 * 3600:
                    urgent_banner = {
                        "reportKey": cand["reportKey"],
                        "storyId": cand["storyId"],
                        "title": cand["title"],
                        "sourceName": cand["sourceName"],
                        "time": _format_beijing(cand.get("publishedAt")),
                    }
                    break

            # Source coverage stats (deduplicated by source name)
            dedup_status: dict[str, dict[str, Any]] = {}
            for row in source_statuses:
                sname = str(row.get("source") or row.get("name") or row.get("id") or "").strip()
                if not sname:
                    continue
                ok = bool(row.get("ok"))
                if sname not in dedup_status or (ok and not dedup_status[sname]["ok"]):
                    dedup_status[sname] = {
                        "name": sname,
                        "ok": ok,
                        "count": int(row.get("count") or 0),
                        "cache": row.get("cache") or ("fresh" if ok else "stale"),
                        "error": row.get("error"),
                    }
            source_health_list = list(dedup_status.values())
            ok_count = sum(1 for row in source_health_list if row["ok"])

            lead_clean = (
                {
                    **{k: v for k, v in lead.items() if not k.startswith("_")},
                    "sectionCode": _BUCKET_BY_KEY[lead["bucket"]]["code"],
                    "sectionName": _BUCKET_BY_KEY[lead["bucket"]]["name"],
                }
                if lead else None
            )
            overview_text = self._compose_overview(target_type, lead_clean, key_picks, allow_llm=allow_llm)
            market_strip = self._build_market_strip(target_type)
            calendar_data = self.news_service.calendar.overview() if hasattr(self.news_service, "calendar") else {"items": [], "partial": False, "stale": False, "sources": []}

            weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
            dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
            date_label = f"{dt_obj.year} 年 {dt_obj.month} 月 {dt_obj.day} 日 · 星期{weekday_names[dt_obj.weekday()]}"

            payload = {
                "editionKey": edition_key,
                "editionDate": target_date,
                "editionType": target_type,
                "editionTag": "早刊" if target_type == "morning" else "晚刊",
                "publishTimeLabel": "08:00 定时出刊" if target_type == "morning" else "18:00 定时出刊",
                "dateLabel": date_label,
                "dayNumber": f"{dt_obj.day:02d}",
                "generatedAt": now_utc.isoformat(),
                "overview": overview_text,
                "marketStrip": market_strip,
                "urgentBanner": urgent_banner,
                "lead": lead_clean,
                "keyPicks": key_picks,
                "sections": sections_out,
                "calendar": calendar_data,
                "coverage": {
                    "activeSources": ok_count,
                    "totalSources": len(source_health_list),
                    "rawReports": len(reports),
                    "trackedStories": len(stories),
                    "selectedCount": (1 if lead_clean else 0) + len(all_section_items),
                    "editorialEngine": "glm" if llm_rerank_used else "rule",
                    "sources": source_health_list,
                },
            }
            snap_hash = hashlib.sha1(json.dumps(
                {"lead": lead_key, "sections": [i["reportKey"] for i in all_section_items]},
                sort_keys=True,
            ).encode("utf-8")).hexdigest()
            self.store.save_daily_edition(
                edition_key=edition_key,
                edition_date=target_date,
                edition_type=target_type,
                payload=payload,
                snapshot_hash=snap_hash,
                prompt_version=PROMPT_VERSION,
            )
            return payload

    def list_editions(self, limit: int = 60) -> list[dict[str, Any]]:
        return self.store.list_daily_editions(limit=limit)

    def latest_edition(self, edition_type: str | None = None) -> dict[str, Any]:
        with self._lock:
            stored = self.store.get_latest_daily_edition(edition_type=edition_type)
            if stored:
                return stored
            return self.compose_edition(edition_type=edition_type, refresh_upstream=False, allow_llm=False)

    def get_edition(self, edition_key: str) -> dict[str, Any] | None:
        return self.store.get_daily_edition(edition_key)

    def refresh_now(self, edition_type: str | None = None) -> dict[str, Any]:
        return self.compose_edition(edition_type=edition_type, refresh_upstream=True, allow_llm=True)

    def get_report_detail(self, report_key: str) -> dict[str, Any] | None:
        report = self.store.get_report_detail(report_key)
        if not report:
            return None
        now_utc = self.now_fn().astimezone(UTC)
        bucket = report.get("bucket") or classify_bucket(report["title"], report.get("summary", ""), str(report.get("track") or ""), report["source"])
        bucket_meta = _BUCKET_BY_KEY.get(bucket, FINANCE_BUCKETS[1])
        story_id = report.get("storyId")
        story = self.store.get_tracked_story(story_id) if story_id else None

        followups: list[dict[str, Any]] = []
        event_summary = None
        if story:
            seen: set[str] = {report_key}
            for rep in story.get("reports") or []:
                rk = rep.get("reportKey") or rep.get("id")
                if not rk or rk in seen:
                    continue
                seen.add(rk)
                followups.append({
                    "reportKey": rk,
                    "title": rep["title"],
                    "sourceName": rep["source"],
                    "publishedAt": rep.get("publishedAt"),
                    "relativeTime": _relative_time(rep.get("publishedAt"), now_utc),
                    "originalUrl": rep.get("originalUrl"),
                    "role": rep.get("role") or "report",
                })
            event_summary = {
                "storyId": story["storyId"],
                "title": story["title"],
                "reportCount": len(story.get("reports") or []),
                "milestoneCount": len(story.get("milestones") or []),
            }

        return {
            "reportKey": report["reportKey"],
            "title": report["title"],
            "summary": report.get("summary") or report["title"],
            "publishedAt": report.get("publishedAt"),
            "timeLabel": _format_beijing(report.get("publishedAt")),
            "relativeTime": _relative_time(report.get("publishedAt"), now_utc),
            "sourceName": report["source"],
            "sourceTier": "官方原文" if report.get("official") or _effective_grade(report, self.registry) == "S" else (
                "权威信源" if _effective_grade(report, self.registry) == "A" else "公开报道"
            ),
            "originalUrl": report.get("originalUrl"),
            "bucket": bucket,
            "bucketName": bucket_meta["name"],
            "tags": story.get("tags") if story else [bucket_meta["name"]],
            "relatedStocks": report.get("relatedStocks") or [],
            "eventSummary": event_summary,
            "followups": followups,
        }

    def get_tracked_event(self, story_id: str) -> dict[str, Any] | None:
        story = self.store.get_tracked_story(story_id)
        if not story:
            return None
        now_utc = self.now_fn().astimezone(UTC)
        overview = self._ensure_event_overview(story, allow_llm=False)
        why_hot = self.compute_heat_and_why_hot(story, now=now_utc)
        heat_series = self._build_heat_series(story)
        bucket_meta = _BUCKET_BY_KEY.get(story.get("bucket") or "china", FINANCE_BUCKETS[1])

        milestones_out: list[dict[str, Any]] = []
        for ms in story.get("milestones") or []:
            ms_reports = []
            for rep in ms.get("reports") or []:
                ms_reports.append({
                    "reportKey": rep.get("reportKey") or rep.get("id"),
                    "title": rep["title"],
                    "sourceName": rep["source"],
                    "sourceTier": "官方原文" if rep.get("official") or _effective_grade(rep, self.registry) == "S" else "精选报道",
                    "publishedAt": rep.get("publishedAt"),
                    "timeLabel": _format_beijing(rep.get("publishedAt")),
                    "originalUrl": rep.get("originalUrl"),
                })
            rep_story = next((r for r in ms_reports if r["reportKey"] == ms.get("representativeReportKey")), ms_reports[0] if ms_reports else None)
            milestones_out.append({
                "milestoneId": ms["milestoneId"],
                "title": ms["title"],
                "occurredAt": ms["occurredAt"],
                "timeLabel": _format_beijing(ms["occurredAt"]),
                "reportCount": max(int(ms.get("reportCount") or 0), len(ms_reports)),
                "sourceSummary": " · ".join(dict.fromkeys(r["sourceName"] for r in ms_reports[:4])) or (rep_story["sourceName"] if rep_story else "公开来源"),
                "marketNote": ms.get("marketNote") or "",
                "representativeReportKey": rep_story["reportKey"] if rep_story else ms.get("representativeReportKey"),
                "reports": ms_reports,
            })

        reports_timeline = [
            {
                "reportKey": rep.get("reportKey") or rep.get("id"),
                "title": rep["title"],
                "sourceName": rep["source"],
                "sourceTier": "官方原文" if rep.get("official") or _effective_grade(rep, self.registry) == "S" else (
                    "权威信源" if _effective_grade(rep, self.registry) == "A" else "同事件报道"
                ),
                "publishedAt": rep.get("publishedAt"),
                "timeLabel": _format_beijing(rep.get("publishedAt")),
                "relativeTime": _relative_time(rep.get("publishedAt"), now_utc),
                "originalUrl": rep.get("originalUrl"),
            }
            for rep in sorted(story.get("reports") or [], key=lambda r: r.get("publishedAt") or "", reverse=True)
        ]

        indep_names = independent_sources(story.get("reports") or [])
        return {
            "storyId": story["storyId"],
            "title": story["title"],
            "bucket": bucket_meta["key"],
            "bucketName": bucket_meta["name"],
            "statusTag": "热点事件 · 持续更新" if why_hot["participants48h"] >= 2 else "持续事件 · 跟踪中",
            "reportCount": len(reports_timeline),
            "sourceCount": max(1, len(indep_names)),
            "firstReportLabel": f"{_format_beijing(story.get('firstReportAt')).split(' ')[0]} 首发",
            "latestUpdateLabel": f"{_relative_time(story.get('latestAt'), now_utc)}更新",
            "overview": overview,
            "milestones": milestones_out,
            "reports": reports_timeline,
            "whyHot": why_hot,
            "heatSeries": heat_series,
            "tags": story.get("tags") or [bucket_meta["name"]],
            "recordMeta": {
                "firstAt": _format_beijing(story.get("firstReportAt")),
                "latestAt": _format_beijing(story.get("latestAt")),
                "nodeCount": len(milestones_out),
            },
        }


class FinancialDailyScheduler:
    """Schedules 08:00 morning and 18:00 evening editions + hourly heat snapshots."""

    def __init__(self, service: FinancialDailyService, *, interval_seconds: int = 60, refresh_upstream: bool = False):
        self.service = service
        self.interval_seconds = max(10, int(interval_seconds))
        self.refresh_upstream = refresh_upstream
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_hour_key: str | None = None

    def run_once(self) -> list[str]:
        generated: list[str] = []
        now_bj = self.service.now_fn().astimezone(SHANGHAI)
        today = now_bj.strftime("%Y-%m-%d")

        if now_bj.hour >= 8 and not self.service.get_edition(f"{today}-morning"):
            self.service.compose_edition(
                edition_date=today,
                edition_type="morning",
                refresh_upstream=self.refresh_upstream,
                allow_llm=True,
            )
            generated.append(f"{today}-morning")

        if now_bj.hour >= 18 and not self.service.get_edition(f"{today}-evening"):
            self.service.compose_edition(
                edition_date=today,
                edition_type="evening",
                refresh_upstream=self.refresh_upstream,
                allow_llm=True,
            )
            generated.append(f"{today}-evening")

        hour_key = now_bj.strftime("%Y-%m-%d %H:00")
        if hour_key != self._last_hour_key:
            self.service.record_hourly_heat_snapshots()
            self._last_hour_key = hour_key
        return generated

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()

        def loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_once()
                except Exception:  # noqa: BLE001
                    logger.exception("financial daily scheduler cycle failed")
                self._stop_event.wait(self.interval_seconds)

        self._thread = threading.Thread(target=loop, name="financial-daily-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
