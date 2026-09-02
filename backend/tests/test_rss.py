from datetime import datetime, timezone
from pathlib import Path

import pytest

import rss


RSS = '''<?xml version="1.0"?><rss><channel><title>测试媒体</title>
<item><guid>one</guid><title>第一条</title><link>https://example.com/one</link>
<pubDate>Tue, 02 Sep 2026 10:00:00 +0800</pubDate><description><![CDATA[<p>摘要 <b>一</b> &amp; 继续</p>]]></description></item>
<item><guid>two</guid><title>第二条</title><link>https://example.com/two</link>
<pubDate>Mon, 01 Sep 2026 10:00:00 +0800</pubDate><description>第二个摘要</description></item>
<item><guid>three</guid><title>第三条</title><link>https://example.com/three</link>
<pubDate>Sun, 31 Aug 2026 10:00:00 +0800</pubDate><description>第三个摘要</description></item>
<item><guid>four</guid><title>第四条</title><link>https://example.com/four</link>
<pubDate>Sat, 30 Aug 2026 10:00:00 +0800</pubDate><description>第四个摘要</description></item>
</channel></rss>'''.encode()

ATOM = '''<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom 媒体</title>
<entry><id>tag:atom,1</id><title>Atom 新闻</title><link href="https://atom.example/story"/>
<updated>2026-09-02T02:00:00Z</updated><summary type="html">&lt;p&gt;Atom 摘要&lt;/p&gt;</summary></entry></feed>'''.encode()


def test_removed_subscriptions_are_not_fetched_or_returned(tmp_path):
    fetched = []
    def fetch(url):
        fetched.append(url)
        return RSS
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=fetch, validate_dns=False)
    catalog.refresh_builtins()
    assert not {"36kr", "technode"} & {s["id"] for s in catalog.sources()}
    assert not any("36kr.com" in url or "technode.com" in url for url in fetched)


@pytest.mark.parametrize("radar_items", [[], [{"title": "过滤后的旧标题", "url": "https://example.com/old", "time": "09-01 10:00"}]])
def test_filtered_radar_does_not_replace_rss_subscription_cache(tmp_path, radar_items):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: RSS, validate_dns=False)
    source = catalog.source_defs[0]
    snapshot = catalog.refresh(source)
    catalog.record_radar_result(source, radar_items)
    assert catalog.sources()[0] == snapshot


def test_radar_cannot_clear_subscription_failure_state(tmp_path):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: RSS, validate_dns=False)
    source = catalog.source_defs[0]
    catalog.refresh(source)
    catalog.fetcher = lambda _url: (_ for _ in ()).throw(OSError("offline"))
    catalog.refresh(source)
    snapshot = catalog.sources()[0]
    catalog.record_radar_result(source, [])
    assert catalog.sources()[0] == snapshot


def test_full_text_feed_over_two_mb_is_downloaded_and_parsed(monkeypatch):
    import io
    # Full-text RSS can exceed 2 MB even when only three headlines are shown.
    raw = RSS.replace(b"</channel>", b"<!--" + b"x" * 2_300_000 + b"--></channel>")
    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(raw))}
    class Opener:
        def open(self, request, timeout):
            return Response(raw)
    monkeypatch.setattr(rss, "validate_public_url", lambda url: url)
    monkeypatch.setattr(rss.urllib.request, "build_opener", lambda *handlers: Opener())
    feed = rss.parse_feed(rss.fetch_url("https://example.com/rss"), source_url="https://example.com/rss")
    assert len(feed.items) == 4
    assert feed.items[0].title == "第一条"


def test_feed_over_four_mb_is_rejected():
    with pytest.raises(rss.RssFetchError):
        rss.parse_feed(b"x" * (4 * 1024 * 1024 + 1), source_url="https://example.com/rss")


def test_parse_rss_cleans_summary_and_sorts_items():
    feed = rss.parse_feed(RSS, source_url="https://example.com/feed")
    assert feed.name == "测试媒体"
    assert [item.title for item in feed.items] == ["第一条", "第二条", "第三条", "第四条"]
    assert feed.items[0].summary == "摘要 一 & 继续"
    assert "<" not in feed.items[0].summary
    assert feed.items[0].originalUrl == "https://example.com/one"


def test_parse_atom_feed_uses_href_and_updated():
    feed = rss.parse_feed(ATOM, source_url="https://atom.example/feed")
    assert feed.name == "Atom 媒体"
    assert feed.items[0].originalUrl == "https://atom.example/story"
    assert feed.items[0].publishedAt == "2026-09-02T02:00:00+00:00"


@pytest.mark.parametrize("url", [
    "ftp://example.com/feed",
    "https://user:pass@example.com/feed",
    "http://localhost/feed",
    "http://127.0.0.1/feed",
    "http://10.0.0.4/feed",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/feed",
])
def test_validate_public_url_rejects_unsafe_targets(url):
    with pytest.raises(rss.RssSecurityError):
        rss.validate_public_url(url, resolve_dns=False)


