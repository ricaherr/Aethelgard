"""
Test for Concurrent MT5 Startup
Tests that MT5Connector initialization doesn't block the main thread.
"""
import time
from unittest.mock import patch, MagicMock

from connectors.mt5_connector import MT5Connector, ConnectionState
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from data_vault.storage import StorageManager


def test_mt5_connector_states():
    """Test MT5Connector has proper state management"""
    # Mock MT5 library
    with patch('connectors.mt5_connector.mt5') as mock_mt5:
        mock_mt5.initialize.return_value = False  # Simulate failure

        connector = MT5Connector()

        # Should start in DISCONNECTED state
        assert not connector.is_connected
        assert connector.connection_state == ConnectionState.DISCONNECTED

        # start() should initiate background connection
        connector.start()
        
        # Should be connecting in background
        assert connector.connection_thread is not None
        assert connector.connection_thread.is_alive()
        
        # Wait a bit for thread to start
        time.sleep(0.1)
        assert connector.connection_state in [ConnectionState.CONNECTING, ConnectionState.FAILED]


def test_executor_init_non_blocking():
    """Test OrderExecutor initialization doesn't block on MT5"""
    # Mock MT5 connection
    with patch('connectors.mt5_connector.MT5Connector') as mock_mt5_class:
        mock_connector = MagicMock()
        mock_mt5_class.return_value = mock_connector

        storage = StorageManager()
        risk_manager = RiskManager(storage=storage, initial_capital=1000)

        # This should initialize quickly (no connection attempt)
        start_time = time.time()
        executor = OrderExecutor(risk_manager=risk_manager, storage=storage)
        elapsed = time.time() - start_time

        # Should initialize quickly
        assert elapsed < 1.0  # Less than 1 second
        assert isinstance(executor, OrderExecutor)
        # Should have loaded MT5 connector
        from models.signal import ConnectorType
        assert ConnectorType.METATRADER5 in executor.connectors
        
        # MT5 connector should not have started connecting yet
        assert not mock_connector.start.called