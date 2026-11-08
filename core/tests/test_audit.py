import json
import sqlite3

import pytest

from brz.audit import AuditLog


def test_audit_records_append_only_task_history(tmp_path):
    audit = AuditLog(tmp_path / "audit.db")
    audit.log_task_start("task-1", "live_ai:task", "code")
    audit.log_stage("task-1", "planning", details={"provider_calls": 1})
    audit.log_error("task-1", "critic", "policy_denied", "Forbidden import detected: socket")
    audit.log_execution("task-1", "blocked", "", "Forbidden import", 1, 0)

    history = audit.task_history("task-1")
    assert history is not None
    assert history["task"]["request_label"] == "live_ai:task"
    assert [row["event_type"] for row in history["events"]] == ["transition", "error"]
    assert json.loads(history["events"][1]["details"])["code"] == "policy_denied"
    assert history["execution_result"]["status"] == "blocked"

    with sqlite3.connect(tmp_path / "audit.db") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("update execution_results set status = 'succeeded'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("delete from events")


def test_duplicate_final_result_does_not_mutate_audit(tmp_path):
    audit = AuditLog(tmp_path / "audit.db")
    audit.log_task_start("task-1", "preset:csv-analysis", "code")
    audit.log_execution("task-1", "succeeded", "first", "", 0, 0)
    audit.log_execution("task-1", "failed", "second", "changed", 1, 1)
    result = audit.task_history("task-1")["execution_result"]
    assert result["status"] == "succeeded"
    assert result["output_bytes"] == len(b"first")
    assert len(result["output_sha256"]) == 64