def test_redirect_target_is_revalidated(monkeypatch):
    class Redirect(rss.urllib.request.HTTPRedirectHandler):
        pass

    with pytest.raises(rss.RssSecurityError):
        rss.SafeRedirectHandler().redirect_request(
                type("Response", (), {"geturl": lambda self: "https://example.com/feed"})(),
                "http://127.0.0.1/private",
                {},
                302,
                "redirect",
                "http://127.0.0.1/private",
            )


def test_catalog_returns_three_latest_and_stale_cache(tmp_path: Path):
    calls = []

    def fetch(url):
        calls.append(url)
        return RSS

    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=fetch, validate_dns=False)
    source = {"id": "test", "name": "测试媒体", "url": "https://example.com/feed", "category": "tech", "region": "cn", "priority": 1, "homepage": "https://example.com"}
    first = catalog.resolve(source["url"], source=source)
    assert len(first["items"]) == 3
    assert [item["title"] for item in first["items"]] == ["第一条", "第二条", "第三条"]
    assert first["stale"] is False
    catalog.fetcher = lambda _url: (_ for _ in ()).throw(OSError("offline"))
    stale = catalog.refresh(source)
    assert stale["stale"] is True
    assert stale["lastSuccessAt"]
    assert len(stale["items"]) == 3
    assert len(calls) == 1


def test_catalog_marks_never_successful_source_unavailable(tmp_path: Path):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: (_ for _ in ()).throw(OSError("offline")), validate_dns=False)
    source = {"id": "missing", "name": "不可用", "url": "https://example.com/feed", "category": "tech", "region": "cn", "priority": 1, "homepage": "https://example.com"}
    result = catalog.refresh(source)
    assert result["items"] == []
    assert result["lastSuccessAt"] is None
    assert result["stale"] is False
    assert "offline" in result["error"]


def test_dns_failure_isolated_and_visible_after_cache_read(tmp_path, monkeypatch):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: RSS, validate_dns=False)
    catalog.source_defs = catalog.source_defs[:2]
    original_validate = rss.validate_public_url

    def validate(url, **kwargs):
        if "ithome" in url:
            raise rss.RssSecurityError("RSS 域名无法解析")
        return original_validate(url, resolve_dns=False)

    monkeypatch.setattr(rss, "validate_public_url", validate)
    catalog.refresh_builtins()
    result = catalog.sources()
    assert result[0]["lastSuccessAt"] is None
    assert result[0]["error"] == "RSS 域名无法解析"
    assert len(result[1]["items"]) == 3


def test_failure_preserves_content_and_health_across_catalog_restart(tmp_path):
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: RSS, validate_dns=False)
    source = catalog.source_defs[0]
    success = catalog.refresh(source)
    catalog.fetcher = lambda _url: (_ for _ in ()).throw(OSError("upstream offline"))
    catalog.refresh(source)
    reloaded = rss.RssCatalog(cache_dir=tmp_path, validate_dns=False).sources()[0]
    assert reloaded["items"] == success["items"]
    assert reloaded["lastSuccessAt"] == success["lastSuccessAt"]
    assert reloaded["stale"] is True
    assert "upstream offline" in reloaded["error"]
    catalog.fetcher = lambda _url: RSS
    catalog.refresh(source)
    assert catalog.sources()[0]["error"] is None
    assert catalog.sources()[0]["stale"] is False


@pytest.mark.parametrize("when,stale", [
    ("2026-09-02T10:29:59+00:00", False),
    ("2026-09-02T10:30:00+00:00", True),
])
def test_successful_cache_expires_after_thirty_minutes(tmp_path, monkeypatch, when, stale):
    monkeypatch.setattr(rss, "_now", lambda: "2026-09-02T10:00:00+00:00")
    catalog = rss.RssCatalog(cache_dir=tmp_path, fetcher=lambda _url: RSS, validate_dns=False)
    catalog.refresh(catalog.source_defs[0])
    monkeypatch.setattr(rss, "_now", lambda: when)
    snapshot = catalog.sources()[0]
    assert snapshot["stale"] is stale
    assert len(snapshot["items"]) == 3


def test_scheduler_survives_failed_cycle_and_can_restart(tmp_path):
    import threading

    catalog = rss.RssCatalog(cache_dir=tmp_path, validate_dns=False)
    completed = threading.Event()
    calls = []

    def refresh():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("temporary cache failure")
        completed.set()

    catalog.refresh_builtins = refresh
    catalog.start_scheduler(interval=0.01)
    try:
        assert completed.wait(1), "a failed cycle must not kill the refresh thread"
    finally:
        catalog.stop_scheduler()
        catalog._thread.join(1)
    completed.clear()
    catalog.start_scheduler(interval=0.01)
    try:
        assert completed.wait(1), "stopping once must not permanently disable refresh"
    finally:
        catalog.stop_scheduler()
        catalog._thread.join(1)
