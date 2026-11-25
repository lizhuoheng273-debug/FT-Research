from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient

import app as app_module
from financial_daily import FinancialDailyScheduler, FinancialDailyService, _passes_guardrails
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
