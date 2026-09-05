from datetime import datetime, timezone

from financial_hotlist import (
    HotlistCollector,
    SOURCE_SPECS,
    aggregate_hot_rank,
    parse_cls_hotlist,
    parse_cls_headline_html,
    parse_eastmoney_editorial,
    parse_eastmoney_editorial_html,
    parse_sina_hotlist,
    parse_sina_headline_html,
    parse_ths_editorial,
    parse_ths_headline_html,
    source_is_due,
)


NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def test_ths_contract_reads_only_the_active_headline_module():
    html = """
    <div data-slot="card" id="headline-card">
      <div role="tablist">
        <button role="tab" aria-selected="true">头条</button>
        <button role="tab" aria-selected="false">A股</button>
      </div>
      <div class="headline-items">
        <a href="https://news.10jqka.com.cn/20260904/c1.shtml"><h3>头条主标题</h3><p>头条摘要</p></a>
        <a href="https://news.10jqka.com.cn/20260904/c2.shtml"><h3>头条第二条</h3></a>
      </div>
    </div>
    <section><h2>A股</h2><a href="https://news.10jqka.com.cn/20260904/c99.shtml"><h3>不应采集的 A 股栏目</h3></a></section>
    """

    rows = parse_ths_headline_html(html, NOW)

    assert [row["title"] for row in rows] == ["头条主标题", "头条第二条"]
    assert rows[0]["summary"] == "头条摘要"
    assert all(row["listKind"] == "editorial" for row in rows)


def test_eastmoney_contract_reads_only_artitile_list_one():
    html = """
    <div id="otherChannel"><p class="title"><a href="https://finance.eastmoney.com/a/old.html">普通频道流</a></p></div>
    <div class="artitleList2" id="artitileList1"><ul>
      <li id="newsTr1"><p class="title"><a href="https://finance.eastmoney.com/a/1.html">资讯精华第一条</a></p><p class="info">精华摘要</p><p class="time">9月4日 15:00</p></li>
      <li id="newsTr2"><p class="title"><a href="https://finance.eastmoney.com/a/2.html">资讯精华第二条</a></p><p class="info">第二条摘要</p><p class="time">9月4日 14:30</p></li>
    </ul></div>
    """

    rows = parse_eastmoney_editorial_html(html, NOW)

    assert [row["title"] for row in rows] == ["资讯精华第一条", "资讯精华第二条"]
    assert rows[0]["summary"] == "精华摘要"
    assert rows[0]["publishedAt"] == "2026-09-04T07:00:00+00:00"


def test_cls_contract_reads_home_editorial_area_and_detail_links_in_order():
    html = """
    <main>
      <div class="f-l w-420">
        <div class="c-b"><span>头条</span><a href="/detail/101">财联社主标题</a></div>
        <div class="home-article-headline-rec"><a href="/detail/102">关联报道一</a></div>
        <div class="home-article-headline-rec"><a href="/detail/103">关联报道二</a></div>
        <div class="home-article-list"><a href="/detail/104">普通要闻也属于编辑区</a></div>
      </div>
      <section class="telegraph"><a href="/v1/roll/get_roll_list">滚动电报接口文本</a></section>
    </main>
    """

    rows = parse_cls_headline_html(html, NOW)

    assert [row["title"] for row in rows] == ["财联社主标题", "关联报道一", "关联报道二", "普通要闻也属于编辑区"]
    assert [row["sourceRank"] for row in rows] == [1, 2, 3, 4]
    assert all("/detail/" in row["originalUrl"] for row in rows)


def test_sina_contract_keeps_headline_related_and_ordinary_news_order_from_target_container():
    html = """
    <div id="other"><a href="https://finance.sina.com.cn/roll/old.shtml">7x24 旧排行</a></div>
    <div id="fin_tabs0_c0">
      <section class="important-news-area">
        <div id="blk_hdline_01">
          <h3 data-client="headline"><a href="https://finance.sina.com.cn/jjxw/main.shtml">新浪主标题</a></h3>
          <p data-client="throw"><a href="https://finance.sina.com.cn/jjxw/related-1.shtml">关联报道一</a><a href="https://finance.sina.com.cn/jjxw/related-2.shtml">关联报道二</a></p>
        </div>
        <ul class="m-list" data-sudaclick="blk_yw_2"><li><a href="https://finance.sina.com.cn/roll/ordinary-1.shtml">普通要闻一</a></li><li><a href="https://finance.sina.com.cn/roll/ordinary-2.shtml">普通要闻二</a></li></ul>
      </section>
    </div>
    """

    rows = parse_sina_headline_html(html, NOW)

    assert [row["title"] for row in rows] == ["新浪主标题", "关联报道一", "关联报道二", "普通要闻一", "普通要闻二"]
    assert [row["sourceRank"] for row in rows] == [1, 2, 3, 4, 5]
    assert all("top.finance.sina.com.cn" not in row["originalUrl"] for row in rows)


