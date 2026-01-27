"""
Test Orchestrator Recovery - Aethelgard Trading System
======================================================

Tests resilient recovery capabilities of MainOrchestrator.

Validates that:
1. SessionStats reconstructs from DB after restart
2. Executed signals from today are not forgotten
3. System can recover from crashes gracefully
4. Adaptive heartbeat responds to active signals

Based on Gemini's audit recommendation for resilience testing.
"""
import asyncio
import pytest
from datetime import date, datetime
from pathlib import Path
import json
import tempfile
import os

from core_brain.main_orchestrator import MainOrchestrator, SessionStats
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, MarketRegime, ConnectorType


# Mock components for testing
class MockScanner:
    """Mock scanner that returns controlled results"""
    
    def __init__(self, regime: MarketRegime = MarketRegime.TREND):
        self.regime = regime
        self.call_count = 0
    
    async def scan_all_symbols(self):
        self.call_count += 1
        return {
            "EURUSD": {
                "regime": self.regime,
                "score": 0.8,
                "volatility": 0.015
            }
        }


class MockSignalFactory:
    """Mock signal factory that generates test signals"""
    
    def __init__(self, should_generate: bool = True):
        self.should_generate = should_generate
    
    async def process_scan_results(self, scan_results):
        if not self.should_generate:
            return []
        
        return [
            Signal(
                symbol="EURUSD",
                signal_type="BUY",
                confidence=0.85,
                connector_type=ConnectorType.GENERIC,
                entry_price=1.1000,
                stop_loss=1.0950,
                take_profit=1.1100,
                timestamp=datetime.now(),
                metadata={"regime": MarketRegime.TREND.value}
            )
        ]


class MockRiskManager:
    """Mock risk manager"""
    
    def __init__(self, lockdown: bool = False):
        self.lockdown = lockdown
        self.consecutive_losses = 0
    
    def is_lockdown_active(self):
        return self.lockdown


class MockExecutor:
    """Mock executor that simulates successful execution"""
    
    def __init__(self, success: bool = True):
        self.success = success
        self.executed_signals = []
    
    async def execute_signal(self, signal):
        self.executed_signals.append(signal)
        await asyncio.sleep(0.01)  # Simulate async work
        return self.success


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
        # Initialize with proper structure
        initial_data = {
            "signals": [],
            "system_state": {}
        }
        json.dump(initial_data, f)
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def storage(temp_db):
    """Create StorageManager with temp database"""
    return StorageManager(db_path=temp_db)


def test_session_stats_fresh_start(storage):
    """Test SessionStats initialization with no prior data"""
    stats = SessionStats.from_storage(storage)
    
    assert stats.date == date.today()
    assert stats.signals_processed == 0
    assert stats.signals_executed == 0
    assert stats.cycles_completed == 0
    assert stats.errors_count == 0


def test_session_stats_reconstruction_from_db(storage):
    """
    CRITICAL TEST: Verify SessionStats reconstructs from DB.
    
    This ensures trades executed today are not forgotten after restart.
    """
    # Simulate signals executed earlier today
    today = date.today()
    
    # Create mock signals
    signal1 = Signal(
        symbol="EURUSD",
        signal_type="BUY",
        confidence=0.85,
        connector_type=ConnectorType.GENERIC,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        timestamp=datetime.now(),
        metadata={"regime": MarketRegime.TREND.value}
    )
    
    signal2 = Signal(
        symbol="GBPUSD",
        signal_type="SELL",
        confidence=0.80,
        connector_type=ConnectorType.GENERIC,
        entry_price=1.3000,
        stop_loss=1.3050,
        take_profit=1.2900,
        timestamp=datetime.now(),
        metadata={"regime": MarketRegime.TREND.value}
    )
    
    # Persist signals
    storage.save_signal(signal1)
    storage.save_signal(signal2)
    
    # Also persist session stats
    session_data = {
        "date": today.isoformat(),
        "signals_processed": 5,
        "signals_executed": 2,
        "cycles_completed": 3,
        "errors_count": 0
    }
    storage.update_system_state({"session_stats": session_data})
    
    # RESTART SIMULATION: Create new SessionStats from storage
    recovered_stats = SessionStats.from_storage(storage)
    
    # Verify recovery
    assert recovered_stats.date == today
    assert recovered_stats.signals_executed == 2  # From DB count
    assert recovered_stats.signals_processed == 5
    assert recovered_stats.cycles_completed == 3
    assert recovered_stats.errors_count == 0


def test_session_stats_reconstruction_old_data(storage):
    """Test that old session data is ignored for new day"""
    from datetime import timedelta
    
    yesterday = date.today() - timedelta(days=1)
    
    # Store old session data
    old_session_data = {
        "date": yesterday.isoformat(),
        "signals_processed": 10,
        "signals_executed": 5,
        "cycles_completed": 8,
        "errors_count": 2
    }
    storage.update_system_state({"session_stats": old_session_data})
    
    # Reconstruct stats
    stats = SessionStats.from_storage(storage)
    
    # Should start fresh for today
    assert stats.date == date.today()
    assert stats.signals_processed == 0
    assert stats.cycles_completed == 0


@pytest.mark.asyncio
async def test_orchestrator_persistence_after_execution(storage):
    """
    Test that orchestrator persists signals immediately after execution.
    
    This ensures no data loss if system crashes after trade execution.
    """
    # Setup mocks
    scanner = MockScanner()
    signal_factory = MockSignalFactory(should_generate=True)
    risk_manager = MockRiskManager(lockdown=False)
    executor = MockExecutor(success=True)
    
    # Create orchestrator
    orchestrator = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # Run one cycle
    await orchestrator.run_single_cycle()
    
    # Verify signal was persisted
    executed_count = storage.count_executed_signals(date.today())
    assert executed_count == 1
    
    # Verify signals in DB
    signals_today = storage.get_signals_by_date(date.today())
    assert len(signals_today) == 1
    assert signals_today[0]["symbol"] == "EURUSD"
    assert signals_today[0]["status"] == "executed"


