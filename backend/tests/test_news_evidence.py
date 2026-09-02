import json
from datetime import datetime, timezone

import newsradar
from financial_news import FinancialNewsService


def test_rss_explicit_source_is_preserved(monkeypatch):
    from io import BytesIO
    xml=b'<rss><channel><item><title>Fed interest rates unchanged</title><source>Reuters</source><link>https://example.test/a</link></item></channel></rss>'
    monkeypatch.setattr(newsradar.urllib.request,"urlopen",lambda *a,**k:BytesIO(xml))
    result=newsradar._fetch_source({"name":"BBC","url":"https://example.test/rss"},6,None,[])
    assert result[0]["originSource"] == "Reuters"


def test_global_news_app_does_not_block_rss_on_retired_ashare_market_probe():
    import app
    assert app.financial_news_service.status()["marketProbe"]["configured"] is False


def test_slow_rss_does_not_hold_successful_sources_indefinitely(monkeypatch):
    import threading
    release=threading.Event()
    monkeypatch.setattr(newsradar,"BATCH_TIMEOUT",0.05)
    monkeypatch.setattr(newsradar,"_fetch_source",lambda src,*args: release.wait(1) if src["name"]=="slow" else [])
    try:
        rows=newsradar._fetch_sources([(0,{"name":"fast"}),(1,{"name":"slow"})],6,None,[])
        assert rows == [(0,{"name":"fast"},[]),(1,{"name":"slow"},None)]
    finally:
        release.set()


def test_radar_keeps_raw_reports_and_individual_fetch_statuses(tmp_path, monkeypatch):
    cfg = {"sources": [{"name": n, "hint": "macro", "url": f"https://{n}.test/feed"} for n in ["A", "B", "C"]],
           "industries": [{"key": "macro", "name": "宏观", "accent": "orange"}]}
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(newsradar, "SOURCES_FILE", str(path))
    monkeypatch.setattr(newsradar, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(newsradar, "CACHE_FILE", str(tmp_path / "radar.json"))
    monkeypatch.setattr(newsradar, "_media_fields", lambda: {})
    monkeypatch.setattr(newsradar.rss.rss_catalog, "record_radar_result", lambda *a: None)
    monkeypatch.setattr(newsradar, "_fetch_source", lambda src, *a: None if src["name"] == "C" else
                        [{"title": "same title", "source": src["name"], "url": f"https://{src['name']}.test/article", "ts": 1788350400}])
    data = newsradar.fetch_radar()
    assert len(data["industries"][0]["items"]) == 1
    assert len(data["rawReports"]) == 2
    assert {s["source"]: s["ok"] for s in data["sourceStatuses"]} == {"A": True, "B": True, "C": False}


def test_source_health_uses_financial_radar_not_ai_media_catalog_and_survives_restart(tmp_path, monkeypatch):
    now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    svc = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: now)
    monkeypatch.setattr(svc, "_apply_ai_refinements", lambda e: None)
    monkeypatch.setattr(newsradar, "fetch_radar", lambda: {"industries": [], "rawReports": [], "sources": [],
        "sourceStatuses": [{"source": "CNBC", "ok": True, "count": 6, "fetchedAt": now.isoformat()},
                           {"source": "SEC", "ok": False, "count": 0, "fetchedAt": now.isoformat(), "error": "HTTP 403"}]})
    svc.refresh_rss()
    restarted = FinancialNewsService(cache_dir=tmp_path, now_fn=lambda: now)
    states = {r["name"]: r for r in restarted.status()["sources"]}
    assert states["CNBC"]["count"] == 6
    assert states["CNBC"]["ok"] is True
    assert states["SEC"]["lastFailure"] == "HTTP 403"
    assert states["新华社"]["ok"] is False
