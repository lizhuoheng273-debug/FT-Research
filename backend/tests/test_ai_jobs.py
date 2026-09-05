from threading import Event

from ai_jobs import RunCleanupScheduler, RunManager
from ai_limits import Limits
from session_store import SessionStore


def test_disconnect_does_not_restart_model(tmp_path, monkeypatch):
    release, first_saved = Event(), Event()
    calls = []

    def runner(run, control):
        calls.append(run["id"])
        yield {"type": "delta", "payload": {"text": "第一段"}}
        assert release.wait(2)
        yield {"type": "done", "payload": {}}

    store = SessionStore(tmp_path / "test.db")
    append_event = store.append_event
    def append_and_signal(run_id, event_type, payload):
        result = append_event(run_id, event_type, payload)
        if event_type == "delta":
            first_saved.set()
        return result
    monkeypatch.setattr(store, "append_event", append_and_signal)
    principal = store.create_principal("owner")
    conversation = store.create_conversation(principal, "chat", {"type": "review"})
    jobs = RunManager(store, runner, Limits(store), clock=store.clock)
    run = jobs.submit(principal, conversation["id"], "r1", "复盘", {})
    try:
        assert first_saved.wait(2)
        events = store.events_after(principal, run["id"], 0)
        assert events[0]["payload"]["text"] == "第一段"
        retry = jobs.submit(principal, conversation["id"], "r1", "复盘", {})
        assert retry["id"] == run["id"] and len(calls) == 1
    finally:
        release.set()
        jobs.shutdown()


def test_explicit_cancel_keeps_partial_events(tmp_path, monkeypatch):
    started = Event()

    def runner(run, control):
        yield {"type": "delta", "payload": {"text": "部分"}}
        while not control.cancelled:
            control.wait(0.01)
        yield {"type": "done", "payload": {}}

    store = SessionStore(tmp_path / "test.db")
    append_event = store.append_event
    def append_and_signal(run_id, event_type, payload):
        result = append_event(run_id, event_type, payload)
        if event_type == "delta":
            started.set()
        return result
    monkeypatch.setattr(store, "append_event", append_and_signal)
    principal = store.create_principal("owner")
    conversation = store.create_conversation(principal, "chat", {})
    jobs = RunManager(store, runner, Limits(store), clock=store.clock)
    run = jobs.submit(principal, conversation["id"], "r1", "问题", {})
    assert started.wait(2)
    assert jobs.cancel(principal, run["id"])
    jobs.shutdown()
    assert store.run_for_principal(principal, run["id"])["status"] == "stopped"
    assert any(e["type"] == "delta" for e in store.events_after(principal, run["id"], 0))


def test_cleanup_scheduler_ticks_and_stops():
    ticked = Event()

    class Manager:
        def tick(self):
            ticked.set()

    scheduler = RunCleanupScheduler(Manager(), interval=0.01)
    scheduler.start()
    try:
        assert ticked.wait(1)
    finally:
        scheduler.stop()
    assert not scheduler.is_alive()
