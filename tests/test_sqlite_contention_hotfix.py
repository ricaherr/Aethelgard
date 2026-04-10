"""TDD red phase for HU 10.29 SQLite contention hotfix."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from data_vault.backup_manager import DatabaseBackupManager
from data_vault.database_manager import DatabaseManager
from data_vault.storage import StorageManager


@pytest.fixture
def db_manager() -> DatabaseManager:
    """Return a clean DatabaseManager singleton instance for each test."""
    manager = DatabaseManager()
    manager.shutdown()
    yield manager
    manager.shutdown()


def _init_temp_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO sample(value) VALUES (?)", ("alpha",))
    conn.commit()
    conn.close()


def test_execute_query_uses_db_lock_per_path(tmp_path: Path, db_manager: DatabaseManager) -> None:
    db_path = tmp_path / "hotfix_lock.db"
    _init_temp_db(db_path)

    route_lock = threading.RLock()
    db_manager._tx_lock_pool[str(db_path)] = route_lock

    finished = threading.Event()
    payload: dict[str, Any] = {}

    route_lock.acquire()

    def _worker() -> None:
        try:
            payload["rows"] = db_manager.execute_query(str(db_path), "SELECT value FROM sample")
        finally:
            finished.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    assert not finished.wait(0.5), "execute_query must wait when db_path lock is already held"

    route_lock.release()
    thread.join(timeout=2)

    rows = payload.get("rows")
    assert isinstance(rows, list)
    assert rows[0]["value"] == "alpha"


def test_execute_query_cursor_closed_on_exception(monkeypatch: pytest.MonkeyPatch, db_manager: DatabaseManager) -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, sql: str, params: tuple[Any, ...]) -> None:
            raise sqlite3.OperationalError("forced-failure")

        def close(self) -> None:
            self.closed = True

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

    fake_conn = FakeConnection()
    monkeypatch.setattr(db_manager, "get_connection", lambda _db_path: fake_conn)

    with pytest.raises(sqlite3.OperationalError):
        db_manager.execute_query("ignored.db", "SELECT 1")

    assert fake_conn.cursor_instance.closed is True


def test_backup_uses_dedicated_source_connection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "hotfix_backup.db"
    storage = StorageManager(db_path=str(db_path))

    monkeypatch.setattr(
        storage,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("shared connection must not be used by backup")),
    )

    backup_path = storage.create_db_backup(backup_dir=str(tmp_path / "backups"), retention_count=2)

    assert backup_path is not None
    assert Path(backup_path).exists()


def test_backup_manager_does_not_backup_immediately_on_start(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStorage:
        def __init__(self) -> None:
            self.backup_calls = 0

        def get_dynamic_params(self) -> dict[str, Any]:
            return {
                "database_backup": {
                    "enabled": True,
                    "interval_minutes": 60,
                    "backup_dir": "backups",
                    "retention_count": 15,
                }
            }

        def create_db_backup(self, backup_dir: str, retention_count: int) -> str:
            self.backup_calls += 1
            return "ok"

    class OneCycleStopEvent:
        def __init__(self) -> None:
            self._is_set = False

        def clear(self) -> None:
            self._is_set = False

        def set(self) -> None:
            self._is_set = True

        def is_set(self) -> bool:
            return self._is_set

        def wait(self, timeout: float) -> bool:
            self._is_set = True
            return True

    class InlineThread:
        def __init__(self, target: Any, daemon: bool, name: str) -> None:
            self._target = target
            self._alive = False

        def start(self) -> None:
            self._alive = True
            self._target()
            self._alive = False

        def is_alive(self) -> bool:
            return self._alive

        def join(self, timeout: float | None = None) -> None:
            return None

    storage = FakeStorage()
    manager = DatabaseBackupManager(storage=storage, poll_seconds=30)
    manager._stop_event = OneCycleStopEvent()  # type: ignore[assignment]

    monkeypatch.setattr("data_vault.backup_manager.threading.Thread", InlineThread)

    manager.start()

    assert storage.backup_calls == 0


def test_no_regression_transaction_commit_path(tmp_path: Path, db_manager: DatabaseManager) -> None:
    db_path = tmp_path / "hotfix_commit.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE writes (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

    written = db_manager.execute_update(
        str(db_path),
        "INSERT INTO writes(value) VALUES (?)",
        ("persisted",),
    )

    assert written > 0
    rows = db_manager.execute_query(str(db_path), "SELECT value FROM writes")
    assert rows[0]["value"] == "persisted"


def test_no_regression_fetch_all_contract(tmp_path: Path, db_manager: DatabaseManager) -> None:
    db_path = tmp_path / "hotfix_fetch.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE read_model (id INTEGER PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO read_model(value) VALUES (?)", [("a",), ("b",)])
    conn.commit()
    conn.close()

    rows = db_manager.execute_query(str(db_path), "SELECT value FROM read_model ORDER BY id")

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert all(isinstance(row, dict) for row in rows)
    assert rows[0]["value"] == "a"
    assert rows[1]["value"] == "b"
