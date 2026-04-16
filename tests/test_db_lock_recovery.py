"""
TDD coverage for ETI DBLock_Recovery_Refactor_2026-04-16.

Verifies:
- IDatabaseRecoveryStrategy contract on SQLiteDriver
- DatabaseManager.recover_from_lock() orchestration
- Recovery metrics tracking
- Degradation lifecycle (mark / clear)
- Concurrent write stress with auto-recovery
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from data_vault.database_manager import DatabaseManager, get_database_manager
from data_vault.drivers import SQLiteDriver
from data_vault.drivers.interface import (
    IDatabaseRecoveryStrategy,
    RecoveryContext,
    RecoveryResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_manager() -> DatabaseManager:
    """Return a NEW, non-singleton DatabaseManager for isolation."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._initialized = False
    mgr.__init__()
    return mgr


def _fresh_driver(manager: DatabaseManager) -> SQLiteDriver:
    return SQLiteDriver(manager)


# ---------------------------------------------------------------------------
# IDatabaseRecoveryStrategy — interface compliance
# ---------------------------------------------------------------------------


def test_sqlite_driver_implements_recovery_strategy_interface() -> None:
    """SQLiteDriver must satisfy the IDatabaseRecoveryStrategy contract."""
    driver = SQLiteDriver(get_database_manager())
    assert isinstance(driver, IDatabaseRecoveryStrategy)
    assert callable(driver.is_lock_error)
    assert callable(driver.attempt_recovery)


def test_is_lock_error_returns_true_for_lock_messages() -> None:
    """is_lock_error classifies canonical SQLite lock strings."""
    driver = SQLiteDriver(get_database_manager())

    for msg in ("database is locked", "database table is locked", "database is busy"):
        assert driver.is_lock_error(sqlite3.OperationalError(msg)) is True


def test_is_lock_error_returns_false_for_unrelated_errors() -> None:
    """is_lock_error must not classify unrelated errors as lock errors."""
    driver = SQLiteDriver(get_database_manager())

    assert driver.is_lock_error(ValueError("division by zero")) is False
    assert driver.is_lock_error(sqlite3.OperationalError("no such table: foo")) is False


# ---------------------------------------------------------------------------
# attempt_recovery — WAL checkpoint path
# ---------------------------------------------------------------------------


def test_attempt_recovery_wal_checkpoint_success(tmp_path: Path) -> None:
    """attempt_recovery should succeed via WAL checkpoint on a healthy DB."""
    mgr = _fresh_manager()
    driver = _fresh_driver(mgr)
    db_path = str(tmp_path / "recovery_checkpoint.db")

    # Warm up the connection
    with driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    context = RecoveryContext(db_path=db_path, error=Exception("database is locked"), attempt_number=3)
    result = driver.attempt_recovery(context)

    assert result.recovered is True
    assert result.action_taken == "wal_checkpoint"
    assert result.should_degrade is False


def test_attempt_recovery_reconnect_fallback(tmp_path: Path) -> None:
    """When checkpoint raises, attempt_recovery falls back to reconnect."""
    mgr = _fresh_manager()
    driver = _fresh_driver(mgr)
    db_path = str(tmp_path / "recovery_reconnect.db")

    with driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    # Make the shared connection fail on PRAGMA wal_checkpoint
    original_conn = mgr.get_connection(db_path)
    broken_conn = MagicMock(spec=sqlite3.Connection)
    broken_conn.execute.side_effect = sqlite3.OperationalError("database is locked")
    mgr._connection_pool[db_path] = broken_conn  # type: ignore[assignment]

    context = RecoveryContext(db_path=db_path, error=Exception("database is locked"), attempt_number=3)
    result = driver.attempt_recovery(context)

    # After reconnect the pool entry is replaced; result must indicate success
    assert result.recovered is True
    assert result.action_taken == "reconnect"


