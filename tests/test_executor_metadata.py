"""
Tests for Executor - Position Metadata Saving

FASE 2.3: Verificar que metadata se guarda al abrir posición

Tests TDD (Red-Green-Refactor):
1. Metadata guardada al ejecutar señal exitosamente
2. Metadata contiene todos los campos requeridos
3. Metadata NO se guarda si ejecución falla
4. Metadata incluye régimen correcto
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from models.signal import Signal, SignalType, ConnectorType, MarketRegime
from data_vault.storage import StorageManager


# Fixtures

@pytest.fixture
def mock_storage():
    """Mock StorageManager"""
    storage = Mock(spec=StorageManager)
    storage.has_open_position = Mock(return_value=False)
    storage.has_recent_signal = Mock(return_value=False)
    storage.save_signal = Mock()
    storage.update_signal_status = Mock()
    storage.update_position_metadata = Mock(return_value=True)
    # Multi-timeframe limiter needs these
    storage.get_signals = Mock(return_value=[])
    return storage


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager"""
    rm = Mock(spec=RiskManager)
    rm.is_locked = Mock(return_value=False)
    rm.calculate_position_size_master = Mock(return_value=0.10)
    return rm


@pytest.fixture
def mock_connector():
    """Mock MT5Connector"""
    connector = Mock()
    connector.is_connected = True
    connector.execute_signal = Mock(return_value={
        'success': True,
        'ticket': 12345678,
        'volume': 0.10,
        'entry_price': 1.08500,
        'sl': 1.08200,
        'tp': 1.09000
    })
    connector.get_account_balance = Mock(return_value=10000.0)
    return connector


@pytest.fixture
def executor(mock_risk_manager, mock_storage, mock_connector):
    """Create Executor with mocked dependencies"""
    connectors = {
        ConnectorType.METATRADER5: mock_connector
    }
    
    executor = OrderExecutor(
        risk_manager=mock_risk_manager,
        storage=mock_storage,
        notificator=None,
        connectors=connectors
    )
    
    return executor


@pytest.fixture
def test_signal():
    """Create test signal"""
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


# Tests FASE 2.3

@pytest.mark.asyncio
async def test_metadata_saved_on_successful_execution(
    executor,
    test_signal,
    mock_storage,
    mock_connector
):
    """
    Test: Metadata se guarda cuando señal se ejecuta exitosamente
    
    Expected: storage.update_position_metadata llamado con datos correctos
    """
    # Execute signal
    result = await executor.execute_signal(test_signal)
    
    # Assert: Execution successful
    assert result is True
    
    # Assert: Metadata saved
    mock_storage.update_position_metadata.assert_called_once()
    
    # Get call arguments
    call_args = mock_storage.update_position_metadata.call_args[0]
    ticket = call_args[0]
    metadata = call_args[1]
    
    # Assert: Ticket correct
    assert ticket == 12345678
    
    # Assert: Required fields present
    assert 'ticket' in metadata
    assert 'symbol' in metadata
    assert 'entry_price' in metadata
    assert 'sl' in metadata
    assert 'tp' in metadata
    assert 'initial_risk_usd' in metadata
    assert 'entry_time' in metadata
    assert 'entry_regime' in metadata


@pytest.mark.asyncio
async def test_metadata_contains_all_required_fields(
    executor,
    test_signal,
    mock_storage
):
    """
    Test: Metadata contiene todos los campos requeridos por PositionManager
    
    Expected: 8 campos mínimos presentes
    """
    # Execute signal
    await executor.execute_signal(test_signal)
    
    # Get metadata from call
    call_args = mock_storage.update_position_metadata.call_args[0]
    metadata = call_args[1]
    
    # Required fields for PositionManager
    required_fields = [
        'ticket',
        'symbol',
        'entry_price',
        'sl',
        'tp',
        'initial_risk_usd',
        'entry_time',
        'entry_regime'
    ]
    
    for field in required_fields:
        assert field in metadata, f"Missing required field: {field}"
    
    # Assert: Values have correct types
    assert isinstance(metadata['ticket'], int)
    assert isinstance(metadata['symbol'], str)
    assert isinstance(metadata['entry_price'], (int, float))
    assert isinstance(metadata['sl'], (int, float))
    assert isinstance(metadata['tp'], (int, float))
    assert isinstance(metadata['initial_risk_usd'], (int, float, Decimal))
    assert isinstance(metadata['entry_time'], str)  # ISO format
    assert isinstance(metadata['entry_regime'], str)  # "TREND", "RANGE", etc.


@pytest.mark.asyncio
async def test_metadata_not_saved_on_failed_execution(
    executor,
    test_signal,
    mock_storage,
    mock_connector
):
    """
    Test: Metadata NO se guarda si ejecución falla
    
    Expected: storage.update_position_metadata NO llamado
    """
    # Setup: Mock connector to fail
    mock_connector.execute_signal = Mock(return_value={
        'success': False,
        'error': 'Insufficient margin'
    })
    
    # Execute signal
    result = await executor.execute_signal(test_signal)
    
    # Assert: Execution failed
    assert result is False
    
    # Assert: Metadata NOT saved
    mock_storage.update_position_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_includes_correct_regime(
    executor,
    test_signal,
    mock_storage
):
    """
    Test: Metadata incluye régimen correcto desde signal.metadata
    
    Expected: entry_regime = "TREND"
    """
    # Signal tiene régimen TREND en metadata
    assert test_signal.metadata['regime'] == MarketRegime.TREND.value
    
    # Execute signal
    await executor.execute_signal(test_signal)
    
    # Get metadata from call
    call_args = mock_storage.update_position_metadata.call_args[0]
    metadata = call_args[1]
    
    # Assert: Regime preserved
    assert metadata['entry_regime'] == MarketRegime.TREND.value


@pytest.mark.asyncio
async def test_metadata_calculates_initial_risk_usd(
    executor,
    test_signal,
    mock_storage,
    mock_connector
):
    """
    Test: initial_risk_usd calculado correctamente
    
    Formula: (entry_price - sl) * volume * contract_size * point_value
    Expected: Valor > 0
    """
    # Execute signal
    await executor.execute_signal(test_signal)
    
    # Get metadata from call
    call_args = mock_storage.update_position_metadata.call_args[0]
    metadata = call_args[1]
    
    # Assert: initial_risk_usd calculated
    initial_risk = metadata['initial_risk_usd']
    assert initial_risk > 0, "Initial risk must be positive"
    assert isinstance(initial_risk, (int, float, Decimal))


@pytest.mark.asyncio
async def test_metadata_entry_time_is_iso_format(
    executor,
    test_signal,
    mock_storage
):
    """
    Test: entry_time está en formato ISO (parseable por datetime.fromisoformat)
    
    Expected: datetime.fromisoformat(entry_time) no falla
    """
    # Execute signal
    await executor.execute_signal(test_signal)
    
    # Get metadata from call
    call_args = mock_storage.update_position_metadata.call_args[0]
    metadata = call_args[1]
    
    # Assert: entry_time is ISO format
    entry_time_str = metadata['entry_time']
    
    # Should not raise exception
    try:
        parsed_time = datetime.fromisoformat(entry_time_str)
        assert isinstance(parsed_time, datetime)
    except ValueError:
        pytest.fail(f"entry_time not in ISO format: {entry_time_str}")
