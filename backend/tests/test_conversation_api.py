import pytest
from fastapi.testclient import TestClient

from ai_jobs import RunManager
from ai_limits import Limits
from auth import AuthService, hash_password
from app import app
from session_store import SessionStore


@pytest.fixture()
def services(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")

    def runner(run, control):
        yield {"type": "delta", "payload": {"text": "测试回答"}}
        yield {"type": "done", "payload": {}}

    manager = RunManager(store, runner, Limits(store), clock=store.clock)
    old = (app.state.store, app.state.auth, app.state.run_manager)
    app.state.store = store
    app.state.auth = AuthService(store, hash_password("owner-password"), clock=store.clock)
    app.state.run_manager = manager
    with TestClient(app) as client:
        owner, owner_token = app.state.auth.login("owner-password")
        guest_a, token_a = app.state.auth.start_guest()
        guest_b, token_b = app.state.auth.start_guest()
        yield client, {"owner": {"Authorization": f"Bearer {owner_token}"}, "a": {"Authorization": f"Bearer {token_a}"}, "b": {"Authorization": f"Bearer {token_b}"}}
    manager.shutdown()
    app.state.store, app.state.auth, app.state.run_manager = old


def test_another_guest_cannot_read_or_cancel(services):
    client, headers = services
    created = client.post("/api/conversations", headers=headers["a"], json={"kind": "chat", "source": {"type": "watchlist"}})
    assert created.status_code == 200
    cid = created.json()["id"]
    for path in [f"/api/conversations/{cid}", f"/api/conversations/{cid}/export"]:
        assert client.get(path, headers=headers["b"]).status_code == 404
    assert client.delete(f"/api/conversations/{cid}", headers=headers["b"]).status_code == 404


def test_turn_events_and_idempotent_retry(services):
    client, headers = services
    cid = client.post("/api/conversations", headers=headers["a"], json={}).json()["id"]
    response = client.post(f"/api/conversations/{cid}/turns", headers=headers["a"], json={"clientRequestId": "r1", "question": "问题", "context": {}})
    assert response.status_code == 202
    run_id = response.json()["runId"]
    retry = client.post(f"/api/conversations/{cid}/turns", headers=headers["a"], json={"clientRequestId": "r1", "question": "问题", "context": {}})
    assert retry.status_code == 202 and retry.json()["runId"] == run_id
    assert client.get(f"/api/runs/{run_id}/events", headers=headers["b"]).status_code == 404
    events = client.get(f"/api/runs/{run_id}/events", headers=headers["a"]).text
    assert '"type": "delta"' in events and '"type": "done"' in events


def test_guest_cannot_import_history(services):
    client, headers = services
    result = client.post("/api/conversations/import", headers=headers["a"], json={"sourceKey": "legacy", "messages": [{"role": "user", "content": "x"}]})
    assert result.status_code == 403
