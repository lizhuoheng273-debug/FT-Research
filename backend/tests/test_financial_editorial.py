from datetime import datetime, timezone

import pytest

from financial_news import FinancialNewsService, _independent_source_names

NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def service(tmp_path, monkeypatch):
    import glm_config
    monkeypatch.setattr(glm_config, "load_glm_config", lambda: {})
    return FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: NOW)


def event(title, count=3, **extra):
    return dict(title=title, summary="", independentSourceCount=count, sourceLevel="A",
                source="CNBC", originalUrl="https://example.test/news", publishedAt="2026-09-02T11:30:00+00:00", **extra)


@pytest.mark.parametrize("title", ["全球山地冰川呈加速消融态势", "电影延长上映至10月10日", "明星旅游探访西藏", "伊朗说其新战略将摧毁敌方根基"])
def test_non_financial_reports_never_enter_hot_list_even_if_widely_reprinted(service, title):
    assert service._is_global_highlight(event(title)) is False


@pytest.mark.parametrize("title", ["美联储降息25个基点", "英伟达财报营收超预期", "韩国股市暴跌触发熔断", "干旱导致小麦出口减少，国际粮价上涨", "US bond yields surge after inflation data"])
def test_financial_events_with_independent_coverage_are_eligible(service, title):
    assert service._is_global_highlight(event(title)) is True


def test_even_official_single_source_is_not_multi_source_hot_news(service):
    assert not service._is_global_highlight(event("美联储降息25个基点", 1, official=True))


def test_unclickable_or_unsafe_originals_do_not_enter_top_five(service):
    for url in ["", "javascript:alert(1)", "https://"]:
        row = event("美联储降息25个基点")
        row["originalUrl"] = url
        assert not service._is_global_highlight(row)


def test_repeated_updates_by_one_publisher_are_only_one_independent_source():
    reports = [{"source": "CNBC", "title": "美联储降息", "summary": str(i)} for i in range(4)]
    assert _independent_source_names(reports) == ["CNBC"]


def test_same_wire_attribution_is_not_three_independent_confirmations():
    reports = [{"source": s, "title": "美联储降息25个基点", "summary": f"据路透社报道，{i}号消息"}
               for i, s in enumerate(["同花顺快讯", "新浪财经快讯", "东方财富快讯"])]
    assert _independent_source_names(reports) == ["路透社"]


def test_cls_dateline_in_aggregated_text_is_one_wire_not_four_publishers():
    reports = [{"source": s, "title": "某公司财报公布", "summary": f"【公司财报】财联社9月2日电，利润增长，转载段落{i}"}
               for i, s in enumerate(["同花顺快讯", "新浪财经快讯", "东方财富快讯", "财联社电报"])]
    assert _independent_source_names(reports) == ["财联社"]


def test_routine_lottery_results_are_not_global_market_highlights(service):
    assert not service._is_global_highlight(event("某公司IPO网上发行最终中签率0.024%"))


def test_trade_company_name_does_not_turn_contract_into_macro_release():
    from financial_editorial import financial_topic
    assert financial_topic({"title": "中国船舶签订造船合同", "summary": "中国船舶工业贸易有限公司签订10亿美元合同"}) == "company_disclosure"


def test_raw_rss_reports_retain_evidence_that_the_radar_display_deduplicates(service):
    raw = [{"title": "美联储降息", "source": s, "ts": NOW.timestamp() - 30, "url": f"https://{s}.test/a"} for s in ["CNBC", "BBC"]]
    rows = service.normalize_radar({"rawReports": raw, "industries": [{"name": "宏观", "items": raw[:1]}]})
    assert {r["source"] for r in rows} == {"CNBC", "BBC"}


def test_top_five_only_and_no_single_source_fillers(service):
    titles = ["美联储利率决议公布", "韩国股市触发熔断", "日本央行上调政策利率", "英伟达财报收入大增", "欧元区通胀下降", "国际原油库存超预期", "美国非农就业低于预期"]
    rows = []
    for i, title in enumerate(titles):
        for src in ["CNBC", "BBC财经"]:
            rows += service.normalize_quick_rows([{"标题": title, "摘要": "经济金融数据公布", "发布时间": "2026-09-02 19:30:00", "链接": f"https://{src}.test/{i}"}], source=src)
    result = service._compose(rows, [], [])
    assert len(result["globalHighlights"]) == 5
    assert all(e["independentSourceCount"] == 2 for e in result["globalHighlights"])


def test_old_snapshot_cannot_bypass_new_editorial_rules(service):
    service.save_payload({"globalHighlights": [event("冰川正在融化"), event("韩国股市触发熔断", 1)], "feed": []})
    assert service.overview()["globalHighlights"] == []


def test_roundup_cannot_bridge_unrelated_stock_and_bond_events(service):
    titles = ["【美股盘前要闻速递】①全球主要国债收益率持续走高。②戴尔科技盘前涨9.76%。③SK海力士美股盘前跌超2%。",
              "全球主要国债收益率持续走高", "戴尔科技盘前涨9.76%", "SK海力士美股盘前跌超2%"]
    rows = [dict(event(title), sourceTier=30, id=str(i)) for i, title in enumerate(titles)]
    assert len(service.cluster_items(rows)) == 4
    assert not service._is_global_highlight(event(titles[0]))


def test_fulltext_bracketed_headline_still_matches_its_short_headline():
    from financial_news import _similar
    assert _similar("【美联储宣布利率决议】" + "详细经济政策内容" * 20, "美联储宣布利率决议")


def test_identical_wire_body_with_dateline_removed_counts_once():
    body = "全球主要国债收益率持续走高，英国10年期国债收益率上涨7个基点至5.29%，为2007年8月以来最高水平。德国10年期国债收益率上涨5个基点至3.39%。"
    reports = [dict(source="同花顺快讯", title="全球主要国债收益率持续走高", summary=body),
               dict(source="财联社电报", title="全球主要国债收益率持续走高", summary="【全球主要国债收益率持续走高】财联社9月2日电，" + body)]
    assert _independent_source_names(reports) == ["财联社"]


def test_parenthesized_original_publisher_is_not_another_source():
    reports = [dict(source="同花顺快讯", title="美国核心通胀回落", summary="财政部长发表经济展望。（新浪财经）"),
               dict(source="新浪财经快讯", title="美国核心通胀回落", summary="财政部长发表经济展望。")]
    assert _independent_source_names(reports) == ["新浪财经"]


def test_compose_retains_wire_attribution_and_cache_flags_through_sqlite(service):
    raw = [dict(title="Fed interest rates unchanged", source=s, originSource="Reuters", stale=True, ts=NOW.timestamp()-30, url=f"https://{s}.test/story") for s in ["CNBC", "BBC"]]
    result=service._compose([], service.normalize_radar({"rawReports":raw}), [])
    assert result["globalHighlights"] == []
    assert result["feed"][0]["independentSources"] == ["路透社"]
    assert result["feed"][0]["stale"] is True
    assert all(r["originSource"] == "Reuters" for r in service.store.load_reports())
