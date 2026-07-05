"""
database.py
------------
Minimal job persistence using stdlib sqlite3 -- deliberately dependency-free
so the storage layer works even in the most stripped-down deployment. Swap
this for Postgres by replacing the connection helper if you need multi-
instance horizontal scaling; the schema is intentionally simple (one row per
job, JSON blob for the result) so that migration is a non-event.
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

DB_PATH = os.environ.get("PLAGCHECK_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db"))
_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_conn():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                progress_message TEXT DEFAULT '',
                request_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def create_job(request: dict) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, status, progress, progress_message, request_json, created_at, updated_at) "
            "VALUES (?, 'pending', 0, 'Queued', ?, ?, ?)",
            (job_id, json.dumps(request), now, now),
        )
    return job_id


def update_progress(job_id: str, progress: int, message: str, status: str = "running"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, progress=?, progress_message=?, updated_at=? WHERE id=?",
            (status, progress, message, now, job_id),
        )


def complete_job(job_id: str, result: dict):
    now = datetime.utcnow().isoformat()
    status = "completed" if result.get("status") == "completed" else "failed"
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, progress=100, progress_message='Done', result_json=?, updated_at=? WHERE id=?",
            (status, json.dumps(result), now, job_id),
        )


def fail_job(job_id: str, error: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=?",
            (error, now, job_id),
        )


def get_job(job_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["request"] = json.loads(d.pop("request_json"))
        d["result"] = json.loads(d["result_json"]) if d.get("result_json") else None
        d.pop("result_json", None)
        return d


def list_jobs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, status, progress, created_at, updated_at FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
