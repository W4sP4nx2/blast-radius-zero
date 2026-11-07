"""Audit: persistent SQLite audit trail for task execution."""
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path("/tmp/.blast-radius-zero") / "audit.db"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        pragma journal_mode = wal;
        create table if not exists tasks (
            task_id text primary key,
            user_request text not null,
            pattern text not null,
            status text not null,
            created_at real not null,
            updated_at real not null
        );
        create table if not exists stages (
            id integer primary key autoincrement,
            task_id text not null references tasks(task_id),
            stage text not null,
            duration_ms integer,
            details text,
            created_at real not null
        );
        create table if not exists errors (
            id integer primary key autoincrement,
            task_id text not null references tasks(task_id),
            stage text not null,
            code text,
            message text not null,
            created_at real not null
        );
        create table if not exists execution_results (
            task_id text primary key references tasks(task_id),
            status text not null,
            output text,
            error text,
            provider_requests integer,
            recoveries integer,
            created_at real not null,
            updated_at real not null
        );
        create index if not exists idx_stages_task on stages(task_id);
        create index if not exists idx_errors_task on errors(task_id);
        -- Prevent updates/deletes on execution_results (immutable after insert)
        create trigger if not exists tr_prevent_exec_update
        before update on execution_results
        begin
            select raise(abort, 'execution results are immutable');
        end;
        create trigger if not exists tr_prevent_exec_delete
        before delete on execution_results
        begin
            select raise(abort, 'execution results are immutable');
        end;
    """)


class AuditLog:
    """Thread-safe SQLite audit log with triggers that prevent immutable data modification."""
    _local = threading.local()

    def __init__(self, path: Path | None = None):
        self._path = path or DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None or not getattr(self._local, "connected", False):
            self._conn = sqlite3.connect(self._path, isolation_level=None)
            ensure_schema(self._conn)
            self._local.connected = True
        return self._conn

    def log_task_start(self, task_id: str, user_request: str, pattern: str) -> None:
        conn = self._get_conn()
        now = _now()
        conn.execute(
            """
            insert into tasks (task_id, user_request, pattern, status, created_at, updated_at)
            values (?, ?, ?, 'queued', ?, ?)
            on conflict(task_id) do update set updated_at = excluded.updated_at
            """,
            (task_id, user_request[:10000], pattern, now, now),
        )

    def log_stage(self, task_id: str, stage: str, duration_ms: int | None = None, details: dict | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            "insert into stages (task_id, stage, duration_ms, details, created_at) values (?, ?, ?, ?, ?)",
            (task_id, stage, duration_ms, json.dumps(details) if details else None, _now()),
        )

    def log_error(self, task_id: str, stage: str, code: str | None, message: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "insert into errors (task_id, stage, code, message, created_at) values (?, ?, ?, ?, ?)",
            (task_id, stage, code, message, _now()),
        )

    def log_execution(self, task_id: str, status: str, output: str, error: str | None,
                      provider_requests: int, recoveries: int) -> None:
        now = _now()
        conn = self._get_conn()
        conn.execute(
            """
            insert into execution_results (task_id, status, output, error, provider_requests, recoveries, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(task_id) do update set
                status = excluded.status,
                output = excluded.output,
                error = excluded.error,
                provider_requests = excluded.provider_requests,
                recoveries = excluded.recoveries,
                updated_at = excluded.updated_at
            """,
            (task_id, status, output[:262144], error, provider_requests, recoveries, now, now),
        )

    def get_task(self, task_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("select * from tasks where task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return {
            "task_id": row[0], "user_request": row[1], "pattern": row[2],
            "status": row[3], "created_at": row[4], "updated_at": row[5],
        }

    def close(self) -> None:
        # Don't close connection if running in different thread (SQLite limitation)
        if self._conn and getattr(self._local, "connected", False):
            try:
                self._conn.close()
            except sqlite3.ProgrammingError:
                pass  # Connection already closed or wrong thread
            finally:
                self._local.connected = False


def _now() -> float:
    import time
    return time.time()
