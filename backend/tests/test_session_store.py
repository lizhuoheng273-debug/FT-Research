import threading

import pytest

from session_store import Conflict, NotFound, SessionStore


def test_isolation_and_retry(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    a = store.create_principal("guest")
    b = store.create_principal("guest")
    c = store.create_conversation(a, "chat", {"type": "watchlist"})
    with pytest.raises(NotFound):
        store.get_conversation(b, c["id"])
    one = store.create_run(a, c["id"], "request-1", "分析", {})
    two = store.create_run(a, c["id"], "request-1", "分析", {})
    assert one["id"] == two["id"]
    assert one["created"] is True and two["created"] is False


def test_events_terminal_runs_and_model_history(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    owner = store.create_principal("owner")
    conversation = store.create_conversation(owner, "chat", {"type": "review"})
    run = store.create_run(owner, conversation["id"], "r1", "问题", {})
    assert store.append_event(run["id"], "delta", {"text": "部分"})["seq"] == 1
    assert store.transition_run(run["id"], "queued", "running")
    assert store.transition_run(run["id"], "running", "completed")
    assert store.append_event(run["id"], "done", {}) is None
    store.finalize_messages(run["id"], "问题", "完整回答")
    assert store.history_for_model(owner, conversation["id"]) == [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "完整回答"},
    ]


def test_delete_cascades_and_late_event_is_rejected(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    owner = store.create_principal("owner")
    conversation = store.create_conversation(owner, "chat", {})
    run = store.create_run(owner, conversation["id"], "r1", "问题", {})
    assert store.delete_conversation(owner, conversation["id"])
    with pytest.raises(NotFound):
        store.get_conversation(owner, conversation["id"])
    assert store.append_event(run["id"], "delta", {"text": "迟到"}) is None


def test_two_threads_same_request_create_once(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    owner = store.create_principal("owner")
    conversation = store.create_conversation(owner, "chat", {})
    results = []

    def submit():
        results.append(store.create_run(owner, conversation["id"], "same", "问题", {}))

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {item["id"] for item in results}.__len__() == 1
    assert sorted(item["created"] for item in results) == [False, True]


def test_same_request_with_different_payload_conflicts(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    owner = store.create_principal("owner")
    conversation = store.create_conversation(owner, "chat", {})
    store.create_run(owner, conversation["id"], "same", "问题", {})
    with pytest.raises(Conflict):
        store.create_run(owner, conversation["id"], "same", "另一个问题", {})
