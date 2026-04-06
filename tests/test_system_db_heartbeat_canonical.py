import sqlite3
from typing import Any

from data_vault.system_db import SystemMixin


class _SystemRepoForTest(SystemMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        return None

    def _execute_serialized(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return func(self._conn, *args, **kwargs)


def test_get_latest_module_heartbeat_audit_prefers_sys_audit_logs() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE sys_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            resource TEXT,
            timestamp TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE system_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            resource TEXT,
            timestamp TEXT
        )
        """
    )
    cur.execute(
        "INSERT INTO sys_audit_logs (user_id, action, resource, timestamp) VALUES ('SYSTEM','HEARTBEAT','orchestrator','2026-04-05 10:00:00')"
    )
    cur.execute(
        "INSERT INTO system_audit_logs (action, resource, timestamp) VALUES ('HEARTBEAT','orchestrator','2026-04-05 11:00:00')"
    )
    conn.commit()

    repo = _SystemRepoForTest(conn)
    ts = repo.get_latest_module_heartbeat_audit("orchestrator")
    assert ts == "2026-04-05 10:00:00"


def test_get_latest_module_heartbeat_audit_falls_back_to_system_audit_logs() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE system_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            resource TEXT,
            timestamp TEXT
        )
        """
    )
    cur.execute(
        "INSERT INTO system_audit_logs (action, resource, timestamp) VALUES ('HEARTBEAT','orchestrator','2026-04-05 12:00:00')"
    )
    conn.commit()

    repo = _SystemRepoForTest(conn)
    ts = repo.get_latest_module_heartbeat_audit("orchestrator")
    assert ts == "2026-04-05 12:00:00"
