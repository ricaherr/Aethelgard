"""
Test Suite: FASE D - Trade Results Migration & Execution Normalization
========================================================================

Tests for:
1. Schema migration: trade_results → usr_trades
2. Retrocompatibility: existing usr_trades maintain LIVE/MT5/REAL defaults
3. New fields persistence: execution_mode, provider, account_type
4. Query filtering: get_usr_trades() with execution_mode parameter
5. Default behavior: metrics (get_win_rate, etc.) default to LIVE usr_trades
6. SHADOW usr_trades: StrategyRanker can explicitly query SHADOW mode

Principle: No test modification for failures (SSOT = code corrects bugs).
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
from models.signal import Signal, ConnectorType
from models.execution_mode import ExecutionMode, Provider, AccountType


@pytest.fixture
def test_db():
    """Create in-memory test database with schema."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    run_migrations(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def test_trade_id():
    """Generate dynamic test trade ID to avoid hardcoding."""
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def test_signal_id():
    """Generate dynamic test signal ID to avoid hardcoding."""
    return f"SIG-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def storage(test_db):
    """Create StorageManager backed by the pre-initialized test_db connection."""
    storage_instance = StorageManager(db_path=':memory:')
    # Redirect the persistent connection to the schema-initialised test_db
    storage_instance._persistent_conn = test_db
    yield storage_instance


class TestSchemaMigration:
    """Test schema migration from trade_results to usr_trades."""
    
    def test_usr_trades_table_exists(self, test_db):
        """Verify usr_trades table exists after schema init."""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usr_trades'")
        assert cursor.fetchone() is not None, "usr_trades table does not exist"
    
    def test_usr_trades_has_execution_mode_column(self, test_db, test_trade_id):
        """Verify execution_mode column exists with default from ExecutionMode enum."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(usr_trades)")
        cols = {row[1]: row for row in cursor.fetchall()}
        assert 'execution_mode' in cols, "execution_mode column missing"
        # Check default
        cursor.execute("""
            INSERT INTO usr_trades (id, symbol) VALUES (?, ?)
        """, (test_trade_id, 'EURUSD'))
        test_db.commit()
        cursor.execute("SELECT execution_mode FROM usr_trades WHERE id=?", (test_trade_id,))
        result = cursor.fetchone()
        assert result[0] == ExecutionMode.LIVE.value, f"Default execution_mode is not {ExecutionMode.LIVE.value}, got {result[0]}"
    
    def test_usr_trades_has_provider_column(self, test_db, test_trade_id):
        """Verify provider column exists with default from Provider enum."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(usr_trades)")
        cols = {row[1]: row for row in cursor.fetchall()}
        assert 'provider' in cols, "provider column missing"
        # Check default
        cursor.execute("""
            INSERT INTO usr_trades (id, symbol) VALUES (?, ?)
        """, (test_trade_id, 'GBPUSD'))
        test_db.commit()
        cursor.execute("SELECT provider FROM usr_trades WHERE id=?", (test_trade_id,))
        result = cursor.fetchone()
        assert result[0] == Provider.MT5.value, f"Default provider is not {Provider.MT5.value}, got {result[0]}"
    
    def test_usr_trades_has_account_type_column(self, test_db, test_trade_id):
        """Verify account_type column exists with default from AccountType enum."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(usr_trades)")
        cols = {row[1]: row for row in cursor.fetchall()}
        assert 'account_type' in cols, "account_type column missing"
        # Check default
        cursor.execute("""
            INSERT INTO usr_trades (id, symbol) VALUES (?, ?)
        """, (test_trade_id, 'USDJPY'))
        test_db.commit()
        cursor.execute("SELECT account_type FROM usr_trades WHERE id=?", (test_trade_id,))
        result = cursor.fetchone()
        assert result[0] == AccountType.REAL.value, f"Default account_type is not {AccountType.REAL.value}, got {result[0]}"
    
    def test_usr_trades_maintains_foreign_key_signal_id(self, test_db, test_trade_id, test_signal_id):
        """Verify FK constraint between usr_trades.signal_id and sys_signals.id."""
        cursor = test_db.cursor()
        # Create a signal first
        cursor.execute("""
            INSERT INTO sys_signals (id, symbol, signal_type) 
            VALUES (?, ?, ?)
        """, (test_signal_id, 'EURUSD', 'BUY'))
        # Create a trade linked to the signal
        cursor.execute("""
            INSERT INTO usr_trades (id, signal_id, symbol, entry_price, exit_price, profit)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (test_trade_id, test_signal_id, 'EURUSD', 1.08, 1.09, 100))
        test_db.commit()
        # Verify the trade was inserted
        cursor.execute("SELECT signal_id FROM usr_trades WHERE id=?", (test_trade_id,))
        result = cursor.fetchone()
        assert result[0] == test_signal_id, "FK relationship broken"


