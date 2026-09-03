import time

from ai_jobs import RunManager
from ai_limits import Limits
from session_store import SessionStore


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