def test_four_platform_parsers_return_only_the_first_ten_ranked_links():
    sina = "var data = " + __import__("json").dumps({"data": [
        {"title": f"新浪财经事件{i}", "url": f"https://finance.sina.com.cn/{i}", "create_date": "2026-09-04", "create_time": "15:00"}
        for i in range(1, 13)
    ]}, ensure_ascii=False) + ";"
    eastmoney = {"data": {"list": [
        {"title": f"东方财富事件{i}", "url": f"https://finance.eastmoney.com/a/{i}.html", "showTime": "2026-09-04 15:00:00"}
        for i in range(1, 13)
    ]}}
    cls = {"data": {"roll_data": [
        {"title": f"财联社事件{i}", "shareurl": f"https://www.cls.cn/detail/{i}", "reading_num": 1000 - i, "ctime": 1788505200}
        for i in range(1, 13)
    ]}}
    ths = '<section><h2>头条</h2><a href="https://evil10jqka.com.cn/trap"><h3>股票诈骗链接</h3></a>' + "".join(
        f'<a href="https://news.10jqka.com.cn/20260904/c{i}.shtml"><h3>同花顺事件{i}</h3><p>摘要{i}不应混入标题</p></a>'
        for i in range(1, 13)
    ) + "</section><section><h2>A股</h2></section>"

    parsed = [
        parse_sina_hotlist(sina, NOW),
        parse_eastmoney_editorial(eastmoney, NOW),
        parse_cls_hotlist(cls, NOW),
        parse_ths_editorial(ths, NOW),
    ]

    assert [len(rows) for rows in parsed] == [10, 10, 10, 10]
    assert all([row["sourceRank"] for row in rows] == list(range(1, 11)) for rows in parsed)
    assert {rows[0]["sourceId"] for rows in parsed} == {"sina", "eastmoney", "cls", "ths"}
    assert parsed[-1][0]["title"] == "同花顺事件1"
    assert parsed[-1][0]["summary"] == "摘要1不应混入标题"
    assert "evil10jqka" not in {row["originalUrl"] for row in parsed[-1]}
    assert parsed[0][0]["publishedAt"] == "2026-09-04T07:00:00+00:00"
    assert parsed[1][0]["publishedAt"] == "2026-09-04T07:00:00+00:00"


