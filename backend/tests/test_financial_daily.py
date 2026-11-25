from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient

import app as app_module
from financial_daily import FinancialDailyScheduler, FinancialDailyService, _clean_text, _passes_guardrails, classify_bucket
from financial_news import FinancialNewsService
from financial_news_store import FinancialNewsStore
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


class _StubOfficial:
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


class _StubMarketReview:
    def get_review(self):
        return {
            "tradingDate": "2026-11-25",
            "partial": False,
            "stale": False,
            "indices": [
                {"name": "上证指数", "price": 3386.42, "changePct": 0.84},
                {"name": "创业板指", "price": 2248.15, "changePct": 1.62},
                {"name": "恒生指数", "price": 20418.6, "changePct": 0.51},
            ],
            "liquidity": {"todayAmountYuan": 1.76e12, "changePct": 8.7},
        }


def _make_news_service(tmp_path, now_fn):
    svc = FinancialNewsService(
        cache_dir=tmp_path / "news",
        now_fn=lambda: now_fn().astimezone(UTC),
    )
    svc.quick_fetchers = {}
    svc.calendar = _StubCalendar()
    return svc


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
            "source": "同花顺快讯",
            "originalUrl": "https://news.10jqka.com.cn/expired",
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

    # 12 days pass: _prune() should delete unlinked 72h-old report, but keep 30-day tracked report
    now[0] = now[0] + timedelta(days=12)
    store._prune()

    assert store.get_report_detail(ids[0]) is not None
    assert store.get_report_detail(ids[1]) is None
    store.close()


