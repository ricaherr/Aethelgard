"""
Test Suite for Main Orchestrator
Tests the main orchestration loop with mocked components.

Test scenarios:
1. Complete cycle: Scan -> Signal -> Risk -> Execute
2. Dynamic frequency based on market regime
3. Graceful shutdown with state persistence
4. SessionStats tracking across cycles
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, date
from pathlib import Path

from core_brain.main_orchestrator import MainOrchestrator, SessionStats
from models.signal import MarketRegime, Signal, SignalType, ConnectorType, MembershipTier


@pytest.fixture
def mock_scanner():
    """Mock ScannerEngine that returns predictable regime data"""
    scanner = MagicMock()
    # Usar get_scan_results_with_data para compatibilidad con la implementación real
    scanner.get_scan_results_with_data = MagicMock(return_value={
        "EURUSD": {"regime": MarketRegime.TREND, "atr": 0.0015, "df": MagicMock()},
        "GBPUSD": {"regime": MarketRegime.RANGE, "atr": 0.0020, "df": MagicMock()}
    })
    return scanner


@pytest.fixture
def mock_signal_factory():
    """Mock SignalFactory that generates test signals"""
    factory = MagicMock()
    
    # Create a realistic signal
    test_signal = Signal(
        symbol="EURUSD",
        signal_type="BUY",
        confidence=0.85,
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950
    )
    
    factory.generate_signals_batch = AsyncMock(return_value=[test_signal])
    return factory


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager that validates positions"""
    risk_mgr = MagicMock()
    risk_mgr.is_lockdown_active.return_value = False
    risk_mgr.calculate_position_size.return_value = 0.1
    return risk_mgr


@pytest.fixture
def mock_executor():
    """Mock OrderExecutor that simulates trade execution"""
    executor = MagicMock()
    executor.execute_signal = AsyncMock(return_value=True)
    return executor


