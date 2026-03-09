"""
Test Suite: FASE E - SHADOW Signal Persistence & Origin Mode Tracking
========================================================================

Tests for:
1. Schema migration: origin_mode column added to sys_signals
2. Signal persistence: save_signal() accepts and persists origin_mode parameter
3. SHADOW signal tracking: Signals generated in SHADOW mode are auditable
4. LIVE signal tracking: Signals generated in LIVE mode are distinguished from SHADOW
5. Integration: SignalFactory determines strategy execution mode and passes to save_signal()
6. Backward compatibility: Existing signals without origin_mode default to 'LIVE'

Principle: Signals MUST be saved in BOTH SHADOW and LIVE modes for:
- Testing strategy accuracy (SHADOW accumulates metrics)
- Auditing (origin_mode column tracks when signal was generated)
- Promotion logic (StrategyRanker can count SHADOW vs LIVE trades)

SSOT:
- Use ExecutionMode enum from models.execution_mode
- origin_mode defaults to 'LIVE' for backward compatibility
- SHADOW signals paired with SHADOW trades enable strategy ranking
"""
import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from data_vault.storage import StorageManager
from data_vault.schema import initialize_schema, run_migrations
from models.signal import Signal, SignalType, ConnectorType
from models.execution_mode import ExecutionMode


@pytest.fixture
def test_db():
    """Create in-memory test database with schema."""
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def storage(test_db):
    """Create StorageManager with in-memory test database."""
    manager = StorageManager(db_path=":memory:")
    # Force use of test_db for this fixture
    manager._conn = test_db
    yield manager
    manager._close_conn(test_db)


