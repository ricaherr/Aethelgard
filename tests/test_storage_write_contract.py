"""
HU 8.5: Tests TDD — StorageManager write methods use driver contract.

Verifies that save_coherence_event, update_user_config,
append_to_system_ledger and save_economic_event persist correctly
through the BaseRepository.transaction() contract.
"""
import json
import sqlite3
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from data_vault.storage import StorageManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_storage(db_conn: sqlite3.Connection) -> StorageManager:
    """Return a StorageManager instance backed by an in-memory SQLite DB."""

    @contextmanager
    def _fake_transaction(db_path: str):  # type: ignore[return]
        yield db_conn

    mock_driver = MagicMock()
    mock_driver.transaction.side_effect = _fake_transaction

    storage = StorageManager.__new__(StorageManager)
    storage.db_driver = mock_driver
    storage.db_path = ":memory:"
    storage._get_conn = lambda: db_conn  # type: ignore[assignment]
    storage._close_conn = lambda c: None  # type: ignore[assignment]
    return storage


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    """In-memory SQLite connection with minimal schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE usr_coherence_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id        TEXT,
            symbol           TEXT NOT NULL,
            timeframe        TEXT,
            strategy         TEXT,
            stage            TEXT,
            status           TEXT,
            incoherence_type TEXT,
            reason           TEXT,
            details          TEXT,
            connector_type   TEXT,
            timestamp        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE sys_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    return conn


@pytest.fixture()
def storage(mem_conn: sqlite3.Connection) -> StorageManager:
    return _make_storage(mem_conn)


# ---------------------------------------------------------------------------
# Tests — save_coherence_event
# ---------------------------------------------------------------------------

class TestSaveCoherenceEvent:
    def test_persists_full_event(self, storage: StorageManager, mem_conn: sqlite3.Connection) -> None:
        event = {
            "signal_id": "sig-abc",
            "symbol": "EURUSD",
            "timeframe": "H4",
            "strategy": "ema_cross",
            "stage": "ENTRY",
            "status": "INCOHERENT",
            "incoherence_type": "SPREAD_SPIKE",
            "reason": "Spread exceeded threshold",
            "details": None,
            "connector_type": "MT5",
        }
        storage.save_coherence_event(event)

        row = mem_conn.execute(
            "SELECT * FROM usr_coherence_events WHERE signal_id = 'sig-abc'"
        ).fetchone()
        assert row is not None
        assert row["symbol"] == "EURUSD"
        assert row["status"] == "INCOHERENT"

    def test_persists_minimal_event(self, storage: StorageManager, mem_conn: sqlite3.Connection) -> None:
        event = {
            "symbol": "USDJPY",
            "stage": "EXIT",
            "status": "OK",
            "reason": "Normal exit",
        }
        storage.save_coherence_event(event)

        row = mem_conn.execute(
            "SELECT symbol, status FROM usr_coherence_events WHERE symbol = 'USDJPY'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "OK"


# ---------------------------------------------------------------------------
# Tests — update_user_config
# ---------------------------------------------------------------------------

class TestUpdateUserConfig:
    @pytest.mark.asyncio
    async def test_creates_config_for_new_user(
        self, storage: StorageManager, mem_conn: sqlite3.Connection
    ) -> None:
        await storage.update_user_config("user-1", {"theme": "dark"})

        row = mem_conn.execute(
            "SELECT value FROM sys_config WHERE key = 'user:user-1:config'"
        ).fetchone()
        assert row is not None
        cfg = json.loads(row["value"])
        assert cfg["theme"] == "dark"

    @pytest.mark.asyncio
    async def test_merges_updates_into_existing_config(
        self, storage: StorageManager, mem_conn: sqlite3.Connection
    ) -> None:
        await storage.update_user_config("user-2", {"theme": "light"})
        await storage.update_user_config("user-2", {"language": "es"})

        row = mem_conn.execute(
            "SELECT value FROM sys_config WHERE key = 'user:user-2:config'"
        ).fetchone()
        cfg = json.loads(row["value"])
        assert cfg["theme"] == "light"
        assert cfg["language"] == "es"


# ---------------------------------------------------------------------------
# Tests — append_to_system_ledger
# ---------------------------------------------------------------------------

class TestAppendToSystemLedger:
    @pytest.mark.asyncio
    async def test_creates_ledger_with_first_entry(
        self, storage: StorageManager, mem_conn: sqlite3.Connection
    ) -> None:
        entry = {"event_type": "EPIC_ARCHIVED", "epic_id": "E15"}
        await storage.append_to_system_ledger(entry)

        row = mem_conn.execute(
            "SELECT value FROM sys_config WHERE key = 'system_ledger'"
        ).fetchone()
        assert row is not None
        ledger = json.loads(row["value"])
        assert len(ledger) == 1
        assert ledger[0]["epic_id"] == "E15"

    @pytest.mark.asyncio
    async def test_appends_to_existing_ledger(
        self, storage: StorageManager, mem_conn: sqlite3.Connection
    ) -> None:
        await storage.append_to_system_ledger({"event_type": "A"})
        await storage.append_to_system_ledger({"event_type": "B"})

        row = mem_conn.execute(
            "SELECT value FROM sys_config WHERE key = 'system_ledger'"
        ).fetchone()
        ledger = json.loads(row["value"])
        assert len(ledger) == 2
        assert ledger[1]["event_type"] == "B"


# ---------------------------------------------------------------------------
# Tests — save_economic_event
# ---------------------------------------------------------------------------

class TestSaveEconomicEvent:
    @pytest.fixture()
    def storage_with_calendar(self, mem_conn: sqlite3.Connection) -> StorageManager:
        """Storage backed by a connection that also has economic_calendar table."""
        mem_conn.execute("""
            CREATE TABLE IF NOT EXISTS economic_calendar (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id      TEXT UNIQUE NOT NULL,
                provider_source TEXT NOT NULL,
                event_name    TEXT NOT NULL,
                country       TEXT NOT NULL,
                currency      TEXT,
                impact_score  TEXT,
                forecast      REAL,
                actual        REAL,
                previous      REAL,
                event_time_utc TEXT NOT NULL,
                is_verified   BOOLEAN DEFAULT 0,
                data_version  INTEGER DEFAULT 1,
                created_at    TEXT NOT NULL
            )
        """)
        mem_conn.commit()
        return _make_storage(mem_conn)

    def test_persists_economic_event(
        self, storage_with_calendar: StorageManager, mem_conn: sqlite3.Connection
    ) -> None:
        event = {
            "event_id": "evt-uuid-001",
            "provider_source": "FOREXFACTORY",
            "event_name": "Non-Farm Payrolls",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
            "forecast": 200000.0,
            "actual": 215000.0,
            "previous": 198000.0,
            "event_time_utc": "2026-04-07T12:30:00",
            "is_verified": True,
            "data_version": 1,
            "created_at": "2026-04-07T12:00:00",
        }
        returned_id = storage_with_calendar.save_economic_event(event)

        assert returned_id == "evt-uuid-001"
        row = mem_conn.execute(
            "SELECT event_name, impact_score FROM economic_calendar WHERE event_id = 'evt-uuid-001'"
        ).fetchone()
        assert row is not None
        assert row["event_name"] == "Non-Farm Payrolls"
        assert row["impact_score"] == "HIGH"

    def test_raises_persistence_error_on_duplicate(
        self, storage_with_calendar: StorageManager
    ) -> None:
        from core_brain.news_errors import PersistenceError

        event = {
            "event_id": "evt-dup",
            "provider_source": "BLOOMBERG",
            "event_name": "CPI",
            "country": "USA",
            "currency": "USD",
            "impact_score": "MED",
            "event_time_utc": "2026-04-07T14:00:00",
            "created_at": "2026-04-07T13:00:00",
        }
        storage_with_calendar.save_economic_event(event)

        with pytest.raises(PersistenceError):
            storage_with_calendar.save_economic_event(event)  # Duplicate event_id