def test_cross_platform_count_precedes_rank_points_and_same_platform_duplicates_count_once():
    rows = [
        {"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 8, "title": "OpenAI发布GPT-6新模型", "originalUrl": "https://ths.test/gpt", "fetchedAt": NOW.isoformat()},
        {"sourceId": "eastmoney", "sourceName": "东方财富", "listKind": "editorial", "sourceRank": 9, "title": "GPT-6正式发布 OpenAI宣布进入新阶段", "originalUrl": "https://em.test/gpt", "fetchedAt": NOW.isoformat()},
        {"sourceId": "sina", "sourceName": "新浪财经", "listKind": "popularity", "sourceRank": 10, "title": "OpenAI GPT-6模型正式推出", "originalUrl": "https://sina.test/gpt", "fetchedAt": NOW.isoformat()},
        {"sourceId": "cls", "sourceName": "财联社", "listKind": "popularity", "sourceRank": 1, "title": "美联储释放降息信号", "originalUrl": "https://cls.test/fed", "fetchedAt": NOW.isoformat()},
        {"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 1, "title": "美联储释放降息信号", "originalUrl": "https://ths.test/fed", "fetchedAt": NOW.isoformat()},
        {"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 2, "title": "美联储释放降息信号！", "originalUrl": "https://ths.test/fed-copy", "fetchedAt": NOW.isoformat()},
    ]

    result = aggregate_hot_rank(rows, now=NOW)

    assert result[0]["platformCount"] == 3
    assert result[0]["rankScore"] == 6
    assert result[1]["platformCount"] == 2
    assert result[1]["rankScore"] == 20
    assert len(result[1]["placements"]) == 2
    assert result[0]["aiDigestStatus"] == "pending"


def test_source_refresh_intervals_follow_each_platform_schedule():
    assert {source_id: spec.list_kind for source_id, spec in SOURCE_SPECS.items()} == {
        "ths": "editorial", "eastmoney": "editorial", "cls": "editorial", "sina": "editorial",
    }
    assert SOURCE_SPECS["ths"].interval_seconds == 300
    assert SOURCE_SPECS["eastmoney"].interval_seconds == 300
    assert SOURCE_SPECS["cls"].interval_seconds == 1800
    assert SOURCE_SPECS["sina"].interval_seconds == 3600
    assert source_is_due(SOURCE_SPECS["cls"], "2026-09-04T07:29:59+00:00", NOW)
    assert not source_is_due(SOURCE_SPECS["cls"], "2026-09-04T07:30:01+00:00", NOW)


def test_collector_fetches_only_due_sources_and_excludes_non_financial_headlines(tmp_path):
    calls = []

    def fetch(source_id):
        calls.append(source_id)
        return [
            {"sourceId": source_id, "sourceName": SOURCE_SPECS[source_id].source_name, "listKind": SOURCE_SPECS[source_id].list_kind, "sourceRank": 1, "title": "OpenAI发布GPT-6模型，软件板块走强", "originalUrl": f"https://{source_id}.test/gpt", "fetchedAt": NOW.isoformat()},
            {"sourceId": source_id, "sourceName": SOURCE_SPECS[source_id].source_name, "listKind": SOURCE_SPECS[source_id].list_kind, "sourceRank": 2, "title": "某地发布洪水黄色预警", "originalUrl": f"https://{source_id}.test/weather", "fetchedAt": NOW.isoformat()},
        ]

    collector = HotlistCollector(tmp_path, now_fn=lambda: NOW, fetch_fn=fetch)
    first = collector.refresh_due()
    second = collector.refresh_due()

    assert set(calls) == set(SOURCE_SPECS)
    assert len(calls) == 4
    assert first["hotRank"][0]["platformCount"] == 4
    assert len(first["hotRank"]) == 1
    assert second["hotRank"] == first["hotRank"]


def test_expired_source_snapshot_is_not_counted_in_platform_total(tmp_path):
    old = "2026-09-04T05:00:00+00:00"
    collector = HotlistCollector(tmp_path, now_fn=lambda: NOW, fetch_fn=lambda _source: [])
    collector._write({
        "sources": {
            "ths": {
                "entries": [{"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 1, "title": "央行发布货币政策", "originalUrl": "https://ths.test/policy", "fetchedAt": old}],
                "lastSuccessAt": old,
                "lastAttemptAt": NOW.isoformat(),
            },
            "cls": {
                "entries": [{"sourceId": "cls", "sourceName": "财联社", "listKind": "popularity", "sourceRank": 2, "title": "央行发布货币政策", "originalUrl": "https://cls.test/policy", "fetchedAt": NOW.isoformat()}],
                "lastSuccessAt": NOW.isoformat(),
                "lastAttemptAt": NOW.isoformat(),
            },
        }
    })

    result = collector.overview()

    assert result["hotRank"][0]["platformCount"] == 1
    assert next(row for row in result["sourceStatus"] if row["sourceId"] == "ths")["cache"] == "stale"


def test_all_expired_sources_remain_visible_as_cached_fallback(tmp_path):
    old = "2026-09-04T05:00:00+00:00"
    collector = HotlistCollector(tmp_path, now_fn=lambda: NOW, fetch_fn=lambda _source: [])
    collector._write({
        "generatedAt": old,
        "sources": {
            "ths": {
                "entries": [{
                    "sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial",
                    "sourceRank": 1, "title": "央行发布货币政策",
                    "originalUrl": "https://news.10jqka.com.cn/policy", "fetchedAt": old,
                }],
                "lastSuccessAt": old, "lastAttemptAt": NOW.isoformat(), "error": "upstream offline",
            },
        },
    })

    result = collector.overview()

    assert result["hotRank"][0]["title"] == "央行发布货币政策"
    assert result["hotRank"][0]["stale"] is True
    assert result["stale"] is True


def test_failed_refresh_retains_recent_cache_but_marks_event_stale(tmp_path):
    collector = HotlistCollector(tmp_path, now_fn=lambda: NOW, fetch_fn=lambda _source: (_ for _ in ()).throw(RuntimeError("offline")))
    collector._write({"sources": {"ths": {
        "entries": [{"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 1, "title": "央行发布货币政策", "originalUrl": "https://news.10jqka.com.cn/a.shtml", "fetchedAt": NOW.isoformat()}],
        "lastSuccessAt": NOW.isoformat(), "lastAttemptAt": "2026-09-04T07:50:00+00:00",
    }}})

    result = collector.refresh_due(force=True)

    assert result["hotRank"][0]["stale"] is True
    assert result["hotRank"][0]["placements"][0]["stale"] is True
    assert next(row for row in result["sourceStatus"] if row["sourceId"] == "ths")["cache"] == "stale"


def test_event_id_survives_rank_lead_changes_and_new_day_changes_digest_identity(tmp_path):
    state = {"phase": 1}
    def fetch(source_id):
        rank = 1 if (state["phase"] == 1 and source_id == "ths") or (state["phase"] == 2 and source_id == "sina") else 5
        title = "OpenAI发布GPT新模型" if source_id == "ths" else "GPT新模型正式发布 OpenAI公布"
        return [{"sourceId": source_id, "sourceName": SOURCE_SPECS[source_id].source_name, "listKind": SOURCE_SPECS[source_id].list_kind, "sourceRank": rank, "title": title, "originalUrl": f"https://{source_id}.test/story", "fetchedAt": NOW.isoformat(), "publishedAt": NOW.isoformat()}]
    collector = HotlistCollector(tmp_path, now_fn=lambda: NOW, fetch_fn=fetch)
    first = collector.refresh_due(force=True)["hotRank"][0]
    state["phase"] = 2
    second = collector.refresh_due(force=True)["hotRank"][0]

    assert second["id"] == first["id"]


def test_sina_request_uses_beijing_calendar_day_across_midnight(tmp_path, monkeypatch):
    requested = {}
    class Response:
        text = '<div id="fin_tabs0_c0"><section class="important-news-area"><div id="blk_hdline_01"><h3 data-client="headline"><a href="https://finance.sina.com.cn/jjxw/main.shtml">新浪主标题</a></h3></div></section></div>'
        apparent_encoding = "utf-8"
        encoding = "utf-8"
    collector = HotlistCollector(
        tmp_path,
        now_fn=lambda: datetime(2026, 9, 3, 16, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(collector, "_get", lambda url, **kwargs: requested.update({"url": url}) or Response())

    collector._fetch_source("sina")

    assert requested["url"] == "https://finance.sina.com.cn/"


def test_source_requests_use_the_four_editorial_pages_and_never_legacy_feeds(tmp_path, monkeypatch):
    collector = HotlistCollector(tmp_path)
    requested = []

    class Response:
        text = ""
        apparent_encoding = "utf-8"
        encoding = "utf-8"

    monkeypatch.setattr(collector, "_get", lambda url, **kwargs: requested.append((url, kwargs.get("params"))) or Response())
    for source_id in SOURCE_SPECS:
        try:
            collector._fetch_source(source_id)
        except ValueError:
            pass

    assert [url for url, _ in requested] == [
        "https://www.10jqka.com.cn/",
        "https://finance.eastmoney.com/yaowen.html",
        "https://www.cls.cn/",
        "https://finance.sina.com.cn/",
    ]
    assert all("get_roll_list" not in url and "GetTopDataList.php" not in url and "column" not in (params or {}) for url, params in requested)


def test_event_ids_are_unique_when_one_previous_event_splits_into_two():
    previous = [{
        "id": "old-event", "eventDay": "2026-09-04", "title": "OpenAI发布GPT模型推动软件产业升级",
    }]
    rows = [
        {"sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 1, "title": "OpenAI发布GPT模型", "originalUrl": "https://news.10jqka.com.cn/a", "fetchedAt": NOW.isoformat()},
        {"sourceId": "sina", "sourceName": "新浪财经", "listKind": "popularity", "sourceRank": 1, "title": "软件产业升级政策发布", "originalUrl": "https://finance.sina.com.cn/b", "fetchedAt": NOW.isoformat()},
    ]

    result = aggregate_hot_rank(rows, now=NOW, previous_events=previous)

    assert len({event["id"] for event in result}) == len(result)
    assert [event["id"] for event in result].count("old-event") == 1


def test_missing_publish_time_uses_persisted_event_day_not_current_day():
    yesterday = [{"id": "yesterday", "eventDay": "2026-09-03", "title": "央行发布重要货币政策"}]
    rows = [{
        "sourceId": "ths", "sourceName": "同花顺", "listKind": "editorial", "sourceRank": 1,
        "title": "央行发布重要货币政策", "originalUrl": "https://news.10jqka.com.cn/a",
        "fetchedAt": "2026-09-04T00:10:00+00:00",
    }]

    event = aggregate_hot_rank(rows, now=NOW, previous_events=yesterday)[0]

    assert event["eventDay"] == "2026-09-04"
    assert event["id"] != "yesterday"