@pytest.mark.asyncio
async def test_orchestrator_recovery_after_crash(storage):
    """
    RESILIENCE TEST: Simulate crash and recovery.
    
    Steps:
    1. Execute signals
    2. Simulate crash (create new orchestrator instance)
    3. Verify state is recovered correctly
    """
    # === PHASE 1: Initial execution ===
    scanner = MockScanner()
    signal_factory = MockSignalFactory(should_generate=True)
    risk_manager = MockRiskManager(lockdown=False)
    executor = MockExecutor(success=True)
    
    orchestrator1 = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # Execute 2 cycles
    await orchestrator1.run_single_cycle()
    await orchestrator1.run_single_cycle()
    
    initial_executed = orchestrator1.stats.signals_executed
    assert initial_executed == 2
    
    # === PHASE 2: Simulate crash and restart ===
    # Create new orchestrator instance (simulates restart)
    scanner2 = MockScanner()
    signal_factory2 = MockSignalFactory(should_generate=False)  # No new signals
    risk_manager2 = MockRiskManager(lockdown=False)
    executor2 = MockExecutor(success=True)
    
    orchestrator2 = MainOrchestrator(
        scanner=scanner2,
        signal_factory=signal_factory2,
        risk_manager=risk_manager2,
        executor=executor2,
        storage=storage
    )
    
    # Verify stats were recovered
    assert orchestrator2.stats.signals_executed == 2  # Recovered from DB
    assert orchestrator2.stats.date == date.today()
    
    # Verify DB still has signals
    signals_today = storage.get_signals_by_date(date.today())
    assert len(signals_today) == 2


@pytest.mark.asyncio
async def test_adaptive_heartbeat_with_signals(storage):
    """
    Test adaptive heartbeat (Latido de Guardia).
    
    Verify that sleep interval reduces when signals are active.
    """
    scanner = MockScanner(regime=MarketRegime.RANGE)
    signal_factory = MockSignalFactory(should_generate=True)
    risk_manager = MockRiskManager(lockdown=False)
    executor = MockExecutor(success=True)
    
    orchestrator = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # Run cycle to generate signals
    await orchestrator.run_single_cycle()
    
    # Check that active signals were registered
    assert len(orchestrator._active_signals) > 0
    
    # Verify adaptive interval is reduced
    base_interval = orchestrator.intervals[MarketRegime.RANGE]
    adaptive_interval = orchestrator._get_sleep_interval()
    
    assert adaptive_interval < base_interval
    assert adaptive_interval == orchestrator.MIN_SLEEP_INTERVAL


@pytest.mark.asyncio
async def test_adaptive_heartbeat_without_signals(storage):
    """Test that heartbeat uses normal interval when no signals"""
    scanner = MockScanner(regime=MarketRegime.RANGE)
    signal_factory = MockSignalFactory(should_generate=False)  # No signals
    risk_manager = MockRiskManager(lockdown=False)
    executor = MockExecutor(success=True)
    
    orchestrator = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # Run cycle (no signals)
    await orchestrator.run_single_cycle()
    
    # Verify no active signals
    assert len(orchestrator._active_signals) == 0
    
    # Verify normal interval is used
    base_interval = orchestrator.intervals[MarketRegime.RANGE]
    adaptive_interval = orchestrator._get_sleep_interval()
    
    assert adaptive_interval == base_interval


@pytest.mark.asyncio
async def test_stats_persistence_after_each_cycle(storage):
    """
    Test that stats are persisted after each cycle.
    
    Ensures minimal data loss even if crash occurs between cycles.
    """
    scanner = MockScanner()
    signal_factory = MockSignalFactory(should_generate=True)
    risk_manager = MockRiskManager(lockdown=False)
    executor = MockExecutor(success=True)
    
    orchestrator = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # Run cycle
    await orchestrator.run_single_cycle()
    
    # Verify stats were persisted to DB
    system_state = storage.get_system_state()
    session_stats = system_state.get("session_stats", {})
    
    assert session_stats["signals_processed"] == 1
    assert session_stats["signals_executed"] == 1
    assert session_stats["cycles_completed"] == 1
    assert "last_update" in session_stats


def test_count_executed_signals_filters_by_date(storage):
    """Test that count_executed_signals correctly filters by date"""
    from datetime import timedelta
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Create signal for today
    signal_today = Signal(
        symbol="EURUSD",
        signal_type="BUY",
        confidence=0.85,
        connector_type=ConnectorType.GENERIC,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        timestamp=datetime.now(),
        metadata={"regime": MarketRegime.TREND.value}
    )
    
    # Manually create signal for yesterday
    signal_yesterday_record = {
        "id": "test-yesterday",
        "symbol": "GBPUSD",
        "signal_type": "SELL",
        "entry_price": 1.3000,
        "stop_loss": 1.3050,
        "take_profit": 1.2900,
        "timestamp": datetime.now().isoformat(),
        "date": yesterday.isoformat(),
        "status": "executed"
    }
    
    # Save today's signal normally
    storage.save_signal(signal_today)
    
    # Manually add yesterday's signal
    with open(storage.db_path, 'r') as f:
        data = json.load(f)
    data["signals"].append(signal_yesterday_record)
    with open(storage.db_path, 'w') as f:
        json.dump(data, f, indent=4)
    
    # Verify counts
    today_count = storage.count_executed_signals(today)
    yesterday_count = storage.count_executed_signals(yesterday)
    
    assert today_count == 1
    assert yesterday_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