class TestTradeResultPersistence:
    """Test that usr_trades are saved with execution_mode, provider, account_type."""
    
    def test_save_trade_result_with_new_fields(self, storage, test_trade_id, test_signal_id):
        """Test save_trade_result includes execution_mode, provider, account_type."""
        trade_data = {
            'id': test_trade_id,
            'signal_id': test_signal_id,
            'symbol': 'EURUSD',
            'entry_price': 1.08,
            'exit_price': 1.09,
            'profit': 100,
            'exit_reason': 'take_profit_hit',
            'close_time': datetime.now(timezone.utc).isoformat(),
            'execution_mode': ExecutionMode.SHADOW.value,
            'provider': Provider.INTERNAL.value,
            'account_type': AccountType.DEMO.value
        }
        
        # Save trade — SHADOW routes to sys_trades (Capa 0), NOT usr_trades (Sprint 22)
        storage.save_trade_result(trade_data)

        # Verify in sys_trades, not usr_trades
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            # sys_trades must have the SHADOW record
            cursor.execute("SELECT * FROM sys_trades WHERE id=?", (test_trade_id,))
            row = cursor.fetchone()
            assert row is not None, "SHADOW trade must be in sys_trades (Capa 0)"
            row = dict(row)
            assert row['execution_mode'] == ExecutionMode.SHADOW.value, "execution_mode not persisted"
            # usr_trades must NOT have the SHADOW record (trigger blocks it)
            cursor.execute("SELECT * FROM usr_trades WHERE id=?", (test_trade_id,))
            assert cursor.fetchone() is None, "SHADOW trade must NOT be in usr_trades"
        finally:
            storage._close_conn(conn)
    
    def test_save_trade_result_backward_compatible(self, storage, test_trade_id, test_signal_id):
        """Test save_trade_result with missing new fields defaults to LIVE/MT5/REAL."""
        trade_data = {
            'id': test_trade_id,
            'signal_id': test_signal_id,
            'symbol': 'GBPUSD',
            'entry_price': 1.35,
            'exit_price': 1.36,
            'profit': 50,
            'exit_reason': 'manual_close',
            'close_time': datetime.now(timezone.utc).isoformat()
            # NOTE: execution_mode, provider, account_type NOT provided
        }
        
        # Save trade (should use defaults)
        storage.save_trade_result(trade_data)
        
        # Retrieve and verify defaults
        conn = storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT execution_mode, provider, account_type FROM usr_trades WHERE id=?", (test_trade_id,))
            row = dict(cursor.fetchone())
            
            assert row['execution_mode'] == ExecutionMode.LIVE.value, f"Default execution_mode not {ExecutionMode.LIVE.value}"
            assert row['provider'] == Provider.MT5.value, f"Default provider not {Provider.MT5.value}"
            assert row['account_type'] == AccountType.REAL.value, f"Default account_type not {AccountType.REAL.value}"
        finally:
            storage._close_conn(conn)


class TestQueryFiltering:
    """Test that queries respect execution_mode filtering."""
    
    def test_get_total_profit_defaults_to_live(self, storage):
        """get_total_profit() should default to LIVE usr_trades only."""
        # Create LIVE trade
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 100,
            'execution_mode': ExecutionMode.LIVE.value
        })
        # Create SHADOW trade
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 50,
            'execution_mode': ExecutionMode.SHADOW.value
        })
        
        # Get total profit (should only count LIVE)
        total = storage.get_total_profit(days=30)
        assert total == 100, f"Expected 100 (LIVE only), got {total}"
    
    def test_get_total_profit_with_shadow_filter(self, storage):
        """get_total_profit(execution_mode='SHADOW') should return only SHADOW usr_trades."""
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 100,
            'execution_mode': ExecutionMode.LIVE.value
        })
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 75,
            'execution_mode': ExecutionMode.SHADOW.value
        })
        
        # Get SHADOW profit
        shadow_total = storage.get_total_profit(days=30, execution_mode=ExecutionMode.SHADOW.value)
        assert shadow_total == 75, f"Expected 75 (SHADOW only), got {shadow_total}"
    
    def test_get_win_rate_defaults_to_live(self, storage):
        """get_win_rate() should default to LIVE usr_trades only."""
        # Create LIVE: 2 wins, 1 loss
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 100, 'execution_mode': ExecutionMode.LIVE.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 50, 'execution_mode': ExecutionMode.LIVE.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -25, 'execution_mode': ExecutionMode.LIVE.value})
        
        # Create SHADOW: 1 win, 2 losses
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 200, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -100, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -50, 'execution_mode': ExecutionMode.SHADOW.value})
        
        # Get LIVE win rate: 2/3 = 0.667
        live_wr = storage.get_win_rate(days=30)
        assert abs(live_wr - 2/3) < 0.01, f"Expected ~0.667 (LIVE), got {live_wr}"
    
    def test_get_win_rate_with_shadow_filter(self, storage):
        """get_win_rate(execution_mode='SHADOW') should return only SHADOW usr_trades."""
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 100, 'execution_mode': ExecutionMode.LIVE.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -25, 'execution_mode': ExecutionMode.LIVE.value})
        
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 200, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -100, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': -50, 'execution_mode': ExecutionMode.SHADOW.value})
        
        # Get SHADOW win rate: 1/3 = 0.333
        shadow_wr = storage.get_win_rate(days=30, execution_mode=ExecutionMode.SHADOW.value)
        assert abs(shadow_wr - 1/3) < 0.01, f"Expected ~0.333 (SHADOW), got {shadow_wr}"
    
    def test_get_usr_trades_public_method_exists(self, storage):
        """Verify get_usr_trades() public method exists for unified query."""
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 100, 'execution_mode': ExecutionMode.LIVE.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 50, 'execution_mode': ExecutionMode.SHADOW.value})
        
        # Test LIVE query
        live_usr_trades = storage.get_usr_trades(execution_mode=ExecutionMode.LIVE.value, limit=10)
        assert len(live_usr_trades) == 1, "Should return 1 LIVE trade"
        
        # Test SHADOW query
        shadow_usr_trades = storage.get_usr_trades(execution_mode=ExecutionMode.SHADOW.value, limit=10)
        assert len(shadow_usr_trades) == 1, "Should return 1 SHADOW trade"


