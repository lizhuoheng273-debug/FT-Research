from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app
from financial_news import FinancialNewsService, global_importance_score
from following_news import build_following_stream, normalize_codes


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


def _event(**overrides):
    event = {
        "id": "event-1",
        "title": "央行公布货币政策决定",
        "summary": "官方发布政策决定，未披露额外数字。",
        "publishedAt": (NOW - timedelta(minutes=20)).isoformat(),
        "latestAt": (NOW - timedelta(minutes=20)).isoformat(),
        "category": "宏观政策",
        "source": "中国人民银行",
        "sourceTier": 35,
        "sourceLevel": "S",
        "relatedSources": ["中国人民银行"],
        "relatedSourceCount": 1,
        "independentSourceCount": 1,
        "reports": [],
    }
    event.update(overrides)
    return event


def test_global_score_uses_importance_authority_timeliness_and_confirmation_without_a_share_gate():
    score, breakdown, reasons = global_importance_score(_event(importanceType="policy_decision"), now=NOW)

    assert sum(breakdown.values()) == score
    assert breakdown["importance"] == 30
    assert breakdown["authority"] == 25
    assert breakdown["timeliness"] == 25
    assert breakdown["independentConfirmation"] == 20
    assert any("本站计算" in reason for reason in reasons)


def test_global_score_does_not_reward_hype_words_or_future_dates():
    plain = _event(title="市场出现明确政策安排", importanceType="none", sourceTier=8, sourceLevel="C", relatedSourceCount=1)
    hype = _event(title="重磅暴涨黑马横空出世", importanceType="none", sourceTier=8, sourceLevel="C", relatedSourceCount=1)
    future = _event(publishedAt=(NOW + timedelta(days=2)).isoformat(), latestAt=(NOW + timedelta(days=2)).isoformat())

    plain_score, _, _ = global_importance_score(plain, now=NOW)
    hype_score, _, _ = global_importance_score(hype, now=NOW)
    future_score, future_breakdown, _ = global_importance_score(future, now=NOW)

    assert hype_score == plain_score
    assert future_score != plain_score
    assert future_breakdown["timeliness"] == 0


def test_compose_keeps_single_source_events_in_legacy_feed_not_curated_hot_list(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    rows = [
        service.normalize_quick_rows([{
            "标题": ["美联储调整利率安排", "欧洲央行更新资产购买", "联合国通过停火决议", "某国发布财政预算", "主要交易所修改规则", "大型银行披露年度业绩", "能源供应出现中断", "芯片厂商宣布扩产计划", "汽车厂商发布召回公告", "航运公司暂停航线", "粮食出口政策发生变化", "大型保险公司披露风险", "央行公布外汇政策", "监管机构发布资本要求", "国际组织下调经济展望", "油价供应端出现变化", "半导体设备出口限制", "主要市场交易中断", "航空公司披露经营变化", "大型药企公布试验结果", "云服务商发布安全公告", "港口发生重大事故", "政府发布贸易措施", "银行系统发生故障", "矿产供应协议签署"][index],
            "摘要": "官方发布明确决定",
            "发布时间": "2026-08-31 15:55:00",
        }], source="Federal Reserve")[0]
        for index in range(25)
    ]
    rows[0]["importanceType"] = "policy_decision"

    result = service._compose(rows, [], [])

    assert result["globalHighlights"] == []
    assert len(result["feed"]) == 25
    assert result["aShareHot"] == []


def test_substantive_update_changes_event_timestamp_but_repost_does_not_refresh_importance(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    old = service.normalize_quick_rows([{"标题": "某央行公布政策决定", "摘要": "首次公布", "发布时间": "2026-08-30 15:55:00"}], source="Federal Reserve")[0]
    repost = service.normalize_quick_rows([{"标题": "某央行公布政策决定！", "摘要": "首次公布", "发布时间": "2026-08-31 15:55:00"}], source="MarketWatch")[0]
    update = service.normalize_quick_rows([{"标题": "某央行公布政策决定：新增执行安排", "摘要": "新增执行安排", "发布时间": "2026-08-31 15:56:00"}], source="Federal Reserve")[0]

    repost_event = service.cluster_items([old, repost])[0]
    updated_event = service.cluster_items([old, update])[0]

    assert repost_event["substantiveUpdate"] is False
    assert updated_event["substantiveUpdate"] is True


def test_substantive_update_keeps_the_original_event_id(tmp_path):
    service = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)
    old = service.normalize_quick_rows([{"标题": "某央行公布政策决定", "摘要": "首次公布", "发布时间": "2026-08-30 15:55:00"}], source="Federal Reserve")[0]
    update = service.normalize_quick_rows([{"标题": "某央行公布政策决定：新增执行安排", "摘要": "新增执行安排", "发布时间": "2026-08-31 15:56:00"}], source="Federal Reserve")[0]

    original_event = service.cluster_items([old])[0]
    updated_event = service.cluster_items([old, update])[0]

    assert updated_event["id"] == original_event["id"]


def test_following_stream_requires_code_normalization_and_deduplicates_same_event_with_pagination():
    assert normalize_codes(["600519", "bad", "600519", " 000001 ", "1234567"]) == ["600519", "000001"]
    rows = build_following_stream(
        ["600519"],
        profiles={"600519": {"shortName": "贵州茅台", "industry": "白酒", "mainBusiness": "白酒生产销售"}},
        direct_rows={"600519": [
            {"title": "公司发布公告", "date": "2026-08-31", "kind": "公告", "url": "https://example.test/a"},
            {"title": "公司发布公告", "date": "2026-08-31", "kind": "新闻", "url": "https://example.test/a"},
        ]},
        events=[{
            "id": "event-1", "title": "白酒行业政策变化", "summary": "行业消息", "publishedAt": "2026-08-31T07:00:00+00:00",
            "latestAt": "2026-08-31T07:00:00+00:00", "category": "产业", "track": "白酒", "importanceScore": 60,
        }],
    )

    assert len(rows) == 2
    assert rows[0]["relationType"] in {"个股", "行业"}
    assert rows[0]["evidence"]
    assert build_following_stream(["600519"], profiles={}, direct_rows={}, events=[]) == []


def test_following_endpoint_is_query_only_and_returns_paginated_rows(monkeypatch):
    monkeypatch.setattr(app.financial_news_service, "following", lambda codes, page, page_size: {
        "items": [{"code": "600519", "title": "关注消息", "publishedAt": "2026-08-31"}],
        "page": page, "pageSize": page_size, "hasMore": False,
    })
    response = TestClient(app.app).post("/api/finance/news/following", json={"codes": ["600519"], "page": 2, "pageSize": 1})

    assert response.status_code == 200
    assert response.json()["data"]["page"] == 2
