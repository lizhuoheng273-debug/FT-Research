import chat


def test_context_only_completion_never_exposes_tools_to_model(monkeypatch):
    calls = []

    def complete(cfg, messages, use_tools, *, timeout_seconds=90):
        calls.append({"messages": messages, "use_tools": use_tools, "timeout": timeout_seconds})
        return {"choices": [{"message": {"content": "快照简述"}}]}

    monkeypatch.setattr(chat, "_call_llm", complete)

    result = chat.run_chat_context_only(
        {"baseURL": "https://example.com/v4", "apiKey": "test", "model": "test"},
        [{"role": "user", "content": "总结现有快照"}],
        context="完整市场快照",
        analysis_scope="market",
    )

    assert result == {"content": "快照简述", "trace": [], "rounds": 1}
    assert calls[0]["use_tools"] is False
    assert calls[0]["timeout"] == 45
    assert "完整市场快照" in calls[0]["messages"][0]["content"]
