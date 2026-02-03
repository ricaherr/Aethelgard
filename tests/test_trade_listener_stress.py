"""
Trade Closure Listener - Stress Test
====================================

Simulates 10 trade closures happening almost simultaneously to verify:
1. Retry logic doesn't collapse under concurrent DB access
2. Idempotence prevents duplicate processing
3. Metrics are accurate under load
4. No race conditions or data corruption

Test Objectives:
- 10 concurrent trade closure events
- Each event processes in parallel (asyncio)
- Verify all trades persisted correctly
- Verify idempotent protection works (retry same event twice)
- Validate listener metrics under stress
"""
import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from datetime import datetime
import os

from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager
from core_brain.tuner import EdgeTuner
from core_brain.trade_closure_listener import TradeClosureListener
from models.broker_event import BrokerTradeClosedEvent, BrokerEvent, BrokerEventType, TradeResult


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory with necessary files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create minimal config/dynamic_params.json
        config_data = {
            "adx_threshold": 25,
            "atr_multiplier": 0.3,
            "sma20_proximity_pct": 1.5,
            "min_score": 60
        }
        config_file = tmpdir_path / "dynamic_params.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        # Create risk_settings.json
        risk_settings_data = {
            "max_consecutive_losses": 3,
            "min_trades_for_tuning": 5,
            "target_win_rate": 0.55
        }
        risk_file = tmpdir_path / "risk_settings.json"
        with open(risk_file, "w") as f:
            json.dump(risk_settings_data, f)
        
        yield tmpdir_path


