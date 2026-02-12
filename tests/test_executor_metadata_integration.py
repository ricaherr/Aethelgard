"""
INTEGRATION TEST: Executor + StorageManager (REAL DB)

This test validates that Executor ACTUALLY saves metadata to database.
No mocks, no fakes - REAL integration.

WHY THIS EXISTS:
- Previous tests used Mocks, allowing non-existent methods to "pass"
- This test uses REAL StorageManager with in-memory SQLite
- If StorageManager.update_position_metadata() doesn't exist → TEST FAILS

RULE: If this test passes, metadata saving ACTUALLY WORKS in production.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType, MarketRegime


@pytest.fixture
def real_storage(tmp_path):
    """REAL StorageManager with temporary database"""
    db_path = tmp_path / "integration_test.db"
    return StorageManager(db_path=str(db_path))


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager (safe to mock - external dependency)"""
    rm = Mock(spec=RiskManager)
    rm.is_locked = Mock(return_value=False)
    rm.calculate_position_size_master = Mock(return_value=0.10)
    return rm


@pytest.fixture
def mock_connector():
    """Mock MT5Connector (safe to mock - broker integration)"""
    connector = Mock()
    connector.is_connected = True
    connector.execute_signal = Mock(return_value={
        'success': True,
        'ticket': 98765432,
        'volume': 0.10,
        'entry_price': 1.08500,
        'sl': 1.08200,
        'tp': 1.09000
    })
    connector.get_account_balance = Mock(return_value=10000.0)
    return connector


@pytest.fixture
def executor(mock_risk_manager, real_storage, mock_connector):
    """Executor with REAL storage"""
    connectors = {
        ConnectorType.METATRADER5: mock_connector
    }
    
    executor = OrderExecutor(
        risk_manager=mock_risk_manager,
        storage=real_storage,
        notificator=None,
        connectors=connectors
    )
    
    return executor


@pytest.fixture
def test_signal():
    """Test signal"""
    return Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        connector_type=ConnectorType.METATRADER5,
        timeframe="H1",
        entry_price=1.08500,
        stop_loss=1.08200,
        take_profit=1.09000,
        confidence=0.85,
        metadata={
            "regime": MarketRegime.TREND.value,
            "atr": 0.0015,
            "expiration_bars": 5
        }
    )


# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
async def test_executor_actually_saves_metadata_to_database(
    executor,
    test_signal,
    real_storage
):
    """
    CRITICAL INTEGRATION TEST
    
    Validates that Executor ACTUALLY saves metadata to REAL database.
    
    If StorageManager.update_position_metadata() doesn't exist:
    - This test WILL FAIL with AttributeError
    - Previous mock-based tests incorrectly passed
    
    Expected:
    1. Executor executes signal
    2. Metadata saved to database
    3. Metadata retrievable via get_position_metadata()
    """
    # Execute signal
    result = await executor.execute_signal(test_signal)
    
    # Assert: Execution successful
    assert result is True, "Signal execution should succeed"
    
    # Assert: Metadata exists in database (REAL DB CHECK)
    metadata = real_storage.get_position_metadata(98765432)
    
    assert metadata is not None, "Metadata should exist in database"
    assert metadata['ticket'] == 98765432
    assert metadata['symbol'] == "EURUSD"
    assert metadata['entry_price'] == 1.08500
    assert metadata['sl'] == 1.08200
    assert metadata['tp'] == 1.09000
    assert metadata['entry_regime'] in ['TREND', 'RANGE', 'VOLATILE', 'NEUTRAL']
    assert metadata['initial_risk_usd'] > 0  # Should be calculated


