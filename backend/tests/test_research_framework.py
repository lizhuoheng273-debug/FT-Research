"""自动路由融合研究框架的行为契约。"""

from fastapi.testclient import TestClient

import app as app_module
import chat


client = TestClient(app_module.app)


def test_market_scope_uses_market_framework_without_forcing_stock_valuation():
    prompt = chat.build_system_prompt(
        "今日市场上下文",
        analysis_scope="market",
        user_messages=[{"role": "user", "content": "请复盘今天的 A 股市场"}],
    )

    assert "【市场复盘框架】" in prompt
    assert "市场宽度" in prompt
    assert "板块轮动" in prompt
    assert "全球市场映射" in prompt
    assert "PE / PB" not in prompt


def test_full_stock_question_uses_fused_stock_framework():
    prompt = chat.build_system_prompt(
        "贵州茅台（600519）",
        analysis_scope="stock",
        user_messages=[{"role": "user", "content": "请全面分析 600519"}],
    )

    assert "【个股融合研究框架】" in prompt
    assert "估值、财报质量与行业景气" in prompt
    assert "大盘—板块—个股联动" in prompt
    assert "EMA" in prompt
    assert "情景验证与失效条件" in prompt
    assert "回答模式：完整分析" in prompt


def test_focused_stock_question_does_not_force_full_framework_output():
    prompt = chat.build_system_prompt(
        "贵州茅台（600519）",
        analysis_scope="stock",
        user_messages=[{"role": "user", "content": "这只股票的 K 线怎么看"}],
    )

    assert "回答模式：聚焦回答" in prompt
    assert "只展开与问题直接相关的模块" in prompt


def test_fact_question_is_routed_to_direct_answer_mode():
    prompt = chat.build_system_prompt(
        "贵州茅台（600519）",
        analysis_scope="stock",
        user_messages=[{"role": "user", "content": "600519 现价多少"}],
    )

    assert "回答模式：事实简答" in prompt
    assert "直接回答事实" in prompt


def test_explicit_question_object_overrides_page_default_scope():
    prompt = chat.build_system_prompt(
        "贵州茅台（600519）",
        analysis_scope="stock",
        user_messages=[{"role": "user", "content": "今天大盘和市场情绪怎么样"}],
    )

    assert "实际范围：market" in prompt
    assert "【市场复盘框架】" in prompt
    assert "【个股融合研究框架】" not in prompt


def test_six_digit_index_code_does_not_turn_index_page_into_stock_scope():
    prompt = chat.build_system_prompt(
        "上证指数（000001）",
        analysis_scope="index",
        user_messages=[{"role": "user", "content": "000001 这段走势怎么看"}],
    )

    assert "实际范围：index" in prompt
    assert "【指数研究框架】" in prompt


def test_every_scope_keeps_evidence_and_safety_rules():
    for scope in ("general", "market", "index", "sector", "stock"):
        prompt = chat.build_system_prompt(
            "上下文",
            analysis_scope=scope,
            user_messages=[{"role": "user", "content": "分析一下"}],
        )
        assert "不得编造" in prompt
        assert "数据缺口" in prompt
        assert "不提供买卖" in prompt


def test_chat_route_forwards_analysis_scope(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        app_module.glm_config,
        "load_glm_config",
        lambda: {"apiKey": "server-key", "baseURL": "https://example.com/v1", "model": "model"},
    )

    def fake_stream(_cfg, _messages, _context, analysis_scope):
        captured["analysis_scope"] = analysis_scope
        yield {"type": "done", "trace": [], "rounds": 1}

    monkeypatch.setattr(app_module.chat_layer, "run_chat_stream", fake_stream)
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "复盘今天"}], "analysis_scope": "market"},
    )

    assert response.status_code == 200
    assert captured["analysis_scope"] == "market"
    assert response.json()["type"] == "done"


def test_chat_route_rejects_unknown_analysis_scope():
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "分析"}], "analysis_scope": "unknown"},
    )

    assert response.status_code == 422
