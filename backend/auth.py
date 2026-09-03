"""Owner password and temporary guest authentication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Literal

from session_store import Principal, SessionStore


class Unauthorized(PermissionError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password must not be empty")
    n, r, p = 32768, 8, 1
    salt = secrets.token_bytes(32)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=64, maxmem=128 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        key = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=64, maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(key, _unb64(expected))
    except (AttributeError, TypeError, ValueError, IndexError):
        return False


class AuthService:
    OWNER_TTL = 12 * 60 * 60
    GUEST_TTL = 2 * 60 * 60

    def __init__(self, store: SessionStore, owner_password_hash: str, clock=time.time):
        if not owner_password_hash:
            raise ValueError("FT_OWNER_PASSWORD_HASH is required")
        self.store = store
        self.owner_password_hash = owner_password_hash
        self.clock = clock

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _issue(self, principal: Principal, ttl: float) -> tuple[Principal, str]:
        token = secrets.token_urlsafe(32)
        self.store.create_auth_session(self._token_hash(token), principal, self.clock() + ttl)
        return principal, token

    def login(self, password: str) -> tuple[Principal, str]:
        if not verify_password(password, self.owner_password_hash):
            raise Unauthorized("密码错误")
        return self._issue(self.store.create_principal("owner"), self.OWNER_TTL)

    def start_guest(self) -> tuple[Principal, str]:
        return self._issue(self.store.create_principal("guest"), self.GUEST_TTL)

    def authenticate(self, token: str, mode: Literal["owner", "guest", "any"] = "any") -> Principal:
        if not token or not isinstance(token, str):
            raise Unauthorized("未登录")
        session = self.store.auth_session(self._token_hash(token))
        now = float(self.clock())
        if not session or session["revoked"] or session["expires_at"] <= now:
            raise Unauthorized("登录已过期")
        if session["kind"] == "guest" and session["last_heartbeat"] + 30 * 60 <= now:
            self.store.revoke_auth_session(session["token_hash"])
            raise Unauthorized("游客体验已过期")
        if mode not in {"any", session["kind"]}:
            raise Unauthorized("身份凭据类型不匹配")
        return self.store.principal_by_id(session["principal_id"])

    def heartbeat(self, token: str) -> Principal:
        principal = self.authenticate(token, "guest")
        self.store.touch_auth_session(self._token_hash(token))
        return principal

    def logout(self, token: str) -> Principal:
        if not token:
            raise Unauthorized("未登录")
        principal = self.store.revoke_auth_session(self._token_hash(token))
        if not principal:
            raise Unauthorized("未登录")
        return principal

    def expired_guests(self) -> list[str]:
        return [row["principal_id"] for row in self.store.guest_sessions(self.clock())]