class TestStrategyRankerIntegration:
    """Test StrategyRanker can query SHADOW usr_trades for analysis."""
    
    def test_strategy_ranker_can_query_shadow_usr_trades(self, storage):
        """StrategyRanker must be able to explicitly query SHADOW usr_trades."""
        # Create mixed usr_trades
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 100,
            'execution_mode': ExecutionMode.LIVE.value
        })
        storage.save_trade_result({
            'id': str(uuid.uuid4()),
            'symbol': 'EURUSD',
            'profit': 75,
            'execution_mode': ExecutionMode.SHADOW.value
        })
        
        # StrategyRanker would call:
        shadow_results = storage.get_usr_trades(execution_mode=ExecutionMode.SHADOW.value, limit=100)
        assert len(shadow_results) == 1, "Should find 1 SHADOW trade"
        assert shadow_results[0]['execution_mode'] == ExecutionMode.SHADOW.value
    
    def test_strategy_ranker_promotion_logic(self, storage):
        """Test promotion criteria: SHADOW with good metrics can be promoted to LIVE."""
        # Simulate SHADOW usr_trades for a strategy
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 100, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 120, 'execution_mode': ExecutionMode.SHADOW.value})
        storage.save_trade_result({'id': str(uuid.uuid4()), 'profit': 90, 'execution_mode': ExecutionMode.SHADOW.value})
        
        # Get SHADOW win rate (3/3 = 100%)
        shadow_usr_trades = storage.get_usr_trades(execution_mode=ExecutionMode.SHADOW.value)
        shadow_wr = storage.get_win_rate(execution_mode=ExecutionMode.SHADOW.value)
        
        # Promotion criteria would be: PF > 1.5 && WR > 50% && Trades >= 3
        # In this case: WR = 100% ✓, Trades = 3 ✓
        # PF calculation (needs profit_factor impl in StrategyRanker)
        
        assert len(shadow_usr_trades) >= 3, "Should have at least 3 SHADOW usr_trades"
        assert shadow_wr >= 0.5, "Should have >50% win rate for promotion"


class TestIntegrity:
    """Test data integrity and retrocompatibility with existing usr_trades."""
    
    def test_existing_trade_history_not_contaminated(self, storage):
        """Historical usr_trades (LIVE) should not be contaminated by SHADOW analysis."""
        # Create a mix in order they would be created historically
        old_usr_trades = [
            {'id': str(uuid.uuid4()), 'profit': (i % 2) * 100 - 25, 'symbol': 'EURUSD'}
            for i in range(10)
        ]
        
        for trade in old_usr_trades:
            # These usr_trades have NO execution_mode specified
            storage.save_trade_result(trade)
        
        # They should all default to LIVE
        live_count = len(storage.get_trade_results(limit=100))
        assert live_count == 10, "All historical usr_trades should be LIVE"
        
        # SHADOW search should return nothing
        shadow_usr_trades = storage.get_usr_trades(execution_mode=ExecutionMode.SHADOW.value)
        assert len(shadow_usr_trades) == 0, "Should not contaminate LIVE with SHADOW"