def test_attempt_recovery_degrade_when_reconnect_also_fails(tmp_path: Path) -> None:
    """should_degrade is True when both checkpoint and reconnect fail."""
    mgr = _fresh_manager()
    driver = _fresh_driver(mgr)
    db_path = str(tmp_path / "recovery_degrade.db")

    # Inject a broken connection so checkpoint fails
    broken = MagicMock(spec=sqlite3.Connection)
    broken.execute.side_effect = sqlite3.OperationalError("database is locked")
    mgr._connection_pool[db_path] = broken  # type: ignore[assignment]

    # Also make close_connection raise so reconnect path fails
    with patch.object(mgr, "close_connection", side_effect=Exception("cannot close")):
        context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
        result = driver.attempt_recovery(context)

    assert result.recovered is False
    assert result.should_degrade is True


# ---------------------------------------------------------------------------
# DatabaseManager.recover_from_lock() — orchestration
# ---------------------------------------------------------------------------


def test_recover_from_lock_delegates_to_registered_strategy(tmp_path: Path) -> None:
    """recover_from_lock must invoke the registered strategy exactly once."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "orch_delegate.db")

    mock_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    mock_strategy.attempt_recovery.return_value = RecoveryResult(
        recovered=True, action_taken="mock_action"
    )
    mgr.register_recovery_strategy(mock_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=1)
    result = mgr.recover_from_lock(context)

    mock_strategy.attempt_recovery.assert_called_once_with(context)
    assert result.recovered is True


def test_recover_from_lock_returns_no_strategy_when_none_registered() -> None:
    """recover_from_lock returns action='no_strategy' when no strategy is set."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._initialized = False
    mgr.__init__()
    # Do NOT register any strategy
    mgr._recovery_strategy = None

    context = RecoveryContext(db_path="any.db", error=Exception("locked"), attempt_number=1)
    result = mgr.recover_from_lock(context)

    assert result.recovered is False
    assert result.action_taken == "no_strategy"


