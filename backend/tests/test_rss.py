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
