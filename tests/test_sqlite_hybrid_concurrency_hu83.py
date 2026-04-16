"""TDD coverage for HU 8.3 SQLite hybrid concurrency policy."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from data_vault.drivers import SQLiteDriver
from data_vault.drivers.errors import PersistenceOperationalError
from data_vault.storage import StorageManager


class FakeDatabaseManager:
    """Minimal DatabaseManager stub for controlled concurrency behavior tests."""

    def __init__(self) -> None:
        self.calls = 0

    def execute_update(self, db_path: str, sql: str, params: tuple[object, ...] = ()) -> int:
        self.calls += 1
        return 1

    def execute_many(self, db_path: str, sql: str, param_list: list[tuple[object, ...]]) -> int:
        self.calls += 1
        return len(param_list)

    def execute_query(self, db_path: str, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return []

    def get_connection(self, db_path: str) -> sqlite3.Connection:
        return sqlite3.connect(":memory:")

    def transaction(self, db_path: str):  # pragma: no cover - not needed in these tests
        raise NotImplementedError

    def health_check(self) -> dict[str, object]:
        return {"status": "HEALTHY"}

    def is_sqlite_lock_error(self, error: Exception) -> bool:
        return "locked" in str(error).lower() or "busy" in str(error).lower()

    def observe_sqlite_concurrency_event(self, event_name: str, payload: dict[str, object]) -> None:
        return None

    def register_recovery_strategy(self, strategy: object) -> None:
        pass

    def recover_from_lock(self, context: object) -> object:
        from data_vault.drivers.interface import RecoveryResult
        return RecoveryResult(recovered=False, action_taken="no_strategy")


@pytest.fixture
def sqlite_driver() -> SQLiteDriver:
    driver = SQLiteDriver(FakeDatabaseManager())
    driver.set_runtime_concurrency_policy(
        {
            "retry_max_attempts": 3,
            "retry_base_backoff_ms": 1,
            "retry_backoff_multiplier": 2.0,
            "retry_max_backoff_ms": 4,
            "telemetry_queue_max_size": 50,
            "telemetry_flush_interval_ms": 0,
        }
    )
    return driver


def test_sqlite_retry_backoff_on_locked_write(sqlite_driver: SQLiteDriver) -> None:
    attempts = {"value": 0}

    def flaky_update(db_path: str, sql: str, params: tuple[object, ...] = ()) -> int:
        attempts["value"] += 1
        if attempts["value"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return 1

    sqlite_driver.database_manager.execute_update = flaky_update  # type: ignore[method-assign]

    written = sqlite_driver.execute(":memory:", "INSERT INTO t(a) VALUES (?)", ("ok",), write_mode="critical")

    assert written == 1
    assert attempts["value"] == 3
    metrics = sqlite_driver.get_concurrency_metrics()
    assert metrics["retry_attempts"] >= 2


def test_sqlite_retry_exhaustion_raises_persistence_operational_error(sqlite_driver: SQLiteDriver) -> None:
    def always_locked(db_path: str, sql: str, params: tuple[object, ...] = ()) -> int:
        raise sqlite3.OperationalError("database is locked")

    sqlite_driver.database_manager.execute_update = always_locked  # type: ignore[method-assign]

    with pytest.raises(PersistenceOperationalError):
        sqlite_driver.execute(":memory:", "UPDATE t SET x = ?", (1,), write_mode="critical")


def test_selective_queue_accepts_telemetry_writes(sqlite_driver: SQLiteDriver) -> None:
    sqlite_driver.set_runtime_concurrency_policy(
        {
            "retry_max_attempts": 3,
            "retry_base_backoff_ms": 1,
            "retry_backoff_multiplier": 2.0,
            "retry_max_backoff_ms": 4,
            "telemetry_queue_max_size": 50,
            "telemetry_flush_interval_ms": 10000,
        }
    )

    sqlite_driver.execute(":memory:", "INSERT INTO telemetry(value) VALUES (?)", ("event-1",), write_mode="telemetry")
    sqlite_driver.execute(":memory:", "INSERT INTO telemetry(value) VALUES (?)", ("event-2",), write_mode="telemetry")

    metrics = sqlite_driver.get_concurrency_metrics()
    assert metrics["telemetry_enqueued"] >= 2

    flushed = sqlite_driver.flush_telemetry_queue(":memory:")
    assert flushed >= 2


def test_selective_queue_does_not_wrap_critical_writes(sqlite_driver: SQLiteDriver) -> None:
    enqueue_called = {"value": 0}

    def tracked_enqueue(*args: object, **kwargs: object) -> None:
        enqueue_called["value"] += 1

    sqlite_driver._enqueue_telemetry_write = tracked_enqueue  # type: ignore[method-assign]

    sqlite_driver.execute(":memory:", "INSERT INTO critical(value) VALUES (?)", ("critical",), write_mode="critical")

    assert enqueue_called["value"] == 0


def test_mixed_workload_critical_progress_under_telemetry_burst(sqlite_driver: SQLiteDriver) -> None:
    for idx in range(25):
        sqlite_driver.execute(":memory:", "INSERT INTO telemetry(value) VALUES (?)", (f"t-{idx}",), write_mode="telemetry")

    critical_result = sqlite_driver.execute(
        ":memory:",
        "INSERT INTO critical(value) VALUES (?)",
        ("priority",),
        write_mode="critical",
    )

    assert critical_result == 1


def test_bootstrap_path_bypasses_selective_queue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    enqueue_called = {"value": 0}

    def tracked_enqueue(self: SQLiteDriver, db_path: str, sql: str, params: tuple[object, ...]) -> None:
        enqueue_called["value"] += 1

    monkeypatch.setattr(SQLiteDriver, "_enqueue_telemetry_write", tracked_enqueue)

    storage = StorageManager(db_path=str(tmp_path / "bootstrap_bypass.db"))

    assert storage.db_path.endswith("bootstrap_bypass.db")
    assert enqueue_called["value"] == 0


def test_metrics_for_retries_and_queue_flush(sqlite_driver: SQLiteDriver) -> None:
    # One retry path
    attempts = {"value": 0}

    def flaky_once(db_path: str, sql: str, params: tuple[object, ...] = ()) -> int:
        attempts["value"] += 1
        if attempts["value"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return 1

    sqlite_driver.database_manager.execute_update = flaky_once  # type: ignore[method-assign]
    sqlite_driver.execute(":memory:", "INSERT INTO c(value) VALUES (?)", ("x",), write_mode="critical")

    # Queue + flush path
    sqlite_driver.execute(":memory:", "INSERT INTO telemetry(value) VALUES (?)", ("q",), write_mode="telemetry")
    sqlite_driver.flush_telemetry_queue(":memory:")

    metrics = sqlite_driver.get_concurrency_metrics()
    assert metrics["retry_attempts"] >= 1
    assert metrics["telemetry_enqueued"] >= 1
    assert metrics["telemetry_flushed"] >= 1
    assert metrics["last_flush_latency_ms"] >= 0
