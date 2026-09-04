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
