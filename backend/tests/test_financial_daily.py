from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient

import app as app_module
from financial_daily import (
    FINANCE_BUCKETS,
    FinancialDailyScheduler,
    FinancialDailyService,
    _clean_text,
    _passes_guardrails,
    classify_bucket,
    detect_market_chart,
    extract_markdown_outline,
)
from financial_daily_sources import DAILY_SOURCES, _html_to_clean_markdown, _parse_rss_feed
from financial_news import FinancialNewsService
from financial_news_store import FinancialNewsStore
from market_chart import normalize_asset_code
from route_policy import policy_for

SHANGHAI = timezone(timedelta(hours=8))
UTC = timezone.utc


class _StubCalendar:
    def overview(self):
        return {
            "items": [
                {
                    "id": "cal-1",
                    "title": "美联储 FOMC 议息决议",
                    "category": "央行",
                    "date": "2026-11-26",
                    "startsAt": "2026-11-26T03:00:00+08:00",
                    "precision": "time",
                    "sourceTimezone": "America/New_York",
                    "originalUrl": "https://www.federalreserve.gov/",
                    "source": "Federal Reserve",
                    "status": "scheduled",
                    "stale": False,
                }
            ],
            "generatedAt": "2026-11-25T08:00:00+00:00",
            "windowStart": "2026-11-25",
            "windowEnd": "2026-12-09",
            "timezone": "Asia/Shanghai",
            "stale": False,
            "partial": False,
            "refreshIntervalSeconds": 1800,
            "sources": [],
        }

    def start(self):
        pass

    def stop(self):
        pass


class _StubCollector:
    def __init__(self, reports):
        self._reports = reports

    def load_cached(self):
        return {
            "generatedAt": "2026-11-25T08:00:00+00:00",
            "reports": self._reports,
            "sourceStatus": [
                {"id": "pbc", "source": "中国人民银行", "ok": True, "count": len(self._reports), "cache": "fresh", "error": None}
            ],
        }

    def fetch(self):
        return self.load_cached()


def _make_news_service(tmp_path, now_fn):
    svc = FinancialNewsService(
        cache_dir=tmp_path / "news",
        now_fn=lambda: now_fn().astimezone(UTC),
    )
    svc.quick_fetchers = {}
    svc.calendar = _StubCalendar()
    return svc


