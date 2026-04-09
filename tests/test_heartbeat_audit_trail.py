from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any
from unittest.mock import MagicMock

from core_brain.operational_edge_monitor import CheckStatus, OperationalEdgeMonitor
from data_vault.system_db import SystemMixin


class _SystemRepoForHeartbeatTests(SystemMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        return None

    def _execute_serialized(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return func(self._conn, *args, **kwargs)


def _build_repo() -> _SystemRepoForHeartbeatTests:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE sys_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE sys_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            resource TEXT,
            resource_id TEXT,
            status TEXT,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trace_id TEXT UNIQUE
        )
        """
    )
    conn.commit()
    return _SystemRepoForHeartbeatTests(conn)


def _count_heartbeat_rows(repo: _SystemRepoForHeartbeatTests, module_name: str) -> int:
    cursor = repo._get_conn().cursor()
    cursor.execute(
        "SELECT COUNT(*) AS total FROM sys_audit_logs WHERE action = 'HEARTBEAT' AND resource = ?",
        (module_name,),
    )
    row = cursor.fetchone()
    return int(row["total"])


def _ts(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def test_first_heartbeat_after_boot_is_always_audited_even_with_recent_last_marker() -> None:
    repo = _build_repo()
    repo.update_sys_config(
        {
            "heartbeat_audit_interval_s": 120,
            "heartbeat_audit_last_orchestrator": _ts(5),
        }
    )

    repo.update_module_heartbeat("orchestrator")

    assert _count_heartbeat_rows(repo, "orchestrator") == 1


def test_heartbeat_throttle_skips_second_write_within_interval() -> None:
    repo = _build_repo()
    repo.update_sys_config({"heartbeat_audit_interval_s": 120})

    repo.update_module_heartbeat("orchestrator")
    repo.update_module_heartbeat("orchestrator")

    assert _count_heartbeat_rows(repo, "orchestrator") == 1


def test_heartbeat_post_interval_writes_new_audit_event() -> None:
    repo = _build_repo()
    repo.update_sys_config({"heartbeat_audit_interval_s": 120})

    repo.update_module_heartbeat("orchestrator")
    repo.update_sys_config({"heartbeat_audit_last_orchestrator": _ts(360)})

    repo.update_module_heartbeat("orchestrator")

    assert _count_heartbeat_rows(repo, "orchestrator") == 2


def test_oem_prioritizes_recent_audit_trail_over_stale_sys_config() -> None:
    storage = MagicMock()
    storage.get_all_signal_rankings.return_value = []
    storage.get_sys_broker_accounts.return_value = []
    storage.get_recent_sys_signals.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.save_edge_learning.return_value = None
    storage.get_module_heartbeats.return_value = {"orchestrator": _ts(1800)}
    storage.get_latest_module_heartbeat_audit.return_value = _ts(60)
    storage.get_sys_config.return_value = {}

    oem = OperationalEdgeMonitor(storage=storage, interval_seconds=9999)

    result = oem._check_orchestrator_heartbeat()

    assert result.status == CheckStatus.OK
    assert "source=sys_audit_logs" in result.detail


def test_oem_falls_back_to_sys_config_when_audit_unavailable() -> None:
    storage = MagicMock()
    storage.get_all_signal_rankings.return_value = []
    storage.get_sys_broker_accounts.return_value = []
    storage.get_recent_sys_signals.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.save_edge_learning.return_value = None
    storage.get_module_heartbeats.return_value = {"orchestrator": _ts(60)}
    storage.get_latest_module_heartbeat_audit.return_value = None
    storage.get_sys_config.return_value = {}

    oem = OperationalEdgeMonitor(storage=storage, interval_seconds=9999)

    result = oem._check_orchestrator_heartbeat()

    assert result.status == CheckStatus.OK
    assert "source=sys_config" in result.detail
