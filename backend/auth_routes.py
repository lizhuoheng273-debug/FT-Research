from __future__ import annotations

import secrets

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from auth import AuthService, Unauthorized
from session_store import Principal


OWNER_COOKIE = "ft-owner-session"
GUEST_HEADER = "authorization"
CSRF_COOKIE = "ft-csrf"


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=512)


def _auth(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth", None)
    if service is None:
        raise HTTPException(503, "管理员认证尚未配置 FT_OWNER_PASSWORD_HASH")
    return service


def _token(request: Request) -> tuple[str | None, str | None]:
    cookie = request.cookies.get(OWNER_COOKIE)
    header = request.headers.get("authorization", "")
    bearer = header[7:].strip() if header.lower().startswith("bearer ") else None
    if cookie and bearer:
        raise HTTPException(401, "请勿混用管理员 Cookie 与访客令牌")
    return cookie, bearer


def require_principal(request: Request) -> Principal:
    cookie, bearer = _token(request)
    try:
        return _auth(request).authenticate(cookie or bearer or "", "owner" if cookie else "guest" if bearer else "any")
    except Unauthorized as exc:
        raise HTTPException(401, str(exc)) from exc


def require_owner(request: Request) -> Principal:
    cookie, bearer = _token(request)
    if bearer or not cookie:
        raise HTTPException(403, "仅管理员可访问")
    try:
        return _auth(request).authenticate(cookie, "owner")
    except Unauthorized as exc:
        raise HTTPException(401, str(exc)) from exc


def enforce_write_csrf(request: Request) -> None:
    # Bearer credentials are not sent automatically by a browser, while owner
    # cookies are. Require a same-origin token for cookie-authenticated writes.
    if request.cookies.get(OWNER_COOKIE):
        origin = request.headers.get("origin")
        allowed = getattr(request.app.state, "allowed_origins", set())
        if allowed and origin and origin not in allowed:
            raise HTTPException(403, "Origin 不被允许")
        csrf = request.headers.get("x-csrf-token")
        if not csrf or not secrets.compare_digest(csrf, request.cookies.get(CSRF_COOKIE, "")):
            raise HTTPException(403, "缺少 CSRF token")


def install_auth_routes(app):
    @app.post("/api/auth/login")
    def login(body: LoginBody, request: Request):
        try:
            principal, token = _auth(request).login(body.password)
        except Unauthorized as exc:
            raise HTTPException(401, "密码错误") from exc
        response = {"id": principal.id, "kind": principal.kind, "expiresAt": _auth(request).clock() + AuthService.OWNER_TTL}
        # The token is only placed in an HttpOnly cookie; it is never returned.
        from fastapi.responses import JSONResponse
        result = JSONResponse(response)
        result.set_cookie(OWNER_COOKIE, token, max_age=AuthService.OWNER_TTL, httponly=True, secure=getattr(request.app.state, "secure_cookie", False), samesite="lax")
        result.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), max_age=AuthService.OWNER_TTL, httponly=False, secure=getattr(request.app.state, "secure_cookie", False), samesite="lax")
        return result

    @app.post("/api/auth/guest")
    def guest(request: Request):
        principal, token = _auth(request).start_guest()
        return {"identity": {"id": principal.id, "kind": principal.kind, "expiresAt": _auth(request).clock() + AuthService.GUEST_TTL}, "token": token}

    @app.get("/api/auth/me")
    def me(request: Request):
        principal = require_principal(request)
        session_token, bearer = _token(request)
        session = _auth(request).store.auth_session(_auth(request)._token_hash(session_token or bearer or ""))
        return {"id": principal.id, "kind": principal.kind, "expiresAt": session["expires_at"] if session else None}

    @app.post("/api/auth/heartbeat")
    def heartbeat(request: Request):
        enforce_write_csrf(request)
        _, bearer = _token(request)
        if not bearer:
            raise HTTPException(403, "访客心跳需要访客令牌")
        try:
            principal = _auth(request).heartbeat(bearer)
        except Unauthorized as exc:
            raise HTTPException(401, str(exc)) from exc
        return {"id": principal.id, "kind": principal.kind}

    @app.post("/api/auth/logout")
    def logout(request: Request):
        enforce_write_csrf(request)
        cookie, bearer = _token(request)
        token = cookie or bearer
        if not token:
            return {"ok": True}
        try:
            principal = _auth(request).logout(token)
        except Unauthorized:
            principal = None
        if principal and principal.kind == "guest":
            getattr(request.app.state, "run_manager", None) and request.app.state.run_manager.purge_guest(principal.id)
        from fastapi.responses import JSONResponse
        result = JSONResponse({"ok": True, "principal": {"id": principal.id, "kind": principal.kind} if principal else None})
        result.delete_cookie(OWNER_COOKIE)
        result.delete_cookie(CSRF_COOKIE)
        return result
