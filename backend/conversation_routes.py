from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from auth_routes import enforce_write_csrf, require_owner, require_principal
from session_store import Conflict, NotFound


class ConversationBody(BaseModel):
    kind: str = Field(default="chat", pattern="^(chat|debate)$")
    source: dict[str, Any] = Field(default_factory=dict)


class TitleBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class TurnBody(BaseModel):
    clientRequestId: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class ImportBody(BaseModel):
    sourceKey: str = Field(min_length=1, max_length=300)
    messages: list[dict[str, Any]] = Field(max_length=40)


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "对话存储尚未初始化")
    return store


def _manager(request: Request):
    manager = getattr(request.app.state, "run_manager", None)
    if manager is None:
        raise HTTPException(503, "AI 任务服务尚未初始化")
    return manager


def _detail(store, principal, conversation_id: str) -> dict:
    conversation = store.get_conversation(principal, conversation_id)
    messages = store.get_messages(principal, conversation_id)
    active = None
    with store._connect() as conn:
        row = conn.execute("SELECT id FROM run WHERE conversation_id=? AND principal_id=? AND status IN ('queued','running')", (conversation_id, principal.id)).fetchone()
        if row:
            active = row["id"]
    return {"conversation": conversation, "messages": messages, "activeRunId": active}


def install_conversation_routes(app):
    @app.get("/api/conversations")
    def list_conversations(request: Request, q: str = Query("", max_length=100), limit: int = Query(30, ge=1, le=100), cursor: str | None = None):
        principal = require_principal(request)
        return _store(request).list_conversations(principal, q, limit, cursor)

    @app.post("/api/conversations")
    def create_conversation(body: ConversationBody, request: Request):
        enforce_write_csrf(request)
        principal = require_principal(request)
        return _store(request).create_conversation(principal, body.kind, body.source)

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, request: Request):
        principal = require_principal(request)
        try:
            return _detail(_store(request), principal, conversation_id)
        except NotFound as exc:
            raise HTTPException(404, "对话不存在") from exc

    @app.patch("/api/conversations/{conversation_id}")
    def rename_conversation(conversation_id: str, body: TitleBody, request: Request):
        enforce_write_csrf(request)
        principal = require_principal(request)
        try:
            return _store(request).update_conversation_title(principal, conversation_id, body.title)
        except NotFound as exc:
            raise HTTPException(404, "对话不存在") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str, request: Request):
        enforce_write_csrf(request)
        principal = require_principal(request)
        try:
            _store(request).delete_conversation(principal, conversation_id)
        except NotFound as exc:
            raise HTTPException(404, "对话不存在") from exc
        return {"ok": True}

    @app.post("/api/conversations/{conversation_id}/turns", status_code=202)
    def start_turn(conversation_id: str, body: TurnBody, request: Request):
        enforce_write_csrf(request)
        principal = require_principal(request)
        try:
            # Context is an immutable snapshot, not an authorization input.
            if len(json.dumps(body.context, ensure_ascii=False)) > 24000:
                raise HTTPException(413, "上下文过长")
            ip = request.client.host if request.client else "unknown"
            result = _manager(request).submit(principal, conversation_id, body.clientRequestId, body.question, body.context, ip)
            return {"runId": result["id"], "status": result["status"]}
        except NotFound as exc:
            raise HTTPException(404, "对话不存在") from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            from ai_limits import LimitExceeded
            if isinstance(exc, LimitExceeded):
                raise HTTPException(429, str(exc)) from exc
            raise

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str, request: Request, after: int = Query(0, ge=0)):
        principal = require_principal(request)
        store = _store(request)
        try:
            run = store.run_for_principal(principal, run_id)
        except NotFound as exc:
            raise HTTPException(404, "任务不存在") from exc

        def generate():
            cursor = after
            deadline = time.monotonic() + 480
            while time.monotonic() < deadline:
                try:
                    # Auth is rechecked on every poll so a guest logout closes access.
                    require_principal(request)
                    events = store.events_after(principal, run_id, cursor)
                except (HTTPException, NotFound):
                    return
                for event in events:
                    cursor = event["seq"]
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                current = store.run_for_principal(principal, run_id)
                if current["status"] in {"completed", "stopped", "failed", "interrupted"}:
                    return
                time.sleep(0.1)

        return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str, request: Request):
        enforce_write_csrf(request)
        principal = require_principal(request)
        try:
            return {"ok": _manager(request).cancel(principal, run_id)}
        except NotFound as exc:
            raise HTTPException(404, "任务不存在") from exc

    @app.get("/api/conversations/{conversation_id}/export")
    def export_conversation(conversation_id: str, request: Request):
        principal = require_principal(request)
        try:
            detail = _detail(_store(request), principal, conversation_id)
        except NotFound as exc:
            raise HTTPException(404, "对话不存在") from exc
        lines = [f"# {detail['conversation']['title']}", ""]
        for message in detail["messages"]:
            if message["role"] in {"user", "assistant"}:
                lines.extend([f"## {'用户' if message['role'] == 'user' else 'AI'}", message["content"], ""])
        return PlainTextResponse("\n".join(lines), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.md"'})

    @app.post("/api/conversations/import")
    def import_conversation(body: ImportBody, request: Request):
        enforce_write_csrf(request)
        principal = require_owner(request)
        allowed = {"user", "assistant"}
        messages = [m for m in body.messages if m.get("role") in allowed and isinstance(m.get("content"), str) and not m.get("partial")]
        if not messages or len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > 1024 * 1024:
            raise HTTPException(413, "历史记录为空或过大")
        content = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        store = _store(request)
        with store._connect() as conn:
            existing = conn.execute("SELECT conversation_id FROM legacy_import WHERE principal_id=? AND source_key=? AND content_hash=?", (principal.id, body.sourceKey, digest)).fetchone()
        if existing:
            return {"conversationId": existing["conversation_id"], "imported": False}
        conversation = store.create_conversation(principal, "chat", {"type": "legacy", "sourceKey": body.sourceKey}, (messages[0]["content"][:30] or "旧对话"))
        now = store.clock()
        with store._connect() as conn:
            for message in messages:
                conn.execute("INSERT INTO message(id,conversation_id,role,content,status,created_at) VALUES(?,?,?,?,?,?)", (__import__('uuid').uuid4().hex, conversation["id"], message["role"], message["content"], "complete", now))
        store.record_legacy_import(principal, body.sourceKey, content, conversation["id"])
        return {"conversationId": conversation["id"], "imported": True}