def test_44_sources_registry_rss_full_body_and_global_index_kline():
    assert len(DAILY_SOURCES) == 44
    ids = {s.source_id for s in DAILY_SOURCES}
    assert len(ids) == 44
    # Confirm zero 7x24 quick wires are in DAILY_SOURCES
    names = {s.name for s in DAILY_SOURCES}
    for banned in ("财联社电报", "同花顺快讯", "东方财富快讯", "新浪财经快讯"):
        assert banned not in names

    # Full RSS body > 160 chars + heading extraction
    long_html = (
        "<h2>宏观背景</h2>"
        "<p>" + ("美联储公布最新通胀数据，核心服务业物价维持韧性，市场重新评估利率路径。" * 6) + "</p>"
        "<h2>市场定价</h2>"
        "<p>" + ("十年期美债收益率上行至 4.42%，现货黄金回落至 2645 美元附近。" * 5) + "</p>"
    )
    md = _html_to_clean_markdown(long_html)
    assert "## 宏观背景" in md
    assert "## 市场定价" in md
    assert len(md) > 300
    outline = extract_markdown_outline(md)
    assert [o["text"] for o in outline] == ["宏观背景", "市场定价"]

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <channel>
        <item>
          <title>Fed Inflation Update</title>
          <link>https://example.com/fed</link>
          <pubDate>Wed, 25 Nov 2026 06:00:00 GMT</pubDate>
          <description>Short snippet.</description>
          <content:encoded><![CDATA[{long_html}]]></content:encoded>
        </item>
      </channel>
    </rss>"""
    parsed = _parse_rss_feed(xml.encode("utf-8"), DAILY_SOURCES[0], now=datetime(2026, 11, 25, 10, 0, tzinfo=UTC))
    assert len(parsed) == 1
    assert len(parsed[0]["bodyText"]) > 300

    # Market chart detection for A-share / HK / US
    assert detect_market_chart("纳斯达克指数收盘大跌 2.1%")["code"] == "NDX"
    assert detect_market_chart("恒生科技指数午后拉升 3.2%")["code"] == "HSTECH"
    assert detect_market_chart("A股收评：沪指放量上涨 1.4%")["code"] == "000001"

    # Global index chart code validation
    assert normalize_asset_code("global_index", "ndx") == "NDX"
    assert normalize_asset_code("global_index", "HSTECH") == "HSTECH"
    try:
        normalize_asset_code("global_index", "INVALID_CODE")
        assert False, "expected ValueError for unsupported global index"
    except ValueError:
        pass


def test_store_retains_reports_linked_to_30_day_tracked_stories(tmp_path):
    now = [datetime(2026, 11, 13, 10, 0, tzinfo=UTC)]
    store = FinancialNewsStore(tmp_path / "events.db", retention_hours=72, now_fn=lambda: now[0])
    day0_ts = now[0].isoformat()

    ids = store.upsert_reports([
        {
            "title": "央行三季度货币政策执行报告",
            "summary": "保持流动性合理充裕。",
            "publishedAt": day0_ts,
            "source": "中国人民银行",
            "originalUrl": "https://www.pbc.gov.cn/q3",
            "official": True,
        },
        {
            "title": "普通过期快讯",
            "summary": "应被72小时清理。",
            "publishedAt": day0_ts,
            "source": "华尔街见闻",
            "originalUrl": "https://wallstreetcn.com/expired",
        },
    ])
    store.upsert_tracked_story(
        story_id="st-pboc",
        title="央行降准主线",
        bucket="macro",
        first_report_at=day0_ts,
        latest_at=day0_ts,
    )
    store.upsert_milestone(
        milestone_id="ms-1",
        story_id="st-pboc",
        title="报告吹风",
        occurred_at=day0_ts,
        representative_report_key=ids[0],
    )
    store.link_milestone_report(milestone_id="ms-1", story_id="st-pboc", report_key=ids[0], role="primary")

    now[0] = now[0] + timedelta(days=12)
    store._prune()

    assert store.get_report_detail(ids[0]) is not None
    assert store.get_report_detail(ids[1]) is None
    store.close()


def test_three_section_edition_invariants_and_no_cross_section_duplicates(tmp_path):
    now = datetime(2026, 11, 25, 18, 10, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)

    collected = [
        {
            "title": "中国人民银行决定下调存款准备金率 0.25 个百分点",
            "summary": "央行宣布下调金融机构存款准备金率 0.25 个百分点，释放长期资金约 5000 亿元，保持银行体系流动性合理充裕。",
            "bodyText": "## 政策核心内容\n\n" + ("中国人民银行宣布下调存款准备金率 0.25 个百分点，释放长期资金约 5000 亿元。" * 8)
            + "\n\n## 流动性影响\n\n" + ("本次降准不含已执行 5% 存款准备金率的金融机构，有助于平滑年末资金面波动。" * 6),
            "publishedAt": (now - timedelta(hours=3)).astimezone(UTC).isoformat(),
            "source": "中国人民银行",
            "originalUrl": "https://www.pbc.gov.cn/rrr-cut",
            "official": True,
            "sourceLevel": "S",
            "sourceTier": 35,
        },
        {
            "title": "美联储会议纪要显示委员对后续降息节奏存在分歧",
            "summary": "多位美联储委员强调继续观察核心服务业通胀回落情况，十年期美债收益率走高至 4.45%。",
            "publishedAt": (now - timedelta(hours=10)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.cnbc.com/fed-minutes",
        },
        {
            "title": "A股收评：沪指放量上涨 1.42%，两市成交额突破 1.8 万亿元",
            "summary": "上证指数收盘上涨 1.42% 报 3386 点，创业板指涨 2.15%，两市成交额较前一交易日放大超 1800 亿元。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "第一财经",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.yicai.com/a-share-close",
        },
        {
            "title": "英伟达三季度数据中心营收同比增长 94%，黄仁勋称 Blackwell 需求强劲",
            "summary": "英伟达公布最新季报，数据中心营收达 308 亿美元，同时公司给出下一季度毛利率短期承压指引引发股价盘后震荡。",
            "publishedAt": (now - timedelta(hours=4)).astimezone(UTC).isoformat(),
            "source": "CNBC Tech",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.cnbc.com/nvidia-q3",
        },
        {
            "title": "小米三季度智能手机毛利率不及预期，电动车业务亏损收窄",
            "summary": "小米集团披露三季度财报，整体营收同比增 30%，但存储芯片涨价拖累手机毛利率略低于市场一致预期。",
            "publishedAt": (now - timedelta(hours=5)).astimezone(UTC).isoformat(),
            "source": "华尔街见闻",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://wallstreetcn.com/xiaomi-q3",
        },
        {
            "title": "布伦特原油回落至 73.2 美元/桶，现货黄金在 2645 美元附近震荡",
            "summary": "北美商业原油库存高于预期令布伦特原油走低，现货黄金维持高位盘整。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "OilPrice",
            "sourceLevel": "B",
            "sourceTier": 18,
            "originalUrl": "https://oilprice.com/brent-73",
        },
        {
            "title": "明星综艺开机与旅游天气预报",
            "summary": "娱乐新闻不应进入金融日报。",
            "publishedAt": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "华尔街见闻",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://wallstreetcn.com/noise",
        },
        {
            "title": "中国人民银行公开市场开展 800 亿元 7 天期逆回购操作",
            "summary": "例行逆回购操作维持流动性平稳。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "中国人民银行",
            "sourceLevel": "S",
            "official": True,
            "originalUrl": "https://www.pbc.gov.cn/omo-800",
        },
    ]

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubCollector(collected),
        now_fn=lambda: now,
    )
    edition = daily.compose_edition(refresh_upstream=False, allow_llm=False)

    assert edition["editionType"] == "evening"
    assert [s["key"] for s in edition["sections"]] == [b["key"] for b in FINANCE_BUCKETS]
    assert [s["name"] for s in edition["sections"]] == ["宏观数据与政策", "市场表现", "海外公司事件与财报"]
    assert "overview" not in edition
    assert "marketStrip" not in edition
    assert "coverage" not in edition
    assert edition["lead"] is not None

    # No story appears in both lead and sections, or across two sections
    section_keys = [item["reportKey"] for sec in edition["sections"] for item in sec["items"]]
    assert len(section_keys) == len(set(section_keys))
    assert edition["lead"]["reportKey"] not in set(section_keys)

    all_items = [edition["lead"]] + [item for sec in edition["sections"] for item in sec["items"]]
    all_titles = [item["title"] for item in all_items]
    assert not any("明星综艺" in t for t in all_titles)
    assert not any("逆回购" in t for t in all_titles)

    # Market section item attaches K-line chart in detail
    market_sec = next(s for s in edition["sections"] if s["key"] == "market")
    assert len(market_sec["items"]) >= 1
    market_detail = daily.get_report_detail(market_sec["items"][0]["reportKey"])
    assert market_detail is not None
    assert market_detail["marketChart"]["code"] == "000001"
    # Single milestone story must have empty followups (hidden in UI)
    assert market_detail["followups"] == []
    assert market_detail["eventSummary"] is None

    # Long Chinese body renders with bodyMode == "full" and outline TOC
    rrr_item = next(it for it in all_items if "存款准备金率" in it["title"])
    rrr_detail = daily.get_report_detail(rrr_item["reportKey"])
    assert rrr_detail is not None
    assert rrr_detail["bodyMode"] == "full"
    assert [o["text"] for o in rrr_detail["outline"]] == ["政策核心内容", "流动性影响"]


def test_incremental_milestones_show_followups_and_guardrails(tmp_path):
    base_time = datetime(2026, 11, 20, 9, 0, tzinfo=SHANGHAI)
    clock = [base_time]
    svc = _make_news_service(tmp_path, lambda: clock[0])

    def mock_llm(messages):
        user_msg = messages[-1]["content"]
        if "SAME_NODE" in user_msg:
            payload = json.loads(user_msg.rsplit("：\n", 1)[1])
            return [
                {
                    "reportKey": row["reportKey"],
                    "action": "NEW_NODE",
                    "storyId": row["candidates"][0]["storyId"],
                }
                for row in payload
            ]
        if "先了解这件事" in user_msg:
            return {"paragraphs": ["央行降准 0.25 个百分点并释放约 5000 亿元资金。"], "latestMilestoneSummary": "降准正式落地。"}
        return {}

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubCollector([]),
        now_fn=lambda: clock[0],
        llm_call=mock_llm,
    )
    day1 = base_time.astimezone(UTC).isoformat()

    r1 = {
        "title": "央行三季度货币政策报告重申保持流动性合理充裕",
        "summary": "保持流动性合理充裕。",
        "publishedAt": day1,
        "source": "中国人民银行",
        "originalUrl": "https://www.pbc.gov.cn/1",
        "official": True,
        "sourceLevel": "S",
        "bucket": "macro",
    }
    svc.store.upsert_reports([r1])
    items1 = [{**rep, "reportKey": rep["id"], "bucket": "macro"} for rep in svc.store.load_reports(hours=72)]
    stories = daily.ingest_to_stories(items1, allow_llm=False)
    assert len(stories) == 1
    sid = stories[0]["storyId"]

    clock[0] = base_time + timedelta(days=5)
    day2 = (clock[0] - timedelta(hours=2)).astimezone(UTC).isoformat()
    r2 = {
        "title": "央行正式宣布下调存款准备金率 0.25 个百分点",
        "summary": "释放长期资金约 5000 亿元。",
        "publishedAt": day2,
        "source": "中国人民银行",
        "originalUrl": "https://www.pbc.gov.cn/2",
        "official": True,
        "sourceLevel": "S",
        "bucket": "macro",
    }
    svc.store.upsert_reports([r2])
    items2 = [{**rep, "reportKey": rep["id"], "bucket": "macro"} for rep in svc.store.load_reports(hours=72)]
    stories_after = daily.ingest_to_stories(items2, allow_llm=True)
    tracked = next(s for s in stories_after if s["storyId"] == sid)
    assert len(tracked["milestones"]) == 2

    # Level 2 detail for r2 must show r1 as a genuine incremental milestone followup
    r2_key = tracked["milestones"][0]["representativeReportKey"]
    detail = daily.get_report_detail(r2_key)
    assert detail is not None
    assert len(detail["followups"]) == 1
    assert detail["eventSummary"]["storyId"] == sid
    assert detail["eventSummary"]["milestoneCount"] == 2

    # Guardrail rejects advisory wording and fabricated numbers
    assert _passes_guardrails("强烈推荐买入该股票，目标价 99 元", "央行降准 0.25 个百分点") is False
    assert _passes_guardrails("央行降准 9.99 个百分点", "央行降准 0.25 个百分点") is False
    assert _passes_guardrails("央行宣布降准 0.25 个百分点", "央行降准 0.25 个百分点") is True


def test_scheduler_idempotent_morning_and_evening_and_api_routes(tmp_path, monkeypatch):
    clock = [datetime(2026, 11, 25, 8, 5, tzinfo=SHANGHAI)]
    svc = _make_news_service(tmp_path, lambda: clock[0])
    reports = [
        {
            "title": "美联储会议纪要显示官员分歧加大",
            "summary": "多位美联储官员强调关注核心通胀回落节奏与美债收益率走势。",
            "publishedAt": (clock[0] - timedelta(hours=3)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://www.cnbc.com/1",
        },
        {
            "title": "A股早盘：沪指放量上涨 1.1%，创业板指涨超 1.8%",
            "summary": "三大股指集体走高，两市成交额显著放大。",
            "publishedAt": (clock[0] - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "第一财经",
            "sourceLevel": "A",
            "originalUrl": "https://www.yicai.com/1",
        },
        {
            "title": "英伟达宣布上调新一代 AI 服务器芯片产能指引",
            "summary": "重点满足北美云厂商数据中心算力采购需求。",
            "publishedAt": (clock[0] - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://www.ft.com/1",
        },
        {
            "title": "苹果披露季度服务业务营收创历史新高",
            "summary": "当季服务营收同比增长 12%，大中华区销量企稳。",
            "publishedAt": (clock[0] - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "CNBC Tech",
            "sourceLevel": "A",
            "originalUrl": "https://www.cnbc.com/2",
        },
    ]
    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubCollector(reports),
        now_fn=lambda: clock[0],
    )
    sched = FinancialDailyScheduler(daily)
    assert sched.run_once() == ["2026-11-25-morning"]
    assert sched.run_once() == []

    clock[0] = datetime(2026, 11, 25, 18, 5, tzinfo=SHANGHAI)
    assert sched.run_once() == ["2026-11-25-evening"]
    assert len(daily.list_editions()) == 2

    assert policy_for("GET", "/api/finance/daily/editions") == "authenticated"
    assert policy_for("GET", "/api/finance/daily/latest") == "authenticated"
    assert policy_for("GET", "/api/finance/daily/2026-11-25-evening") == "authenticated"
    assert policy_for("POST", "/api/finance/daily/refresh") == "authenticated"
    assert policy_for("GET", "/api/finance/news/reports/abc") == "authenticated"
    assert policy_for("GET", "/api/finance/news/tracked-events/xyz") == "authenticated"

    monkeypatch.setattr(app_module, "financial_daily_service", daily)
    with TestClient(app_module.app) as client:
        editions_res = client.get("/api/finance/daily/editions")
        assert editions_res.status_code == 200
        assert len(editions_res.json()["data"]) == 2

        latest_res = client.get("/api/finance/daily/latest?edition=morning")
        assert latest_res.status_code == 200
        ed = latest_res.json()["data"]
        assert ed["editionType"] == "morning"
        lead_key = ed["lead"]["reportKey"]
        story_id = ed["lead"]["storyId"]

        rep_res = client.get(f"/api/finance/news/reports/{lead_key}")
        assert rep_res.status_code == 200
        assert rep_res.json()["data"]["reportKey"] == lead_key

        evt_res = client.get(f"/api/finance/news/tracked-events/{story_id}")
        assert evt_res.status_code == 200
        assert evt_res.json()["data"]["storyId"] == story_id


def test_bucket_precedence_aihot_glm_scoring_translation_and_same_node_dedup(tmp_path):
    now = datetime(2026, 11, 25, 18, 10, tzinfo=SHANGHAI)
    assert classify_bucket("A股午评：沪指跌1.2%，半导体与AI算力回调", "创业板指跌超1%") == "market"
    assert classify_bucket("2026年1—10月，我国对外直接投资9411.3亿元人民币", "商务部公布数据") == "macro"
    assert classify_bucket("现货黄金回升至 2645 美元/盎司，原油走低", "美债利率回落") == "macro"
    assert classify_bucket("小米财报不及预期引发股价震荡", "季度营收披露") == "companies"

    svc = _make_news_service(tmp_path, lambda: now)
    collected = [
        {
            "title": "US preparing plan for new tariffs on 12 global partners",
            "summary": "Washington outlines new 12 partner tariff proposals covering steel and autos.",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "BBC Business",
            "sourceLevel": "A",
            "originalUrl": "https://www.bbc.com/tariffs-12",
        },
        {
            "title": "Trump readies new tariffs on 12 major economies",
            "summary": "Separate report covering the same 12 partner tariff move.",
            "publishedAt": (now - timedelta(hours=3)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://www.ft.com/tariffs-12",
        },
        {
            "title": "Nvidia quarterly revenue reaches 35.1 billion dollars",
            "summary": "Data center demand remains strong at 35.1 billion dollars in Q3.",
            "publishedAt": (now - timedelta(hours=4)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://www.cnbc.com/nvda-35",
        },
        {
            "title": "久远银海：在互动平台表示大模型已应用于部分政务项目",
            "summary": "投资者互动平台回复提问。",
            "publishedAt": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "第一财经",
            "sourceLevel": "A",
            "originalUrl": "https://finance.example.com/ir-qa",
        },
        {
            "title": "100%！美联储加息大消息！“华尔街之狼”发出警告",
            "summary": "发生了什么？",
            "publishedAt": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://finance.example.com/clickbait",
        },
        {
            "title": "现货黄金回升至 2645 美元/盎司，关注美元走势",
            "summary": "国际金价震荡上行至 2645 美元/盎司。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://www.ft.com/gold-2645",
        },
    ]

    def mock_llm(messages):
        user_msg = messages[-1]["content"]
        if "SAME_NODE" in user_msg:
            payload = json.loads(user_msg.rsplit("：\n", 1)[1])
            return [{"reportKey": r["reportKey"], "action": "NEW_STORY"} for r in payload]
        if "实质份量" in user_msg:
            payload = json.loads(user_msg.rsplit("：\n", 1)[1])
            bbc_key = next(r["reportKey"] for r in payload if "tariffs on 12 global" in r["title"].lower())
            out = []
            for r in payload:
                if r["reportKey"] == bbc_key:
                    out.append({"reportKey": r["reportKey"], "score": 92, "bucket": "macro"})
                elif "tariffs on 12 major" in r["title"].lower():
                    out.append({"reportKey": r["reportKey"], "score": 84, "bucket": "macro", "duplicateOf": bbc_key})
                elif "Nvidia" in r["title"]:
                    out.append({"reportKey": r["reportKey"], "score": 88, "bucket": "companies"})
                else:
                    out.append({"reportKey": r["reportKey"], "score": 70, "bucket": r["bucket"]})
            return out
        if "summaryZh" in user_msg:
            payload = json.loads(user_msg.rsplit("：\n", 1)[1])
            out = []
            for r in payload:
                if "tariffs on 12 global" in r["title"].lower():
                    out.append({
                        "reportKey": r["reportKey"],
                        "titleZh": "美国拟对 12 个贸易伙伴推出新关税方案",
                        "summaryZh": "美方正拟定针对 12 个贸易伙伴的新关税提案，涉及钢铁与汽车等多个关键进出口领域，市场持续关注后续贸易摩擦升级风险。",
                    })
                elif "Nvidia" in r["title"]:
                    out.append({
                        "reportKey": r["reportKey"],
                        "titleZh": "英伟达季度营收达 999 亿美元大关",  # fabricated number -> guardrail must reject
                        "summaryZh": "英伟达单季营收达 999 亿美元。",
                    })
                else:
                    out.append({
                        "reportKey": r["reportKey"],
                        "titleZh": r["title"],
                        "summaryZh": r["material"][:120],
                    })
            return out
        return {}

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubCollector(collected),
        now_fn=lambda: now,
        llm_call=mock_llm,
        body_fetcher=lambda _url: "",
    )
    edition = daily.compose_edition(refresh_upstream=False, allow_llm=True)

    assert edition["editorialEngine"] == "glm"
    all_items = ([edition["lead"]] if edition["lead"] else []) + [
        item for sec in edition["sections"] for item in sec["items"]
    ]
    all_titles = [item["title"] for item in all_items]
    assert not any("互动平台" in t for t in all_titles)

    # Cross-outlet tariff story folded into 1 surviving entry translated to Chinese
    tariff_items = [item for item in all_items if "关税" in item["title"] or "tariff" in item["title"].lower()]
    assert len(tariff_items) == 1
    assert tariff_items[0]["title"] == "美国拟对 12 个贸易伙伴推出新关税方案"
    assert tariff_items[0]["originalTitle"] == "US preparing plan for new tariffs on 12 global partners"
    assert tariff_items[0]["independentCount"] >= 2

    # Guardrail rejects fabricated "999" titleZh while keeping original report
    nvda_items = [item for item in all_items if "Nvidia" in item["title"] or "英伟达" in item["title"]]
    assert len(nvda_items) == 1
    assert nvda_items[0]["title"] == "Nvidia quarterly revenue reaches 35.1 billion dollars"

    # Same-milestone duplicate outlets must NOT appear as fake "followups" in Level 2,
    # while still being recorded as corroborating sources in Level 3 tracked event!
    bbc_key = tariff_items[0]["reportKey"]
    bbc_story_id = tariff_items[0]["storyId"]
    detail = daily.get_report_detail(bbc_key)
    assert detail is not None
    assert detail["title"] == "美国拟对 12 个贸易伙伴推出新关税方案"
    assert "钢铁与汽车" in detail["summary"]
    assert detail["followups"] == []

    tracked = daily.get_tracked_event(bbc_story_id)
    assert tracked is not None
    assert tracked["title"] == "美国拟对 12 个贸易伙伴推出新关税方案"
    assert len(tracked["reports"]) >= 2
    assert {"BBC Business", "Financial Times"}.issubset({r["sourceName"] for r in tracked["reports"]})


def test_latest_edition_never_blocks_and_never_fabricates_premature_evening(tmp_path):
    import threading
    import time

    now = datetime(2026, 11, 25, 14, 10, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    collected = [
        {
            "title": "中国人民银行决定下调存款准备金率 0.25 个百分点",
            "summary": "释放长期资金约 5000 亿元，维护银行体系流动性平稳。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "中国人民银行",
            "sourceLevel": "S",
            "official": True,
            "originalUrl": "https://www.pbc.gov.cn/rrr-cut",
        }
    ]
    daily = FinancialDailyService(svc, official_fetcher=_StubCollector(collected), now_fn=lambda: now)
    morning = daily.compose_edition(edition_type="morning", refresh_upstream=False, allow_llm=False)
    assert morning["editionKey"] == "2026-11-25-morning"

    lock_acquired = threading.Event()
    release_lock = threading.Event()

    def hold_lock():
        with daily._lock:
            daily._compose_active = True
            lock_acquired.set()
            release_lock.wait(5)
            daily._compose_active = False

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    assert lock_acquired.wait(2)
    try:
        t0 = time.monotonic()
        res = daily.latest_edition()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5
        assert res["editionKey"] == "2026-11-25-morning"
        assert res["refreshing"] is True

        ev_res = daily.latest_edition(edition_type="evening")
        assert ev_res["editionKey"] == "2026-11-25-morning"
        assert ev_res["requestedEditionPending"]["editionType"] == "evening"
        assert daily.get_edition("2026-11-25-evening") is None
    finally:
        release_lock.set()
        t.join(2)


def test_request_refresh_is_non_blocking(tmp_path, monkeypatch):
    import threading

    now = datetime(2026, 11, 25, 14, 15, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    daily = FinancialDailyService(svc, official_fetcher=_StubCollector([]), now_fn=lambda: now)
    daily.compose_edition(edition_type="morning", refresh_upstream=False, allow_llm=False)

    done = threading.Event()
    monkeypatch.setattr(daily, "compose_edition", lambda **kwargs: (done.set() or daily.get_edition("2026-11-25-morning")))
    res = daily.request_refresh(edition_type="evening")
    assert res["refreshing"] is True
    assert res["refreshOutcome"] == "started"
    assert done.wait(2)
    if daily._refresh_thread:
        daily._refresh_thread.join(2)


def test_english_word_clustering_no_false_merges_and_text_hygiene(tmp_path):
    assert _passes_guardrails("美光将 CEO 安保预算提高 2000%", "Micron boosted CEO security budget by 2,000%") is True
    assert _clean_text("&#34;央行&#34;开展逆回购操作。具体情况如下：") == '"央行"开展逆回购操作。'
    assert _clean_text("A股A股午评：沪指微涨") == "A股午评：沪指微涨"
    trimmed = _clean_text("The verdict was handed down in a federal court in New York today.", max_len=55)
    assert not trimmed.endswith("New Y…")

    now = datetime(2026, 11, 25, 14, 0, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    daily = FinancialDailyService(svc, official_fetcher=_StubCollector([]), now_fn=lambda: now)
    reps = [
        {
            "reportKey": "k-huawei",
            "id": "k-huawei",
            "title": "Huawei found guilty of stealing trade secrets in federal court",
            "summary": "A US jury found Huawei guilty of trade secret theft.",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "BBC Business",
            "sourceLevel": "A",
            "originalUrl": "https://bbc.com/huawei",
            "bucket": "companies",
        },
        {
            "reportKey": "k-hyundai",
            "id": "k-hyundai",
            "title": "Hyundai new Kona N Line is already out testing in cold weather",
            "summary": "Electric vehicle prototype spotted on roads.",
            "publishedAt": (now - timedelta(hours=4)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://ft.com/hyundai",
            "bucket": "companies",
        },
        {
            "reportKey": "k-gta",
            "id": "k-gta",
            "title": "The infamous GTA 6 hacker has been released after pleading guilty",
            "summary": "Gaming security case update.",
            "publishedAt": (now - timedelta(hours=5)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://cnbc.com/gta6",
            "bucket": "companies",
        },
    ]
    svc.store.upsert_reports(reps)
    loaded = [{**r, "reportKey": r["id"], "bucket": "companies"} for r in svc.store.load_reports(hours=72)]
    stories = daily.ingest_to_stories(loaded, allow_llm=False)
    huawei_story = next(st for st in stories if "Huawei" in st["title"])
    assert len(huawei_story["reports"]) == 1
    assert not any("Hyundai" in r["title"] or "GTA" in r["title"] for r in huawei_story["reports"])


def test_scheduler_passes_refresh_upstream_flag(tmp_path):
    now = datetime(2026, 11, 25, 8, 5, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    daily = FinancialDailyService(svc, official_fetcher=_StubCollector([]), now_fn=lambda: now)
    calls = []
    orig = daily.compose_edition

    def spy_compose(*args, **kwargs):
        calls.append(kwargs)
        return orig(*args, **kwargs)

    daily.compose_edition = spy_compose
    sched = FinancialDailyScheduler(daily, refresh_upstream=True)
    sched.run_once()
    assert len(calls) == 1
    assert calls[0]["refresh_upstream"] is True
    assert calls[0]["allow_llm"] is True
