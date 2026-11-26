"""Dedicated 44-source Financial Daily collector with full-body preservation.

Strictly isolated from the 110-source general tech radar and 7x24 quick wires.
Covers the 44 verified financial, official, market, commodity, and global
company sources approved for the dual-edition Financial Daily.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from data_paths import cache_path
from financial_hotlist import parse_cls_headline_html, parse_eastmoney_editorial_html

logger = logging.getLogger(__name__)

SHANGHAI = timezone(timedelta(hours=8))
UTC = timezone.utc
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_SECONDS = 8
BATCH_TIMEOUT_SECONDS = 22
MAX_ITEMS_PER_SOURCE = 20
MAX_BODY_CHARS = 14000

_REDLINE_RE = re.compile(
    r"赌博|博彩|赌场|彩票|下注|押注|预测市场|polymarket|kalshi|prediction market|"
    r"加密货币|虚拟货币|比特币|以太坊|稳定币|crypto|bitcoin|ethereum|stablecoin|"
    r"gambling|betting|casino|lottery|sportsbook|色情|porn",
    re.I,
)
_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
_IGNORE_TITLES = {
    "首页", "更多", "查看更多", "更多>>", "上一页", "下一页", "尾页",
    "关于我们", "联系我们", "网站地图", "版权声明", "English", "RSS", "Skip to main content",
}


@dataclass(frozen=True)
class DailySourceSpec:
    source_id: str
    name: str
    group: str  # official_cn | official_global | media_cn | media_global
    kind: str   # rss | html | json | hotlist
    url: str
    tier: str   # S | A | B
    score: int
    official: bool = False
    default_bucket: str = "macro"
    link_hints: tuple[str, ...] = ()
    allow_body_fetch: bool = False


# Exact 44 live-verified financial daily sources (confirmed 2026-11-25)
DAILY_SOURCES: tuple[DailySourceSpec, ...] = (
    # --- 国内官方政策与监管 (11) ---
    DailySourceSpec("pbc", "中国人民银行", "official_cn", "html", "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html", "S", 35, True, "macro", ("113469", "goutongjiaoliu", ".html", ".shtml"), True),
    DailySourceSpec("csrc", "证监会", "official_cn", "html", "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml", "S", 35, True, "macro", ("csrc/", ".shtml", ".html"), True),
    DailySourceSpec("gov", "中国政府网", "official_cn", "json", "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json", "S", 35, True, "macro", (), True),
    DailySourceSpec("nfra", "国家金融监督管理总局", "official_cn", "json", "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectDocByItemIdAndChild?itemId=915&pageSize=18&pageIndex=1", "S", 35, True, "macro", (), False),
    DailySourceSpec("stats", "国家统计局", "official_cn", "html", "https://www.stats.gov.cn/sj/zxfb/", "S", 35, True, "macro", ("/sj/zxfb/", ".html"), True),
    DailySourceSpec("mof", "财政部", "official_cn", "html", "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/", "S", 35, True, "macro", ("/caizhengxinwen/", ".htm", ".html"), True),
    DailySourceSpec("ndrc", "国家发展改革委", "official_cn", "html", "https://www.ndrc.gov.cn/xwdt/xwfb/", "S", 35, True, "macro", ("/xwfb/", "/xwdt/", ".html"), True),
    DailySourceSpec("mofcom", "商务部", "official_cn", "html", "https://www.mofcom.gov.cn/xwfb/index.html", "S", 35, True, "macro", ("/xwfb/", "/art/", ".html"), True),
    DailySourceSpec("safe", "国家外汇管理局", "official_cn", "html", "https://www.safe.gov.cn/safe/whxw/index.html", "S", 35, True, "macro", ("/safe/", ".html"), True),
    DailySourceSpec("sse", "上交所", "official_cn", "html", "https://www.sse.com.cn/aboutus/mediacenter/hotandd/", "S", 35, True, "market", ("/aboutus/", "/mediacenter/", ".shtml", ".html"), True),
    DailySourceSpec("miit", "工业和信息化部", "official_cn", "html", "https://www.miit.gov.cn/", "S", 35, True, "macro", ("/art/", "/zwgk/", "/xwdt/", ".html"), True),
    # --- 全球央行与官方监管 (10) ---
    DailySourceSpec("fed", "Federal Reserve", "official_global", "rss", "https://www.federalreserve.gov/feeds/press_all.xml", "S", 35, True, "macro", (), True),
    DailySourceSpec("sec", "SEC", "official_global", "rss", "https://www.sec.gov/news/pressreleases.rss", "S", 35, True, "companies", (), True),
    DailySourceSpec("us-treasury", "美国财政部", "official_global", "html", "https://home.treasury.gov/news/press-releases", "S", 35, True, "macro", ("/news/press-releases/",), True),
    DailySourceSpec("bea", "美国经济分析局", "official_global", "rss", "https://apps.bea.gov/rss/rss.xml", "S", 35, True, "macro", (), True),
    DailySourceSpec("ecb", "European Central Bank", "official_global", "rss", "https://www.ecb.europa.eu/rss/press.html", "S", 35, True, "macro", (), True),
    DailySourceSpec("boe", "英国央行", "official_global", "rss", "https://www.bankofengland.co.uk/rss/news", "S", 35, True, "macro", (), True),
    DailySourceSpec("boj", "日本央行", "official_global", "rss", "https://www.boj.or.jp/en/rss/whatsnew.xml", "S", 35, True, "macro", (), False),
    DailySourceSpec("bis", "国际清算银行", "official_global", "rss", "https://www.bis.org/doclist/all_pressrels.rss", "S", 35, True, "macro", (), True),
    DailySourceSpec("hkex", "香港交易所", "official_global", "rss", "https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=zh-HK", "S", 35, True, "market", (), True),
    DailySourceSpec("hkma", "香港金管局", "official_global", "rss", "https://www.hkma.gov.hk/eng/other-information/rss/rss_press-release.xml", "S", 35, True, "macro", (), True),
    # --- 中文深度财经媒体与编辑精选要闻 (9) ---
    DailySourceSpec("yicai", "第一财经", "media_cn", "json", "https://www.yicai.com/api/ajax/getlatest?page=1&pagesize=35", "A", 30, False, "macro", (), True),
    DailySourceSpec("wallstreetcn", "华尔街见闻", "media_cn", "rss", "https://dedicated.wallstreetcn.com/rss.xml", "A", 32, False, "macro", (), False),
    DailySourceSpec("ftchinese", "FT中文网", "media_cn", "rss", "https://www.ftchinese.com/rss/news", "A", 30, False, "companies", (), True),
    DailySourceSpec("nikkei-cn", "日经中文网", "media_cn", "rss", "https://cn.nikkei.com/rss.html", "A", 28, False, "macro", (), True),
    DailySourceSpec("eastmoney-news", "东方财富资讯", "media_cn", "rss", "http://rss.eastmoney.com/rss_partener.xml", "A", 26, False, "market", (), True),
    DailySourceSpec("cns-finance", "中新网财经", "media_cn", "rss", "https://www.chinanews.com.cn/rss/finance.xml", "A", 28, False, "macro", (), True),
    DailySourceSpec("economic-observer", "经济观察网", "media_cn", "rss", "https://www.eeo.com.cn/rss.xml", "A", 28, False, "macro", (), True),
    DailySourceSpec("cls-headline", "财联社要闻", "media_cn", "hotlist", "https://www.cls.cn/", "A", 30, False, "market", (), True),
    DailySourceSpec("em-yaowen", "东方财富要闻", "media_cn", "hotlist", "https://finance.eastmoney.com/yaowen.html", "A", 26, False, "market", (), True),
    # --- 海外核心市场、大宗与公司事件/财报媒体 (14) ---
    DailySourceSpec("bloomberg-markets", "Bloomberg Markets", "media_global", "rss", "https://feeds.bloomberg.com/markets/news.rss", "A", 32, False, "market", (), False),
    DailySourceSpec("wsj-markets", "WSJ Markets", "media_global", "rss", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "A", 32, False, "market", (), False),
    DailySourceSpec("wsj-business", "WSJ Business", "media_global", "rss", "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness", "A", 32, False, "companies", (), False),
    DailySourceSpec("ft", "Financial Times", "media_global", "rss", "https://www.ft.com/rss/home", "A", 32, False, "macro", (), False),
    DailySourceSpec("nyt-business", "NYT Business", "media_global", "rss", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "A", 28, False, "companies", (), False),
    DailySourceSpec("cnbc", "CNBC", "media_global", "rss", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "A", 30, False, "market", (), True),
    DailySourceSpec("cnbc-tech", "CNBC Tech", "media_global", "rss", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "A", 30, False, "companies", (), True),
    DailySourceSpec("cnbc-earnings", "CNBC Earnings", "media_global", "rss", "https://www.cnbc.com/id/15839135/device/rss/rss.html", "A", 32, False, "companies", (), True),
    DailySourceSpec("investing-cn", "英为财情", "media_global", "rss", "https://cn.investing.com/rss/news.rss", "A", 28, False, "companies", (), False),
    DailySourceSpec("bbc-business", "BBC财经", "media_global", "rss", "https://feeds.bbci.co.uk/news/business/rss.xml", "A", 28, False, "macro", (), True),
    DailySourceSpec("oilprice", "OilPrice", "media_global", "rss", "https://oilprice.com/rss/main", "B", 24, False, "macro", (), True),
    DailySourceSpec("techmeme", "Techmeme", "media_global", "rss", "https://www.techmeme.com/feed.xml", "A", 30, False, "companies", (), False),
    DailySourceSpec("cnevpost", "CnEVPost", "media_global", "rss", "https://cnevpost.com/feed/", "A", 28, False, "companies", (), True),
    DailySourceSpec("semianalysis", "SemiAnalysis", "media_global", "rss", "https://semianalysis.substack.com/feed", "A", 30, False, "companies", (), False),
)

SOURCE_SPEC_BY_NAME = {spec.name: spec for spec in DAILY_SOURCES}
SOURCE_SPEC_BY_ID = {spec.source_id: spec for spec in DAILY_SOURCES}


def _safe_http_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return ""
    return str(url).strip() if parsed.scheme in {"http", "https"} and parsed.netloc else ""


_BOILERPLATE_DOM_RE = re.compile(
    r"(?:^|[-_\s])(nav|navbar|subnav|menu|topbar|header|footer|login|signin|signup|register|auth|"
    r"modal|popup|dialog|sidebar|sider|recommend|related|share|social|comment|advert|ad-?box|ad-?wrap|"
    r"banner|toolbar|breadcrumb|hot-?list|rank|qrcode|qr-?code|download|app-?down|subscribe|copyright|"
    r"disclaimer|paywall|cookie|newsletter)(?:$|[-_\s])",
    re.I,
)
_BOILERPLATE_LINE_RE = re.compile(
    r"用户名登录|手机号登录|密码登录|扫码登录|还没有账号|免费注册|立即注册|立即登录|忘记密码|"
    r"退出\s+激活卡|激活卡\s+电子版|电子版\s+购物车|购物车\s+注册|"
    r"扫码下载|下载客户端|下载APP|打开APP|关注微信公众号|微信扫一扫|扫一扫分享|"
    r"^(分享到|责任编辑|编辑[：:]|校对[：:]|来源[：:]|原标题[：:]|点击进入专题|免责声明|版权声明|相关阅读|延伸阅读|推荐阅读|热文推荐|往期回顾|Copyright|All rights reserved|Sign in|Log in|Subscribe)",
    re.I,
)
_BOILERPLATE_BODY_SIGNALS = ("用户名登录", "手机号登录", "还没有账号", "免费注册", "激活卡", "电子版", "购物车", "扫码登录", "下载客户端")


def _is_channel_menu_line(text: str) -> bool:
    """Detect navigation channel dumps like '快讯 全部 时政 公司 A股 港股 美股 基金 商品'."""
    parts = [p for p in re.split(r"[\s|/·]+", text.strip()) if p]
    if len(parts) < 5:
        return False
    short_tokens = sum(1 for p in parts if len(p) <= 4)
    has_punct = bool(re.search(r"[，。；！？,.;!?]", text))
    return (not has_punct) and (short_tokens / len(parts) >= 0.75)


def _strip_boilerplate_nodes(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "aside", "header", "form", "button", "input", "select", "textarea"]):
        tag.decompose()
    for node in list(soup.find_all(True)):
        if getattr(node, "attrs", None) is None:
            continue
        classes = " ".join(node.get("class") or []) if isinstance(node.get("class"), list) else str(node.get("class") or "")
        dom_id = str(node.get("id") or "")
        role = str(node.get("role") or "")
        if role in {"navigation", "banner", "contentinfo", "complementary", "dialog", "search"}:
            node.decompose()
            continue
        if _BOILERPLATE_DOM_RE.search(f"{dom_id} {classes}"):
            # Never accidentally destroy the whole body or main article element
            if node.name not in {"html", "body", "article", "main"}:
                node.decompose()


def _is_boilerplate_body(md: str) -> bool:
    head = (md or "")[:450]
    if not head:
        return True
    hits = sum(1 for kw in _BOILERPLATE_BODY_SIGNALS if kw in head)
    return hits >= 2


def _html_to_clean_markdown(raw_html: str, *, max_chars: int = MAX_BODY_CHARS) -> str:
    """Convert raw article HTML into clean Markdown paragraphs + h2/h3 headings, stripping nav/login/ads."""
    if not raw_html:
        return ""
    text_in = html_lib.unescape(str(raw_html))
    if "<" not in text_in:
        cleaned = re.sub(r"\s+", " ", text_in).strip()
        return "" if _is_boilerplate_body(cleaned) else cleaned[:max_chars]

    soup = BeautifulSoup(text_in, "html.parser")
    _strip_boilerplate_nodes(soup)

    blocks: list[str] = []
    seen_lines: set[str] = set()
    for node in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        # Skip nested paragraphs inside li/blockquote to prevent duplication
        if node.name == "p" and node.find_parent(["li", "blockquote"]):
            continue
        # Skip link-only nav items (e.g. menu lists, related-article lists)
        total_txt = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        min_len = 2 if node.name in {"h1", "h2", "h3", "h4"} else 6
        if len(total_txt) < min_len or total_txt in seen_lines:
            continue
        if _BOILERPLATE_LINE_RE.search(total_txt) or _is_channel_menu_line(total_txt):
            continue
        if node.name in {"li", "p"}:
            link_txt = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
            if len(total_txt) > 0 and (link_txt / len(total_txt)) > 0.75 and len(total_txt) < 120:
                continue
        seen_lines.add(total_txt)
        if node.name in {"h1", "h2"}:
            blocks.append(f"## {total_txt}")
        elif node.name in {"h3", "h4"}:
            blocks.append(f"### {total_txt}")
        elif node.name == "blockquote":
            blocks.append(f"> {total_txt}")
        elif node.name == "li":
            blocks.append(f"- {total_txt}")
        else:
            blocks.append(total_txt)

    if not blocks:
        return ""

    joined = "\n\n".join(blocks)[:max_chars].strip()
    return "" if _is_boilerplate_body(joined) else joined


def _parse_dt(value: Any, *, default_tz=UTC) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        try:
            ts = int(text)
            if ts > 10_000_000_000:
                ts //= 1000
            return datetime.fromtimestamp(ts, tz=UTC)
        except (ValueError, OSError):
            return None
    try:
        dt = parsedate_to_datetime(text)
        return (dt.replace(tzinfo=default_tz) if dt.tzinfo is None else dt).astimezone(UTC)
    except Exception:
        pass
    cleaned = text.replace("/", "-").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return (dt.replace(tzinfo=default_tz) if dt.tzinfo is None else dt).astimezone(UTC)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned[:19], fmt)
            return dt.replace(tzinfo=default_tz).astimezone(UTC)
        except ValueError:
            continue
    match = _DATE_RE.search(text)
    if match:
        try:
            dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), 9, 0, tzinfo=SHANGHAI)
            return dt.astimezone(UTC)
        except ValueError:
            return None
    return None


def _parse_rss_feed(raw: bytes, spec: DailySourceSpec, *, now: datetime) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    cutoff = now.astimezone(UTC) - timedelta(days=5)
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for node in [e for e in root.iter() if e.tag.split("}")[-1] in ("item", "entry")]:
        title = ""
        url = ""
        raw_time = ""
        desc_raw = ""
        content_raw = ""
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag == "title" and not title:
                title = html_lib.unescape(re.sub(r"\s+", " ", child.text or "")).strip()
            elif tag == "link" and not url:
                url = (child.get("href") or child.text or "").strip()
            elif tag in ("pubdate", "published", "updated", "date") and not raw_time:
                raw_time = (child.text or "").strip()
            elif tag == "encoded" and child.text:
                content_raw = child.text
            elif tag == "content" and child.text and len(child.text) > len(content_raw):
                content_raw = child.text
            elif tag in ("description", "summary") and child.text and not desc_raw:
                desc_raw = child.text
        url = _safe_http_url(url)
        if not title or not url or url in seen_urls:
            continue
        full_raw = content_raw if len(content_raw) >= len(desc_raw) else desc_raw
        body_md = _html_to_clean_markdown(full_raw)
        plain_summary = re.sub(r"\s+", " ", re.sub(r"^[#>\-\s]+", "", body_md, flags=re.M)).strip()
        if _REDLINE_RE.search(f"{title} {plain_summary[:400]}"):
            continue
        dt = _parse_dt(raw_time)
        if dt and (dt < cutoff or dt > now.astimezone(UTC) + timedelta(hours=12)):
            continue
        seen_urls.add(url)
        rows.append({
            "title": title[:180],
            "summary": (plain_summary[:500] or title)[:500],
            "bodyText": body_md if len(body_md) >= 200 else "",
            "publishedAt": dt.isoformat() if dt else now.astimezone(UTC).isoformat(),
            "source": spec.name,
            "originSource": spec.name,
            "sourceTier": spec.score,
            "sourceLevel": spec.tier,
            "originalUrl": url,
            "official": spec.official,
            "defaultBucket": spec.default_bucket,
            "stale": False,
        })
        if len(rows) >= MAX_ITEMS_PER_SOURCE:
            break
    return rows


def _parse_json_source(data: Any, spec: DailySourceSpec, *, now: datetime) -> list[dict[str, Any]]:
    cutoff = now.astimezone(UTC) - timedelta(days=5)
    raw_list: list[dict[str, Any]] = []
    if isinstance(data, list):
        raw_list = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        for k in ("data", "results", "list", "rows"):
            val = data.get(k)
            if isinstance(val, list):
                raw_list = [r for r in val if isinstance(r, dict)]
                break
            if isinstance(val, dict):
                for kk in ("rows", "results", "list"):
                    if isinstance(val.get(kk), list):
                        raw_list = [r for r in val[kk] if isinstance(r, dict)]
                        break
                if raw_list:
                    break

    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in raw_list:
        if spec.source_id == "yicai":
            title = str(item.get("NewsTitle") or "").strip()
            rel_url = str(item.get("url") or "").strip()
            url = _safe_http_url(urljoin("https://www.yicai.com", rel_url))
            summary = str(item.get("NewsNotes") or "").strip()
            raw_time = item.get("CreateDate") or item.get("LastUpdateTime") or item.get("pubDate")
            body = ""
        elif spec.source_id == "gov":
            title = str(item.get("TITLE") or item.get("title") or "").strip()
            url = _safe_http_url(urljoin("https://www.gov.cn", str(item.get("URL") or item.get("url") or "")))
            summary = str(item.get("SUMMARY") or item.get("CHILDTYPE") or title).strip()
            raw_time = item.get("DOCRELPUBTIME") or item.get("PUBTIME") or item.get("time")
            body = ""
        elif spec.source_id == "nfra":
            title = str(item.get("docTitle") or item.get("title") or "").strip()
            doc_id = str(item.get("docId") or "").strip()
            rel_url = str(item.get("docUrl") or item.get("url") or (f"https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId={doc_id}&itemId=915" if doc_id else ""))
            url = _safe_http_url(urljoin("https://www.nfra.gov.cn", rel_url))
            summary = str(item.get("docSubtitle") or item.get("docSummary") or title).strip()
            raw_time = item.get("publishDate") or item.get("builddate")
            body = ""
        else:
            title = str(item.get("title") or "").strip()
            url = _safe_http_url(item.get("url") or "")
            summary = str(item.get("summary") or title).strip()
            raw_time = item.get("publishedAt") or item.get("date")
            body = str(item.get("content") or "")

        title = html_lib.unescape(re.sub(r"\s+", " ", title)).strip()
        summary = html_lib.unescape(re.sub(r"\s+", " ", summary)).strip()
        if not title or not url or url in seen_urls or _REDLINE_RE.search(f"{title} {summary}"):
            continue
        dt = _parse_dt(raw_time, default_tz=SHANGHAI)
        if dt and (dt < cutoff or dt > now.astimezone(UTC) + timedelta(hours=12)):
            continue
        seen_urls.add(url)
        rows.append({
            "title": title[:180],
            "summary": (summary[:500] or title)[:500],
            "bodyText": _html_to_clean_markdown(body) if len(body) >= 200 else "",
            "publishedAt": dt.isoformat() if dt else now.astimezone(UTC).isoformat(),
            "source": spec.name,
            "originSource": spec.name,
            "sourceTier": spec.score,
            "sourceLevel": spec.tier,
            "originalUrl": url,
            "official": spec.official,
            "defaultBucket": spec.default_bucket,
            "stale": False,
        })
        if len(rows) >= MAX_ITEMS_PER_SOURCE:
            break
    return rows


def _parse_html_list(html_text: str, spec: DailySourceSpec, *, now: datetime) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    cutoff = now.astimezone(UTC) - timedelta(days=7)
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href_raw = str(anchor.get("href") or "").strip()
        if not href_raw or href_raw.startswith(("javascript:", "#", "mailto:")):
            continue
        title = html_lib.unescape(re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))).strip()
        if len(title) < 8 or title in _IGNORE_TITLES:
            continue
        resolved = _safe_http_url(urljoin(spec.url, href_raw))
        if not resolved or resolved == spec.url or resolved in seen_urls:
            continue
        if spec.link_hints and not any(hint in resolved for hint in spec.link_hints):
            continue
        parent = anchor.parent
        parent_text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True)) if parent else title
        grand_text = re.sub(r"\s+", " ", parent.parent.get_text(" ", strip=True)) if (parent and parent.parent) else parent_text
        dt = _parse_dt(parent_text, default_tz=SHANGHAI) or _parse_dt(resolved, default_tz=SHANGHAI)
        if dt is None and spec.source_id == "us-treasury":
            time_el = parent.find_previous("time") or (parent.parent.find("time") if parent and parent.parent else None)
            if time_el:
                dt = _parse_dt(time_el.get("datetime") or time_el.get_text(" ", strip=True), default_tz=UTC)
        if dt is None and spec.source_id in {"safe", "miit"}:
            dt = _parse_dt(grand_text, default_tz=SHANGHAI)
        if dt is None:
            continue
        if dt < cutoff or dt > now.astimezone(UTC) + timedelta(days=1):
            continue
        if _REDLINE_RE.search(title):
            continue
        seen_urls.add(resolved)
        rows.append({
            "title": title[:180],
            "summary": title[:300],
            "bodyText": "",
            "publishedAt": dt.isoformat(),
            "source": spec.name,
            "originSource": spec.name,
            "sourceTier": spec.score,
            "sourceLevel": spec.tier,
            "originalUrl": resolved,
            "official": spec.official,
            "defaultBucket": spec.default_bucket,
            "stale": False,
        })
        if len(rows) >= MAX_ITEMS_PER_SOURCE:
            break
    return rows


def _find_best_article_container(soup: BeautifulSoup):
    """Readability-style fallback: find the container with the richest prose paragraphs and lowest link density."""
    best_node = None
    best_score = 0.0
    for node in soup.find_all(["article", "section", "div", "main"]):
        direct_ps = [p for p in node.find_all("p", recursive=False)]
        if len(direct_ps) < 2:
            continue
        prose_chars = 0
        link_chars = 0
        valid_p_count = 0
        for p in direct_ps:
            txt = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
            if len(txt) < 20 or _BOILERPLATE_LINE_RE.search(txt) or _is_channel_menu_line(txt):
                continue
            prose_chars += len(txt)
            link_chars += sum(len(a.get_text(" ", strip=True)) for a in p.find_all("a"))
            valid_p_count += 1
        if prose_chars < 220 or valid_p_count < 2:
            continue
        link_density = link_chars / max(1, prose_chars)
        if link_density > 0.35:
            continue
        score = prose_chars * (1.0 - link_density)
        if score > best_score:
            best_score = score
            best_node = node
    return best_node


def fetch_article_body(url: str, *, timeout: int = 6) -> str:
    """Fetch public article HTML and extract clean readable Markdown body without site chrome/ads."""
    safe_url = _safe_http_url(url)
    if not safe_url:
        return ""
    try:
        resp = requests.get(
            safe_url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
        )
        if resp.status_code != 200 or len(resp.content) > 4_000_000:
            return ""
        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        # Support Next.js SSR JSON articles (e.g., cls.cn /detail/...) before stripping scripts
        next_data_node = soup.find("script", id="__NEXT_DATA__")
        if next_data_node and next_data_node.string:
            try:
                nd = json.loads(next_data_node.string)
                props = nd.get("props") or {}
                det = (props.get("pageProps") or {}).get("articleDetail") or (
                    (props.get("initialState") or {}).get("detail") or {}
                ).get("articleDetail")
                if isinstance(det, dict):
                    raw_content = str(det.get("content") or det.get("brief") or "").strip()
                    if raw_content:
                        md_next = _html_to_clean_markdown(raw_content, max_chars=MAX_BODY_CHARS)
                        if len(md_next) >= 240:
                            return md_next
            except Exception:  # noqa: BLE001
                pass
        _strip_boilerplate_nodes(soup)
        # Prefer explicit article/content containers before falling back to readability scorer (NEVER whole soup.body)
        container = None
        for selector in (
            ".xx_boxsing",
            ".xd-b-content",
            ".cls-article",
            ".detail-body",
            ".article-body",
            ".article-txt",
            ".article_txt",
            "#artibody",
            ".rich_media_content",
            "[itemprop='articleBody']",
            ".article-content",
            ".article_content",
            ".news-content",
            ".m-txt",
            ".TRS_Editor",
            ".pages_content",
            ".ArticleBody-articleBody",
            ".ContentBody",
            ".post-content",
            ".entry-content",
            "#UCAP-CONTENT",
            "#ContentBody",
            "article",
        ):
            found = soup.select_one(selector)
            if found:
                md_try = _html_to_clean_markdown(str(found), max_chars=MAX_BODY_CHARS)
                if len(md_try) >= 240:
                    return md_try
        container = _find_best_article_container(soup)
        if container is None:
            return ""
        md = _html_to_clean_markdown(str(container), max_chars=MAX_BODY_CHARS)
        return md if len(md) >= 240 else ""
    except Exception:  # noqa: BLE001
        return ""


class FinancialDailySourceCollector:
    """Collects from the 44 verified Financial Daily sources with atomic fallback cache."""

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        sources: tuple[DailySourceSpec, ...] = DAILY_SOURCES,
        http_get: Callable[[str], requests.Response] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.cache_dir = Path(cache_dir or cache_path("financial-news"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "daily-44-sources.json"
        self.sources = sources
        self.http_get = http_get or self._default_get
        self.now_fn = now_fn or (lambda: datetime.now(UTC))

    @staticmethod
    def _default_get(url: str) -> requests.Response:
        resp = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "application/json,application/rss+xml,application/xml,text/html,*/*"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp

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
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.cache_file)

    def load_cached(self) -> dict[str, Any]:
        cached = self._read_cache()
        return cached if cached else {"generatedAt": None, "reports": [], "sourceStatus": []}

    def _fetch_one(self, spec: DailySourceSpec) -> tuple[DailySourceSpec, list[dict[str, Any]] | None, str | None]:
        now = self.now_fn()
        try:
            resp = self.http_get(spec.url)
            if spec.kind == "rss":
                rows = _parse_rss_feed(resp.content, spec, now=now)
            elif spec.kind == "json":
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                rows = _parse_json_source(resp.json(), spec, now=now)
            elif spec.kind == "hotlist":
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                raw_rows = (
                    parse_cls_headline_html(resp.text, now)
                    if spec.source_id == "cls-headline"
                    else parse_eastmoney_editorial_html(resp.text, now)
                )
                rows = [
                    {
                        "title": r["title"],
                        "summary": r.get("summary") or r["title"],
                        "bodyText": "",
                        "publishedAt": r.get("publishedAt") or now.astimezone(UTC).isoformat(),
                        "source": spec.name,
                        "originSource": spec.name,
                        "sourceTier": spec.score,
                        "sourceLevel": spec.tier,
                        "originalUrl": r["originalUrl"],
                        "official": False,
                        "defaultBucket": spec.default_bucket,
                        "stale": False,
                    }
                    for r in raw_rows
                    if not _REDLINE_RE.search(f"{r.get('title', '')} {r.get('summary', '')}")
                ]
            else:
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                rows = _parse_html_list(resp.text, spec, now=now)
            return spec, rows, None
        except Exception as exc:  # noqa: BLE001
            return spec, None, str(exc)[:180]

    def fetch(self) -> dict[str, Any]:
        now_iso = self.now_fn().astimezone(UTC).isoformat()
        previous = self._read_cache()
        prev_by_source: dict[str, list[dict[str, Any]]] = {}
        for row in previous.get("reports") or []:
            prev_by_source.setdefault(str(row.get("source") or ""), []).append(row)
        prev_status = {str(s.get("source") or ""): s for s in previous.get("sourceStatus") or []}

        reports: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        executor = ThreadPoolExecutor(max_workers=16)
        futures = {executor.submit(self._fetch_one, spec): spec for spec in self.sources}
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
                        "error": error or "来源暂不可用",
                    })
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        payload = {"generatedAt": now_iso, "reports": reports, "sourceStatus": statuses}
        self._write_cache(payload)
        return payload