def test_tiered_admission_clustering_and_strict_newspaper_invariants(tmp_path):
    now = datetime(2026, 11, 25, 18, 10, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)

    official_reports = [
        {
            "title": "中国人民银行决定下调存款准备金率 0.25 个百分点",
            "summary": "释放长期资金约 5000 亿元，保持流动性合理充裕。",
            "publishedAt": (now - timedelta(hours=3)).astimezone(UTC).isoformat(),
            "source": "中国人民银行",
            "originalUrl": "https://www.pbc.gov.cn/rrr-cut",
            "official": True,
            "sourceLevel": "S",
            "sourceTier": 35,
        }
    ]
    svc.store.upsert_reports([
        {
            "title": "美联储会议纪要显示委员对后续降息节奏存在分歧",
            "summary": "多位委员强调观察核心服务业通胀回落情况，美债收益率走高。",
            "publishedAt": (now - timedelta(hours=10)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.cnbc.com/fed-minutes",
        },
        {
            "title": "沪深交易所修订上市公司并购重组审核指引",
            "summary": "明确硬科技跨行业并购估值说明与信息披露要求。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "上交所",
            "sourceLevel": "S",
            "sourceTier": 35,
            "official": True,
            "originalUrl": "https://www.sse.com.cn/mna-guide",
        },
        {
            "title": "海外云巨头同步上调 2027 财年 AI 数据中心资本开支指引",
            "summary": "重点投向高速光模块与液冷散热基础设施。",
            "publishedAt": (now - timedelta(hours=6)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.ft.com/cloud-capex",
        },
        {
            "title": "港股大型科技平台三季报营收同比增 11%",
            "summary": "云计算利润率改善，维持股东回购计划不变。",
            "publishedAt": (now - timedelta(hours=5)).astimezone(UTC).isoformat(),
            "source": "MarketWatch",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.marketwatch.com/hk-tech",
        },
        {
            "title": "布伦特原油回落至 73.2 美元/桶，关注产油国减产配额执行",
            "summary": "北美商业原油库存高于预期，现货黄金在 2645 美元附近震荡。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "OilPrice",
            "sourceLevel": "C",
            "sourceTier": 10,
            "originalUrl": "https://oilprice.com/brent-73",
        },
        {
            "title": "布伦特原油日内走低至 73.2 美元，库存数据超预期",
            "summary": "原油库存增加压制油价。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "Reuters",
            "sourceLevel": "A",
            "sourceTier": 28,
            "originalUrl": "https://www.reuters.com/brent-73",
        },
        {
            "title": "明星综艺开机与旅游天气预报",
            "summary": "娱乐新闻不应进入金融日报。",
            "publishedAt": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "东方财富快讯",
            "sourceLevel": "B",
            "sourceTier": 18,
            "originalUrl": "https://finance.eastmoney.com/noise",
        },
    ])

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubOfficial(official_reports),
        market_review_service=_StubMarketReview(),
        now_fn=lambda: now,
    )
    edition = daily.compose_edition(refresh_upstream=False, allow_llm=False)

    assert edition["editionType"] == "evening"
    assert edition["lead"] is not None
    assert edition["lead"]["sectionName"]
    assert edition["marketStrip"]["items"][0]["name"] == "上证指数"

    section_keys = {item["reportKey"] for sec in edition["sections"] for item in sec["items"]}
    assert edition["lead"]["reportKey"] not in section_keys
    assert len(edition["keyPicks"]) == 3
    for pick in edition["keyPicks"]:
        assert pick["reportKey"] in section_keys

    all_titles = [edition["lead"]["title"]] + [item["title"] for sec in edition["sections"] for item in sec["items"]]
    assert not any("明星综艺" in t for t in all_titles)

    # Level 2 report detail & Level 3 tracked event detail
    lead_detail = daily.get_report_detail(edition["lead"]["reportKey"])
    assert lead_detail is not None
    assert lead_detail["eventSummary"]["storyId"] == edition["lead"]["storyId"]

    tracked = daily.get_tracked_event(edition["lead"]["storyId"])
    assert tracked is not None
    assert tracked["whyHot"]["participants48h"] >= 1
    assert len(tracked["milestones"]) >= 1
    assert len(tracked["overview"]["paragraphs"]) >= 1


def test_three_tier_clustering_and_guardrails(tmp_path):
    base_time = datetime(2026, 11, 20, 9, 0, tzinfo=SHANGHAI)
    clock = [base_time]
    svc = _make_news_service(tmp_path, lambda: clock[0])

    def mock_llm(messages):
        user_msg = messages[-1]["content"]
        if "SAME_NODE" in user_msg:
            payload = json.loads(user_msg.split("：\n", 1)[1])
            return [
                {
                    "reportKey": row["reportKey"],
                    "action": "NEW_NODE",
                    "storyId": row["candidates"][0]["storyId"],
                }
                for row in payload
            ]
        if "breadth" in user_msg:
            payload = json.loads(user_msg.split("：\n", 1)[1])
            return [{"reportKey": row["reportKey"], "breadth": 4.5, "novelty": 4.0, "evidence": 5.0, "bucket": row["bucket"]} for row in payload]
        if "先了解这件事" in user_msg:
            return {"paragraphs": ["央行降准 0.25 个百分点并释放约 5000 亿元资金。"], "latestMilestoneSummary": "降准正式落地。"}
        if "本期导读" in user_msg:
            return {"overview": "本期关注央行降准 0.25 个百分点落地情况。"}
        return {}

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubOfficial([]),
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

    # 5 days later, a new milestone report arrives and links to the same 30-day tracked story
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

    # Guardrail rejects advisory wording and fabricated numbers
    assert _passes_guardrails("强烈推荐买入该股票，目标价 99 元", "央行降准 0.25 个百分点") is False
    assert _passes_guardrails("央行降准 9.99 个百分点", "央行降准 0.25 个百分点") is False
    assert _passes_guardrails("央行宣布降准 0.25 个百分点", "央行降准 0.25 个百分点") is True


def test_scheduler_idempotent_morning_and_evening_and_api_routes(tmp_path, monkeypatch):
    clock = [datetime(2026, 11, 25, 8, 5, tzinfo=SHANGHAI)]
    svc = _make_news_service(tmp_path, lambda: clock[0])
    svc.store.upsert_reports([
        {
            "title": "美联储会议纪要显示官员分歧加大",
            "summary": "关注通胀数据回落节奏。",
            "publishedAt": (clock[0] - timedelta(hours=3)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://www.cnbc.com/1",
        },
        {
            "title": "上交所发布并购重组审核指引修订稿",
            "summary": "明确硬科技并购披露标准。",
            "publishedAt": (clock[0] - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "上交所",
            "sourceLevel": "S",
            "official": True,
            "originalUrl": "https://www.sse.com.cn/1",
        },
        {
            "title": "海外云厂商上调 AI 资本开支指引",
            "summary": "重点投向液冷与光互连。",
            "publishedAt": (clock[0] - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://www.ft.com/1",
        },
        {
            "title": "港股大型互联网平台披露回购进展",
            "summary": "当季完成回购 32 亿美元。",
            "publishedAt": (clock[0] - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "MarketWatch",
            "sourceLevel": "A",
            "originalUrl": "https://www.marketwatch.com/1",
        },
    ])
    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubOfficial([]),
        market_review_service=_StubMarketReview(),
        now_fn=lambda: clock[0],
    )
    sched = FinancialDailyScheduler(daily)
    assert sched.run_once() == ["2026-11-25-morning"]
    assert sched.run_once() == []

    clock[0] = datetime(2026, 11, 25, 18, 5, tzinfo=SHANGHAI)
    assert sched.run_once() == ["2026-11-25-evening"]
    assert len(daily.list_editions()) == 2

    # API routes & route policy checks
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


def test_bucket_precedence_noise_clickbait_and_glm_translation_dedup(tmp_path):
    now = datetime(2026, 11, 25, 18, 10, tzinfo=SHANGHAI)
    assert classify_bucket("A股午评：沪指跌1.2%，半导体与AI算力回调", "创业板指跌超1%") == "china"
    assert classify_bucket("2026年1—10月，我国对外直接投资9411.3亿元人民币", "商务部公布数据") == "macro"
    assert classify_bucket("在岸人民币汇率走强至7.18附近", "外汇市场关注美元指数") == "commodities"

    svc = _make_news_service(tmp_path, lambda: now)
    svc.store.upsert_reports([
        {
            "title": "US preparing plan for new tariffs on 12 global partners",
            "summary": "Washington outlines new 12 partner tariff proposals.",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "BBC财经",
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
            "summary": "Data center demand remains strong at 35.1 billion.",
            "publishedAt": (now - timedelta(hours=4)).astimezone(UTC).isoformat(),
            "source": "CNBC",
            "sourceLevel": "A",
            "originalUrl": "https://www.cnbc.com/nvda-35",
        },
        {
            "title": "久远银海：在互动平台表示大模型已应用于部分政务项目",
            "summary": "投资者互动平台回复提问。",
            "publishedAt": (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
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
            "title": "上交所公布科创板指数样本调整名单",
            "summary": "例行指数样本调整将于下月生效。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "上交所",
            "sourceLevel": "S",
            "official": True,
            "originalUrl": "https://www.sse.com.cn/index-adj",
        },
        {
            "title": "现货黄金回升至 2645 美元/盎司，关注美元走势",
            "summary": "国际金价震荡上行。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "Financial Times",
            "sourceLevel": "A",
            "originalUrl": "https://www.ft.com/gold-2645",
        },
    ])

    def mock_llm(messages):
        user_msg = messages[-1]["content"]
        if "SAME_NODE" in user_msg:
            payload = json.loads(user_msg.split("：\n", 1)[1])
            return [{"reportKey": r["reportKey"], "action": "NEW_STORY"} for r in payload]
        if "breadth" in user_msg:
            payload = json.loads(user_msg.split("：\n", 1)[1])
            bbc_key = next(r["reportKey"] for r in payload if "BBC" in r["source"])
            out = []
            for r in payload:
                if "BBC" in r["source"]:
                    out.append({
                        "reportKey": r["reportKey"],
                        "breadth": 4.9,
                        "novelty": 4.8,
                        "evidence": 4.6,
                        "bucket": "macro",
                        "titleZh": "美国拟对 12 个贸易伙伴推出新关税方案",
                        "summaryZh": "美方正拟定针对 12 个贸易伙伴的新关税提案。",
                    })
                elif "Financial Times" in r["source"] and "tariffs" in r["title"].lower():
                    out.append({
                        "reportKey": r["reportKey"],
                        "breadth": 4.5,
                        "novelty": 4.4,
                        "evidence": 4.5,
                        "bucket": "macro",
                        "duplicateOf": bbc_key,
                    })
                elif "Nvidia" in r["title"]:
                    out.append({
                        "reportKey": r["reportKey"],
                        "breadth": 4.2,
                        "novelty": 4.0,
                        "evidence": 4.3,
                        "bucket": "tech",
                        "titleZh": "英伟达季度营收达 999 亿美元大关",  # fabricated number -> guardrail must reject
                    })
                else:
                    out.append({
                        "reportKey": r["reportKey"],
                        "breadth": 3.8,
                        "novelty": 3.5,
                        "evidence": 4.0,
                        "bucket": r["bucket"],
                    })
            return out
        if "先了解这件事" in user_msg:
            return {"paragraphs": ["围绕 12 个贸易伙伴的关税方案引发市场关注。"], "latestMilestoneSummary": "提案正在酝酿。"}
        if "本期导读" in user_msg:
            return {"overview": "本期关注美国拟对 12 个贸易伙伴推出新关税方案。"}
        return {}

    daily = FinancialDailyService(
        svc,
        official_fetcher=_StubOfficial([]),
        market_review_service=_StubMarketReview(),
        now_fn=lambda: now,
        llm_call=mock_llm,
    )
    edition = daily.compose_edition(refresh_upstream=False, allow_llm=True)

    assert edition["coverage"]["editorialEngine"] == "glm"
    all_items = ([edition["lead"]] if edition["lead"] else []) + [
        item for sec in edition["sections"] for item in sec["items"]
    ]
    all_titles = [item["title"] for item in all_items]
    assert not any("互动平台" in t for t in all_titles)
    assert not any("华尔街之狼" in t or "100%！" in t for t in all_titles)

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

    # P1 verification: GLM Chinese translation AND duplicateOf cross-outlet merge must persist to Level 2 & Level 3
    bbc_key = tariff_items[0]["reportKey"]
    bbc_story_id = tariff_items[0]["storyId"]
    detail = daily.get_report_detail(bbc_key)
    assert detail is not None
    assert detail["title"] == "美国拟对 12 个贸易伙伴推出新关税方案"
    assert detail["summary"] == "美方正拟定针对 12 个贸易伙伴的新关税提案。"
    assert any(f["sourceName"] == "Financial Times" for f in detail["followups"])

    tracked = daily.get_tracked_event(bbc_story_id)
    assert tracked is not None
    assert tracked["title"] == "美国拟对 12 个贸易伙伴推出新关税方案"
    assert len(tracked["reports"]) >= 2
    assert {"BBC财经", "Financial Times"}.issubset({r["sourceName"] for r in tracked["reports"]})


def test_latest_edition_never_blocks_and_never_fabricates_premature_evening(tmp_path):
    import threading
    import time

    now = datetime(2026, 11, 25, 14, 10, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    svc.store.upsert_reports([
        {
            "title": "中国人民银行公开市场净投放 2000 亿元",
            "summary": "维护月末流动性平稳。",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "中国人民银行",
            "sourceLevel": "S",
            "official": True,
            "originalUrl": "https://www.pbc.gov.cn/omo-2000",
        }
    ])
    daily = FinancialDailyService(svc, official_fetcher=_StubOfficial([]), now_fn=lambda: now)
    morning = daily.compose_edition(edition_type="morning", refresh_upstream=False, allow_llm=False)
    assert morning["editionKey"] == "2026-11-25-morning"

    # Simulate an active slow refresh holding daily._lock in another thread
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

        # Clicking evening tab at 14:10 must NOT fabricate a fake evening edition
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
    daily = FinancialDailyService(svc, official_fetcher=_StubOfficial([]), now_fn=lambda: now)
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
    daily = FinancialDailyService(svc, official_fetcher=_StubOfficial([]), now_fn=lambda: now)
    reps = [
        {
            "reportKey": "k-huawei",
            "id": "k-huawei",
            "title": "Huawei found guilty of stealing trade secrets in federal court",
            "summary": "A US jury found Huawei guilty of trade secret theft.",
            "publishedAt": (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
            "source": "BBC财经",
            "sourceLevel": "A",
            "originalUrl": "https://bbc.com/huawei",
            "bucket": "tech",
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
            "bucket": "tech",
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
            "bucket": "tech",
        },
    ]
    svc.store.upsert_reports(reps)
    loaded = [{**r, "reportKey": r["id"], "bucket": "tech"} for r in svc.store.load_reports(hours=72)]
    stories = daily.ingest_to_stories(loaded, allow_llm=False)
    # GTA 6 should be filtered as noise; Huawei and Hyundai must NOT merge into the same story
    huawei_story = next(st for st in stories if "Huawei" in st["title"])
    assert len(huawei_story["reports"]) == 1
    assert not any("Hyundai" in r["title"] or "GTA" in r["title"] for r in huawei_story["reports"])


def test_scheduler_passes_refresh_upstream_flag(tmp_path):
    now = datetime(2026, 11, 25, 8, 5, tzinfo=SHANGHAI)
    svc = _make_news_service(tmp_path, lambda: now)
    daily = FinancialDailyService(svc, official_fetcher=_StubOfficial([]), now_fn=lambda: now)
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
