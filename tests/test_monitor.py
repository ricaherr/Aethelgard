"""
Test Suite for Closing Monitor (Feedback Loop)
TDD: Tests first approach for monitoring closed trades
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from core_brain.monitor import ClosingMonitor
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


class TestClosingMonitor:
    """Test cases for ClosingMonitor functionality"""
    
    @pytest.fixture
    def storage(self, tmp_path):
        """Create temporary storage for testing"""
        import tempfile
        import os
        db_path = os.path.join(tmp_path, "test.db")
        storage = StorageManager(db_path=db_path)
        return storage
    
    @pytest.fixture
    def mock_mt5_connector(self):
        """Mock MT5 connector with closed orders"""
        connector = Mock()
        # Will be configured per test
        connector.get_closed_positions = Mock(return_value=[])
        return connector
    
    @pytest.fixture
    def monitor(self, storage, mock_mt5_connector):
        """Create ClosingMonitor instance"""
        connectors = {'MT5': mock_mt5_connector}
        return ClosingMonitor(storage=storage, connectors=connectors)
    
    def test_initialization(self, monitor):
        """Test monitor initializes correctly"""
        assert monitor is not None
        assert monitor.storage is not None
        assert monitor.connectors is not None
        assert monitor.is_running is False
    
    def test_check_closed_positions_empty(self, monitor, storage):
        """Test checking closed positions when none exist"""
        # Setup: No executed signals
        result = monitor.check_closed_positions()
        assert result == 0  # No updates
    
    def test_check_closed_positions_updates_db(self, monitor, storage, mock_mt5_connector):
        """Test that closed positions update the database"""
        # Setup: Create executed signal
        signal_id = storage.save_signal(Signal(
            symbol='EURUSD',
            signal_type=SignalType.BUY,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.8,
            connector_type=ConnectorType.METATRADER5
        ))
        
        # Update signal to EXECUTED status with ticket
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 123456})

        # Verify order_id persisted in signals table
        updated = storage.get_signal_by_id(signal_id)
        assert updated['order_id'] == "123456"
        
        # Configure mock to return a closed position matching our signal
        mock_mt5_connector.get_closed_positions.return_value = [
            {
                'ticket': 123456,
                'symbol': 'EURUSD',
                'entry_price': 1.1000,
                'exit_price': 1.1050,
                'profit': 50.0,
                'close_time': datetime.now(),
                'signal_id': signal_id  # Use the real signal_id
            }
        ]
        
        # Execute monitor check
        updates = monitor.check_closed_positions()
        
        # Verify update occurred
        assert updates == 1
        
        # Verify database was updated
        signals = storage.get_signals()
        updated_signal = next(s for s in signals if s['id'] == signal_id)
        assert updated_signal['status'] == 'CLOSED'
    
    def test_calculate_pips_correctly(self, monitor):
        """Test PIP calculation for different instruments"""
        # EURUSD (4 decimal places)
        pips = monitor._calculate_pips('EURUSD', 1.1000, 1.1050)
        assert pips == 50.0
        
        # USDJPY (2 decimal places)
        pips = monitor._calculate_pips('USDJPY', 110.00, 110.50)
        assert pips == 50.0
        
        # GOLD/XAUUSD (2 decimal places for pips)
        pips = monitor._calculate_pips('XAUUSD', 1800.00, 1810.00)
        assert pips == 1000.0  # 10 * 100
    
    def test_update_trade_result_win(self, monitor, storage):
        """Test updating a winning trade"""
        # Create and execute signal
        signal_id = storage.save_signal(Signal(
            symbol='EURUSD',
            signal_type=SignalType.BUY,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.8,
            connector_type=ConnectorType.METATRADER5
        ))
        
        # Update to closed with profit
        monitor._update_trade_result(
            signal_id=signal_id,
            exit_price=1.1050,
            profit=50.0,
            exit_reason='TAKE_PROFIT'
        )
        
        # Verify trade was saved
        trades = storage.get_recent_trades()
        assert len(trades) == 1
        assert trades[0]['is_win'] is True
        assert trades[0]['profit'] == 50.0
    
    def test_update_trade_result_loss(self, monitor, storage):
        """Test updating a losing trade"""
        signal_id = storage.save_signal(Signal(
            symbol='EURUSD',
            signal_type=SignalType.BUY,
            entry_price=1.1000,
            confidence=0.8,
            connector_type=ConnectorType.METATRADER5,
            stop_loss=1.0950,
            take_profit=1.1100
        ))
        
        # Update to closed with loss
        monitor._update_trade_result(
            signal_id=signal_id,
            exit_price=1.0950,
            profit=-50.0,
            exit_reason='STOP_LOSS'
        )
        
        # Verify trade was saved
        trades = storage.get_recent_trades()
        assert len(trades) == 1
        assert trades[0]['is_win'] is False
        assert trades[0]['profit'] == -50.0
    
    @pytest.mark.asyncio
    async def test_run_monitoring_loop(self, monitor):
        """Test asynchronous monitoring loop"""
        monitor.interval_seconds = 1
        
        # Start monitoring
        task = asyncio.create_task(monitor.start())
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Stop monitoring
        await monitor.stop()
        
        assert monitor.is_running is False
    
    def test_connector_failure_handling(self, monitor, mock_mt5_connector):
        """Test graceful handling of connector failures"""
        # Simulate connector error
        mock_mt5_connector.get_closed_positions.side_effect = Exception("Connection lost")
        
        # Should not raise, should log error
        result = monitor.check_closed_positions()
        assert result == 0
