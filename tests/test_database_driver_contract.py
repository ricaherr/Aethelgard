"""TDD coverage for HU 8.2 persistence driver contract."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from data_vault.base_repo import BaseRepository
from data_vault.database_manager import get_database_manager
from data_vault.drivers import SQLiteDriver
from data_vault.drivers.errors import (
    PersistenceIntegrityError,
    PersistenceOperationalError,
    PersistenceTransactionError,
)
from data_vault.storage import StorageManager


@pytest.fixture
def sqlite_driver() -> SQLiteDriver:
    """Create a SQLite driver backed by the shared DatabaseManager."""
    return SQLiteDriver(get_database_manager())


def test_driver_contract_execute_and_fetch_sqlite(sqlite_driver: SQLiteDriver, tmp_path: Path) -> None:
    """Driver should execute writes and read back rows via fetch APIs."""
    db_path = str(tmp_path / "driver_contract_execute.db")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

    sqlite_driver.execute(db_path, "INSERT INTO demo (name) VALUES (?)", ("alpha",))

    one_row = sqlite_driver.fetch_one(db_path, "SELECT id, name FROM demo WHERE name = ?", ("alpha",))
    all_rows = sqlite_driver.fetch_all(db_path, "SELECT id, name FROM demo")

    assert one_row is not None
    assert one_row["name"] == "alpha"
    assert len(all_rows) == 1


def test_driver_transaction_commit_and_rollback(sqlite_driver: SQLiteDriver, tmp_path: Path) -> None:
    """Transaction context should commit on success and rollback on failure."""
    db_path = str(tmp_path / "driver_contract_tx.db")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE tx_demo (id INTEGER PRIMARY KEY, label TEXT NOT NULL)")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("INSERT INTO tx_demo (label) VALUES ('committed')")

    with pytest.raises(PersistenceTransactionError):
        with sqlite_driver.transaction(db_path) as conn:
            conn.execute("INSERT INTO tx_demo (label) VALUES ('rolled_back')")
            raise RuntimeError("force rollback")

    rows = sqlite_driver.fetch_all(db_path, "SELECT label FROM tx_demo ORDER BY id")
    assert [row["label"] for row in rows] == ["committed"]


def test_storage_manager_uses_driver_for_bootstrap_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """StorageManager bootstrap should go through BaseRepository.transaction()."""
    db_path = str(tmp_path / "storage_bootstrap.db")
    call_counter = {"count": 0}
    original_transaction = BaseRepository.transaction

    @contextmanager
    def tracked_transaction(self: BaseRepository):
        call_counter["count"] += 1
        with original_transaction(self) as conn:
            yield conn

    monkeypatch.setattr(BaseRepository, "transaction", tracked_transaction)

    storage = StorageManager(db_path=db_path)

    assert storage.db_path == db_path
    assert call_counter["count"] >= 1


def test_persistence_error_normalization(sqlite_driver: SQLiteDriver, tmp_path: Path) -> None:
    """SQLite backend errors should map to persistence domain errors."""
    db_path = str(tmp_path / "driver_contract_errors.db")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE err_demo (id INTEGER PRIMARY KEY, code TEXT UNIQUE)")

    sqlite_driver.execute(db_path, "INSERT INTO err_demo (code) VALUES (?)", ("X1",))

    with pytest.raises(PersistenceIntegrityError):
        sqlite_driver.execute(db_path, "INSERT INTO err_demo (code) VALUES (?)", ("X1",))

    with pytest.raises(PersistenceOperationalError):
        sqlite_driver.fetch_all(db_path, "SELECT * FROM table_does_not_exist")


def test_base_repo_backward_compatibility_wrappers(tmp_path: Path) -> None:
    """Legacy wrappers should keep working while using the new driver path."""
    db_path = str(tmp_path / "base_repo_compat.db")
    repo = BaseRepository(db_path=db_path)

    conn = repo._get_conn()
    repo._close_conn(conn)

    repo.execute_update("CREATE TABLE compat_demo (id INTEGER PRIMARY KEY, value TEXT)")
    inserted = repo.execute_update("INSERT INTO compat_demo (value) VALUES (?)", ("ok",))
    rows = repo.execute_query("SELECT value FROM compat_demo")

    assert isinstance(inserted, int)
    assert rows[0]["value"] == "ok"


def test_driver_bulk_execute_many(sqlite_driver: SQLiteDriver, tmp_path: Path) -> None:
    """Driver execute_many should persist all rows in one batch transaction."""
    db_path = str(tmp_path / "driver_contract_bulk.db")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE bulk_demo (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")

    written = sqlite_driver.execute_many(
        db_path,
        "INSERT INTO bulk_demo (payload) VALUES (?)",
        [("a",), ("b",), ("c",)],
    )

    rows = sqlite_driver.fetch_all(db_path, "SELECT payload FROM bulk_demo ORDER BY id")
    assert written >= 3
    assert [row["payload"] for row in rows] == ["a", "b", "c"]


def test_driver_execute_accepts_write_mode_keyword(sqlite_driver: SQLiteDriver, tmp_path: Path) -> None:
    """HU 8.3: driver API should accept write_mode without breaking legacy behavior."""
    db_path = str(tmp_path / "driver_contract_write_mode.db")

    with sqlite_driver.transaction(db_path) as conn:
        conn.execute("CREATE TABLE mode_demo (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")

    inserted = sqlite_driver.execute(
        db_path,
        "INSERT INTO mode_demo (payload) VALUES (?)",
        ("critical",),
        write_mode="critical",
    )

    row = sqlite_driver.fetch_one(db_path, "SELECT payload FROM mode_demo WHERE id = ?", (inserted,))
    assert row is not None
    assert row["payload"] == "critical"