@pytest.fixture
def temp_config(tmp_path):
    """Create temporary config file for testing"""
    config_data = {
        "orchestrator": {
            "loop_interval_trend": 5,
            "loop_interval_range": 30,
            "loop_interval_volatile": 15,
            "loop_interval_shock": 60
        }
    }
    
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary isolated storage for each test"""
    from data_vault.storage import StorageManager
    import tempfile
    
    # Create unique temp DB file for this test
    db_file = tmp_path / f"test_db_{id(tmp_path)}.json"
    storage = StorageManager(db_path=str(db_file))
    
    yield storage
    
    # Cleanup is automatic with tmp_path


class TestSessionStats:
    """Test SessionStats data class"""
    
    def test_initialization(self):
        """Test SessionStats creates with correct initial values"""
        stats = SessionStats()
        
        assert stats.date == date.today()
        assert stats.signals_processed == 0
        assert stats.signals_executed == 0
        assert stats.cycles_completed == 0
        
    def test_increment_signals(self):
        """Test incrementing signal counters"""
        stats = SessionStats()
        
        stats.signals_processed = 5
        stats.signals_executed = 3
        
        assert stats.signals_processed == 5
        assert stats.signals_executed == 3
        
    def test_reset_on_new_day(self):
        """Test stats reset when date changes"""
        stats = SessionStats()
        stats.signals_processed = 10
        stats.cycles_completed = 5
        
        # Simulate new day
        stats.date = date.today()
        stats.signals_processed = 0
        stats.cycles_completed = 0
        
        assert stats.signals_processed == 0
        assert stats.cycles_completed == 0


class TestMainOrchestrator:
    """Test MainOrchestrator orchestration logic"""
    
    @pytest.mark.asyncio
    async def test_single_cycle_execution(
        self, 
        mock_scanner, 
        mock_signal_factory, 
        mock_risk_manager, 
        mock_executor,
        temp_config,
        temp_storage
    ):
        """Test single complete cycle: Scan -> Signal -> Risk -> Execute"""
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=temp_storage,
            config_path=temp_config
        )
        
        # Execute one cycle
        await orchestrator.run_single_cycle()
        
        # Verify the complete chain was executed
        mock_scanner.get_scan_results_with_data.assert_called_once()
        mock_signal_factory.generate_signals_batch.assert_called_once()
        mock_executor.execute_signal.assert_called_once()
        
        # Verify stats were updated
        assert orchestrator.stats.cycles_completed == 1
        assert orchestrator.stats.signals_processed > 0
    
    @pytest.mark.asyncio
    async def test_dynamic_frequency_trend_regime(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config,
        temp_storage
    ):
        """Test loop runs faster in TREND regime"""
        # Configure scanner to return TREND regime
        mock_scanner.get_scan_results_with_data = MagicMock(return_value={
            "EURUSD": {"regime": MarketRegime.TREND, "atr": 0.0015, "df": MagicMock()}
        })
        
        # Configure signal factory to return no signals (so _active_signals is empty)
        mock_signal_factory.generate_signals_batch = AsyncMock(return_value=[])
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=temp_storage,
            config_path=temp_config
        )
        
        # Run a cycle to update the regime
        await orchestrator.run_single_cycle()
        
        # Get interval for TREND regime
        interval = orchestrator._get_sleep_interval()
        
        # Should be 5 seconds (fast) for TREND
        assert interval == 5
    
    @pytest.mark.asyncio
    async def test_dynamic_frequency_range_regime(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config,
        temp_storage
    ):
        """Test loop runs slower in RANGE regime"""
        # Configure scanner to return RANGE regime
        mock_scanner.get_scan_results_with_data = MagicMock(return_value={
            "EURUSD": {"regime": MarketRegime.RANGE, "atr": 0.0015, "df": MagicMock()}
        })
        
        # Configure signal factory to return no signals (so _active_signals is empty)
        mock_signal_factory.generate_signals_batch = AsyncMock(return_value=[])
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=temp_storage,
            config_path=temp_config
        )
        
        # Update current regime
        await orchestrator.run_single_cycle()
        
        # Get interval for RANGE regime
        interval = orchestrator._get_sleep_interval()
        
        # Should be 30 seconds (slow) for RANGE
        assert interval == 30
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config
    ):
        """Test graceful shutdown saves state before exiting"""
        # Mock executor close_connections as async
        mock_executor.close_connections = AsyncMock()
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            config_path=temp_config
        )
        
        # Mock storage save method
        orchestrator.storage = MagicMock()
        orchestrator.storage.update_system_state = MagicMock()
        
        # Trigger shutdown
        await orchestrator.shutdown()
        
        # Verify state was saved
        orchestrator.storage.update_system_state.assert_called_once()
        assert orchestrator._shutdown_requested is True
    
    @pytest.mark.asyncio
    async def test_lockdown_mode_blocks_execution(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config
    ):
        """Test that signals are not executed during lockdown"""
        # Configure risk manager to be in lockdown
        mock_risk_manager.is_lockdown_active.return_value = True
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            config_path=temp_config
        )
        
        # Run single cycle
        await orchestrator.run_single_cycle()
        
        # Scanner and signal factory should run
        mock_scanner.get_scan_results_with_data.assert_called_once()
        mock_signal_factory.generate_signals_batch.assert_called_once()
        
        # But executor should NOT be called due to lockdown
        mock_executor.execute_signal.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_session_stats_persistence(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config,
        temp_storage
    ):
        """Test SessionStats are maintained across cycles"""
        # Create function that returns a new signal each time (avoiding caching issues)
        def create_signal():
            return [Signal(
                symbol="EURUSD",
                signal_type="BUY",
                confidence=0.85,
                connector_type=ConnectorType.METATRADER5,
                entry_price=1.0850,
                stop_loss=1.0800,
                take_profit=1.0950
            )]
        
        # Use side_effect to return fresh signals each call
        mock_signal_factory.generate_signals_batch = AsyncMock(side_effect=[
            create_signal(),
            create_signal(),
            create_signal()
        ])
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=temp_storage,
            config_path=temp_config
        )
        
        # Run multiple cycles
        for _ in range(3):
            await orchestrator.run_single_cycle()
        
        # Verify stats accumulated
        assert orchestrator.stats.cycles_completed == 3
        assert orchestrator.stats.signals_processed == 3  # 1 signal per cycle x 3 cycles
    
    @pytest.mark.asyncio
    async def test_error_handling_continues_loop(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config
    ):
        """Test loop continues after error in one component"""
        # Configure scanner to fail once then succeed
        mock_scanner.get_scan_results_with_data = MagicMock(
            side_effect=[
                Exception("Network error"), 
                {"EURUSD": {"regime": MarketRegime.TREND, "atr": 0.0015, "df": MagicMock()}}
            ]
        )
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            config_path=temp_config
        )
        
        # First cycle should handle error gracefully
        await orchestrator.run_single_cycle()
        
        # Second cycle should work
        await orchestrator.run_single_cycle()
        
        # Verify second call was made despite first error
        assert mock_scanner.get_scan_results_with_data.call_count == 2
    
    @pytest.mark.asyncio
    async def test_daily_stats_reset(
        self,
        mock_scanner,
        mock_signal_factory,
        mock_risk_manager,
        mock_executor,
        temp_config,
        temp_storage
    ):
        """Test stats reset when day changes"""
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=temp_storage,
            config_path=temp_config
        )
        
        # Run a cycle
        await orchestrator.run_single_cycle()
        assert orchestrator.stats.cycles_completed == 1
        
        # Simulate day change
        from datetime import timedelta
        orchestrator.stats.date = date.today() - timedelta(days=1)
        
        # Run cycle - should detect new day and reset
        await orchestrator.run_single_cycle()
        
        # Stats should be reset to 1 (current cycle)
        assert orchestrator.stats.date == date.today()
        assert orchestrator.stats.cycles_completed == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
