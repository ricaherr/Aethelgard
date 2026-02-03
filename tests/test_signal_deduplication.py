"""
Tests for Signal Deduplication System
Ensures no duplicate signals are generated or executed
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from data_vault.storage import StorageManager
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from models.signal import Signal, SignalType, ConnectorType


class TestSignalDeduplication:
    """Test cases for signal deduplication logic"""
    
    @pytest.fixture
    def storage(self, tmp_path):
        """Create isolated storage for testing"""
        db_path = tmp_path / "test_dedup.db"
        return StorageManager(db_path=str(db_path))
    
    @pytest.fixture
    def risk_manager(self):
        """Create risk manager"""
        from data_vault.storage import StorageManager
        storage = StorageManager(db_path=':memory:')
        return RiskManager(storage=storage, initial_capital=10000.0)
    
    @pytest.fixture
    def executor(self, risk_manager, storage):
        """Create executor with paper connector"""
        from connectors.paper_connector import PaperConnector
        
        connectors = {ConnectorType.PAPER: PaperConnector()}
        return OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors=connectors
        )
    
    def test_has_open_position_detection(self, storage):
        """Test detection of open positions"""
        # Initially no open position
        assert not storage.has_open_position("EURUSD")
        
        # Create and execute a signal
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100
        )
        
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 12345})
        
        # Now should have open position
        assert storage.has_open_position("EURUSD")
        
        # Other symbols should not have open position
        assert not storage.has_open_position("GBPUSD")
    
    def test_has_recent_signal_detection(self, storage):
        """Test detection of recent signals"""
        # Initially no recent signal
        assert not storage.has_recent_signal("EURUSD", "BUY", minutes=60)
        
        # Create a signal
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000
        )
        
        storage.save_signal(signal)
        
        # Now should have recent signal
        assert storage.has_recent_signal("EURUSD", "BUY", minutes=60)
        
        # Different type should not match
        assert not storage.has_recent_signal("EURUSD", "SELL", minutes=60)
        
        # Different symbol should not match
        assert not storage.has_recent_signal("GBPUSD", "BUY", minutes=60)
    
    @pytest.mark.asyncio
    async def test_executor_rejects_duplicate_open_position(self, executor, storage):
        """Test executor rejects signal when position already open"""
        # Create and execute first signal
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100
        )
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Try to execute duplicate signal
        signal2 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1050,
            stop_loss=1.1000,
            take_profit=1.1150
        )
        
        result2 = await executor.execute_signal(signal2)
        assert result2 is False  # Should be rejected
    
    @pytest.mark.asyncio
    async def test_executor_rejects_recent_signal(self, executor, storage):
        """Test executor rejects signal if recent one exists"""
        # Create first signal (PENDING, not executed)
        signal1 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2500
        )
        
        # Save but don't execute (stays PENDING)
        storage.save_signal(signal1)
        
        # Try to execute similar signal immediately
        signal2 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2510,
            stop_loss=1.2450,
            take_profit=1.2600
        )
        
        result = await executor.execute_signal(signal2)
        assert result is False  # Should be rejected due to recent signal
    
    @pytest.mark.asyncio
    async def test_executor_allows_different_symbols(self, executor, storage):
        """Test executor allows signals for different symbols"""
        # Execute signal for EURUSD
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100
        )
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Execute signal for GBPUSD (different symbol)
        signal2 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2500,
            stop_loss=1.2450,
            take_profit=1.2600
        )
        
        result2 = await executor.execute_signal(signal2)
        assert result2 is True  # Should be allowed
    
    @pytest.mark.asyncio
    async def test_executor_allows_opposite_signals(self, executor, storage):
        """Test executor behavior with opposite signal types (BUY vs SELL)"""
        # Execute BUY signal
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100
        )
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Try opposite signal type (SELL)
        # This SHOULD be rejected because there's an open BUY position
        # Our deduplication logic prevents opening opposite positions on the same symbol
        signal2 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.SELL,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1050,
            stop_loss=1.1100,
            take_profit=1.1000
        )
        
        result2 = await executor.execute_signal(signal2)
        # Should be rejected because there's an open position (even if opposite direction)
        # This prevents hedging and ensures clear risk management
        assert result2 is False