def test_recover_from_lock_skips_already_degraded_db(tmp_path: Path) -> None:
    """recover_from_lock must short-circuit for already-degraded databases."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "already_degraded.db")
    mgr._degraded_dbs.add(db_path)

    mock_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    mgr.register_recovery_strategy(mock_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=5)
    result = mgr.recover_from_lock(context)

    mock_strategy.attempt_recovery.assert_not_called()
    assert result.action_taken == "already_degraded"


def test_recover_from_lock_marks_db_degraded_on_should_degrade(tmp_path: Path) -> None:
    """DB is added to degraded set when strategy returns should_degrade=True."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "mark_degraded.db")

    failing_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    failing_strategy.attempt_recovery.return_value = RecoveryResult(
        recovered=False, action_taken="reconnect_failed", should_degrade=True
    )
    mgr.register_recovery_strategy(failing_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
    mgr.recover_from_lock(context)

    assert mgr.is_degraded(db_path) is True


def test_clear_degraded_removes_db_from_degraded_set(tmp_path: Path) -> None:
    """clear_degraded un-marks a previously degraded DB."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "clear_degraded.db")
    mgr._degraded_dbs.add(db_path)

    assert mgr.is_degraded(db_path) is True
    mgr.clear_degraded(db_path)
    assert mgr.is_degraded(db_path) is False


# ---------------------------------------------------------------------------
# Recovery metrics
# ---------------------------------------------------------------------------


def test_recovery_metrics_increment_on_success(tmp_path: Path) -> None:
    """Successful recovery increments total_attempts and successes."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "metrics_success.db")

    ok_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    ok_strategy.attempt_recovery.return_value = RecoveryResult(
        recovered=True, action_taken="wal_checkpoint"
    )
    mgr.register_recovery_strategy(ok_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
    mgr.recover_from_lock(context)

    metrics = mgr.get_recovery_metrics()
    assert metrics["total_attempts"] == 1
    assert metrics["successes"] == 1
    assert metrics["failures"] == 0
    assert metrics["degradations"] == 0


def test_recovery_metrics_increment_on_failure_and_degradation(tmp_path: Path) -> None:
    """Failed recovery with degradation increments failures and degradations."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "metrics_failure.db")

    fail_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    fail_strategy.attempt_recovery.return_value = RecoveryResult(
        recovered=False, action_taken="reconnect_failed", should_degrade=True
    )
    mgr.register_recovery_strategy(fail_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
    mgr.recover_from_lock(context)

    metrics = mgr.get_recovery_metrics()
    assert metrics["total_attempts"] == 1
    assert metrics["successes"] == 0
    assert metrics["failures"] == 1
    assert metrics["degradations"] == 1


def test_degradation_counted_only_once_per_db(tmp_path: Path) -> None:
    """Subsequent failed recoveries on an already-degraded DB do not double-count degradations."""
    mgr = _fresh_manager()
    db_path = str(tmp_path / "metrics_once.db")

    fail_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    fail_strategy.attempt_recovery.return_value = RecoveryResult(
        recovered=False, action_taken="reconnect_failed", should_degrade=True
    )
    mgr.register_recovery_strategy(fail_strategy)

    context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
    mgr.recover_from_lock(context)  # first call — degrades
    mgr.recover_from_lock(context)  # second call — already_degraded, skips strategy

    metrics = mgr.get_recovery_metrics()
    assert metrics["degradations"] == 1


# ---------------------------------------------------------------------------
# _with_retry integration — post-recovery attempt
# ---------------------------------------------------------------------------


def test_driver_retry_invokes_recovery_and_retries_operation(tmp_path: Path) -> None:
    """After max retries, driver invokes recover_from_lock and retries the operation once."""
    mgr = _fresh_manager()
    driver = _fresh_driver(mgr)

    call_counts: dict[str, int] = {"operation": 0, "recovery": 0}
    lock_error = sqlite3.OperationalError("database is locked")

    def flaky_recovery(context: RecoveryContext) -> RecoveryResult:
        call_counts["recovery"] += 1
        return RecoveryResult(recovered=True, action_taken="mock_checkpoint")

    mgr.register_recovery_strategy(MagicMock(
        spec=IDatabaseRecoveryStrategy,
        is_lock_error=MagicMock(return_value=True),
        attempt_recovery=flaky_recovery,
    ))

    # Replace the actual recovery strategy registered by the driver with our stub
    mock_strategy = MagicMock(spec=IDatabaseRecoveryStrategy)
    mock_strategy.attempt_recovery.side_effect = flaky_recovery
    mgr._recovery_strategy = mock_strategy

    # Patch execute_update to fail twice (retries), then succeed on post-recovery call
    original = mgr.execute_update
    attempt_counter = {"n": 0}

    def patched_execute_update(db_path: str, sql: str, params: Any = ()) -> int:
        attempt_counter["n"] += 1
        if attempt_counter["n"] <= 2:
            raise lock_error
        return original(db_path, sql, params)

    db_path = str(tmp_path / "retry_recovery.db")
    with driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE r (id INTEGER PRIMARY KEY, v TEXT)")

    driver.set_runtime_concurrency_policy({"retry_max_attempts": 2})

    with patch.object(mgr, "execute_update", side_effect=patched_execute_update):
        # Should succeed: 2 lock failures → recovery → 1 clean attempt
        result = driver.execute(db_path, "INSERT INTO r (v) VALUES (?)", ("x",))

    assert call_counts["recovery"] == 1
    assert result >= 0


# ---------------------------------------------------------------------------
# Concurrent writes — no permanent lock
# ---------------------------------------------------------------------------


def test_concurrent_writes_do_not_deadlock(tmp_path: Path) -> None:
    """10 concurrent threads writing to the same DB should all complete."""
    mgr = _fresh_manager()
    driver = _fresh_driver(mgr)
    db_path = str(tmp_path / "concurrent.db")

    with driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE cw (id INTEGER PRIMARY KEY, val INTEGER)")

    errors: list[Exception] = []

    def write_row(n: int) -> None:
        try:
            driver.execute(db_path, "INSERT INTO cw (val) VALUES (?)", (n,))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write_row, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    rows = driver.fetch_all(db_path, "SELECT val FROM cw")
    assert len(errors) == 0, f"Concurrent write errors: {errors}"
    assert len(rows) == 10
