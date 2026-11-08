"""Append-only SQLite audit events owned by the trusted coordinator."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
pragma journal_mode = wal;
pragma foreign_keys = on;
create table if not exists tasks (
    task_id text primary key,
    request_label text not null,
    pattern text not null,
    created_at real not null
);
create table if not exists events (
    id integer primary key autoincrement,
    task_id text not null references tasks(task_id),
    stage text not null,
    event_type text not null,
    details text,
    duration_ms integer,
    created_at real not null
);
create table if not exists execution_results (
    task_id text primary key references tasks(task_id),
    status text not null,
    output_bytes integer not null,
    output_sha256 text not null,
    error text not null,
    provider_requests integer not null,
    recoveries integer not null,
    created_at real not null
);
create index if not exists idx_audit_events_task on events(task_id, id);

create trigger if not exists audit_tasks_no_update
before update on tasks begin select raise(abort, 'audit rows are append-only'); end;
create trigger if not exists audit_tasks_no_delete
before delete on tasks begin select raise(abort, 'audit rows are append-only'); end;
create trigger if not exists audit_events_no_update
before update on events begin select raise(abort, 'audit rows are append-only'); end;
create trigger if not exists audit_events_no_delete
before delete on events begin select raise(abort, 'audit rows are append-only'); end;
create trigger if not exists audit_results_no_update
before update on execution_results begin select raise(abort, 'audit rows are append-only'); end;
create trigger if not exists audit_results_no_delete
before delete on execution_results begin select raise(abort, 'audit rows are append-only'); end;
"""


class AuditLog:
    """Small synchronous audit writer; callers move writes off the event loop."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("pragma foreign_keys = on")
        connection.execute("pragma busy_timeout = 5000")
        return connection

    def log_task_start(self, task_id: str, request_label: str, pattern: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "insert or ignore into tasks values (?, ?, ?, ?)",
                (task_id, request_label[:256], pattern, time.time()),
            )

    def log_stage(
        self,
        task_id: str,
        stage: str,
        *,
        event_type: str = "transition",
        duration_ms: int | None = None,
        details: dict | None = None,
    ) -> None:
        encoded = json.dumps(details, separators=(",", ":"), ensure_ascii=False) if details else None
        with self._connect() as connection:
            connection.execute(
                """insert into events
                   (task_id, stage, event_type, details, duration_ms, created_at)
                   values (?, ?, ?, ?, ?, ?)""",
                (task_id, stage, event_type, encoded, duration_ms, time.time()),
            )

    def log_error(self, task_id: str, stage: str, code: str, message: str) -> None:
        self.log_stage(
            task_id,
            stage,
            event_type="error",
            details={"code": code, "message": message[:4096]},
        )

    def log_execution(
        self,
        task_id: str,
        status: str,
        output: str,
        error: str,
        provider_requests: int,
        recoveries: int,
    ) -> None:
        output_bytes = output.encode("utf-8", errors="replace")
        with self._connect() as connection:
            connection.execute(
                """insert or ignore into execution_results
                   (task_id, status, output_bytes, output_sha256, error,
                    provider_requests, recoveries, created_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    status,
                    len(output_bytes),
                    hashlib.sha256(output_bytes).hexdigest(),
                    error[:4096],
                    provider_requests,
                    recoveries,
                    time.time(),
                ),
            )

    def task_history(self, task_id: str) -> dict | None:
        connection = self._connect()
        connection.row_factory = sqlite3.Row
        try:
            task = connection.execute(
                "select * from tasks where task_id = ?", (task_id,)
            ).fetchone()
            if task is None:
                return None
            events = connection.execute(
                "select * from events where task_id = ? order by id", (task_id,)
            ).fetchall()
            result = connection.execute(
                "select * from execution_results where task_id = ?", (task_id,)
            ).fetchone()
            return {
                "task": dict(task),
                "events": [dict(row) for row in events],
                "execution_result": dict(result) if result else None,
            }
        finally:
            connection.close()

    def close(self) -> None:
        """Connections are operation-scoped; retained for lifecycle symmetry."""
