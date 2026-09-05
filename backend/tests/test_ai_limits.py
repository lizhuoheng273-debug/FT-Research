import pytest

from ai_limits import LimitExceeded, Limits
from session_store import SessionStore


def test_guest_and_ip_budgets_are_server_side(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    limits = Limits(store, guest_calls=2, ip_calls=3, site_calls=100)
    guest = store.create_principal("guest")
    assert limits.reserve(guest, "127.0.0.1", "r1")
    assert limits.reserve(guest, "127.0.0.1", "r2")
    with pytest.raises(LimitExceeded):
        limits.reserve(guest, "127.0.0.1", "r3")


def test_same_ip_cannot_reset_budget_with_new_guest(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    limits = Limits(store, guest_calls=10, ip_calls=1, site_calls=100)
    first = store.create_principal("guest")
    second = store.create_principal("guest")
    limits.reserve(first, "same-ip", "r1")
    with pytest.raises(LimitExceeded):
        limits.reserve(second, "same-ip", "r2")


def test_guest_session_issuance_is_limited_before_creating_principals(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    limits = Limits(store, guest_session_ip=1, guest_session_site=10)

    assert limits.reserve_guest_session("same-ip")
    with pytest.raises(LimitExceeded):
        limits.reserve_guest_session("same-ip")

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM principal").fetchone()[0] == 0


def test_guest_session_issuance_prunes_stale_usage_buckets(tmp_path):
    store = SessionStore(tmp_path / "test.db", clock=lambda: 1_800_000_000)
    with store._connect() as conn:
        conn.execute("INSERT INTO usage_counter(bucket,dimension,count) VALUES('2020-01-01','stale',1)")

    Limits(store, guest_session_ip=2, guest_session_site=10).reserve_guest_session("ip")

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_counter WHERE dimension='stale'").fetchone()[0] == 0