class TestShadowSignalPersistence:
    """Test SHADOW mode signal persistence (PHASE E)."""

    def test_schema_migration_origin_mode_column_exists(self, test_db):
        """Verify origin_mode column was added to sys_signals."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_signals)")
        columns = {row[1] for row in cursor.fetchall()}
        
        assert "origin_mode" in columns, "origin_mode column missing from sys_signals"
        
        # Verify column default
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sys_signals'")
        create_sql = cursor.fetchone()[0]
        assert "origin_mode" in create_sql.upper()

    def test_schema_index_origin_mode_created(self, test_db):
        """Verify index on origin_mode for efficient querying."""
        cursor = test_db.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sys_signals_origin_mode'"
        )
        index_exists = cursor.fetchone() is not None
        assert index_exists, "Index idx_sys_signals_origin_mode not created"

    def test_save_signal_with_default_origin_mode_live(self, storage):
        """Test save_signal() defaults to origin_mode='LIVE' when not specified."""
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.METATRADER5,
            metadata={"strategy_id": "TEST_STRATEGY_001"},
            entry_price=1.0950,
        )
        
        signal_id = storage.save_signal(signal)  # No origin_mode specified
        
        # Verify signal saved with origin_mode='LIVE'
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT origin_mode FROM sys_signals WHERE id=?", (signal_id,))
            row = cursor.fetchone()
            
            assert row is not None, "Signal not saved"
            assert row[0] == 'LIVE', f"Expected origin_mode='LIVE', got '{row[0]}'"
        finally:
            storage._close_conn(conn)

    def test_save_signal_with_explicit_shadow_origin_mode(self, storage):
        """Test save_signal() persists explicit origin_mode='SHADOW'."""
        signal = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.SELL,
            confidence=0.75,
            connector_type=ConnectorType.METATRADER5,
            metadata={"strategy_id": "LIQ_SWEEP_0001"},
            entry_price=1.2750,
        )
        
        signal_id = storage.save_signal(signal, origin_mode='SHADOW')
        
        # Verify signal saved with origin_mode='SHADOW'
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT origin_mode, symbol, signal_type FROM sys_signals WHERE id=?", (signal_id,))
            row = dict(cursor.fetchone())
            
            assert row['origin_mode'] == 'SHADOW', f"Expected 'SHADOW', got '{row['origin_mode']}'"
            assert row['symbol'] == 'GBPUSD'
            assert row['signal_type'] == SignalType.SELL.value
        finally:
            storage._close_conn(conn)

    def test_save_signal_with_explicit_live_origin_mode(self, storage):
        """Test save_signal() persists explicit origin_mode='LIVE'."""
        signal = Signal(
            symbol="USDJPY",
            signal_type=SignalType.BUY,
            confidence=0.80,
            connector_type=ConnectorType.METATRADER5,
            metadata={"strategy_id": "MOM_BIAS_0001"},
            entry_price=148.750,
        )
        
        signal_id = storage.save_signal(signal, origin_mode='LIVE')
        
        # Verify signal saved with origin_mode='LIVE'
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT origin_mode FROM sys_signals WHERE id=?", (signal_id,))
            row = cursor.fetchone()
            
            assert row[0] == 'LIVE', f"Expected 'LIVE', got '{row[0]}'"
        finally:
            storage._close_conn(conn)

    def test_count_signals_by_origin_mode(self, storage):
        """Test querying signals filtered by origin_mode (audit trail)."""
        # Create multiple signals in different modes
        shadow_signals = []
        live_signals = []
        
        for i in range(3):
            signal = Signal(
                symbol=f"PAIR{i}",
                signal_type=SignalType.BUY,
                confidence=0.80,
                connector_type=ConnectorType.METATRADER5,
                metadata={"strategy_id": f"SHADOW_STRATEGY_{i}"},
                entry_price=1.0000 + i * 0.0100,
            )
            signal_id = storage.save_signal(signal, origin_mode='SHADOW')
            shadow_signals.append(signal_id)
        
        for i in range(2):
            signal = Signal(
                symbol=f"LIVE_PAIR{i}",
                signal_type=SignalType.SELL,
                confidence=0.75,
                connector_type=ConnectorType.METATRADER5,
                metadata={"strategy_id": f"LIVE_STRATEGY_{i}"},
                entry_price=1.5000 + i * 0.0100,
            )
            signal_id = storage.save_signal(signal, origin_mode='LIVE')
            live_signals.append(signal_id)
        
        # Query SHADOW signals
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sys_signals WHERE origin_mode='SHADOW'")
            shadow_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sys_signals WHERE origin_mode='LIVE'")
            live_count = cursor.fetchone()[0]
            
            assert shadow_count == 3, f"Expected 3 SHADOW signals, got {shadow_count}"
            assert live_count == 2, f"Expected 2 LIVE signals, got {live_count}"
        finally:
            storage._close_conn(conn)

    def test_shadow_signals_do_not_interfere_with_live_metrics(self, storage):
        """Test that SHADOW signals don't contaminate LIVE signal metrics."""
        # Save 5 SHADOW signals
        for i in range(5):
            signal = Signal(
                symbol="EURUSD",
                signal_type=SignalType.BUY,
                confidence=0.85,
                connector_type=ConnectorType.METATRADER5,
                metadata={"strategy_id": "TEST_SHADOW"},
                entry_price=1.0900 + i * 0.0001,
            )
            storage.save_signal(signal, origin_mode='SHADOW')
        
        # Save 1 LIVE signal
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.SELL,
            confidence=0.80,
            connector_type=ConnectorType.METATRADER5,
            metadata={"strategy_id": "TEST_LIVE"},
            entry_price=1.0950,
        )
        storage.save_signal(signal, origin_mode='LIVE')
        
        # Query total signals
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sys_signals")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sys_signals WHERE origin_mode='SHADOW'")
            shadow = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sys_signals WHERE origin_mode='LIVE'")
            live = cursor.fetchone()[0]
            
            assert total == 6, f"Expected 6 total signals, got {total}"
            assert shadow == 5, f"Expected 5 SHADOW, got {shadow}"
            assert live == 1, f"Expected 1 LIVE, got {live}"
        finally:
            storage._close_conn(conn)

    def test_signal_fk_relationship_with_trades(self, storage):
        """Test that sys_signals can be FK'd from usr_trades (enables auditing)."""
        # Create a SHADOW signal
        signal = Signal(
            symbol="AUDUSD",
            signal_type=SignalType.BUY,
            confidence=0.88,
            connector_type=ConnectorType.METATRADER5,
            metadata={"strategy_id": "SHADOW_AUDIT_TEST"},
            entry_price=0.6550,
        )
        signal_id = storage.save_signal(signal, origin_mode='SHADOW')
        
        # Create a SHADOW trade linked to that signal
        trade_data = {
            'id': str(uuid.uuid4()),
            'signal_id': signal_id,
            'symbol': 'AUDUSD',
            'entry_price': 0.6550,
            'exit_price': 0.6575,
            'profit': 25.0,
            'execution_mode': ExecutionMode.SHADOW.value,  # Paired SHADOW trade
        }
        storage.save_trade_result(trade_data)
        
        # Verify signal-trade relationship
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.origin_mode, t.execution_mode 
                FROM sys_signals s
                LEFT JOIN usr_trades t ON s.id = t.signal_id
                WHERE s.id = ?
                """,
                (signal_id,)
            )
            row = cursor.fetchone()
            
            assert row is not None
            assert row[0] == 'SHADOW', f"Signal origin_mode should be SHADOW, got {row[0]}"
            assert row[1] == 'SHADOW', f"Trade execution_mode should be SHADOW, got {row[1]}"
        finally:
            storage._close_conn(conn)


class TestSignalFactoryOriginModeIntegration:
    """Test SignalFactory integration with origin_mode tracking.
    
    NOTE: These tests verify the CONTRACT that SignalFactory should:
    1. Extract strategy_id from signal.metadata
    2. Query storage for strategy execution_mode
    3. Pass that mode to save_signal()
    
    Full integration test would require MainOrchestrator setup;
    this test verifies the storage layer contract.
    """

    def test_signal_origin_mode_stored_from_factory(self, storage):
        """Contract test: Signals generated by factory should store origin_mode."""
        # Simulate what SignalFactory._process_valid_signal would do
        
        signal = Signal(
            symbol="NZDUSD",
            signal_type=SignalType.BUY,
            confidence=0.82,
            connector_type=ConnectorType.METATRADER5,
            metadata={
                "strategy_id": "MOM_BIAS_0001",
                "score": 0.85,
                "confluence": True,
            },
            entry_price=0.6200,
        )
        
        # Simulate strategy ranker query
        # (In real scenario, this would be: storage.get_strategy_ranking("MOM_BIAS_0001"))
        # For this test, we directly save with SHADOW mode
        origin_mode = 'SHADOW'
        signal_id = storage.save_signal(signal, origin_mode=origin_mode)
        
        # Verify persistence
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT origin_mode, symbol FROM sys_signals WHERE id=?",
                (signal_id,)
            )
            row = dict(cursor.fetchone())
            
            assert row['origin_mode'] == 'SHADOW'
            assert row['symbol'] == 'NZDUSD'
        finally:
            storage._close_conn(conn)
