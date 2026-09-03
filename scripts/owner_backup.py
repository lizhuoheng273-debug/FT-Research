#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from session_store import SessionStore


def export_owner(source: Path, target: Path) -> None:
    if target.exists():
        raise SystemExit(f"refusing to overwrite existing backup: {target}")
    source_conn = sqlite3.connect(source)
    source_conn.row_factory = sqlite3.Row
    try:
        owner = source_conn.execute("SELECT * FROM principal WHERE kind='owner'").fetchone()
        if not owner:
            raise SystemExit("source has no owner")
        target_store = SessionStore(target)
        with target_store._connect() as dest:
            dest.execute("INSERT INTO principal(id,kind,created_at,expires_at) VALUES(?,?,?,?)", tuple(owner))
            conversations = source_conn.execute("SELECT * FROM conversation WHERE principal_id=? AND deleted_at IS NULL", (owner["id"],)).fetchall()
            for row in conversations:
                dest.execute("INSERT INTO conversation VALUES(?,?,?,?,?,?,?,?)", tuple(row))
            ids = [row["id"] for row in conversations]
            if ids:
                marks = ",".join("?" for _ in ids)
                runs = source_conn.execute(f"SELECT * FROM run WHERE principal_id=? AND conversation_id IN ({marks})", [owner["id"], *ids]).fetchall()
                for row in runs:
                    dest.execute("INSERT INTO run VALUES(?,?,?,?,?,?,?,?,?,?,?)", tuple(row))
                for row in source_conn.execute(f"SELECT * FROM message WHERE conversation_id IN ({marks})", ids):
                    dest.execute("INSERT INTO message VALUES(?,?,?,?,?,?,?,?)", tuple(row))
                run_ids = [row["id"] for row in runs]
                if run_ids:
                    marks2 = ",".join("?" for _ in run_ids)
                    for row in source_conn.execute(f"SELECT * FROM run_event WHERE run_id IN ({marks2})", run_ids):
                        dest.execute("INSERT INTO run_event VALUES(?,?,?,?,?)", tuple(row))
                for row in source_conn.execute(f"SELECT * FROM legacy_import WHERE principal_id=? AND conversation_id IN ({marks})", [owner["id"], *ids]):
                    dest.execute("INSERT INTO legacy_import VALUES(?,?,?,?,?)", tuple(row))
    finally:
        source_conn.close()


def restore_backup(source: Path, target: Path) -> None:
    if target.exists():
        raise SystemExit(f"refusing to overwrite existing database: {target}")
    with sqlite3.connect(source) as conn:
        rows = conn.execute("SELECT kind FROM principal").fetchall()
        if not rows or any(row[0] != "owner" for row in rows) or conn.execute("SELECT COUNT(*) FROM auth_session").fetchone()[0]:
            raise SystemExit("backup is not owner-only")
    target.parent.mkdir(parents=True, exist_ok=True)
    target_store = SessionStore(target)
    with sqlite3.connect(source) as src, target_store._connect() as dest:
        for table in ("principal", "conversation", "run", "message", "run_event", "legacy_import"):
            columns = [row[1] for row in src.execute(f"PRAGMA table_info({table})")]
            marks = ",".join("?" for _ in columns)
            for row in src.execute(f"SELECT {','.join(columns)} FROM {table}"):
                dest.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({marks})", tuple(row))
        dest.execute("UPDATE run SET status='interrupted' WHERE status IN ('queued','running')")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    out = sub.add_parser("export")
    out.add_argument("--db", type=Path, required=True)
    out.add_argument("--out", type=Path, required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--from", dest="source", type=Path, required=True)
    restore.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        export_owner(args.db, args.out)
    else:
        restore_backup(args.source, args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
