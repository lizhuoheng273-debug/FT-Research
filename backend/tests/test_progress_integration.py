import time

from ai_jobs import RunManager
from ai_limits import Limits
from session_store import SessionStore


def test_actual_background_adapter_preserves_progress_payload(tmp_path, monkeypatch):
    import app as app_module
    from ai_jobs import RunControl

    store = SessionStore(tmp_path / "adapter.sqlite3")
    owner = store.create_principal("owner")
    conversation = store.create_conversation(owner, "chat", {})
    monkeypatch.setattr(app_module, "session_store", store)
    monkeypatch.setattr(app_module.glm_config, "load_glm_config", lambda: {"apiKey": "test-only"})
    monkeypatch.setattr(app_module.chat_layer, "run_chat_stream", lambda *a, **kw: iter([
        {"type": "progress", "payload": {"phase": "tool", "status": "running", "tool": "query_market", "message": "查询行情"}},
        {"type": "delta", "text": "正文"},
        {"type": "done", "rounds": 1},
    ]))
    events = list(app_module._background_runner({"principal_id": owner.id, "conversation_id": conversation["id"], "question": "复盘", "context": {}}, RunControl(lambda: True)))
    assert events[0]["payload"].get("message") == "查询行情"
    assert events[0]["payload"].get("phase") == "tool"
    assert events[1]["payload"] == {"text": "正文"}
    assert events[2]["payload"]["rounds"] == 1


def test_progress_events_are_persisted_before_answer_and_title_is_auto_named(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    principal = store.create_principal("owner")
    conversation = store.create_conversation(principal, "chat", {"type": "news"})

    def runner(_run, _control):
        yield {"type": "progress", "payload": {"phase": "model", "status": "running", "message": "模型分析中"}}
        yield {"type": "tool", "payload": {"tool": "query_news", "status": "running"}}
        yield {"type": "progress", "payload": {"phase": "tool", "status": "completed", "tool": "query_news", "message": "查询完成"}}
        yield {"type": "delta", "payload": {"text": "回答"}}
        yield {"type": "done", "payload": {}}

    store.auto_name_conversation(principal, conversation["id"], "分析今日市场")
    manager = RunManager(store, runner, Limits(store), clock=store.clock)
    run = manager.submit(principal, conversation["id"], "progress-r1", "分析今日市场", {})
    try:
        deadline = time.monotonic() + 2
        while store.run_for_principal(principal, run["id"])["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
        events = store.events_after(principal, run["id"], 0)
        assert [event["type"] for event in events] == ["progress", "tool", "progress", "delta", "done"]
        assert store.get_conversation(principal, conversation["id"])["title"] == "金融资讯 · 分析今日市场"
    finally:
        manager.shutdown()
