"""Dual-edition Financial Daily engine modeled on AIHOT editorial principles.

Uses the 44 verified financial sources (decoupled from 7x24 quick wires and
non-financial tech blogs), 3 thematic sections (宏观数据与政策 / 市场表现 /
海外公司事件与财报), AIHOT-inspired content-value scoring, full-body
answer-first Chinese summaries, long-read Chinese body + TOC outline,
embedded K-line charts for market-performance items, and strict incremental
milestone follow-ups.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from data_paths import cache_path
from financial_daily_sources import (
    _BOILERPLATE_BODY_SIGNALS,
    DAILY_SOURCES,
    SOURCE_SPEC_BY_NAME,
    FinancialDailySourceCollector,
    fetch_article_body,
)
from financial_editorial import headline, independent_sources, is_roundup, origin_owner
from financial_news_store import FinancialNewsStore, _parse, _report_key
from source_registry import load_registry, source_grade, source_tier

logger = logging.getLogger(__name__)

UTC = timezone.utc
SHANGHAI = timezone(timedelta(hours=8))
PROMPT_VERSION = "financial-daily-v5.2"
TRACKED_WINDOW_DAYS = 30

# User-defined 3 thematic sections
FINANCE_BUCKETS: tuple[dict[str, str], ...] = (
    {
        "key": "macro",
        "code": "01",
        "name": "宏观数据与政策",
        "note": "重磅经济政策、央行与财政动向、国际地缘政局、CPI/PPI/利率及原油黄金美债异动",
    },
    {
        "key": "market",
        "code": "02",
        "name": "市场表现",
        "note": "异动的中美港市场整体表现、成交量变化与重要指数走势",
    },
    {
        "key": "companies",
        "code": "03",
        "name": "海外公司事件与财报",
        "note": "重点科技与龙头公司重大事件、股价催化与财报分析",
    },
)
_BUCKET_BY_KEY = {row["key"]: row for row in FINANCE_BUCKETS}

_NON_ADVISORY_RE = re.compile(r"买入建议|强烈推荐|目标价|必涨|抄底|建议买入|建议卖出|重仓买入|坚决看多|逢低买入")
_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?")

_NOISE_RE = re.compile(
    r"在互动平台表示|互动平台回复|投资者互动平台|互动易回复|回复投资者提问|董秘回复|"
    r"财经早餐|早报汇总|早间必读|新闻联播|要闻汇总|隔夜外盘|每日必读|"
    r"盘前必读|早盘必读|操盘必读|午间公告一览|晚间公告一览|热点前瞻|一周综述|每日复盘汇总|"
    r"开展\d+亿元.*逆回购|公开市场业务交易公告|股东户数|过街码|地铁.*试点|党内法规|地方委员会工作条例|"
    r"加满一箱.*汽油|92号汽油|95号汽油|成品油调价|国内油价(?:上调|下调|调整)|汽柴油(?:价格|零售价)|"
    r"三峡水运|常态化帮扶资金|thanksgiving|grocery stores|black friday deals|holiday shopping|"
    r"弃皮衣|穿迪奥|棉夹克|售价\d+元.*售罄|同款标价|街拍|衣品|造型首秀|穿搭|"
    r"gta\s*6|video game|declares\s+\$[\d.]+\s+dividend|monthly distribution|quarterly distribution|"
    r"buying a new bmw|in my 70s|owner of detroit lions|dies at \d+",
    re.I,
)
_CLICKBAIT_RE = re.compile(
    r"100%！|刚刚！.*突发|突发！.*大消息|重磅！.*大消息|发生了什么？|惊天|炸裂|史诗级|太猛了|暴涨预警|华尔街之狼",
    re.I,
)

_MARKET_RE = re.compile(
    r"A股(?:午评|收评|早评|三大股指|开盘|收盘|大涨|大跌|跳水|反攻|放量|缩量)|"
    r"沪指|上证指数|深证成指|深成指|创业板指|科创50|北证50|两市成交额|下跌个股|上涨个股|宽基ETF|"
    r"美股(?:三大股指|收涨|收跌|开盘|收盘|暴跌|大涨|回调|反弹)|纳指|纳斯达克|标普500|道指|道琼斯|"
    r"港股(?:收涨|收跌|大涨|大跌|回调|反弹)|恒生指数|恒指|恒生科技|"
    r"日股|日经(?:225|平均指数)?|韩股|韩国股市|KOSPI|欧股|亚太(?:股市|市场)|全球股市|股市(?:回调|大跌|大涨|重挫|崩盘|救市|稳市)|"
    r"stock market|wall street|s&p\s*500|nasdaq|dow jones|hang seng|nikkei|kospi|equities|stocks rally|stocks tumble|selloff|sell-off|market convulsions",
    re.I,
)
_MAJOR_COMPANIES_RE = re.compile(
    r"英伟达|黄仁勋|苹果|微软|谷歌|亚马逊|特斯拉|马斯克|Meta|OpenAI|Anthropic|xAI|台积电|AMD|超威|英特尔|博通|美光|阿斯麦|戴尔|甲骨文|奈飞|高通|ARM|"
    r"Palantir|Salesforce|思科|IBM|Adobe|优步|爱彼迎|沃尔玛|开市客|伯克希尔|巴菲特|摩根大通|高盛|摩根士丹利|花旗|美银|瑞银|汇丰|贝莱德|"
    r"波音|空客|礼来|诺和诺德|辉瑞|埃克森美孚|雪佛龙|沙特阿美|丰田|索尼|软银|三星|SK海力士|"
    r"小米|雷军|阿里巴巴|阿里|马云|平头哥|腾讯|字节跳动|拼多多|京东|美团|比亚迪|宁德时代|华为|中芯国际|茅台|百度|网易|蔚来|小鹏|理想|吉利|"
    r"蚂蚁集团|滴滴|携程|快手|哔哩哔哩|联想|海尔|美的|格力|泡泡玛特|寒武纪|中际旭创|工业富联|"
    r"nvidia|jensen huang|apple|microsoft|google|alphabet|amazon|tesla|elon musk|tsmc|intel|broadcom|micron|asml|dell|oracle|netflix|qualcomm|"
    r"cisco|uber|airbnb|walmart|costco|berkshire|jpmorgan|goldman sachs|morgan stanley|citigroup|bank of america|blackrock|boeing|airbus|"
    r"eli lilly|novo nordisk|pfizer|exxon|chevron|aramco|toyota|sony|softbank|samsung|sk hynix|"
    r"xiaomi|alibaba|tencent|bytedance|pinduoduo|pdd|jd\.com|meituan|byd|catl|huawei|smic|baidu|netease|nio|xpeng|li auto|geely",
    re.I,
)
_COMPANIES_RE = re.compile(
    r"财报|季报|年报|营收|净利润|每股收益|指引|业绩|(?:业绩|盈利|营收|财报|利润)(?:不及预期|超预期)|股价|市值|裁员|收购|并购|反垄断|起诉|董事会|CEO|首席执行官|"
    r"英伟达|黄仁勋|苹果|微软|谷歌|亚马逊|特斯拉|Meta|OpenAI|Anthropic|台积电|AMD|英特尔|博通|美光|戴尔|甲骨文|奈飞|高通|阿斯麦|"
    r"小米|阿里巴巴|阿里|腾讯|字节跳动|拼多多|京东|美团|比亚迪|宁德时代|蔚来|小鹏|理想|华为|"
    r"nvidia|jensen huang|apple|microsoft|google|alphabet|amazon|tesla|tsmc|intel|broadcom|micron|dell|oracle|netflix|qualcomm|asml|"
    r"xiaomi|alibaba|tencent|bytedance|byd|catl|huawei|earnings|quarterly results|guidance|revenue|profit|ipo|antitrust|acquisition|lawsuit",
    re.I,
)
_MACRO_RE = re.compile(
    r"央行|美联储|欧央行|英国央行|日本央行|利率|降息|加息|降准|LPR|MLF|财政部|发改委|商务部|外汇局|国务院|国新办|证监会|金融监管总局|"
    r"通胀|CPI|PPI|PCE|PMI|GDP|非农|失业率|关税|贸易|国债|美债|收益率|货币政策|财政政策|救市|刺激政策|降息概率|加息概率|"
    r"原油|油价|布伦特|WTI|黄金|金价|白银|铜价|贵金属|霍尔木兹|地缘|冲突|制裁|停火|选举|白宫|特朗普|伊朗|中东|俄乌|"
    r"fomc|federal reserve|\bfed\b|\becb\b|\bboe\b|\bboj\b|inflation|tariff|treasury|yield|crude|brent|oil|gold|silver|copper|geopolitical|sanctions|central bank|imf|bis",
    re.I,
)

_ENTITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pboc", ("中国人民银行", "中国央行", "央行", "pboc")),
    ("fed", ("美联储", "federal reserve", "fomc")),
    ("ecb", ("欧央行", "欧洲央行", "european central bank")),
    ("boe", ("英国央行", "bank of england")),
    ("boj", ("日本央行", "日央行", "bank of japan")),
    ("csrc", ("证监会", "csrc")),
    ("sec", ("美国证监会", "sec ")),
    ("trump", ("特朗普", "trump")),
    ("tariff", ("关税", "tariff", "tariffs")),
    ("iran", ("伊朗", "霍尔木兹", "iran", "hormuz")),
    ("nvidia", ("英伟达", "黄仁勋", "nvidia", "jensen huang", "nvda")),
    ("xiaomi", ("小米", "xiaomi")),
    ("apple", ("苹果", "apple", "aapl")),
    ("microsoft", ("微软", "microsoft", "msft")),
    ("google", ("谷歌", "alphabet", "google")),
    ("amazon", ("亚马逊", "amazon")),
    ("meta", ("meta", "facebook")),
    ("tesla", ("特斯拉", "tesla", "tsla")),
    ("dell", ("戴尔", "dell")),
    ("tsmc", ("台积电", "tsmc")),
    ("micron", ("美光", "micron")),
    ("openai", ("openai", "chatgpt")),
    ("huawei", ("华为", "huawei")),
    ("alibaba", ("阿里巴巴", "阿里", "alibaba")),
    ("tencent", ("腾讯", "tencent")),
    ("byd", ("比亚迪", "byd")),
    ("catl", ("宁德时代", "catl")),
    ("gold", ("黄金", "金价", "gold")),
    ("oil", ("原油", "布伦特", "wti", "brent", "crude")),
    ("treasury", ("美债", "国债收益率", "treasury yield")),
    ("cpi", ("cpi", "通胀", "inflation", "pce")),
    ("gdp", ("gdp", "国内生产总值")),
)
_GENERIC_ENTITIES = {"trump"}
_COMPANY_ENTITIES = {
    "nvidia", "xiaomi", "apple", "microsoft", "google", "amazon", "meta", "tesla",
    "dell", "tsmc", "micron", "openai", "huawei", "alibaba", "tencent", "byd", "catl",
}

_EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "has", "have", "had", "are", "was", "were",
    "will", "not", "but", "out", "new", "over", "after", "more", "than", "says", "said", "shows",
    "into", "about", "been", "being", "its", "their", "your", "our", "all", "can", "may", "now",
    "how", "why", "what", "who", "when", "where", "here", "there", "also", "just", "get", "gets",
    "got", "make", "makes", "made", "still", "already", "could", "would", "should", "one", "two",
    "first", "last", "year", "years", "day", "days", "week", "month", "report", "news", "video",
}

_MARKET_CHART_RULES: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    (re.compile(r"创业板指|创业板", re.I), {"asset": "index", "code": "399006", "name": "创业板指"}),
    (re.compile(r"科创50|科创板", re.I), {"asset": "index", "code": "000688", "name": "科创50"}),
    (re.compile(r"深证成指|深成指", re.I), {"asset": "index", "code": "399001", "name": "深证成指"}),
    (re.compile(r"沪深300", re.I), {"asset": "index", "code": "000300", "name": "沪深300"}),
    (re.compile(r"上证指数|沪指|A股|两市成交", re.I), {"asset": "index", "code": "000001", "name": "上证指数"}),
    (re.compile(r"恒生科技|港股科技", re.I), {"asset": "global_index", "code": "HSTECH", "name": "恒生科技"}),
    (re.compile(r"恒生指数|恒指|港股|香港股市|hang seng", re.I), {"asset": "global_index", "code": "HSI", "name": "恒生指数"}),
    (re.compile(r"纳斯达克|纳指|nasdaq|科技股", re.I), {"asset": "global_index", "code": "NDX", "name": "纳斯达克"}),
    (re.compile(r"道琼斯|道指|dow jones", re.I), {"asset": "global_index", "code": "DJI", "name": "道琼斯"}),
    (re.compile(r"标普|美股|华尔街|s&p\s*500|wall street|us stocks|equities", re.I), {"asset": "global_index", "code": "SPX", "name": "标普500"}),
)


def detect_market_chart(title: str, summary: str = "") -> dict[str, str] | None:
    """Detect the most relevant A-share / HK / US index K-line chart for a market-performance story."""
    for text in (title or "", (summary or "")[:260]):
        if not text:
            continue
        for pattern, chart in _MARKET_CHART_RULES:
            if pattern.search(text):
                return dict(chart)
    return {"asset": "index", "code": "000001", "name": "上证指数"}


def extract_markdown_outline(markdown_text: str) -> list[dict[str, Any]]:
    """Extract h2/h3 headings from Markdown into a TOC outline."""
    outline: list[dict[str, Any]] = []
    idx = 0
    for line in (markdown_text or "").splitlines():
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line.strip())
        if not m:
            continue
        level = len(m.group(1))
        text = re.sub(r"[*_`]+", "", m.group(2)).strip()
        if not text:
            continue
        idx += 1
        outline.append({"id": f"sec-{idx}", "text": text[:60], "level": level})
    return outline


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("http://", "https://")) else ""


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"A股A股", "A股", text)
    text = re.sub(r"具体情况如下[：:]\s*$", "", text).strip()
    text = re.sub(r"^原标题[：:]\s*", "", text).strip()
    if len(text) <= max_len:
        # Trim dangling truncated RSS fragments (e.g. "...利益，双方") cleanly to last sentence end
        if len(text) >= 90 and not re.search(r"[。！？.!?…\"”」』）)]$", text):
            for sep in ("。", "！", "？"):
                pos = text.rfind(sep)
                if pos >= int(len(text) * 0.6):
                    return text[: pos + 1].strip()
        return text
    cut = text[:max_len]
    for sep in ("。", "！", "？", ";", "；", ". "):
        pos = cut.rfind(sep)
        if pos >= int(max_len * 0.55):
            return cut[: pos + len(sep.strip())].strip()
    if re.search(r"[A-Za-z0-9]$", cut) and max_len < len(text) and re.match(r"[A-Za-z0-9]", text[max_len]):
        sp = cut.rfind(" ")
        if sp >= int(max_len * 0.5):
            return cut[:sp].rstrip(" ,;:-") + "…"
    return cut.rstrip(" ,;:，；：") + "…"


def _is_mostly_english(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    latin = len(re.findall(r"[A-Za-z]", s))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    return latin >= 10 and latin > cjk * 1.6


def _normalized(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def _bigrams(text: str) -> set[str]:
    """Use CJK 2-grams for Chinese and meaningful whole words for English/Latin."""
    low = (text or "").lower()
    tokens: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", low):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i : i + 2] for i in range(len(run) - 1))
    for word in re.findall(r"[a-z0-9]{3,}", low):
        if word not in _EN_STOPWORDS:
            tokens.add(word)
    return tokens


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
    for num in re.findall(r"\d+(?:\.\d+)?%|\d+bp", blob):
        found.add(f"num:{num}")
    return found


_BANK_COMMENTARY_PREFIX_RE = re.compile(
    r"(?:^|[，,：:\s])(?:摩根大通|高盛|摩根士丹利|瑞银|汇丰|巴克莱|美银|花旗|德意志银行|德银|野村|贝莱德|中金|中信证券|华泰证券|开源证券|天风证券)[：:]",
    re.I,
)


def classify_bucket(title: str, summary: str = "", track: str = "", source: str = "") -> str:
    """Classify into the 3 fixed thematic sections: macro / market / companies.

    Key disambiguation:
    - Bank/analyst commentary headlines ('摩根大通：日股回调还没到头', '高盛：标普500...') are classified
      by the SUBJECT they analyze (market or macro), NOT as 'companies' just because a bank is named.
    - Explicit market-index / equity-market moves go to 'market' (including Japan/Korea/Asia markets).
    - Company earnings, ratings on a specific firm, CEO/board/regulatory/M&A events go to 'companies'.
    """
    blob = f"{title} {summary[:320]}"
    # Market index / equity-market moves & bank equity strategy calls -> market
    if _MARKET_RE.search(title):
        return "market"
    if _BANK_COMMENTARY_PREFIX_RE.search(title):
        if _MARKET_RE.search(blob):
            return "market"
        if _MACRO_RE.search(blob):
            return "macro"
    if _MARKET_RE.search(blob) and not _COMPANIES_RE.search(title):
        return "market"
    if _COMPANIES_RE.search(title):
        return "companies"
    if _MACRO_RE.search(blob) or source in {
        "中国人民银行", "证监会", "中国政府网", "国家金融监督管理总局", "国家统计局",
        "财政部", "国家发展改革委", "商务部", "国家外汇管理局", "工业和信息化部",
        "Federal Reserve", "美国财政部", "美国经济分析局", "European Central Bank",
        "英国央行", "日本央行", "国际清算银行", "香港金管局", "OilPrice",
    }:
        return "macro"
    if _COMPANIES_RE.search(blob) or source in {"CNBC Tech", "CNBC Earnings", "Techmeme", "CnEVPost", "SemiAnalysis", "WSJ Business", "SEC"}:
        return "companies"
    if source in {"WSJ Markets", "Bloomberg Markets", "上交所", "香港交易所"}:
        return "market"
    spec = SOURCE_SPEC_BY_NAME.get(source)
    if spec and spec.default_bucket in _BUCKET_BY_KEY:
        return spec.default_bucket
    return "macro"


def _effective_grade(report: dict[str, Any], registry: dict[str, Any]) -> str:
    source = str(report.get("source") or "")
    spec = SOURCE_SPEC_BY_NAME.get(source)
    if spec:
        return spec.tier
    if report.get("official"):
        return "S"
    grade = str(report.get("sourceLevel") or source_grade(source, registry) or "C").upper()
    return grade if grade in {"S", "A", "B", "C"} else "C"


def _has_market_relevance(report: dict[str, Any]) -> bool:
    title = str(report.get("title") or "")
    summary = str(report.get("summary") or "")
    if not title or is_roundup(title):
        return False
    if _NOISE_RE.search(title) or _NOISE_RE.search(summary[:240]):
        return False
    blob = f"{title} {summary[:320]}"
    return bool(_MACRO_RE.search(blob) or _MARKET_RE.search(blob) or _COMPANIES_RE.search(blob))


def _passes_guardrails(text: str, source_corpus: str) -> bool:
    if not text or _NON_ADVISORY_RE.search(text):
        return False
    norm_text = re.sub(r"(?<=\d),(?=\d)", "", text)
    norm_corpus = re.sub(r"(?<=\d),(?=\d)", "", source_corpus)
    generated_nums = set(_NUMERIC_TOKEN_RE.findall(norm_text))
    allowed_nums = set(_NUMERIC_TOKEN_RE.findall(norm_corpus))
    extra = generated_nums - allowed_nums
    if not extra:
        return True
    # Allow exact unit-scale equivalents (e.g. billion->亿 x10, million->万 x100) and trailing-zero formatting
    corpus_vals: list[float] = []
    for tok in allowed_nums:
        try:
            corpus_vals.append(float(tok.rstrip("%")))
        except ValueError:
            continue
    for tok in extra:
        try:
            val = float(tok.rstrip("%"))
        except ValueError:
            return False
        matched = False
        for base in corpus_vals:
            if any(abs(val - base * factor) <= max(1e-6, abs(val) * 1e-4) for factor in (1.0, 10.0, 100.0, 0.1, 0.01)):
                matched = True
                break
        if not matched:
            return False
    return True


def _format_beijing(iso_value: str | None) -> str:
    dt = _parse(iso_value)
    if not dt:
        return "近期"
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
    """Orchestrates 44-source collection, 30-day event tracking, and AIHOT-style dual editions."""

    def __init__(
        self,
        news_service: Any,
        *,
        source_collector: FinancialDailySourceCollector | None = None,
        official_fetcher: Any = None,
        market_review_service: Any = None,
        global_indices_fn: Callable[[], list[dict[str, Any]]] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        llm_call: Callable[[list[dict[str, str]]], Any] | None = None,
        config_loader: Callable[[], dict[str, str]] | None = None,
        body_fetcher: Callable[[str], str] | None = None,
    ):
        self.news_service = news_service
        self.store: FinancialNewsStore = news_service.store
        self.registry: dict[str, Any] = getattr(news_service, "registry", None) or load_registry()
        cache_dir = getattr(news_service, "cache_dir", cache_path("financial-news"))
        self.source_collector = source_collector or FinancialDailySourceCollector(
            cache_dir=cache_dir,
            now_fn=(lambda: now_fn().astimezone(UTC)) if now_fn else None,
        )
        self.official_fetcher = official_fetcher
        self.market_review_service = market_review_service
        self.global_indices_fn = global_indices_fn
        self.now_fn = now_fn or (lambda: datetime.now(SHANGHAI))
        self.llm_call = llm_call
        self.config_loader = config_loader
        self.body_fetcher = body_fetcher or fetch_article_body
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None
        self._compose_active = False

    def is_refreshing(self) -> bool:
        return bool(self._refresh_lock.locked() or self._compose_active)

    def _call_llm_json(self, system_prompt: str, user_prompt: str, *, timeout_seconds: int = 45) -> Any:
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
                timeout_seconds=timeout_seconds,
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

    def _collect_unified_pool(self, *, refresh_upstream: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Collect strictly from the 44 verified financial sources (plus test stubs when injected)."""
        collected_reports: list[dict[str, Any]] = []
        source_statuses: list[dict[str, Any]] = []

        if self.official_fetcher is not None:
            # Test / injected stub compatibility path
            off_payload = self.official_fetcher.fetch() if refresh_upstream else self.official_fetcher.load_cached()
            collected_reports.extend(off_payload.get("reports") or [])
            source_statuses.extend(off_payload.get("sourceStatus") or [])
        else:
            if refresh_upstream:
                payload = self.source_collector.fetch()
            else:
                payload = self.source_collector.load_cached()
                if not payload.get("reports"):
                    try:
                        payload = self.source_collector.fetch()
                    except Exception:  # noqa: BLE001
                        payload = {"reports": [], "sourceStatus": []}
            collected_reports.extend(payload.get("reports") or [])
            source_statuses.extend(payload.get("sourceStatus") or [])

        # Include previously stored reports from our 44 approved sources (or all seeded store rows in unit-test stub mode)
        allowed_names = set(SOURCE_SPEC_BY_NAME.keys())
        if self.official_fetcher is None and not getattr(self, "_legacy_purged", False):
            try:
                self.store.purge_unapproved_sources(allowed_names)
                self.store.clear_dirty_bodies(_BOILERPLATE_BODY_SIGNALS)
                self._legacy_purged = True
            except Exception:  # noqa: BLE001
                logger.exception("legacy source/body cleanup failed")
        stored_reports = self.store.load_reports(hours=72)
        if self.official_fetcher is None and collected_reports:
            stored_reports = [r for r in stored_reports if str(r.get("source") or "") in allowed_names]
        rolling_keys = {str(r.get("id") or "") for r in stored_reports if r.get("id")}

        deduped: dict[str, dict[str, Any]] = {}
        for raw in collected_reports + stored_reports:
            url = _safe_http_url(raw.get("originalUrl") or raw.get("url"))
            title = _clean_text(raw.get("title") or "", max_len=160)
            if not title or not url:
                continue
            item = dict(raw)
            item["originalUrl"] = url
            item["title"] = title
            item["summary"] = _clean_text(item.get("summary") or title, max_len=480)
            item["source"] = str(item.get("source") or "公开来源").strip()
            item["sourceLevel"] = _effective_grade(item, self.registry)
            item["sourceTier"] = int(item.get("sourceTier") or source_tier(item["source"], self.registry))
            item["bucket"] = classify_bucket(title, item["summary"], str(item.get("track") or ""), item["source"])
            rkey = _report_key(item)
            item["reportKey"] = rkey
            item["id"] = rkey
            if rkey not in deduped or (len(str(item.get("bodyText") or "")) > len(str(deduped[rkey].get("bodyText") or ""))):
                deduped[rkey] = item

        reports_list = list(deduped.values())
        to_persist = [
            item for item in reports_list
            if item["reportKey"] not in rolling_keys or item.get("bodyText") or item.get("official")
        ]
        if to_persist:
            self.store.upsert_reports(to_persist)

        return reports_list, source_statuses

    def admit_report(self, report: dict[str, Any], *, corroborating_count: int = 1, matches_active_story: bool = False) -> bool:
        if not _safe_http_url(report.get("originalUrl")):
            return False
        if not _has_market_relevance(report):
            return False
        if _CLICKBAIT_RE.search(str(report.get("title") or "")) and not report.get("official") and corroborating_count < 2:
            return False
        grade = str(report.get("sourceLevel") or "C").upper()
        if report.get("official") or grade in {"S", "A"}:
            return True
        if matches_active_story:
            return True
        return corroborating_count >= 2 or grade == "B"

    def _recall_candidates(
        self,
        report: dict[str, Any],
        active_stories: list[dict[str, Any]],
        *,
        allow_weak: bool = False,
    ) -> list[dict[str, Any]]:
        entities = extract_entities(report["title"], report.get("summary", ""))
        specific_entities = entities - _GENERIC_ENTITIES
        bg = _bigrams(headline(report["title"]))
        scored: list[tuple[float, dict[str, Any]]] = []
        for story in active_stories:
            story_entities = extract_entities(story["title"])
            for m in story.get("milestones") or []:
                story_entities |= extract_entities(m.get("title") or "")
            ent_overlap = len(entities & story_entities)
            spec_overlap = len(specific_entities & (story_entities - _GENERIC_ENTITIES))
            title_sim = _dice(bg, _bigrams(headline(story["title"])))
            for m in story.get("milestones") or []:
                title_sim = max(title_sim, _dice(bg, _bigrams(headline(m.get("title") or ""))))
            score = spec_overlap * 0.45 + ent_overlap * 0.25 + title_sim
            strong_match = (
                spec_overlap >= 2
                or title_sim >= 0.42
                or (spec_overlap >= 1 and title_sim >= 0.26)
                or (ent_overlap >= 2 and title_sim >= 0.22)
            )
            weak_match = allow_weak and spec_overlap >= 1 and story.get("bucket") == report.get("bucket")
            if strong_match or weak_match:
                scored.append((score, story))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [story for _, story in scored[:5]]

    def _classify_story_links(
        self,
        new_reports: list[dict[str, Any]],
        active_stories: list[dict[str, Any]],
        *,
        allow_llm: bool,
    ) -> dict[str, dict[str, Any]]:
        """Classify each report as SAME_NODE (same fact/commentary), NEW_NODE (true incremental stage), or NEW_STORY."""
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

            if best_ms and best_sim >= 0.52:
                ms_dt = _parse(best_ms.get("occurredAt"))
                if not rep_dt or not ms_dt or abs((rep_dt - ms_dt).total_seconds()) <= 30 * 3600:
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
                        for st in candidates[:3]
                    ],
                })
            else:
                rep_ent = extract_entities(rep["title"], rep.get("summary", "")) - _GENERIC_ENTITIES
                st_ent = extract_entities(best_story["title"]) - _GENERIC_ENTITIES
                ent_ov = len(rep_ent & st_ent)
                if best_ms and (best_sim >= 0.45 or (ent_ov >= 2 and best_sim >= 0.22)):
                    # Default to SAME_NODE within 30 hours unless clearly separated in time
                    ms_dt = _parse(best_ms.get("occurredAt"))
                    if not rep_dt or not ms_dt or abs((rep_dt - ms_dt).total_seconds()) <= 30 * 3600:
                        decisions[rep["reportKey"]] = {
                            "action": "SAME_NODE",
                            "storyId": best_story["storyId"],
                            "milestoneId": best_ms["milestoneId"],
                        }
                    else:
                        decisions[rep["reportKey"]] = {"action": "NEW_NODE", "storyId": best_story["storyId"]}
                else:
                    decisions[rep["reportKey"]] = {"action": "NEW_STORY"}

        if allow_llm and batch_for_llm:
            try:
                rows = self._call_llm_json(
                    "你是严格遵循 AIHOT 事件脉络标准的财经编辑。只返回严格 JSON 数组，不得编造 ID。",
                    (
                        "请判断每篇新报道是否属于已有事件主题，以及它是否构成真正的「增量新进展」：\n"
                        "- SAME_NODE：多家媒体报道同一件事的同一个节点，或对同一进展的评论/解读/复盘/多角度分析（例如多篇文章都在谈“黄仁勋复职”或“关税提案”）——没有实质性新阶段事实，一律归为 SAME_NODE，绝不新建节点！\n"
                        "- NEW_NODE：明确服务于同一个事件主题，且带来了清晰的「新时间节点/新事实增量」（例如：曝光风波 → 正式辞职 → 员工请愿 → 董事会物色继任者 → 正式投票复职 → 监管调查/股价异动），绝不能把同日评论或无关事件标为 NEW_NODE！\n"
                        "- NEW_STORY：完全不同的独立事件主题（例如俄乌安全保障与中美关税是不同事件，必须选 NEW_STORY）。\n"
                        "返回严格 JSON 数组，每项字段：reportKey, action (SAME_NODE|NEW_NODE|NEW_STORY), storyId(可选), milestoneId(仅SAME_NODE必填), milestoneTitle(仅NEW_NODE必填，15-28字客观中文节点标题)：\n"
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
                        mtitle = _clean_text(row.get("milestoneTitle") or "", max_len=64)
                        if rkey and action == "SAME_NODE" and sid in valid_stories and mid in valid_stories[sid]:
                            decisions[rkey] = {"action": "SAME_NODE", "storyId": sid, "milestoneId": mid}
                        elif rkey and action == "NEW_NODE" and sid in valid_stories:
                            decisions[rkey] = {"action": "NEW_NODE", "storyId": sid, "milestoneTitle": mtitle}
                        elif rkey and action == "NEW_STORY":
                            decisions[rkey] = {"action": "NEW_STORY"}
            except Exception:  # noqa: BLE001
                logger.exception("batch story linking llm failed; using conservative fallback")

        for rep in new_reports:
            if rep["reportKey"] not in decisions:
                decisions[rep["reportKey"]] = {"action": "NEW_STORY"}
        return decisions

    def _consolidate_story_milestones(self, story: dict[str, Any]) -> bool:
        """Fold redundant same-day / overlapping commentary milestones and detach off-topic legacy links."""
        milestones = story.get("milestones") or []
        if len(milestones) < 2:
            return False
        story_ents = extract_entities(story.get("title") or "") - _GENERIC_ENTITIES
        story_bg = _bigrams(headline(story.get("title") or ""))
        kept: list[dict[str, Any]] = []
        merges: dict[str, list[str]] = {}
        changed = False
        for ms in milestones:
            ms_title = ms.get("title") or ""
            ms_ents = extract_entities(ms_title) - _GENERIC_ENTITIES
            ms_bg = _bigrams(headline(ms_title))
            # Evict obviously off-topic legacy milestones (e.g. Ukraine security inside a tariff story)
            if kept and story_ents and not (ms_ents & story_ents) and _dice(ms_bg, story_bg) < 0.12:
                self.store.unlink_milestone(story_id=story["storyId"], milestone_id=ms["milestoneId"])
                changed = True
                continue
            ms_dt = _parse(ms.get("occurredAt"))
            merged_into = None
            for anchor in kept:
                an_dt = _parse(anchor.get("occurredAt"))
                an_bg = _bigrams(headline(anchor.get("title") or ""))
                sim = _dice(ms_bg, an_bg)
                within_24h = bool(ms_dt and an_dt and abs((ms_dt - an_dt).total_seconds()) <= 24 * 3600)
                if sim >= 0.42 or (within_24h and sim >= 0.24):
                    merged_into = anchor["milestoneId"]
                    break
            if merged_into:
                merges.setdefault(merged_into, []).append(ms["milestoneId"])
            else:
                kept.append(ms)
        for keep_id, drop_ids in merges.items():
            self.store.merge_milestones(
                story_id=story["storyId"],
                keep_milestone_id=keep_id,
                drop_milestone_ids=drop_ids,
            )
            changed = True
        return changed

    def _translate_english_titles(self, entries: list[dict[str, str]], *, persist: bool = True) -> dict[str, str]:
        """Translate a small batch of English report/milestone titles to Chinese and optionally persist to SQLite."""
        todo = [e for e in entries if e.get("reportKey") and _is_mostly_english(e.get("title") or "")]
        if not todo:
            return {}
        by_key = {e["reportKey"]: e for e in todo}
        payload = [{"reportKey": e["reportKey"], "title": e["title"][:160]} for e in list(by_key.values())[:12]]
        try:
            rows = self._call_llm_json(
                "你是客观财经翻译编辑。将英文财经标题忠实译成简练自然的中文标题，保留专有名词缩写与原数字，不编造事实，只返回严格 JSON 数组。",
                (
                    "请将以下英文新闻标题逐条译为简练中文标题，返回严格 JSON 数组，每项字段：reportKey, titleZh：\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
                timeout_seconds=30,
            )
        except Exception:  # noqa: BLE001
            logger.exception("english followup/milestone title translation failed")
            return {}
        translated: dict[str, str] = {}
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rk = str(row.get("reportKey") or "")
                t_zh = _clean_text(row.get("titleZh") or "", max_len=140)
                orig = by_key.get(rk)
                if not orig or not t_zh or _is_mostly_english(t_zh):
                    continue
                if _passes_guardrails(t_zh, orig["title"]):
                    translated[rk] = t_zh
                    if persist:
                        self.store.apply_report_translation(rk, title_zh=t_zh)
        return translated

    def ingest_to_stories(self, reports: list[dict[str, Any]], *, allow_llm: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            now_dt = self.now_fn().astimezone(UTC)
            active_stories = self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)
            known_report_keys = {
                rep["reportKey"]
                for st in active_stories
                for rep in st.get("reports") or []
            }
            title_groups: dict[str, list[dict[str, Any]]] = {}
            for rep in reports:
                norm = _normalized(headline(rep["title"]))
                title_groups.setdefault(norm, []).append(rep)

            admitted: list[dict[str, Any]] = []
            for rep in sorted(reports, key=lambda r: r.get("publishedAt") or "", reverse=True):
                if rep["reportKey"] in known_report_keys:
                    continue
                pub_dt = _parse(rep.get("publishedAt"))
                if pub_dt and (now_dt - pub_dt).total_seconds() > 60 * 3600:
                    continue
                norm = _normalized(headline(rep["title"]))
                peers = title_groups.get(norm) or [rep]
                indep_count = len(independent_sources(peers))
                direct_ok = self.admit_report(rep, corroborating_count=indep_count, matches_active_story=False)
                if not direct_ok:
                    matches_active = bool(self._recall_candidates(rep, active_stories))
                    if not self.admit_report(rep, corroborating_count=indep_count, matches_active_story=matches_active):
                        continue
                admitted.append(rep)
                if len(admitted) >= 150:
                    break

            if admitted:
                decisions = self._classify_story_links(admitted, active_stories, allow_llm=allow_llm)
                for rep in admitted:
                    rkey = rep["reportKey"]
                    dec = decisions.get(rkey) or {"action": "NEW_STORY"}
                    action = dec["action"]
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
                        ms_title = dec.get("milestoneTitle") or headline(rep["title"])
                        self.store.upsert_milestone(
                            milestone_id=mid,
                            story_id=sid,
                            title=ms_title,
                            occurred_at=published_iso,
                            representative_report_key=rkey,
                            market_note="",
                            report_count=1,
                        )
                        self.store.link_milestone_report(milestone_id=mid, story_id=sid, report_key=rkey, role=role)
                        self.store.upsert_tracked_story(
                            story_id=sid,
                            title=next((s["title"] for s in active_stories if s["storyId"] == sid), rep["title"]),
                            bucket=rep["bucket"],
                            latest_at=published_iso,
                        )
                    else:
                        sid = "st-" + hashlib.sha1(f"{rep['bucket']}:{headline(rep['title'])}".encode("utf-8")).hexdigest()[:12]
                        mid = "ms-" + hashlib.sha1(f"{sid}:{rkey}".encode("utf-8")).hexdigest()[:12]
                        tags = [_BUCKET_BY_KEY[rep["bucket"]]["name"]]
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
            "detail": "统计已剔除同源重复转载，按发布时间与信源权威度客观计算。" if participants_48h else "当前处于早期收录阶段。",
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
            ms_label = str(latest_ms.get("title") or "")[:32] if (ms_dt and abs((current.astimezone(UTC) - ms_dt).total_seconds()) <= 3600) else ""
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
        return list(by_day.values())[-7:]

    def _prepare_event_overview(self, story: dict[str, Any], *, allow_llm: bool) -> tuple[dict[str, Any], str, bool]:
        milestones = story.get("milestones") or []
        reports = story.get("reports") or []
        corpus_material = [
            {
                "id": r.get("reportKey"),
                "title": r.get("title"),
                "summary": (r.get("summary") or "")[:300],
                "source": r.get("source"),
                "publishedAt": r.get("publishedAt"),
            }
            for r in reports[:20]
        ]
        inputs_hash = hashlib.sha1(json.dumps(corpus_material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        existing_overview = story.get("overview") or {}
        existing_paras = existing_overview.get("paragraphs") or []
        existing_is_en = _is_mostly_english(" ".join(str(p) for p in existing_paras))
        if existing_paras and story.get("overviewInputsHash") == inputs_hash and not existing_is_en:
            return existing_overview, inputs_hash, False

        latest_ms = milestones[0] if milestones else {}
        latest_line = f"{_format_beijing(latest_ms.get('occurredAt'))} · {latest_ms.get('title', story['title'])}" if latest_ms else ""
        zh_fallback_paras = [
            _clean_text(r.get("summary") or r.get("title"), max_len=260)
            for r in sorted(reports, key=lambda item: item.get("publishedAt") or "", reverse=True)
            if (r.get("summary") or r.get("title")) and not _is_mostly_english(r.get("summary") or r.get("title") or "")
        ][:2]
        fallback = {
            "paragraphs": zh_fallback_paras or [_clean_text(story["title"], max_len=160)],
            "latestMilestoneSummary": latest_line,
            "generatedBy": "rule",
        }
        if not allow_llm or not reports or (len(milestones) < 2 and not existing_is_en):
            return fallback, inputs_hash, True

        source_corpus = " ".join(f"{r.get('title', '')} {r.get('summary', '')}" for r in reports)
        try:
            prompt_payload = {
                "eventTitle": story["title"],
                "milestones": [{"time": _format_beijing(m.get("occurredAt")), "title": m.get("title")} for m in milestones[:8]],
                "reports": corpus_material[:12],
            }
            res = self._call_llm_json(
                "你是客观财经编辑。只能概括输入报道中已核实的事实，不得补充外部数字或投资建议。",
                (
                    "请为该持续财经事件生成「先了解这件事」的客观中文概览，返回严格 JSON 对象："
                    '{"paragraphs": ["100-180字事实总结段1", "可选补充段2"], "latestMilestoneSummary": "一句最新进展"}。'
                    "不得出现输入里没有的数字，不得预测涨跌或给出买卖建议：\n"
                    + json.dumps(prompt_payload, ensure_ascii=False)
                ),
            )
            if isinstance(res, dict) and isinstance(res.get("paragraphs"), list):
                paras = [str(p).strip() for p in res["paragraphs"] if isinstance(p, str) and p.strip()][:3]
                latest_sum = str(res.get("latestMilestoneSummary") or latest_line).strip()
                if paras and _passes_guardrails(" ".join(paras + [latest_sum]), source_corpus):
                    return {"paragraphs": paras, "latestMilestoneSummary": latest_sum, "generatedBy": "glm"}, inputs_hash, True
        except Exception:  # noqa: BLE001
            logger.exception("event overview generation failed")
        return fallback, inputs_hash, True

    def _rule_candidate_score(self, story: dict[str, Any], rep: dict[str, Any], now_dt: datetime) -> float:
        """Content-first deterministic recall score (no blind bias for routine bureaucratic notices)."""
        title = str(rep.get("title") or "")
        summary = str(rep.get("summary") or "")
        body_len = len(str(rep.get("bodyText") or ""))
        blob = f"{title} {summary[:240]}"
        pts = 20.0
        # Reward substantive market/company/macro catalysts
        if re.search(r"降息|加息|降准|CPI|PPI|PCE|GDP|非农|关税|制裁|霍尔木兹|原油|黄金|美债|财报|不及预期|超预期|暴涨|暴跌|大跌|大涨|放量|黄仁勋|英伟达|小米|苹果|微软|特斯拉|美联储", blob, re.I):
            pts += 22.0
        if body_len >= 400:
            pts += 8.0
        indep_count = len(independent_sources(story.get("reports") or [rep]))
        pts += min(24.0, indep_count * 7.0)
        pub = _parse(rep.get("publishedAt"))
        age_h = max(0.0, (now_dt - pub).total_seconds() / 3600.0) if pub else 24.0
        pts += max(0.0, 18.0 - age_h * 0.7)
        if _CLICKBAIT_RE.search(title):
            pts -= 25.0
        return pts

    def _score_and_classify_with_glm(self, candidates: list[dict[str, Any]], *, allow_llm: bool) -> tuple[dict[str, dict[str, Any]], bool]:
        """AIHOT-inspired 4-axis content-value scoring (sig/nov/reson/cred) + 3-section assignment + duplicateOf."""
        scores: dict[str, dict[str, Any]] = {}
        cand_by_key: dict[str, dict[str, Any]] = {}
        for c in candidates:
            cand_by_key[c["reportKey"]] = c
            scores[c["reportKey"]] = {
                "score": round(min(90.0, max(20.0, c["_ruleScore"])), 1),
                "bucket": c["bucket"],
                "drop": False,
                "duplicateOf": "",
            }

        if not allow_llm or not candidates:
            return scores, False

        compact = [
            {
                "reportKey": c["reportKey"],
                "bucket": c["bucket"],
                "title": c["title"][:130],
                "summary": c["summary"][:220],
                "independentSources": c["independentCount"],
            }
            for c in candidates[:48]
        ]

        def _eval_chunk(chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
            try:
                rows = self._call_llm_json(
                    "你是严格遵循 AIHOT 分项细则标准的客观金融日报选稿评审。只看事件本身对投资者的实质价值，不按媒体名气给分，只返回严格 JSON 数组。",
                    (
                        "请对以下候选新闻按 4 个维度分别打 0-100 分，并判定准确栏目 bucket：\n"
                        "【四维打分细则（必须逐项对照低/中/高标准，由程序按 35%/25%/25%/15% 算总分）】\n"
                        "1. sig（实质份量 35%）：\n"
                        "   - 高(80-100)：改写大类资产定价逻辑（央行超预期利率/降准、CPI/PCE/非农大幅偏离预期、重大关税/地缘升级、核心龙头重大突发或业绩明显超/不及预期、主要指数单日放量剧烈异动、油金美债利率大幅波动）\n"
                        "   - 中(50-79)：影响重点赛道或中期预期（头部大行调整利率路径或大盘定调、龙头常规财报或资本开支调整、行业级政策落地）\n"
                        "   - 低(0-49)：边缘小盘琐事、例行公文会议精神、纯情绪口水、花边生活稿\n"
                        "2. nov（信息增量 25%）：\n"
                        "   - 高(80-100)：一手新事实/反共识偏离预期/持续事件出现清晰新阶段转折/首次披露的关键量化数据\n"
                        "   - 中(50-79)：已有预期事件的新细则/时间表，或头部机构基于新数据的量化测算更新\n"
                        "   - 低(0-49)：炒冷饭、把昨天已知事实换角度写评论/社论、无新数字的常规盘面口水复述、每日早报/财经早餐汇总\n"
                        "3. reson（市场关注与讨论度 25%，参考 independentSources 独立报道数）：\n"
                        "   - 高(80-100)：当下全市场核心交易主线且多家权威源交叉报道（如美联储加息反转、AI算力泡沫争议、中美关税、英伟达/小米等高关注龙头、A股放量异动）\n"
                        "   - 中(50-79)：机构资金明确关注但未成全场焦点（1-2家权威源跟进）\n"
                        "   - 低(0-49)：绝大多数投资者不关心的冷门边缘话题\n"
                        "4. cred（证据强度 15%）：\n"
                        "   - 高(80-100)：官方正式发布/财报/交易所公告/实盘数据/核心当事人具名表态\n"
                        "   - 中(50-79)：权威媒体援引消息人士或头部投行正式研报量化测算\n"
                        "   - 低(0-49)：未经证实的小作文、模糊猜测或缺乏数据支撑的主观观点\n\n"
                        "【三栏精确归类与宁缺毋滥硬标准（核心原则：看「事件主体是谁」，绝不凑数！）】\n"
                        "- macro（宏观数据与政策）：央行货币政策/利率/加息概率、财政政策、国际政局与关税地缘、CPI/PPI/PCE/GDP/非农数据、国际黄金/原油期货/美债利率与汇率大势（民生类国内成品油零售调价直接 drop！）。\n"
                        "- market（市场表现）：A股/美股/港股/日股/韩股/欧股等整体指数走势、回调、大涨大跌、成交额、ETF资金流、股市救市/稳市措施、以及投行对股市大盘/指数的策略研判（如「摩根大通：日股这轮回调还没到头」「高盛看涨标普500」均归 market！）。\n"
                        "- companies（海外公司事件与财报）：宁缺毋滥！仅限全球或中国高关注度大型科技与行业龙头（如英伟达、苹果、微软、谷歌、亚马逊、Meta、特斯拉、台积电、AMD、英特尔、博通、美光、阿斯麦、戴尔、甲骨文、OpenAI、Anthropic、小米、阿里、腾讯、字节、拼多多、比亚迪、宁德时代、华为、美团、京东、平头哥、伯克希尔及大型跨国龙头）的重大事件、财报或权威评级变动（如「标普将英伟达列入负面观察」）。海外冷门小盘/微盘公司（普通投资者不熟悉的小市值工业、加密或地区小公司）的常规季报或订单，一律直接判 drop（sig<40、reson<30）！\n"
                        "- drop（严格淘汰）：海外冷门小公司财报/订单、国内汽油零售调价等民生稿、财经早餐/早报汇总/盘前必读合集、例行公文会议、小盘股琐事、低增量口水评论、花边生活稿。\n"
                        "若本批次两条新闻讲述同一具体事件，在较弱那条填写 duplicateOf 为更强那条的 reportKey。\n"
                        "返回严格 JSON 数组，每项字段：reportKey, sig, nov, reson, cred (均为 0-100 整数), bucket (macro|market|companies|drop), duplicateOf(可选)：\n"
                        + json.dumps(chunk, ensure_ascii=False)
                    ),
                )
                return rows if isinstance(rows, list) else []
            except Exception:  # noqa: BLE001
                logger.exception("AIHOT-style scoring chunk failed")
                return []

        chunks = [compact[i : i + 12] for i in range(0, len(compact), 12)]
        all_rows: list[dict[str, Any]] = []
        if len(chunks) == 1:
            all_rows = _eval_chunk(chunks[0])
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
                for part in pool.map(_eval_chunk, chunks):
                    all_rows.extend(part)

        llm_used = False
        scored_keys: set[str] = set()
        for row in all_rows:
            if not isinstance(row, dict):
                continue
            rkey = str(row.get("reportKey") or "")
            if rkey not in scores:
                continue
            sub_keys = ("sig", "nov", "reson", "cred")
            if all(row.get(k) is not None for k in sub_keys):
                try:
                    sig = max(0.0, min(100.0, float(row["sig"])))
                    nov = max(0.0, min(100.0, float(row["nov"])))
                    reson = max(0.0, min(100.0, float(row["reson"])))
                    cred = max(0.0, min(100.0, float(row["cred"])))
                except (TypeError, ValueError):
                    continue
                val = 0.35 * sig + 0.25 * nov + 0.25 * reson + 0.15 * cred
                # 宁缺毋滥硬淘汰线：四维单项一票否决
                veto = sig < 55.0 or nov < 50.0 or reson < 45.0 or cred < 50.0
            else:
                try:
                    val = max(0.0, min(100.0, float(row.get("score"))))
                except (TypeError, ValueError):
                    continue
                veto = False
            raw_bucket = str(row.get("bucket") or scores[rkey]["bucket"]).strip().lower()
            # 宁缺毋滥总分硬门槛：低于 62 分一律淘汰，绝不凑数
            drop = raw_bucket == "drop" or veto or val < 62.0
            bucket = raw_bucket if raw_bucket in _BUCKET_BY_KEY else scores[rkey]["bucket"]
            dup_of = str(row.get("duplicateOf") or "").strip()
            if dup_of == rkey or dup_of not in cand_by_key:
                dup_of = ""
            scores[rkey] = {"score": round(val, 1), "bucket": bucket, "drop": drop, "duplicateOf": dup_of}
            scored_keys.add(rkey)
            llm_used = True
        if llm_used:
            # 未被模型返回评分的候选同样卡死 62 分底线，不给漏网通行证
            for rkey, sc_row in scores.items():
                if rkey not in scored_keys and float(sc_row.get("score") or 0.0) < 62.0:
                    sc_row["drop"] = True
        return scores, llm_used

    def _enrich_and_write_selected(self, items: list[dict[str, Any]], *, allow_llm: bool, lead_key: str = "") -> bool:
        """Fetch full bodies where helpful, write answer-first Chinese headline+summary, and prepare long-read Markdown + TOC + K-line."""
        if not items:
            return False

        # Step 1: Concurrently fetch public article body for selected stories with short snippets
        # (and borrow fuller same-milestone corroborating body if the chosen headline came from a brief stub)
        def _maybe_fetch_body(it: dict[str, Any]) -> tuple[str, str]:
            existing = str(it.get("bodyText") or "").strip()
            if len(existing) >= 450:
                return it["reportKey"], existing
            spec = SOURCE_SPEC_BY_NAME.get(it.get("sourceName") or "")
            if spec and spec.allow_body_fetch and it.get("originalUrl"):
                fetched = self.body_fetcher(it["originalUrl"])
                if len(fetched) > len(existing):
                    existing = fetched
            if len(existing) < 420 and it.get("storyId"):
                st = self.store.get_tracked_story(it["storyId"])
                if st:
                    ms_id = it.get("milestoneId")
                    for ms in st.get("milestones") or []:
                        if ms_id and ms.get("milestoneId") != ms_id:
                            continue
                        for rep in ms.get("reports") or []:
                            cand_body = str(rep.get("bodyText") or rep.get("bodyMarkdown") or "").strip()
                            if len(cand_body) > len(existing) and len(cand_body) >= 450:
                                existing = cand_body
            return it["reportKey"], existing

        if allow_llm:
            body_executor = ThreadPoolExecutor(max_workers=6)
            body_futs = {body_executor.submit(_maybe_fetch_body, it): it for it in items}
            try:
                done_b, _ = wait(body_futs.keys(), timeout=12)
                for fut in done_b:
                    try:
                        rk, b = fut.result()
                        if b:
                            body_futs[fut]["bodyText"] = b
                    except Exception:  # noqa: BLE001
                        continue
            finally:
                body_executor.shutdown(wait=False, cancel_futures=True)

        # Step 2: AIHOT Answer-First Chinese headline + complete factual summary (80-160 chars; Lead 140-220 chars)
        changed = False
        if allow_llm:
            def _write_chunk(chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
                payload = [
                    {
                        "reportKey": it["reportKey"],
                        "isLead": bool(lead_key and it["reportKey"] == lead_key),
                        "title": it["title"][:160],
                        "material": (str(it.get("bodyText") or it.get("summary") or it["title"]))[:1400],
                    }
                    for it in chunk
                ]
                try:
                    rows = self._call_llm_json(
                        "你是严格遵循 AIHOT 答案前置规则的中文财经日报编辑。只输出严格 JSON 数组，绝不编造输入以外的数字、事实或投资建议。",
                        (
                            "请根据提供的标题和原文材料，为每条新闻生成高质量中文标题与答案前置事实摘要：\n"
                            "1. titleZh：100%自然简练的中文标题（英文新闻必须完整译成中文，保留 Nvidia/OpenAI/Meta/CPI/PCE/GDP 等常见缩写与原数字，不换算单位）。\n"
                            "2. summaryZh：答案前置中文摘要。若 isLead=true（头条），请写 140-220 字（3-4个紧凑陈述句），充分交代核心结论、关键数字、背景成因及市场影响；"
                            "普通条目写 90-160 字（2-3个紧凑陈述句）。第一句直接交代「谁做了什么、核心数字或结果是什么」；"
                            "禁用「据报道」「本文介绍」「文章讨论」等套话，不得短于标题，不得预测涨跌或给买卖建议。\n"
                            "返回严格 JSON 数组，每项字段：reportKey, titleZh, summaryZh：\n"
                            + json.dumps(payload, ensure_ascii=False)
                        ),
                        timeout_seconds=60,
                    )
                    return rows if isinstance(rows, list) else []
                except Exception:  # noqa: BLE001
                    logger.exception("answer-first writing chunk failed")
                    return []

            chunks = [items[i : i + 4] for i in range(0, len(items), 4)]
            written_rows: list[dict[str, Any]] = []
            if len(chunks) == 1:
                written_rows = _write_chunk(chunks[0])
            else:
                with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
                    for part in pool.map(_write_chunk, chunks):
                        written_rows.extend(part)

            by_key = {it["reportKey"]: it for it in items}
            for row in written_rows:
                if not isinstance(row, dict):
                    continue
                rk = str(row.get("reportKey") or "")
                it = by_key.get(rk)
                if not it:
                    continue
                corpus = f"{it['title']} {it.get('summary', '')} {str(it.get('bodyText') or '')[:3000]}"
                t_zh = _clean_text(row.get("titleZh") or "", max_len=140)
                s_zh = _clean_text(row.get("summaryZh") or "", max_len=300 if rk == lead_key else 240)
                if t_zh and _passes_guardrails(t_zh, corpus):
                    it.setdefault("originalTitle", it["title"])
                    it["title"] = t_zh
                    changed = True
                min_sum_len = 18 if _is_mostly_english(it.get("summary") or "") else max(28, len(it["title"]))
                if s_zh and len(s_zh) >= min_sum_len and _passes_guardrails(s_zh, corpus):
                    it["summary"] = s_zh
                    changed = True

            # Targeted retry for any remaining untranslated English titles/summaries OR summaries stuck equal to title
            still_weak = [
                it for it in items
                if _is_mostly_english(it["title"])
                or _is_mostly_english(it.get("summary") or "")
                or len(str(it.get("summary") or "").strip()) <= len(str(it["title"]).strip()) + 10
            ]
            if still_weak:
                retry_rows = _write_chunk(still_weak[:6])
                for row in retry_rows:
                    if not isinstance(row, dict):
                        continue
                    rk = str(row.get("reportKey") or "")
                    it = by_key.get(rk)
                    if not it:
                        continue
                    corpus = f"{it['title']} {it.get('summary', '')} {str(it.get('bodyText') or '')[:3000]}"
                    t_zh = _clean_text(row.get("titleZh") or "", max_len=140)
                    s_zh = _clean_text(row.get("summaryZh") or "", max_len=300 if rk == lead_key else 240)
                    if t_zh and not _is_mostly_english(t_zh) and _passes_guardrails(t_zh, corpus):
                        it.setdefault("originalTitle", it["title"])
                        it["title"] = t_zh
                        changed = True
                    if s_zh and not _is_mostly_english(s_zh) and len(s_zh) >= 18 and _passes_guardrails(s_zh, corpus):
                        it["summary"] = s_zh
                        changed = True

        # Deterministic lead-paragraph fallback: never leave summary identical to title when a clean bodyText exists
        for it in items:
            cur_sum = str(it.get("summary") or "").strip()
            cur_title = str(it.get("title") or "").strip()
            raw_b = str(it.get("bodyText") or "").strip()
            if raw_b and not _is_mostly_english(raw_b) and (cur_sum == cur_title or len(cur_sum) <= len(cur_title) + 10):
                prose_lines = [
                    re.sub(r"^[#>\-\s]+", "", ln).strip()
                    for ln in raw_b.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                joined_prose = " ".join(ln for ln in prose_lines if len(ln) >= 16 and ln != cur_title)
                if len(joined_prose) > len(cur_title) + 15:
                    it["summary"] = _clean_text(joined_prose, max_len=200)
                    changed = True

        # Prioritize flagship Lead + top-scored English long bodies for Chinese Markdown translation (up to 6)
        en_translate_keys: set[str] = set()
        if allow_llm:
            prioritized = sorted(
                items,
                key=lambda x: (1 if x["reportKey"] == lead_key else 0, float(x.get("finalScore") or 0.0)),
                reverse=True,
            )
            for it in prioritized:
                rb = str(it.get("bodyText") or "").strip()
                ml = 700 if it.get("bucket") == "market" else 380
                if len(rb) >= ml and len(rb) >= len(it.get("summary") or "") * 1.8 and _is_mostly_english(rb):
                    en_translate_keys.add(it["reportKey"])
                    if len(en_translate_keys) >= 6:
                        break

        # Step 3: Decide bodyMode ("full" vs "summary"), translate English long bodies to Chinese Markdown + TOC, attach K-line for market
        def _prepare_body(it: dict[str, Any]) -> tuple[str, str, str, list[dict[str, Any]], dict[str, str] | None]:
            rk = it["reportKey"]
            market_chart = detect_market_chart(it["title"], it.get("summary", "")) if it.get("bucket") == "market" else None
            raw_body = str(it.get("bodyText") or "").strip()
            min_len = 700 if it.get("bucket") == "market" else 380
            has_depth = len(raw_body) >= min_len and len(raw_body) >= len(it.get("summary") or "") * 1.8
            if not has_depth:
                return rk, "", "summary", [], market_chart

            if _is_mostly_english(raw_body):
                if not allow_llm or rk not in en_translate_keys:
                    return rk, "", "summary", [], market_chart
                try:
                    res = self._call_llm_json(
                        "你是专业财经翻译编辑。将英文财经报道忠实译为自然流畅的中文 Markdown 正文，保留原文数字、专有名词和结构，不增删事实，不给投资建议。",
                        (
                            "请把以下英文财经正文翻译为中文 Markdown；若正文较长（超过 900 字），请合理划分 2-4 个简洁的 `## 小节标题` 方便目录跳转。"
                            '返回严格 JSON 对象 `{"markdown": "..."}`：\n'
                            + raw_body[:3000]
                        ),
                        timeout_seconds=40,
                    )
                    md = str(res.get("markdown") or "").strip() if isinstance(res, dict) else ""
                    if md and len(md) >= 260 and _passes_guardrails(md, f"{it['title']} {raw_body[:3500]}"):
                        return rk, md, "full", extract_markdown_outline(md), market_chart
                except Exception:  # noqa: BLE001
                    logger.exception("long body translation failed for %s", rk)
                return rk, "", "summary", [], market_chart

            # Already Chinese long body
            md = raw_body[:6000].strip()
            outline = extract_markdown_outline(md)
            return rk, md, "full", outline, market_chart

        prep_executor = ThreadPoolExecutor(max_workers=4)
        prep_futs = {prep_executor.submit(_prepare_body, it): it for it in items}
        enriched_bodies: list[tuple[str, str, str, list[dict[str, Any]], dict[str, str] | None]] = []
        try:
            done_p, not_done_p = wait(prep_futs.keys(), timeout=45)
            for fut in done_p:
                try:
                    enriched_bodies.append(fut.result())
                except Exception:  # noqa: BLE001
                    it = prep_futs[fut]
                    mc = detect_market_chart(it["title"], it.get("summary", "")) if it.get("bucket") == "market" else None
                    enriched_bodies.append((it["reportKey"], "", "summary", [], mc))
            for fut in not_done_p:
                it = prep_futs[fut]
                mc = detect_market_chart(it["title"], it.get("summary", "")) if it.get("bucket") == "market" else None
                enriched_bodies.append((it["reportKey"], "", "summary", [], mc))
        finally:
            prep_executor.shutdown(wait=False, cancel_futures=True)

        for rk, body_md, body_mode, outline, market_chart in enriched_bodies:
            it = next((x for x in items if x["reportKey"] == rk), None)
            if not it:
                continue
            it["bodyMode"] = body_mode
            if market_chart:
                it["marketChart"] = market_chart
            self.store.apply_report_translation(
                rk,
                title_zh=it["title"],
                summary_zh=it["summary"],
                body_markdown=body_md,
                body_mode=body_mode,
                outline=outline,
                market_chart=market_chart,
            )
            changed = True
        return changed

    @staticmethod
    def _is_duplicate_story(a: dict[str, Any], b: dict[str, Any]) -> bool:
        if a["storyId"] == b["storyId"] or a["reportKey"] == b["reportKey"]:
            return True
        bg_a = _bigrams(headline(a["title"]))
        bg_b = _bigrams(headline(b["title"]))
        sim = _dice(bg_a, bg_b)
        if sim >= 0.45:
            return True
        ent_ov = len(extract_entities(a["title"], a.get("summary", "")) & extract_entities(b["title"], b.get("summary", "")))
        return ent_ov >= 2 and sim >= 0.25

    def _edition_window(self, target_date: str, target_type: str, now_utc: datetime) -> tuple[datetime, datetime, str]:
        """Return (window_start_utc, cutoff_utc, publish_label) with non-overlapping 18:00->08:00 / 08:00->18:00 windows."""
        dt_day = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=SHANGHAI)
        if target_type == "morning":
            # 早报 08:00：严格截取 昨日 18:00 ~ 今日 08:00（14 小时，零重叠）
            cutoff_bj = dt_day.replace(hour=8, minute=0, second=0, microsecond=0)
            start_bj = cutoff_bj - timedelta(hours=14)
            return start_bj.astimezone(UTC), cutoff_bj.astimezone(UTC), "昨18:00–今08:00"
        # 晚报 18:00：严格截取 今日 08:00 ~ 今日 18:00（10 小时，零重叠）
        cutoff_bj = dt_day.replace(hour=18, minute=0, second=0, microsecond=0)
        start_bj = dt_day.replace(hour=8, minute=0, second=0, microsecond=0)
        return start_bj.astimezone(UTC), cutoff_bj.astimezone(UTC), "今08:00–18:00"

    def compose_edition(
        self,
        *,
        edition_date: str | None = None,
        edition_type: str | None = None,
        refresh_upstream: bool = False,
        allow_llm: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self._compose_active = True
            try:
                return self._compose_edition_locked(
                    edition_date=edition_date,
                    edition_type=edition_type,
                    refresh_upstream=refresh_upstream,
                    allow_llm=allow_llm,
                )
            finally:
                self._compose_active = False

    def _compose_edition_locked(
        self,
        *,
        edition_date: str | None = None,
        edition_type: str | None = None,
        refresh_upstream: bool = False,
        allow_llm: bool = True,
    ) -> dict[str, Any]:
        now_bj = self.now_fn().astimezone(SHANGHAI)
        now_utc = now_bj.astimezone(UTC)
        target_date = edition_date or now_bj.strftime("%Y-%m-%d")
        target_type = edition_type if edition_type in {"morning", "evening"} else ("evening" if now_bj.hour >= 18 else "morning")
        edition_key = f"{target_date}-{target_type}"
        win_start_utc, cutoff_utc, cutoff_label = self._edition_window(target_date, target_type, now_utc)

        reports, source_statuses = self._collect_unified_pool(refresh_upstream=refresh_upstream)
        stories = self.ingest_to_stories(reports, allow_llm=allow_llm)

        # Prior edition milestones (avoid stale repeats unless there is a genuine new milestone)
        prior_milestone_ids: set[str] = set()
        for meta in self.store.list_daily_editions(limit=10):
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

        allowed_names = set(SOURCE_SPEC_BY_NAME.keys())

        def _collect_candidates(strict_cutoff: bool) -> list[dict[str, Any]]:
            pools: dict[str, list[dict[str, Any]]] = {row["key"]: [] for row in FINANCE_BUCKETS}
            upper_bound = cutoff_utc if strict_cutoff else now_utc
            lower_bound = win_start_utc if strict_cutoff else (now_utc - timedelta(hours=48))
            for story in stories:
                milestones = story.get("milestones") or []
                if not milestones:
                    continue
                latest_ms = milestones[0]
                is_new_ms = latest_ms["milestoneId"] not in prior_milestone_ids
                ms_dt = _parse(latest_ms.get("occurredAt"))
                if ms_dt:
                    if ms_dt < lower_bound or ms_dt > upper_bound + timedelta(minutes=15):
                        continue
                    age_h = (upper_bound - ms_dt).total_seconds() / 3600.0
                    if not is_new_ms and age_h > 14.0:
                        continue
                rep = next(
                    (r for r in (latest_ms.get("reports") or []) if r.get("reportKey") == latest_ms.get("representativeReportKey")),
                    (latest_ms.get("reports") or [None])[0],
                )
                if not rep or not _safe_http_url(rep.get("originalUrl")):
                    continue
                if self.official_fetcher is None and str(rep.get("source") or "") not in allowed_names:
                    continue
                if not _has_market_relevance(rep):
                    continue
                bucket = story.get("bucket") if story.get("bucket") in _BUCKET_BY_KEY else classify_bucket(rep["title"], rep.get("summary", ""), "", rep["source"])
                indep_count = len(independent_sources(story.get("reports") or [rep]))
                grade = _effective_grade(rep, self.registry)
                cand = {
                    "reportKey": rep["reportKey"],
                    "storyId": story["storyId"],
                    "milestoneId": latest_ms["milestoneId"],
                    "milestoneCount": len(milestones),
                    "reportCount": len(story.get("reports") or []),
                    "bucket": bucket,
                    "title": _clean_text(rep["title"], max_len=160),
                    "summary": _clean_text(rep.get("summary") or rep["title"], max_len=320),
                    "bodyText": str(rep.get("bodyText") or ""),
                    "sourceName": rep["source"],
                    "sourceTierGrade": grade,
                    "official": bool(rep.get("official") or grade == "S"),
                    "publishedAt": rep.get("publishedAt"),
                    "timeLabel": _format_beijing(rep.get("publishedAt")),
                    "originalUrl": rep["originalUrl"],
                    "independentCount": indep_count,
                    "isNewMilestone": is_new_ms,
                    "_ruleScore": self._rule_candidate_score(story, rep, upper_bound),
                }
                pools[bucket].append(cand)
            out: list[dict[str, Any]] = []
            for key in pools:
                pools[key].sort(key=lambda item: item["_ruleScore"], reverse=True)
                out.extend(pools[key][:16])
            return out

        recalled = _collect_candidates(strict_cutoff=True)
        # 宁缺毋滥：仅当严切窗口内不足 3 条（如极端节假日休市）才回退放宽时间窗，且绝不降低 62 分质量门槛
        if len(recalled) < 3:
            recalled = _collect_candidates(strict_cutoff=False)

        # Stage B: AIHOT-style 4-axis content-value scoring & cross-outlet duplicate folding
        score_map, llm_used = self._score_and_classify_with_glm(recalled, allow_llm=allow_llm)
        by_key = {c["reportKey"]: c for c in recalled}
        dropped_keys: set[str] = set()
        merged_any = False
        for cand in recalled:
            sc = score_map.get(cand["reportKey"]) or {}
            if sc.get("drop"):
                dropped_keys.add(cand["reportKey"])
                continue
            dup_target = str(sc.get("duplicateOf") or "").strip()
            if dup_target and dup_target != cand["reportKey"] and dup_target in by_key:
                if dup_target not in dropped_keys and cand["reportKey"] not in dropped_keys:
                    target_cand = by_key[dup_target]
                    target_cand["independentCount"] += 1
                    dropped_keys.add(cand["reportKey"])
                    if target_cand["storyId"] != cand["storyId"]:
                        self.store.merge_tracked_stories(
                            target_story_id=target_cand["storyId"],
                            duplicate_story_id=cand["storyId"],
                        )
                        merged_story = self.store.get_tracked_story(target_cand["storyId"])
                        if merged_story:
                            target_cand["reportCount"] = len(merged_story.get("reports") or [])
                            target_cand["milestoneCount"] = len(merged_story.get("milestones") or [])
                        merged_any = True

        filtered: list[dict[str, Any]] = []
        for cand in recalled:
            if cand["reportKey"] in dropped_keys:
                continue
            sc = score_map.get(cand["reportKey"]) or {"score": 50.0, "bucket": cand["bucket"]}
            cand["bucket"] = sc["bucket"]
            title_txt = cand["title"]
            summary_txt = cand.get("summary") or ""
            # Deterministic post-guards preventing common LLM bucket misclassifications
            if re.search(r"Q[1-4]营收|季报|财报|交付指引|营收同增|营收同比|earnings|quarterly results", title_txt, re.I):
                cand["bucket"] = "companies"
            elif _MARKET_RE.search(title_txt) and not _COMPANIES_RE.search(title_txt):
                cand["bucket"] = "market"
            elif _BANK_COMMENTARY_PREFIX_RE.search(title_txt):
                if _MARKET_RE.search(f"{title_txt} {summary_txt[:220]}"):
                    cand["bucket"] = "market"
                elif _MACRO_RE.search(f"{title_txt} {summary_txt[:220]}"):
                    cand["bucket"] = "macro"
            elif _MACRO_RE.search(title_txt) and not _COMPANIES_RE.search(title_txt) and not _MARKET_RE.search(title_txt):
                cand["bucket"] = "macro"
            # 宁缺毋滥硬卡死：03 公司栏目只允许头部知名龙头或 >=2 家独立权威源交叉验证的大事件，彻底挡掉海外冷门小盘股
            if cand["bucket"] == "companies" and allow_llm:
                if not _MAJOR_COMPANIES_RE.search(f"{title_txt} {summary_txt[:240]}") and cand["independentCount"] < 2:
                    continue
            cand["finalScore"] = round(float(sc["score"]) + min(10.0, (cand["independentCount"] - 1) * 3.0), 2)
            filtered.append(cand)
        filtered.sort(key=lambda item: (item["finalScore"], item["independentCount"]), reverse=True)

        # Stage C: 1 Lead (strongly preferring stories with full article depth) + 3 Thematic Sections + 3 Key Picks
        def _depth_potential(c: dict[str, Any]) -> bool:
            if len(str(c.get("bodyText") or "")) >= 400 or len(str(c.get("summary") or "")) >= 180:
                return True
            spec = SOURCE_SPEC_BY_NAME.get(c.get("sourceName") or "")
            return bool(spec and spec.allow_body_fetch)

        lead = (
            max(
                filtered[:10],
                key=lambda item: (
                    float(item["finalScore"]) + (10.0 if _depth_potential(item) else -10.0),
                    len(str(item.get("bodyText") or "")),
                    item["independentCount"],
                ),
            )
            if filtered else None
        )
        chosen_all: list[dict[str, Any]] = [lead] if lead else []
        source_counts: dict[str, int] = {lead["sourceName"]: 1} if lead else {}
        lead_company_ents = (extract_entities(lead["title"], lead.get("summary", "")) & _COMPANY_ENTITIES) if lead else set()

        sections_out: list[dict[str, Any]] = []
        all_section_items: list[dict[str, Any]] = []
        for meta in FINANCE_BUCKETS:
            chosen: list[dict[str, Any]] = []
            sec_company_ents: set[str] = set(lead_company_ents) if meta["key"] == "companies" else set()
            for cand in filtered:
                if cand["bucket"] != meta["key"]:
                    continue
                if any(self._is_duplicate_story(cand, existing) for existing in chosen_all):
                    continue
                cand_company_ents = extract_entities(cand["title"], cand.get("summary", "")) & _COMPANY_ENTITIES
                if cand_company_ents and (cand_company_ents & sec_company_ents):
                    # Keep at most 1 headline per major company/CEO in the same section so one company never dominates
                    continue
                if source_counts.get(cand["sourceName"], 0) >= 3:
                    continue
                source_counts[cand["sourceName"]] = source_counts.get(cand["sourceName"], 0) + 1
                sec_company_ents |= cand_company_ents
                chosen_all.append(cand)
                item_out = {
                    **{k: v for k, v in cand.items() if not k.startswith("_")},
                    "sectionCode": meta["code"],
                    "sectionName": meta["name"],
                }
                chosen.append(item_out)
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

        lead_clean = (
            {
                **{k: v for k, v in lead.items() if not k.startswith("_")},
                "sectionCode": _BUCKET_BY_KEY[lead["bucket"]]["code"],
                "sectionName": _BUCKET_BY_KEY[lead["bucket"]]["name"],
            }
            if lead else None
        )

        # Stage D: Full-body fetch + Answer-first Chinese writing + Long-body translation/TOC + Market K-line
        selected_cards = ([lead_clean] if lead_clean else []) + all_section_items
        enriched_any = self._enrich_and_write_selected(
            selected_cards,
            allow_llm=allow_llm,
            lead_key=(lead_clean["reportKey"] if lead_clean else ""),
        )
        for card in selected_cards:
            card.pop("bodyText", None)

        # 宁缺毋滥：若某条既无完整正文、又无 K 线图、且摘要仍等于标题（一句话空壳短讯），直接从版面剔除
        if allow_llm:
            def _is_bare_stub(card: dict[str, Any]) -> bool:
                s = str(card.get("summary") or "").strip()
                t = str(card.get("title") or "").strip()
                return (
                    card.get("bodyMode") != "full"
                    and not card.get("marketChart")
                    and (s == t or len(s) <= len(t) + 6)
                )

            for sec in sections_out:
                sec["items"] = [it for it in sec["items"] if not _is_bare_stub(it)]
            all_section_items = [it for sec in sections_out for it in sec["items"]]
            if lead_clean and _is_bare_stub(lead_clean) and all_section_items:
                best_sec = max(
                    (s for s in sections_out if s["items"]),
                    key=lambda s: float(s["items"][0].get("finalScore") or 0),
                    default=None,
                )
                if best_sec:
                    lead_clean = best_sec["items"].pop(0)
                    all_section_items = [it for sec in sections_out for it in sec["items"]]
            selected_cards = ([lead_clean] if lead_clean else []) + all_section_items

        # Guarantee Lead has substantive depth: if Lead still ended up without full body & with a short summary,
        # promote the highest-scoring full-body story from sections and place the old lead into its section.
        if lead_clean and lead_clean.get("bodyMode") != "full" and len(str(lead_clean.get("summary") or "")) < 130:
            full_candidates = [
                (sec, idx, it)
                for sec in sections_out
                for idx, it in enumerate(sec["items"])
                if it.get("bodyMode") == "full" and float(it.get("finalScore") or 0) >= float(lead_clean.get("finalScore") or 0) - 12.0
            ]
            if full_candidates:
                full_candidates.sort(key=lambda tup: float(tup[2].get("finalScore") or 0), reverse=True)
                best_sec, best_idx, best_item = full_candidates[0]
                old_lead = lead_clean
                lead_clean = best_item
                best_sec["items"].pop(best_idx)
                target_sec = next((s for s in sections_out if s["key"] == old_lead["bucket"]), best_sec)
                target_sec["items"].insert(0, old_lead)
                all_section_items = [it for sec in sections_out for it in sec["items"]]

        # Pick 3 Key Picks strictly from the 3 sections, strongly preferring stories with full body or K-line chart
        def _pick_rank(item: dict[str, Any]) -> tuple[float, float, int]:
            depth_tier = 2.0 if item.get("bodyMode") == "full" else (1.0 if item.get("marketChart") else 0.0)
            return (depth_tier, float(item.get("finalScore") or 0.0), len(str(item.get("summary") or "")))

        picks_pool = sorted(all_section_items, key=_pick_rank, reverse=True)
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
            picked = {p["reportKey"] for p in key_picks}
            for item in picks_pool:
                if item["reportKey"] in picked:
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

        if merged_any or enriched_any:
            stories = self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)

        # Consolidate redundant same-day milestones & translate any English milestone titles on selected stories
        selected_sids = {c["storyId"] for c in selected_cards if c.get("storyId")}
        consolidated_any = False
        english_ms_entries: list[dict[str, str]] = []
        for st in stories:
            if st["storyId"] not in selected_sids:
                continue
            if self._consolidate_story_milestones(st):
                consolidated_any = True
        if consolidated_any:
            stories = self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)
        if allow_llm:
            for st in stories:
                if st["storyId"] not in selected_sids:
                    continue
                for ms in st.get("milestones") or []:
                    rep_key = ms.get("representativeReportKey") or ""
                    title = ms.get("title") or ""
                    if rep_key and _is_mostly_english(title):
                        english_ms_entries.append({"reportKey": rep_key, "title": title})
            if english_ms_entries:
                self._translate_english_titles(english_ms_entries, persist=True)
                stories = self.store.list_active_stories(days=TRACKED_WINDOW_DAYS)

        # Precompute multi-milestone event overviews concurrently
        story_by_id = {st["storyId"]: st for st in stories}
        multi_sids = [
            sid for sid in ({c["storyId"] for c in selected_cards})
            if sid in story_by_id and len(story_by_id[sid].get("milestones") or []) >= 2
        ][:6]
        if multi_sids:
            with ThreadPoolExecutor(max_workers=4) as pool:
                ov_results = list(pool.map(lambda s: (s, self._prepare_event_overview(story_by_id[s], allow_llm=allow_llm)), multi_sids))
            for sid, (ov, inputs_hash, ov_changed) in ov_results:
                if ov_changed:
                    self.store.update_tracked_overview(sid, ov, inputs_hash)

        calendar_data = (
            self.news_service.calendar.overview()
            if hasattr(self.news_service, "calendar")
            else {"items": [], "partial": False, "stale": False, "sources": []}
        )

        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
        date_label = f"{dt_obj.year} 年 {dt_obj.month} 月 {dt_obj.day} 日 · 星期{weekday_names[dt_obj.weekday()]}"

        payload = {
            "editionKey": edition_key,
            "promptVersion": PROMPT_VERSION,
            "editionDate": target_date,
            "editionType": target_type,
            "editionTag": "早刊" if target_type == "morning" else "晚刊",
            "publishTimeLabel": cutoff_label,
            "dateLabel": date_label,
            "dayNumber": f"{dt_obj.day:02d}",
            "generatedAt": now_utc.isoformat(),
            "lead": lead_clean,
            "keyPicks": key_picks,
            "sections": sections_out,
            "calendar": calendar_data,
            "storyCount": len(selected_cards),
            "editorialEngine": "glm" if llm_used else "rule",
        }
        snap_hash = hashlib.sha1(json.dumps(
            {"lead": lead_clean["reportKey"] if lead_clean else None, "sections": [i["reportKey"] for i in all_section_items]},
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

    def _initializing_skeleton(self, edition_type: str | None = None) -> dict[str, Any]:
        now_bj = self.now_fn().astimezone(SHANGHAI)
        now_utc = now_bj.astimezone(UTC)
        target_date = now_bj.strftime("%Y-%m-%d")
        target_type = edition_type if edition_type in {"morning", "evening"} else ("evening" if now_bj.hour >= 18 else "morning")
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        date_label = f"{now_bj.year} 年 {now_bj.month} 月 {now_bj.day} 日 · 星期{weekday_names[now_bj.weekday()]}"
        calendar_data = (
            self.news_service.calendar.overview()
            if hasattr(self.news_service, "calendar")
            else {"items": [], "partial": False, "stale": False, "sources": []}
        )
        return {
            "editionKey": f"{target_date}-{target_type}",
            "promptVersion": PROMPT_VERSION,
            "editionDate": target_date,
            "editionType": target_type,
            "editionTag": "早刊" if target_type == "morning" else "晚刊",
            "publishTimeLabel": "截至 08:00 截稿" if target_type == "morning" else "截至 18:00 截稿",
            "dateLabel": date_label,
            "dayNumber": f"{now_bj.day:02d}",
            "generatedAt": now_utc.isoformat(),
            "lead": None,
            "keyPicks": [],
            "sections": [
                {"key": meta["key"], "code": meta["code"], "name": meta["name"], "note": meta["note"], "items": []}
                for meta in FINANCE_BUCKETS
            ],
            "calendar": calendar_data,
            "storyCount": 0,
            "editorialEngine": "rule",
            "refreshing": True,
            "initializing": True,
        }

    def latest_edition(self, edition_type: str | None = None) -> dict[str, Any]:
        stored = self.store.get_latest_daily_edition(edition_type=edition_type)
        if stored:
            return {**stored, "refreshing": self.is_refreshing()}

        now_bj = self.now_fn().astimezone(SHANGHAI)
        if edition_type == "evening" and now_bj.hour < 18:
            fallback = self.store.get_latest_daily_edition(edition_type=None)
            if fallback:
                return {
                    **fallback,
                    "refreshing": self.is_refreshing(),
                    "requestedEditionPending": {
                        "editionType": "evening",
                        "message": "今日晚报将于 18:00 定时出刊，当前为您展示已出刊的早报",
                    },
                }
        if edition_type == "morning" and now_bj.hour < 8:
            fallback = self.store.get_latest_daily_edition(edition_type=None)
            if fallback:
                return {
                    **fallback,
                    "refreshing": self.is_refreshing(),
                    "requestedEditionPending": {
                        "editionType": "morning",
                        "message": "今日早报将于 08:00 定时出刊，当前为您展示上一期晚报",
                    },
                }

        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return self._initializing_skeleton(edition_type=edition_type)
        try:
            stored_again = self.store.get_latest_daily_edition(edition_type=edition_type)
            if stored_again:
                return {**stored_again, "refreshing": self.is_refreshing()}
            built = self.compose_edition(edition_type=edition_type, refresh_upstream=False, allow_llm=False)
            return {**built, "refreshing": self.is_refreshing()}
        finally:
            self._lock.release()

    def get_edition(self, edition_key: str) -> dict[str, Any] | None:
        item = self.store.get_daily_edition(edition_key)
        if not item:
            return None
        return {**item, "refreshing": self.is_refreshing()}

    def refresh_now(self, edition_type: str | None = None) -> dict[str, Any]:
        return self.compose_edition(edition_type=edition_type, refresh_upstream=True, allow_llm=True)

    def request_refresh(self, edition_type: str | None = None) -> dict[str, Any]:
        now_bj = self.now_fn().astimezone(SHANGHAI)
        target_type = (
            edition_type
            if edition_type in {"morning", "evening"}
            else ("evening" if now_bj.hour >= 18 else "morning")
        )
        if target_type == "evening" and now_bj.hour < 18:
            target_type = "morning"

        started = self._refresh_lock.acquire(blocking=False)
        if started:
            def _worker() -> None:
                try:
                    self.compose_edition(edition_type=target_type, refresh_upstream=True, allow_llm=True)
                except Exception:  # noqa: BLE001
                    logger.exception("background financial daily refresh failed")
                finally:
                    self._refresh_lock.release()

            self._refresh_thread = threading.Thread(
                target=_worker,
                name="financial-daily-manual-refresh",
                daemon=True,
            )
            self._refresh_thread.start()

        current = self.store.get_latest_daily_edition(edition_type=target_type) or self.store.get_latest_daily_edition()
        if not current:
            current = self._initializing_skeleton(edition_type=target_type)
        return {
            **current,
            "refreshing": True,
            "refreshOutcome": "started" if started else "already_running",
        }

    def get_report_detail(self, report_key: str) -> dict[str, Any] | None:
        report = self.store.get_report_detail(report_key)
        if not report:
            return None
        now_utc = self.now_fn().astimezone(UTC)
        bucket = report.get("bucket") if report.get("bucket") in _BUCKET_BY_KEY else classify_bucket(
            report["title"], report.get("summary", ""), str(report.get("track") or ""), report["source"]
        )
        bucket_meta = _BUCKET_BY_KEY.get(bucket, FINANCE_BUCKETS[0])
        story_id = report.get("storyId")
        current_milestone_id = report.get("milestoneId")
        story = self.store.get_tracked_story(story_id) if story_id else None

        # AIHOT-style incremental followups: ONLY other distinct milestones (1 representative per milestone), NEVER same-fact duplicates
        followups: list[dict[str, Any]] = []
        same_node_reports: list[dict[str, Any]] = []
        event_summary = None
        if story:
            if self._consolidate_story_milestones(story):
                story = self.store.get_tracked_story(story_id) or story
            milestones = story.get("milestones") or []
            for ms in milestones:
                ms_reps = ms.get("reports") or []
                if current_milestone_id and ms["milestoneId"] == current_milestone_id:
                    for r in ms_reps:
                        rk_other = r.get("reportKey") or r.get("id")
                        if not rk_other or rk_other == report_key:
                            continue
                        same_node_reports.append({
                            "reportKey": rk_other,
                            "title": r["title"],
                            "sourceName": r["source"],
                            "timeLabel": _format_beijing(r.get("publishedAt")),
                            "originalUrl": r.get("originalUrl"),
                        })
                    continue
                rep = next((r for r in ms_reps if r.get("reportKey") == ms.get("representativeReportKey")), ms_reps[0] if ms_reps else None)
                if not rep or rep.get("reportKey") == report_key:
                    continue
                followups.append({
                    "reportKey": rep["reportKey"],
                    "milestoneId": ms["milestoneId"],
                    "title": ms.get("title") or rep["title"],
                    "sourceName": rep["source"],
                    "publishedAt": ms.get("occurredAt") or rep.get("publishedAt"),
                    "timeLabel": _format_beijing(ms.get("occurredAt") or rep.get("publishedAt")),
                    "relativeTime": _relative_time(ms.get("occurredAt") or rep.get("publishedAt"), now_utc),
                    "originalUrl": rep.get("originalUrl"),
                    "role": "milestone",
                })
            # Ensure zero untranslated English titles in followups or same-node corroborating sources
            en_batch = [
                {"reportKey": item["reportKey"], "title": item["title"]}
                for item in followups + same_node_reports
                if _is_mostly_english(item["title"])
            ]
            if en_batch:
                zh_map = self._translate_english_titles(en_batch, persist=True)
                for item in followups:
                    if item["reportKey"] in zh_map:
                        item["title"] = zh_map[item["reportKey"]]
                for item in same_node_reports:
                    if item["reportKey"] in zh_map:
                        item["title"] = zh_map[item["reportKey"]]
            if len(milestones) >= 2:
                event_summary = {
                    "storyId": story["storyId"],
                    "title": story["title"],
                    "reportCount": len(story.get("reports") or []),
                    "milestoneCount": len(milestones),
                }

        body_markdown = str(report.get("bodyMarkdown") or "").strip()
        if body_markdown and sum(1 for kw in _BOILERPLATE_BODY_SIGNALS if kw in body_markdown[:450]) >= 2:
            body_markdown = ""
        body_mode = "full" if (str(report.get("bodyMode") or "") == "full" and len(body_markdown) >= 240) else "summary"
        outline = report.get("outline") if isinstance(report.get("outline"), list) else extract_markdown_outline(body_markdown)
        market_chart = report.get("marketChart") if isinstance(report.get("marketChart"), dict) else (
            detect_market_chart(report["title"], report.get("summary", "")) if bucket == "market" else None
        )

        return {
            "reportKey": report["reportKey"],
            "title": report["title"],
            "originalTitle": report.get("originalTitle") or "",
            "summary": report.get("summary") or report["title"],
            "bodyMode": body_mode,
            "bodyMarkdown": body_markdown if body_mode == "full" else "",
            "outline": outline if body_mode == "full" else [],
            "marketChart": market_chart,
            "publishedAt": report.get("publishedAt"),
            "timeLabel": _format_beijing(report.get("publishedAt")),
            "relativeTime": _relative_time(report.get("publishedAt"), now_utc),
            "sourceName": report["source"],
            "sourceTier": "官方原文" if report.get("official") or _effective_grade(report, self.registry) == "S" else "公开报道",
            "originalUrl": report.get("originalUrl"),
            "bucket": bucket,
            "bucketName": bucket_meta["name"],
            "eventSummary": event_summary,
            "followups": followups,
            "sameNodeReports": same_node_reports,
        }

    def get_tracked_event(self, story_id: str) -> dict[str, Any] | None:
        story = self.store.get_tracked_story(story_id)
        if not story:
            return None
        if self._consolidate_story_milestones(story):
            story = self.store.get_tracked_story(story_id) or story
        en_ms = [
            {"reportKey": ms.get("representativeReportKey") or "", "title": ms.get("title") or ""}
            for ms in (story.get("milestones") or [])
            if ms.get("representativeReportKey") and _is_mostly_english(ms.get("title") or "")
        ]
        if en_ms:
            if self._translate_english_titles(en_ms, persist=True):
                story = self.store.get_tracked_story(story_id) or story
        now_utc = self.now_fn().astimezone(UTC)
        ex_ov = story.get("overview") or {}
        need_zh_ov = _is_mostly_english(" ".join(str(p) for p in (ex_ov.get("paragraphs") or [])))
        overview, inputs_hash, changed = self._prepare_event_overview(story, allow_llm=need_zh_ov)
        if changed:
            self.store.update_tracked_overview(story_id, overview, inputs_hash)
        why_hot = self.compute_heat_and_why_hot(story, now=now_utc)
        heat_series = self._build_heat_series(story)
        bucket_meta = _BUCKET_BY_KEY.get(story.get("bucket") or "macro", FINANCE_BUCKETS[0])

        milestones_out: list[dict[str, Any]] = []
        for ms in story.get("milestones") or []:
            ms_reports = [
                {
                    "reportKey": rep.get("reportKey") or rep.get("id"),
                    "title": rep["title"],
                    "sourceName": rep["source"],
                    "sourceTier": "官方原文" if rep.get("official") or _effective_grade(rep, self.registry) == "S" else "精选报道",
                    "publishedAt": rep.get("publishedAt"),
                    "timeLabel": _format_beijing(rep.get("publishedAt")),
                    "originalUrl": rep.get("originalUrl"),
                }
                for rep in (ms.get("reports") or [])
            ]
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
                "sourceTier": "官方原文" if rep.get("official") or _effective_grade(rep, self.registry) == "S" else "精选报道",
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
            "tags": [bucket_meta["name"]],
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

        if now_bj.hour < 18:
            self.service.store.delete_daily_edition(f"{today}-evening")

        # Prioritize the currently active edition first (evening first after 18:00),
        # and reuse the freshly fetched 44-source cache if backfilling the earlier edition.
        ordered_types = ("evening", "morning") if now_bj.hour >= 18 else ("morning",)
        refreshed_this_cycle = False
        for ed_type in ordered_types:
            min_hour = 18 if ed_type == "evening" else 8
            if now_bj.hour < min_hour:
                continue
            ed_key = f"{today}-{ed_type}"
            existing_ed = self.service.get_edition(ed_key)
            if not existing_ed or existing_ed.get("promptVersion") != PROMPT_VERSION:
                self.service.compose_edition(
                    edition_date=today,
                    edition_type=ed_type,
                    refresh_upstream=(self.refresh_upstream and not refreshed_this_cycle),
                    allow_llm=True,
                )
                refreshed_this_cycle = True
                generated.append(ed_key)

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
