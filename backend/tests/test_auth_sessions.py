import pytest

from auth import AuthService, Unauthorized, hash_password, verify_password
from session_store import SessionStore


def test_guest_is_unique_and_expiration_is_server_side(tmp_path):
    now = [0.0]
    store = SessionStore(tmp_path / "test.db", clock=lambda: now[0])
    auth = AuthService(store, hash_password("a-long-test-password"), clock=lambda: now[0])
    a, token_a = auth.start_guest()
    b, token_b = auth.start_guest()
    assert a.id != b.id and token_a != token_b
    assert verify_password("wrong", hash_password("correct")) is False
    now[0] = 1801
    with pytest.raises(Unauthorized):
        auth.authenticate(token_a, "guest")


def test_owner_login_cookie_token_is_not_stored_in_plaintext(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    password_hash = hash_password("correct-password")
    auth = AuthService(store, password_hash)
    principal, token = auth.login("correct-password")
    assert principal.kind == "owner"
    assert auth.authenticate(token, "owner") == principal
    assert token not in {row["token_hash"] for row in _sessions(store)}
    with pytest.raises(Unauthorized):
        auth.login("incorrect")


def test_expired_and_revoked_sessions_are_rejected(tmp_path):
    now = [10.0]
    store = SessionStore(tmp_path / "test.db", clock=lambda: now[0])
    auth = AuthService(store, hash_password("correct-password"), clock=lambda: now[0])
    principal, token = auth.login("correct-password")
    auth.logout(token)
    with pytest.raises(Unauthorized):
        auth.authenticate(token, "owner")
    guest, guest_token = auth.start_guest()
    now[0] = 7211
    with pytest.raises(Unauthorized):
        auth.authenticate(guest_token, "guest")


def _sessions(store):
    with store._connect() as conn:
        return conn.execute("SELECT token_hash FROM auth_session").fetchall()
