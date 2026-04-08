"""
HU 8.5: Tests TDD — MarketMixin write methods use driver contract.

Verifies that log_sys_market_pulse, log_coherence_event,
_clear_ghost_position_inline, log_market_cache and seed_initial_assets
persist correctly through the BaseRepository.transaction() contract.
"""
import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from data_vault.market_db import MarketMixin


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_market_mixin() -> MarketMixin:
    """Build a MarketMixin backed by an in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create minimal schema required by the methods under test
    conn.executescript("""
        CREATE TABLE sys_market_pulse (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            data      TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

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

        CREATE TABLE sys_signals (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol   TEXT NOT NULL,
            status   TEXT,
            metadata TEXT
        );

        CREATE TABLE usr_trades (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT
        );

        CREATE TABLE usr_assets_cfg (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol            TEXT UNIQUE NOT NULL,
            asset_class       TEXT,
            tick_size         REAL,
            lot_step          REAL,
            contract_size     REAL,
            currency          TEXT,
            golden_hour_start TEXT,
            golden_hour_end   TEXT
        );
    """)
    conn.commit()

    mixin = MarketMixin.__new__(MarketMixin)
    # Inject a mock db_driver whose transaction() returns our real in-memory conn
    from contextlib import contextmanager

    @contextmanager
    def _fake_transaction(db_path: str):
        yield conn

    mock_driver = MagicMock()
    mock_driver.transaction.side_effect = _fake_transaction
    mixin.db_driver = mock_driver
    mixin.db_path = ":memory:"
    # Keep legacy _get_conn / _close_conn working for read-only helper methods
    mixin._get_conn = lambda: conn  # type: ignore[assignment]
    mixin._close_conn = lambda c: None  # type: ignore[assignment]
    return mixin


# ---------------------------------------------------------------------------
# Tests — log_sys_market_pulse
# ---------------------------------------------------------------------------

class TestLogSysMarketPulse:
    def test_persists_market_state(self) -> None:
        mixin = _make_market_mixin()
        mixin.log_sys_market_pulse({"symbol": "EURUSD", "regime": "TREND"})

        conn = mixin._get_conn()
        row = conn.execute(
            "SELECT symbol, data FROM sys_market_pulse WHERE symbol = 'EURUSD'"
        ).fetchone()
        assert row is not None
        assert row["symbol"] == "EURUSD"
        payload = json.loads(row["data"])
        assert payload["regime"] == "TREND"

    def test_persists_multiple_entries(self) -> None:
        mixin = _make_market_mixin()
        mixin.log_sys_market_pulse({"symbol": "GBPUSD", "regime": "RANGE"})
        mixin.log_sys_market_pulse({"symbol": "GBPUSD", "regime": "VOLATILE"})

        conn = mixin._get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM sys_market_pulse WHERE symbol = 'GBPUSD'"
        ).fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# Tests — log_coherence_event
# ---------------------------------------------------------------------------

class TestLogCoherenceEvent:
    def test_persists_coherence_event(self) -> None:
        mixin = _make_market_mixin()
        mixin.log_coherence_event(
            signal_id="sig-001",
            symbol="EURUSD",
            timeframe="H1",
            strategy="ema_cross",
            stage="ENTRY",
            status="INCOHERENT",
            incoherence_type="PRICE_DIRECTION_MISMATCH",
            reason="Direction mismatch detected",
            details=None,
            connector_type="MT5",
        )

        conn = mixin._get_conn()
        row = conn.execute(
            "SELECT * FROM usr_coherence_events WHERE signal_id = 'sig-001'"
        ).fetchone()
        assert row is not None
        assert row["symbol"] == "EURUSD"
        assert row["status"] == "INCOHERENT"

    def test_persists_without_optional_fields(self) -> None:
        mixin = _make_market_mixin()
        mixin.log_coherence_event(
            signal_id=None,
            symbol="USDJPY",
            timeframe=None,
            strategy=None,
            stage="PRE_ENTRY",
            status="OK",
            incoherence_type=None,
            reason="No issues",
            details=None,
            connector_type=None,
        )

        conn = mixin._get_conn()
        row = conn.execute(
            "SELECT * FROM usr_coherence_events WHERE symbol = 'USDJPY'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "OK"


# ---------------------------------------------------------------------------
# Tests — _clear_ghost_position_inline
# ---------------------------------------------------------------------------

class TestClearGhostPositionInline:
    def test_closes_orphaned_executed_signal(self) -> None:
        mixin = _make_market_mixin()
        conn = mixin._get_conn()
        # Insert EXECUTED signal with no matching trade
        conn.execute(
            "INSERT INTO sys_signals (symbol, status, metadata) VALUES ('EURUSD', 'EXECUTED', '{}')"
        )
        conn.commit()

        mixin._clear_ghost_position_inline("EURUSD")

        row = conn.execute(
            "SELECT status FROM sys_signals WHERE symbol = 'EURUSD'"
        ).fetchone()
        assert row["status"] == "CLOSED"

    def test_does_not_close_signal_with_trade(self) -> None:
        mixin = _make_market_mixin()
        conn = mixin._get_conn()
        conn.execute(
            "INSERT INTO sys_signals (id, symbol, status, metadata) VALUES (42, 'GBPUSD', 'EXECUTED', '{}')"
        )
        conn.execute(
            "INSERT INTO usr_trades (signal_id) VALUES (42)"
        )
        conn.commit()

        mixin._clear_ghost_position_inline("GBPUSD")

        row = conn.execute(
            "SELECT status FROM sys_signals WHERE symbol = 'GBPUSD'"
        ).fetchone()
        assert row["status"] == "EXECUTED"


# ---------------------------------------------------------------------------
# Tests — log_market_cache
# ---------------------------------------------------------------------------

class TestLogMarketCache:
    def test_persists_cache_entry(self) -> None:
        mixin = _make_market_mixin()
        records = [{"open": 1.1, "close": 1.2, "high": 1.3, "low": 1.0}]
        mixin.log_market_cache("DXY", data=records)

        conn = mixin._get_conn()
        row = conn.execute(
            "SELECT data FROM sys_market_pulse WHERE symbol = 'DXY' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        payload = json.loads(row["data"])
        assert payload["record_count"] == 1

    def test_cleanup_keeps_latest_n_records(self) -> None:
        mixin = _make_market_mixin()
        # Insert more than limit_records to trigger cleanup
        for i in range(5):
            mixin.log_market_cache("DXY", data=[{"tick": i}], limit_records=3)

        conn = mixin._get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM sys_market_pulse WHERE symbol = 'DXY'"
        ).fetchone()[0]
        assert count <= 3


# ---------------------------------------------------------------------------
# Tests — seed_initial_assets
# ---------------------------------------------------------------------------

class TestSeedInitialAssets:
    def test_seeds_five_initial_assets(self) -> None:
        mixin = _make_market_mixin()
        mixin.seed_initial_assets()

        conn = mixin._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM usr_assets_cfg").fetchone()[0]
        assert count == 5

    def test_idempotent_on_second_call(self) -> None:
        mixin = _make_market_mixin()
        mixin.seed_initial_assets()
        mixin.seed_initial_assets()  # Should not insert duplicates

        conn = mixin._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM usr_assets_cfg").fetchone()[0]
        assert count == 5
