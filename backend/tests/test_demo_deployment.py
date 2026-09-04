import sqlite3
import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

_spec = importlib.util.spec_from_file_location("owner_backup", Path(__file__).parents[2] / "scripts" / "owner_backup.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
export_owner, restore_backup = _module.export_owner, _module.restore_backup
from session_store import SessionStore
from app import app


def test_owner_backup_excludes_guests_and_tokens(tmp_path):
    source = tmp_path / "sessions.sqlite3"
    store = SessionStore(source)
    owner = store.create_principal("owner")
    guest = store.create_principal("guest")
    conversation = store.create_conversation(owner, "chat", {})
    store.create_conversation(guest, "chat", {})
    store.create_auth_session("secret-token-hash", owner, 9999)
    store.create_run(owner, conversation["id"], "r", "question", {})
    backup = tmp_path / "owner.sqlite3"
    export_owner(source, backup)
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT COUNT(*) FROM principal WHERE kind='guest'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM auth_session").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    restored = tmp_path / "restored.sqlite3"
    restore_backup(backup, restored)
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT COUNT(*) FROM run WHERE status='interrupted'").fetchone()[0] == 1


def test_backup_refuses_overwrite(tmp_path):
    source = tmp_path / "sessions.sqlite3"
    store = SessionStore(source)
    store.create_principal("owner")
    backup = tmp_path / "owner.sqlite3"
    export_owner(source, backup)
    try:
        export_owner(source, backup)
    except SystemExit as exc:
        assert "overwrite" in str(exc)
    else:
        raise AssertionError("expected overwrite refusal")


def test_spa_does_not_expose_database():
    with TestClient(app) as client:
        assert client.get("/finance/watchlist").status_code == 200
        response = client.get("/api/unknown-endpoint")
        assert response.status_code in (401, 404)
        assert "text/html" not in response.headers.get("content-type", "")
        assert client.get("/data/sessions.sqlite3").status_code == 404
        assert client.get("/.env").status_code == 404
