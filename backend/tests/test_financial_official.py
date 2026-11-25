from datetime import datetime, timezone

from financial_official import OfficialNewsFetcher, OfficialPortalSpec, parse_official_html


def test_parse_official_html_filters_nav_future_and_unsafe_links():
    spec = OfficialPortalSpec(
        source_id="pbc",
        name="中国人民银行",
        url="https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        link_hints=("113469", ".html"),
        category="宏观政策",
    )
    html = """
    <html><body>
      <a href="/goutongjiaoliu/113456/113469/index.html">首页</a>
      <a href="javascript:void(0)">更多</a>
      <li><a href="/goutongjiaoliu/113456/113469/551234/index.html">中国人民银行决定下调存款准备金率 0.25 个百分点</a><span>2026-11-24</span></li>
      <li><a href="/goutongjiaoliu/113456/113469/559999/index.html">未来预告公告不应直接入库</a><span>2026-12-30</span></li>
      <li><a href="/other/999.pdf">无关文件</a><span>2026-11-24</span></li>
    </body></html>
    """
    now = datetime(2026, 11, 25, 2, 0, tzinfo=timezone.utc)
    rows = parse_official_html(html, spec, now=now)
    assert len(rows) == 1
    assert rows[0]["source"] == "中国人民银行"
    assert rows[0]["official"] is True
    assert rows[0]["originalUrl"] == "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/551234/index.html"
    assert "2026-11-24" in rows[0]["publishedAt"]


def test_official_fetcher_caches_fresh_and_falls_back_on_error(tmp_path):
    portals = (
        OfficialPortalSpec("pbc", "中国人民银行", "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html", ("113469", ".html")),
        OfficialPortalSpec("csrc", "证监会", "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml", ("csrc/", ".shtml")),
    )
    now = datetime(2026, 11, 25, 2, 0, tzinfo=timezone.utc)

    def ok_get(url: str) -> str:
        if "pbc.gov.cn" in url:
            return '<li><a href="/goutongjiaoliu/113456/113469/1001/index.html">央行开展公开市场逆回购操作</a> 2026-11-24</li>'
        return '<li><a href="/csrc/c100028/2001.shtml">证监会发布并购重组审核指引修订稿</a> 2026-11-24</li>'

    fetcher = OfficialNewsFetcher(cache_dir=tmp_path, portals=portals, http_get=ok_get, now_fn=lambda: now)
    first = fetcher.fetch()
    assert len(first["reports"]) == 2
    assert all(s["ok"] is True and s["cache"] == "fresh" for s in first["sourceStatus"])

    def failing_pbc_get(url: str) -> str:
        if "pbc.gov.cn" in url:
            raise TimeoutError("upstream timed out")
        return ok_get(url)

    fetcher2 = OfficialNewsFetcher(cache_dir=tmp_path, portals=portals, http_get=failing_pbc_get, now_fn=lambda: now)
    second = fetcher2.fetch()
    assert len(second["reports"]) == 2
    pbc_status = next(s for s in second["sourceStatus"] if s["id"] == "pbc")
    assert pbc_status["ok"] is False
    assert pbc_status["cache"] == "stale"
    pbc_report = next(r for r in second["reports"] if r["source"] == "中国人民银行")
    assert pbc_report["stale"] is True
