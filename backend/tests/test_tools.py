import time

import tools


def test_slow_tool_times_out_without_blocking_worker(monkeypatch):
    def slow(_args):
        time.sleep(0.2)
        return {"status": "ok"}

    monkeypatch.setitem(tools._HANDLERS, "slow_test", slow)
    started = time.monotonic()
    result = tools.execute_scoped_tool("slow_test", {}, None, timeout_seconds=0.02)

    assert time.monotonic() - started < 0.12
    assert result["status"] == "unavailable"
    assert "20" in result["data_gap"]


def test_search_web_falls_back_to_bing_and_allowed_for_guests(monkeypatch):
    from types import SimpleNamespace
    import route_policy

    guest_tools = route_policy.allowed_tools(SimpleNamespace(kind="guest"))
    owner_tools = route_policy.allowed_tools(SimpleNamespace(kind="owner"))
    assert {"search_web", "search_financial_news"}.issubset(guest_tools)
    assert {"search_web", "search_financial_news"}.issubset(owner_tools)

    monkeypatch.setattr(tools, "_search_web_zhipu", lambda *a, **kw: [])
    monkeypatch.setattr(
        tools,
        "_search_web_bing_rss",
        lambda q, count=8: [
            {"title": "摩根大通预计美联储加息三次", "source": "财联社", "published_at": "2026-11-25", "summary": "共75bp至4.50%-4.75%", "url": "https://cls.cn/1"}
        ],
    )
    res = tools.exec_tool("search_web", {"query": "美联储 加息 摩根大通"})
    assert res["provider"] == "bing_news_rss"
    assert res["count"] == 1
    assert "摩根大通" in res["results"][0]["title"]


def test_search_financial_news_queries_sqlite_store(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from financial_news_store import FinancialNewsStore

    db_dir = tmp_path / "financial-news"
    db_dir.mkdir(parents=True, exist_ok=True)
    store = FinancialNewsStore(db_dir / "events.db")
    store.upsert_reports([
        {
            "title": "美联储会议纪要显示鹰派倾向，高盛预计 12 月加息 25bp",
            "summary": "高盛预测联邦基金利率峰值达到 4.25%-4.50%。",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "source": "华尔街见闻",
            "originalUrl": "https://wallstreetcn.com/fed-1",
        }
    ])
    store.close()
    monkeypatch.setattr("data_paths.cache_path", lambda name: tmp_path / name)

    res = tools.exec_tool("search_financial_news", {"query": "美联储 高盛 加息", "days": 7})
    assert res["count"] == 1
    assert "高盛" in res["results"][0]["title"]
