from fastapi.testclient import TestClient

from app import app
from auth import AuthService, hash_password
from session_store import SessionStore


def test_login_sets_http_only_cookie_and_guest_returns_memory_token(monkeypatch, tmp_path):
    old = (app.state.store, app.state.auth)
    store = SessionStore(tmp_path / "auth.db")
    app.state.store = store
    app.state.auth = AuthService(store, hash_password("secret-password"))
    try:
        with TestClient(app) as client:
            owner = client.post("/api/auth/login", json={"password": "secret-password"})
            assert owner.status_code == 200
            assert "token" not in owner.json()
            assert "ft-owner-session" in owner.cookies
            guest = client.post("/api/auth/guest")
            assert guest.status_code == 200 and guest.json()["token"]
            assert guest.json()["identity"]["kind"] == "guest"
    finally:
        app.state.store, app.state.auth = old
