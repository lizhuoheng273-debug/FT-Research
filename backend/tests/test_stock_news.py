"""个股新闻排序测试（不访问网络）。"""

import astock


class _Frame:
    empty = False

    def __init__(self, rows):
        self._rows = rows

    def head(self, limit):
        return _Frame(self._rows[:limit])

    def to_dict(self, orient):
        assert orient == "records"
        return [dict(row) for row in self._rows]


class _Akshare:
    def __init__(self, rows):
        self._rows = rows

    def stock_news_em(self, symbol):
        assert symbol == "600183"
        return _Frame(self._rows)


def test_stock_news_sorts_newest_first_before_applying_limit(monkeypatch):
    rows = [
        {"新闻标题": "八月旧闻", "发布时间": "2026-08-17 10:39:36"},
        {"新闻标题": "九月次新", "发布时间": "2026-09-03 21:15:00"},
        {"新闻标题": "时间缺失", "发布时间": ""},
        {"新闻标题": "九月最新", "发布时间": "2026-09-04 17:06:00"},
    ]
    monkeypatch.setattr(astock, "_akshare", lambda: _Akshare(rows))

    result = astock.stock_news("600183", limit=3)

    assert [item["新闻标题"] for item in result] == ["九月最新", "九月次新", "八月旧闻"]


def test_stock_news_keeps_source_order_for_equal_or_invalid_times(monkeypatch):
    rows = [
        {"新闻标题": "同刻第一条", "发布时间": "2026-09-04 17:06:00"},
        {"新闻标题": "同刻第二条", "发布时间": "2026-09-04 17:06:00"},
        {"新闻标题": "时间异常第一条", "发布时间": "未知"},
        {"新闻标题": "时间异常第二条"},
    ]
    monkeypatch.setattr(astock, "_akshare", lambda: _Akshare(rows))

    result = astock.stock_news("600183", limit=10)

    assert [item["新闻标题"] for item in result] == [
        "同刻第一条", "同刻第二条", "时间异常第一条", "时间异常第二条",
    ]
