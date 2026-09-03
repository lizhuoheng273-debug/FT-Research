"""SQLite-backed identities, conversations, runs and replayable events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    id: str
    kind: Literal["owner", "guest"]


RUN_TERMINAL = {"completed", "stopped", "failed", "interrupted"}
RUN_ACTIVE = {"queued", "running"}


class SessionStore:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _initialize(self) -> None:
        with self._init_lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
                INSERT INTO schema_version(version)
                  SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
                CREATE TABLE IF NOT EXISTS principal(
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL CHECK(kind IN ('owner','guest')),
                  created_at REAL NOT NULL,
                  expires_at REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_owner ON principal(kind) WHERE kind='owner';
                CREATE TABLE IF NOT EXISTS auth_session(
                  token_hash TEXT PRIMARY KEY,
                  principal_id TEXT NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
                  kind TEXT NOT NULL CHECK(kind IN ('owner','guest')),
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  last_heartbeat REAL NOT NULL,
                  revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS auth_principal ON auth_session(principal_id);
                CREATE TABLE IF NOT EXISTS conversation(
                  id TEXT PRIMARY KEY,
                  principal_id TEXT NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
                  kind TEXT NOT NULL CHECK(kind IN ('chat','debate')),
                  title TEXT NOT NULL,
                  source_json TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  deleted_at REAL
                );
                CREATE INDEX IF NOT EXISTS conversation_owner_updated
                  ON conversation(principal_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS run(
                  id TEXT PRIMARY KEY,
                  principal_id TEXT NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
                  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
                  client_request_id TEXT NOT NULL,
                  question TEXT NOT NULL,
                  context_json TEXT NOT NULL,
                  status TEXT NOT NULL CHECK(status IN ('queued','running','completed','stopped','failed','interrupted')),
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  deadline REAL,
                  error_code TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS run_request_identity
                  ON run(principal_id, client_request_id);
                CREATE UNIQUE INDEX IF NOT EXISTS active_conversation
                  ON run(conversation_id) WHERE status IN ('queued','running');
                CREATE INDEX IF NOT EXISTS run_principal ON run(principal_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS message(
                  id TEXT PRIMARY KEY,
                  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
                  run_id TEXT REFERENCES run(id) ON DELETE SET NULL,
                  role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
                  content TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'complete',
                  tool_json TEXT,
                  created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS message_conversation ON message(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS run_event(
                  run_id TEXT NOT NULL REFERENCES run(id) ON DELETE CASCADE,
                  seq INTEGER NOT NULL,
                  type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  PRIMARY KEY(run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS usage_counter(
                  bucket TEXT NOT NULL,
                  dimension TEXT NOT NULL,
                  count INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY(bucket, dimension)
                );
                CREATE TABLE IF NOT EXISTS legacy_import(
                  principal_id TEXT NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
                  source_key TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
                  created_at REAL NOT NULL,
                  PRIMARY KEY(principal_id, source_key, content_hash)
                );
                """
            )

    @staticmethod
    def _principal(row: sqlite3.Row) -> Principal:
        return Principal(row["id"], row["kind"])

    @staticmethod
    def _json(value) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))

    def create_principal(self, kind: Literal["owner", "guest"]) -> Principal:
        if kind not in {"owner", "guest"}:
            raise ValueError("invalid principal kind")
        now = float(self.clock())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if kind == "owner":
                row = conn.execute("SELECT * FROM principal WHERE kind='owner'").fetchone()
                if row:
                    return self._principal(row)
            principal_id = "owner" if kind == "owner" else str(uuid.uuid4())
            expires_at = now + 7200 if kind == "guest" else None
            conn.execute(
                "INSERT INTO principal(id,kind,created_at,expires_at) VALUES (?,?,?,?)",
                (principal_id, kind, now, expires_at),
            )
            return Principal(principal_id, kind)

    def principal_by_id(self, principal_id: str) -> Principal:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM principal WHERE id=?", (principal_id,)).fetchone()
        if not row:
            raise NotFound("principal not found")
        return self._principal(row)

    def create_conversation(self, principal: Principal, kind: str, source: dict, title: str | None = None) -> dict:
        if kind not in {"chat", "debate"}:
            raise ValueError("invalid conversation kind")
        now = float(self.clock())
        conversation_id = str(uuid.uuid4())
        title = (title or "新对话")[:100]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation(id,principal_id,kind,title,source_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (conversation_id, principal.id, kind, title, self._json(source), now, now),
            )
        return self._conversation_dict_from_values(conversation_id, principal.id, kind, title, source, now, now, "idle")

    @staticmethod
    def _conversation_dict_from_values(cid, principal_id, kind, title, source, created, updated, status):
        return {"id": cid, "principalId": principal_id, "kind": kind, "title": title, "source": source,
                "createdAt": created, "updatedAt": updated, "status": status}

    def _conversation_row(self, conn, principal: Principal, conversation_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM conversation WHERE id=? AND principal_id=? AND deleted_at IS NULL",
            (conversation_id, principal.id),
        ).fetchone()
        if not row:
            raise NotFound("conversation not found")
        return row

    def _conversation_dict(self, conn, row: sqlite3.Row) -> dict:
        active = conn.execute(
            "SELECT status FROM run WHERE conversation_id=? AND status IN ('queued','running')", (row["id"],)
        ).fetchone()
        status = active["status"] if active else "idle"
        return self._conversation_dict_from_values(
            row["id"], row["principal_id"], row["kind"], row["title"], json.loads(row["source_json"]),
            row["created_at"], row["updated_at"], status,
        )

    def get_conversation(self, principal: Principal, conversation_id: str) -> dict:
        with self._connect() as conn:
            row = self._conversation_row(conn, principal, conversation_id)
            return self._conversation_dict(conn, row)

    def list_conversations(self, principal: Principal, query: str = "", limit: int = 30, cursor=None) -> dict:
        limit = max(1, min(int(limit), 100))
        params = [principal.id]
        where = "c.principal_id=? AND c.deleted_at IS NULL"
        if query:
            where += " AND c.title LIKE ?"
            params.append(f"%{query[:100]}%")
        if cursor:
            where += " AND c.updated_at < ?"
            params.append(float(cursor))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT c.* FROM conversation c WHERE {where} ORDER BY c.updated_at DESC LIMIT ?", params + [limit + 1]
            ).fetchall()
            items = [self._conversation_dict(conn, row) for row in rows[:limit]]
            next_cursor = str(rows[limit - 1]["updated_at"]) if len(rows) > limit else None
        return {"items": items, "nextCursor": next_cursor}

    def update_conversation_title(self, principal: Principal, conversation_id: str, title: str) -> dict:
        title = title.strip()
        if not 1 <= len(title) <= 100:
            raise ValueError("title must be 1-100 characters")
        with self._connect() as conn:
            self._conversation_row(conn, principal, conversation_id)
            conn.execute("UPDATE conversation SET title=?,updated_at=? WHERE id=? AND principal_id=?", (title, self.clock(), conversation_id, principal.id))
            row = self._conversation_row(conn, principal, conversation_id)
            return self._conversation_dict(conn, row)

    def create_run(self, principal: Principal, conversation_id: str, client_request_id: str, question: str, context: dict) -> dict:
        if not client_request_id or len(client_request_id) > 200:
            raise ValueError("invalid client request id")
        now = float(self.clock())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._conversation_row(conn, principal, conversation_id)
            existing = conn.execute(
                "SELECT * FROM run WHERE principal_id=? AND client_request_id=?", (principal.id, client_request_id)
            ).fetchone()
            if existing:
                if (existing["conversation_id"], existing["question"], existing["context_json"]) != (conversation_id, question, self._json(context)):
                    raise Conflict("client request id already used with a different request")
                return {"id": existing["id"], "status": existing["status"], "created": False, "createdAt": existing["created_at"]}
            if conn.execute("SELECT 1 FROM run WHERE conversation_id=? AND status IN ('queued','running')", (conversation_id,)).fetchone():
                raise Conflict("conversation already has an active run")
            run_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO run(id,principal_id,conversation_id,client_request_id,question,context_json,status,created_at,updated_at,deadline) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, principal.id, conversation_id, client_request_id, question, self._json(context), "queued", now, now, now + 480),
            )
            conn.execute(
                "INSERT INTO message(id,conversation_id,run_id,role,content,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), conversation_id, run_id, "user", question, "pending", now),
            )
        return {"id": run_id, "status": "queued", "created": True, "createdAt": now}

    def run_for_principal(self, principal: Principal, run_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM run WHERE id=? AND principal_id=?", (run_id, principal.id)).fetchone()
        if not row:
            raise NotFound("run not found")
        return dict(row) | {"context": json.loads(row["context_json"])}

    def append_event(self, run_id: str, event_type: str, payload: dict) -> dict | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute("SELECT status FROM run WHERE id=?", (run_id,)).fetchone()
            if not run or run["status"] in RUN_TERMINAL:
                return None
            row = conn.execute("SELECT COALESCE(MAX(seq),0)+1 seq FROM run_event WHERE run_id=?", (run_id,)).fetchone()
            seq = int(row["seq"])
            now = float(self.clock())
            conn.execute("INSERT INTO run_event(run_id,seq,type,payload_json,created_at) VALUES(?,?,?,?,?)", (run_id, seq, event_type, self._json(payload), now))
            conn.execute("UPDATE run SET updated_at=? WHERE id=?", (now, run_id))
            return {"runId": run_id, "seq": seq, "type": event_type, "payload": payload, "createdAt": now}

    def events_after(self, principal: Principal, run_id: str, after: int = 0) -> list[dict]:
        if int(after) < 0:
            raise ValueError("after must be non-negative")
        with self._connect() as conn:
            run = conn.execute("SELECT id FROM run WHERE id=? AND principal_id=?", (run_id, principal.id)).fetchone()
            if not run:
                raise NotFound("run not found")
            rows = conn.execute("SELECT * FROM run_event WHERE run_id=? AND seq>? ORDER BY seq", (run_id, int(after))).fetchall()
        return [{"runId": row["run_id"], "seq": row["seq"], "type": row["type"], "payload": json.loads(row["payload_json"]), "createdAt": row["created_at"]} for row in rows]

    def transition_run(self, run_id: str, expected: str, target: str) -> bool:
        allowed = {"queued": {"running", "stopped", "failed", "interrupted"}, "running": RUN_TERMINAL}
        if target not in allowed.get(expected, set()):
            return False
        with self._connect() as conn:
            changed = conn.execute("UPDATE run SET status=?,updated_at=? WHERE id=? AND status=?", (target, self.clock(), run_id, expected)).rowcount
        return bool(changed)

    def finalize_messages(self, run_id: str, question: str, answer: str, status: str = "complete") -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT conversation_id FROM run WHERE id=?", (run_id,)).fetchone()
            if not row:
                return
            now = float(self.clock())
            conn.execute("UPDATE message SET status=? WHERE run_id=? AND role='user'", (status, run_id))
            conn.execute("INSERT INTO message(id,conversation_id,run_id,role,content,status,created_at) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), row["conversation_id"], run_id, "assistant", answer, status, now))
            conn.execute("UPDATE conversation SET updated_at=? WHERE id=?", (now, row["conversation_id"]))

    def history_for_model(self, principal: Principal, conversation_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            self._conversation_row(conn, principal, conversation_id)
            rows = conn.execute(
                "SELECT m.role,m.content FROM message m JOIN run r ON r.id=m.run_id WHERE m.conversation_id=? AND r.principal_id=? AND r.status='completed' AND m.status='complete' AND m.role IN ('user','assistant') ORDER BY m.created_at DESC LIMIT ?",
                (conversation_id, principal.id, min(limit, 100)),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def get_messages(self, principal: Principal, conversation_id: str) -> list[dict]:
        with self._connect() as conn:
            self._conversation_row(conn, principal, conversation_id)
            rows = conn.execute("SELECT id,run_id,role,content,status,tool_json,created_at FROM message WHERE conversation_id=? ORDER BY created_at", (conversation_id,)).fetchall()
        return [{"id": r["id"], "runId": r["run_id"], "role": r["role"], "content": r["content"], "status": r["status"], "tools": json.loads(r["tool_json"]) if r["tool_json"] else None, "createdAt": r["created_at"]} for r in rows if r["status"] != "pending"]

    def delete_conversation(self, principal: Principal, conversation_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._conversation_row(conn, principal, conversation_id)
            now = float(self.clock())
            conn.execute("UPDATE run SET status='stopped',updated_at=? WHERE conversation_id=? AND status IN ('queued','running')", (now, conversation_id))
            conn.execute("UPDATE conversation SET deleted_at=?,updated_at=? WHERE id=? AND principal_id=?", (now, now, conversation_id, principal.id))
        return True

    def recover_interrupted(self) -> int:
        with self._connect() as conn:
            count = conn.execute("UPDATE run SET status='interrupted',updated_at=? WHERE status IN ('queued','running')", (self.clock(),)).rowcount
        return int(count)

    def purge_guest(self, principal_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT kind FROM principal WHERE id=?", (principal_id,)).fetchone()
            if not row or row["kind"] != "guest":
                return False
            conn.execute("DELETE FROM principal WHERE id=?", (principal_id,))
        return True

    def create_auth_session(self, token_hash: str, principal: Principal, expires_at: float) -> None:
        now = float(self.clock())
        with self._connect() as conn:
            conn.execute("INSERT INTO auth_session(token_hash,principal_id,kind,created_at,expires_at,last_heartbeat) VALUES(?,?,?,?,?,?)", (token_hash, principal.id, principal.kind, now, expires_at, now))

    def auth_session(self, token_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_session WHERE token_hash=?", (token_hash,)).fetchone()
        return dict(row) if row else None

    def touch_auth_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE auth_session SET last_heartbeat=? WHERE token_hash=? AND revoked=0", (self.clock(), token_hash))

    def revoke_auth_session(self, token_hash: str) -> Principal | None:
        with self._connect() as conn:
            row = conn.execute("SELECT p.* FROM auth_session s JOIN principal p ON p.id=s.principal_id WHERE s.token_hash=?", (token_hash,)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE auth_session SET revoked=1 WHERE token_hash=?", (token_hash,))
            return self._principal(row)

    def guest_sessions(self, now: float | None = None) -> list[dict]:
        now = float(self.clock() if now is None else now)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM auth_session WHERE kind='guest' AND revoked=0 AND (expires_at<=? OR last_heartbeat<=?)", (now, now - 90)).fetchall()
        return [dict(row) for row in rows]

    def record_legacy_import(self, principal: Principal, source_key: str, content: str, conversation_id: str) -> bool:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as conn:
            try:
                conn.execute("INSERT INTO legacy_import(principal_id,source_key,content_hash,conversation_id,created_at) VALUES(?,?,?,?,?)", (principal.id, source_key, digest, conversation_id, self.clock()))
            except sqlite3.IntegrityError:
                return False
        return True