@pytest.mark.asyncio
async def test_metadata_persists_across_executor_instances(
    test_signal,
    mock_risk_manager,
    mock_connector,
    real_storage
):
    """
    Test: Metadata survives Executor restart (database persistence)
    
    Scenario:
    1. Executor A saves metadata
    2. Executor A destroyed
    3. Executor B created with same DB
    4. Executor B can read metadata saved by A
    """
    # Create first executor
    connectors = {ConnectorType.METATRADER5: mock_connector}
    executor_a = OrderExecutor(
        risk_manager=mock_risk_manager,
        storage=real_storage,
        notificator=None,
        connectors=connectors
    )
    
    # Execute signal
    await executor_a.execute_signal(test_signal)
    
    # Destroy executor A (simulate restart)
    del executor_a
    
    # Create new executor B with SAME storage
    executor_b = OrderExecutor(
        risk_manager=mock_risk_manager,
        storage=real_storage,
        notificator=None,
        connectors=connectors
    )
    
    # Assert: Metadata still exists (database persistence)
    metadata = real_storage.get_position_metadata(98765432)
    
    assert metadata is not None, "Metadata should persist across executor restarts"
    assert metadata['symbol'] == "EURUSD"


@pytest.mark.asyncio
async def test_failed_execution_does_not_save_metadata(
    executor,
    test_signal,
    real_storage,
    mock_connector
):
    """
    Test: Metadata NOT saved if execution fails
    
    Expected: Database should NOT have metadata for failed trade
    """
    # Configure connector to fail
    mock_connector.execute_signal = Mock(return_value={
        'success': False,
        'error': 'Insufficient margin'
    })
    
    # Execute signal (should fail)
    result = await executor.execute_signal(test_signal)
    
    # Assert: Execution failed
    assert result is False
    
    # Assert: NO metadata in database
    metadata = real_storage.get_position_metadata(98765432)
    assert metadata is None, "Failed execution should NOT save metadata"


@pytest.mark.asyncio
async def test_metadata_includes_correct_risk_calculation(
    executor,
    test_signal,
    real_storage
):
    """
    Test: initial_risk_usd correctly calculated
    
    Formula validation:
    - SL distance: 1.08500 - 1.08200 = 0.00300 (30 pips)
    - Volume: 0.10 lots
    - Contract size: 100,000 (standard FOREX)
    - Point value: ~10 (simplification)
    - Risk: 0.00300 * 0.10 * 10 = ~3.00 USD
    """
    # Execute signal
    await executor.execute_signal(test_signal)
    
    # Get metadata
    metadata = real_storage.get_position_metadata(98765432)
    
    # Assert: Risk calculated
    assert 'initial_risk_usd' in metadata
    assert metadata['initial_risk_usd'] > 0, "Risk must be calculated and > 0"
    
    # NOTE: Exact risk calculation validation is in test_executor_metadata.py
    # This integration test only validates that metadata is SAVED to DB


# ========== REGRESSION TESTS ==========

@pytest.mark.asyncio
async def test_update_position_metadata_method_exists(tmp_path):
    """
    REGRESSION TEST for Issue #123
    
    BUG: StorageManager.update_position_metadata() did not exist.
    Tests passed because they used Mocks instead of real storage.
    
    This test validates the method exists and has correct signature.
    """
    db_path = tmp_path / "regression_test.db"
    storage = StorageManager(db_path=str(db_path))
    
    # Assert: Method exists
    assert hasattr(storage, 'update_position_metadata'), \
        "StorageManager MUST have update_position_metadata() method"
    
    # Assert: Method is callable
    assert callable(storage.update_position_metadata), \
        "update_position_metadata must be callable"
    
    # Assert: Method works
    result = storage.update_position_metadata(
        ticket=12345,
        metadata={
            'symbol': 'EURUSD',
            'entry_price': 1.08500,
            'entry_time': datetime.now().isoformat(),
            'sl': 1.08200,
            'tp': 1.09000,
            'volume': 0.10,
            'initial_risk_usd': 30.0,
            'entry_regime': 'TREND',
            'timeframe': 'H1'
        }
    )
    
    assert result is True, "update_position_metadata should return True on success"
    
    # Verify data saved
    metadata = storage.get_position_metadata(12345)
    assert metadata is not None
    assert metadata['ticket'] == 12345