@pytest.fixture
def temp_db():
    """Create temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def storage(temp_db):
    """Initialize StorageManager with temp DB."""
    storage = StorageManager(db_path=temp_db)
    # Tables are created automatically in __init__
    return storage


@pytest.fixture
def trade_listener(storage, temp_config_dir):
    """Create TradeClosureListener with all dependencies."""
    risk_manager = RiskManager(
        storage=storage,
        initial_capital=10000.0,
        config_path=str(temp_config_dir / "dynamic_params.json"),
        risk_settings_path=str(temp_config_dir / "risk_settings.json")
    )
    
    edge_tuner = EdgeTuner(
        storage=storage,
        config_path=str(temp_config_dir / "dynamic_params.json")
    )
    
    listener = TradeClosureListener(
        storage=storage,
        risk_manager=risk_manager,
        edge_tuner=edge_tuner,
        max_retries=3,
        retry_backoff=0.1  # Faster for testing
    )
    
    return listener


class TestTradeListenerStress:
    """
    Stress tests for TradeClosureListener.
    
    Verifies resilience and concurrent event handling.
    """
    
    @pytest.mark.asyncio
    async def test_concurrent_10_trades_no_collapse(self, trade_listener):
        """
        STRESS TEST: 10 trades arriving almost simultaneously.
        
        Objective: Verify retry logic handles concurrent DB access
        without collapsing or losing data.
        
        Expected Results:
        - All 10 trades successfully saved to DB
        - Metrics show 10 processed, 10 saved, 0 failed
        - No race conditions or data corruption
        """
        # Create 10 trade events (different symbols to avoid exact duplicates)
        events = []
        now = datetime.now()
        
        for i in range(10):
            is_win_flag = i % 3 != 0  # 7 wins, 3 losses
            trade = BrokerTradeClosedEvent(
                ticket=f"STRESS_{i:02d}_{int(now.timestamp() * 1000)}",
                signal_id=f"sig_{i}",
                symbol=f"SYMBOL_{i % 5}",  # 5 different symbols
                entry_price=100.0 + i,
                exit_price=101.0 + i if is_win_flag else 99.0 + i,
                entry_time=now,
                exit_time=now,
                result=TradeResult.WIN if is_win_flag else TradeResult.LOSS,
                pips=10 if is_win_flag else -10,
                profit_loss=100 if is_win_flag else -50,
                exit_reason="test_market_close",
                broker_id="MT5_DEMO",
                metadata={"test": f"stress_{i}"}
            )
            
            event = BrokerEvent(
                event_type=BrokerEventType.TRADE_CLOSED,
                broker_id="MT5_DEMO",
                timestamp=now,
                data=trade
            )
            events.append(event)
        
        # Process all 10 events concurrently (simulate simultaneous arrival)
        results = await asyncio.gather(
            *[trade_listener.handle_trade_closed_event(event) for event in events],
            return_exceptions=True
        )
        
        # Verify all succeeded
        successful = sum(1 for r in results if r is True)
        assert successful == 10, f"Expected 10 successful, got {successful}"
        
        # Verify metrics
        metrics = trade_listener.get_metrics()
        assert metrics["trades_processed"] == 10
        assert metrics["trades_saved"] == 10
        assert metrics["trades_failed"] == 0
        assert metrics["success_rate"] == 100.0
        
        # Verify DB contains all 10 (use public method, not direct SQL)
        all_trades = trade_listener.storage.get_trade_results(limit=100)
        count = len(all_trades)
        assert count == 10, f"Expected 10 trades in DB, found {count}"
        
        print(f"[OK] [STRESS] 10 concurrent trades processed successfully")
        print(f"   Metrics: {metrics}")
    
    @pytest.mark.asyncio
    async def test_idempotent_retry_same_trade_twice(self, trade_listener):
        """
        IDEMPOTENCE STRESS: Send the same trade twice.
        
        Objective: Verify idempotence mechanism prevents duplicate processing.
        
        Expected Results:
        - First event: processed normally (saved)
        - Second event (same ticket): rejected by idempotent check
        - DB contains only 1 copy of the trade
        - Metrics show 2 processed, 1 saved (idempotent intercepted the duplicate)
        """
        now = datetime.now()
        
        # Create a single trade
        trade = BrokerTradeClosedEvent(
            ticket="IDEMPOTENT_TEST_001",
            signal_id="sig_idem",
            symbol="EURUSD",
            entry_price=1.1000,
            exit_price=1.1050,
            entry_time=now,
            exit_time=now,
            result=TradeResult.WIN,
            pips=50,
            profit_loss=100,
            exit_reason="tp_hit",
            broker_id="MT5_DEMO",
            metadata={"test": "idempotent"}
        )
        
        event = BrokerEvent(
            event_type=BrokerEventType.TRADE_CLOSED,
            broker_id="MT5_DEMO",
            timestamp=now,
            data=trade
        )
        
        # Process the event twice (simulating duplicate delivery or retry)
        result1 = await trade_listener.handle_trade_closed_event(event)
        result2 = await trade_listener.handle_trade_closed_event(event)
        
        # Both should return True (first processes, second is idempotent)
        assert result1 is True, "First event should succeed"
        assert result2 is True, "Second event should be idempotent-rejected but return True"
        
        # Verify DB contains only 1 copy (use public method)
        exists = trade_listener.storage.trade_exists("IDEMPOTENT_TEST_001")
        assert exists, "Trade should exist in DB"
        
        all_trades = trade_listener.storage.get_trade_results(limit=100)
        count = len([t for t in all_trades if t.get('id') == 'IDEMPOTENT_TEST_001'])
        assert count == 1, f"Expected 1 trade in DB, found {count}"
        
        # Verify metrics: 2 processed, 1 saved (not 2!)
        metrics = trade_listener.get_metrics()
        assert metrics["trades_processed"] == 2
        assert metrics["trades_saved"] == 1, "Idempotent should prevent duplicate save"
        
        print(f"[OK] [IDEMPOTENT] Duplicate trade rejected, DB integrity maintained")
        print(f"   Metrics: {metrics}")
    
    @pytest.mark.asyncio
    async def test_stress_with_concurrent_db_writes(self, trade_listener):
        """
        LOCK RESILIENCE: Test concurrent DB writes without collapse.
        
        Objective: Verify all 10 trades are saved even under concurrent load.
        
        Expected Results:
        - Retry logic handles concurrent access
        - All trades eventually saved
        - No data loss or corruption
        """
        now = datetime.now()
        events = []
        
        for i in range(10):
            trade = BrokerTradeClosedEvent(
                ticket=f"LOCK_TEST_{i:02d}",
                signal_id=f"sig_lock_{i}",
                symbol="GBPUSD",
                entry_price=1.2500,
                exit_price=1.2550,
                entry_time=now,
                exit_time=now,
                result=TradeResult.WIN,
                pips=50,
                profit_loss=100,
                exit_reason="profit_target",
                broker_id="MT5_DEMO"
            )
            
            event = BrokerEvent(
                event_type=BrokerEventType.TRADE_CLOSED,
                broker_id="MT5_DEMO",
                timestamp=now,
                data=trade
            )
            events.append(event)
        
        # Process all concurrently (stress DB with concurrent writes)
        results = await asyncio.gather(
            *[trade_listener.handle_trade_closed_event(event) for event in events],
            return_exceptions=True
        )
        
        # Verify no exceptions and all succeeded
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Event {i} raised exception: {result}")
            assert result is True
        
        # Verify all saved
        metrics = trade_listener.get_metrics()
        assert metrics["trades_saved"] == 10
        assert metrics["trades_failed"] == 0
        
        print(f"[OK] [CONCURRENT] 10 concurrent writes without collapse")
        print(f"   Metrics: {metrics}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
