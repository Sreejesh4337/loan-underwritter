"""SQLite database wrapper for runs, documents, and outputs.
Replaces the local filesystem JSONL registry and blob storage.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path("data/underwriter.db")
_lock = threading.Lock()


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    application_id TEXT,
                    thread_id TEXT,
                    status TEXT,
                    error TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    application_id TEXT,
                    doc_type TEXT,
                    content BLOB,
                    PRIMARY KEY (application_id, doc_type)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outputs (
                    run_id TEXT,
                    output_type TEXT,
                    content BLOB,
                    PRIMARY KEY (run_id, output_type)
                )
                """
            )
            conn.commit()


_init_db()


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def save_run(record: dict[str, Any]) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, application_id, thread_id, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    error=excluded.error
                """,
                (
                    record["run_id"],
                    record["application_id"],
                    record["thread_id"],
                    record["status"],
                    record.get("error"),
                    record["created_at"],
                ),
            )
            conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def list_runs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM runs ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def save_document(application_id: str, doc_type: str, content: bytes) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO documents (application_id, doc_type, content)
                VALUES (?, ?, ?)
                ON CONFLICT(application_id, doc_type) DO UPDATE SET content=excluded.content
                """,
                (application_id, doc_type, content),
            )
            conn.commit()


def get_document(application_id: str, doc_type: str) -> bytes | None:
    with get_conn() as conn:
        cur = conn.execute("SELECT content FROM documents WHERE application_id = ? AND doc_type = ?", (application_id, doc_type))
        row = cur.fetchone()
        return row[0] if row else None


def save_output(run_id: str, output_type: str, content: bytes) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO outputs (run_id, output_type, content)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id, output_type) DO UPDATE SET content=excluded.content
                """,
                (run_id, output_type, content),
            )
            conn.commit()


def get_output(run_id: str, output_type: str) -> bytes | None:
    with get_conn() as conn:
        cur = conn.execute("SELECT content FROM outputs WHERE run_id = ? AND output_type = ?", (run_id, output_type))
        row = cur.fetchone()
        return row[0] if row else None
