"""A 股代码/名称搜索契约测试。"""

from fastapi.testclient import TestClient

import app as app_module
import astock


client = TestClient(app_module.app)


def test_stock_search_matches_name_and_returns_code(monkeypatch):
    monkeypatch.setattr(
        astock,
        "search_a_stocks",
        lambda query, limit=20: [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "600519", "name": "贵州茅台"},
        ],
    )

    response = client.get("/api/stock/search?q=茅台")

    assert response.status_code == 200
    assert response.json() == {"data": [{"code": "600519", "name": "贵州茅台"}]}


def test_stock_search_rejects_empty_query():
    assert client.get("/api/stock/search?q=").status_code == 400
