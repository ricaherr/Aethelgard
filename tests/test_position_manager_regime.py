"""
Tests for PositionManager - Regime Management and Risk Protection

FASE 1: Gestión por Régimen + Max Drawdown + Validación Freeze Level

Tests TDD (Red-Green-Refactor):
1. Emergency close on max drawdown
2. Adjust SL when regime changes (TREND → RANGE)
3. Adjust TP when regime changes (RANGE → TREND)
4. Time-based exit for stale positions
5. Freeze level validation (EURUSD, GBPJPY)
6. Cooldown between modifications
7. Daily modification limits
8. Metadata persistence
9. Rollback on failure
10. Liquidez validation
11. Integration with MainOrchestrator
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal

from core_brain.position_manager import PositionManager
from models.signal import MarketRegime
from data_vault.storage import StorageManager


# Fixtures

@pytest.fixture
def mock_storage():
    """Mock StorageManager for testing"""
    storage = Mock(spec=StorageManager)
    storage.get_position_metadata = Mock(return_value={})
    storage.update_position_metadata = Mock(return_value=True)
    storage.rollback_position_modification = Mock(return_value=True)
    return storage


@pytest.fixture
def mock_connector():
    """Mock MT5Connector for testing"""
    connector = Mock()
    
    # Symbol info mock
    symbol_info = {
        'trade_stops_level': 5,
        'point': 0.00001,
        'tick_size': 0.00001,
        'spread': 2
    }
    connector.get_symbol_info = Mock(return_value=symbol_info)
    
    # Positions mock
    connector.get_open_positions = Mock(return_value=[])
    
    # Modification mock
    connector.modify_position = Mock(return_value={'success': True})
    
    # Close mock
    connector.close_position = Mock(return_value={'success': True})
    
    # Price mock
    connector.get_current_price = Mock(return_value=1.08500)
    
    return connector


@pytest.fixture
def mock_regime_classifier():
    """Mock RegimeClassifier for testing"""
    classifier = Mock()
    classifier.classify_regime = Mock(return_value=MarketRegime.TREND)
    classifier.get_regime_data = Mock(return_value={'atr': 0.00050})
    return classifier


@pytest.fixture
def position_manager(mock_storage, mock_connector, mock_regime_classifier):
    """Create PositionManager instance with mocks"""
    config = {
        'enabled': True,
        'check_interval_seconds': 10,
        'max_drawdown_multiplier': 2.0,
        'cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'regime_adjustments': {
            'TREND': {
                'sl_atr_multiplier': 3.0,
                'tp_atr_multiplier': 5.0,
                'max_holding_hours': 72
            },
            'RANGE': {
                'sl_atr_multiplier': 1.5,
                'tp_atr_multiplier': 2.0,
                'max_holding_hours': 4
            },
            'VOLATILE': {
                'sl_atr_multiplier': 4.0,
                'tp_atr_multiplier': 3.0,
                'max_holding_hours': 2
            }
        },
        'stale_thresholds_hours': {
            'TREND': 72,
            'RANGE': 4,
            'VOLATILE': 2,
            'CRASH': 1,
            'NEUTRAL': 24
        },
        'freeze_level_safety_margin': 1.1
    }
    
    manager = PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=config
    )
    
    return manager


@pytest.fixture
def mock_position():
    """Create mock position dict for testing"""
    return {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'volume': 0.10,
        'entry_price': 1.08500,
        'current_price': 1.08300,
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': -20.0,
        'swap': -0.80
    }


# Tests FASE 1

def test_emergency_close_max_drawdown(position_manager, mock_position, mock_connector, mock_storage):
    """
    Test emergency close when position loss >= 2x initial risk.
    
    Scenario: Position down -$200 USD, initial risk was $100 USD
    Expected: Position closed immediately with reason "MAX_DRAWDOWN"
    """
    # Setup: Position with loss >= 2x initial risk
    mock_position['profit'] = -200.0
    mock_connector.get_open_positions = Mock(return_value=[mock_position])
    
    # Mock metadata with initial risk
    mock_storage.get_position_metadata = Mock(return_value={
        'ticket': 12345678,
        'initial_risk_usd': 100.0,
        'entry_regime': 'TREND'
    })
    
    # Execute
    result = position_manager.monitor_positions()
    
    # Assert: Position closed
    mock_connector.close_position.assert_called_once_with(12345678, "MAX_DRAWDOWN")
    
    # Assert: Actions recorded
    assert len(result['actions']) == 1
    assert result['actions'][0]['action'] == 'EMERGENCY_CLOSE'


def test_adjust_sl_trend_to_range(position_manager, mock_position, mock_connector, mock_storage, mock_regime_classifier):
    """
    Test SL adjustment when regime changes from TREND to RANGE.
    
    Scenario: Position opened in TREND, market now in RANGE
    Expected: SL tightened (moved closer to entry)
    """
    # Setup: Position opened in TREND, now in RANGE
    mock_position['profit'] = -10.0  # Below max drawdown
    mock_connector.get_open_positions = Mock(return_value=[mock_position])
    
    # Mock metadata
    mock_storage.get_position_metadata = Mock(return_value={
        'ticket': 12345678,
        'initial_risk_usd': 100.0,
        'entry_regime': 'TREND',
        'entry_price': 1.08500,
        'direction': 'BUY',
        'entry_time': datetime.now().isoformat(),
        'sl_modifications_count': 0
    })
    
    # Regime changed to RANGE
    mock_regime_classifier.classify_regime = Mock(return_value=MarketRegime.RANGE)
    
    # Execute
    result = position_manager.monitor_positions()
    
    # Assert: SL modified
    mock_connector.modify_position.assert_called()
    
    # Assert: Regime adjustment action recorded
    assert len(result['actions']) > 0
    assert any(action['action'] == 'REGIME_ADJUSTMENT' for action in result['actions'])


def test_time_based_exit_range_4_hours(position_manager, mock_position, mock_connector, mock_storage, mock_regime_classifier):
    """
    Test time-based exit for stale RANGE position (>4 hours).
    
    Scenario: Position in RANGE for 5 hours without profit
    Expected: Position closed with reason "STALE_POSITION"
    """
    # Setup: Position 5 hours old in RANGE
    mock_position['profit'] = -5.0
    mock_connector.get_open_positions = Mock(return_value=[mock_position])
    
    # Mock metadata - 5 hours ago
    mock_storage.get_position_metadata = Mock(return_value={
        'ticket': 12345678,
        'initial_risk_usd': 100.0,
        'entry_regime': 'RANGE',
        'entry_time': (datetime.now() - timedelta(hours=5)).isoformat()
    })
    
    # Regime still RANGE
    mock_regime_classifier.classify_regime = Mock(return_value=MarketRegime.RANGE)
    
    # Execute
    result = position_manager.monitor_positions()
    
    # Assert: Position closed
    mock_connector.close_position.assert_called_once_with(12345678, "STALE_POSITION")
    
    # Assert: Action recorded
    assert len(result['actions']) == 1
    assert result['actions'][0]['action'] == 'TIME_EXIT'


def test_time_based_exit_trend_72_hours(position_manager, mock_position, mock_connector, mock_storage, mock_regime_classifier):
    """
    Test that TREND position can stay open for 72 hours.
    
    Scenario: Position in TREND for 50 hours
    Expected: Position NOT closed (max is 72 hours for TREND)
    """
    # Setup: Position 50 hours old in TREND
    mock_position['profit'] = -5.0
    mock_connector.get_open_positions = Mock(return_value=[mock_position])
    
    # Mock metadata - 50 hours ago
    mock_storage.get_position_metadata = Mock(return_value={
        'ticket': 12345678,
        'initial_risk_usd': 100.0,
        'entry_regime': 'TREND',
        'entry_time': (datetime.now() - timedelta(hours=50)).isoformat()
    })
    
    # Regime still TREND
    mock_regime_classifier.classify_regime = Mock(return_value=MarketRegime.TREND)
    
    # Execute
    result = position_manager.monitor_positions()
    
    # Assert: Position NOT closed (no TIME_EXIT action)
    assert not any(action['action'] == 'TIME_EXIT' for action in result['actions'])


def test_freeze_level_validation_eurusd(position_manager, mock_connector):
    """
    Test Freeze Level validation for EURUSD (5 pips minimum).
    
    Scenario: Trying to move SL to 2 pips from current price
    Expected: Validation fails (distance too small)
    """
    # Setup: Try to move SL too close
    current_price = 1.08500
    proposed_sl = 1.08480  # Only 2 pips away
    
    # Symbol info: 5 pips minimum
    symbol_info = {
        'trade_stops_level': 5,
        'point': 0.00001
    }
    mock_connector.get_symbol_info = Mock(return_value=symbol_info)
    mock_connector.get_current_price = Mock(return_value=current_price)
    
    # Execute validation
    is_valid = position_manager._validate_freeze_level('EURUSD', proposed_sl, None)
    
    # Assert: Validation failed (SL too close)
    assert is_valid is False


def test_freeze_level_validation_gbpjpy(position_manager, mock_connector):
    """
    Test Freeze Level validation for GBPJPY (10 pips minimum).
    
    Scenario: Trying to move SL to 5 pips from current price on GBPJPY
    Expected: Validation fails
    """
    # Setup: GBPJPY with higher freeze level
    current_price = 189.500
    proposed_sl = 189.450  # Only 5 pips away
    
    symbol_info = {
        'trade_stops_level': 10,  # 10 pips minimum for GBPJPY
        'point': 0.01  # JPY pairs have different point value
    }
    mock_connector.get_symbol_info = Mock(return_value=symbol_info)
    mock_connector.get_current_price = Mock(return_value=current_price)
    
    # Execute validation
    is_valid = position_manager._validate_freeze_level('GBPJPY', proposed_sl, None)
    
    # Assert: Validation failed
    assert is_valid is False


def test_modification_cooldown_prevents_spam(position_manager, mock_storage):
    """
    Test cooldown prevents spam modifications (5 min between modifications).
    
    Scenario: Last modification was 2 minutes ago
    Expected: Modification rejected (cooldown not expired)
    """
    # Setup: Last modification 2 minutes ago
    metadata = {
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=2)).isoformat(),
        'sl_modifications_count': 5
    }
    
    # Execute
    can_modify = position_manager._can_modify(metadata)
    
    # Assert: Modification blocked (cooldown not expired)
    assert can_modify is False


def test_max_10_modifications_per_day(position_manager, mock_storage):
    """
    Test daily modification limit (max 10 per day).
    
    Scenario: Position already modified 10 times today
    Expected: Modification rejected
    """
    # Setup: Already 10 modifications today
    metadata = {
        'last_modification_timestamp': (datetime.now() - timedelta(hours=1)).isoformat(),
        'sl_modifications_count': 10  # Max reached
    }
    
    # Execute
    can_modify = position_manager._can_modify(metadata)
    
    # Assert: Modification blocked (max reached)
    assert can_modify is False


def test_rollback_on_modification_failure(position_manager, mock_position, mock_connector, mock_storage):
    """
    Test metadata rollback when modification fails.
    
    Scenario: Broker rejects modification
    Expected: Metadata rolled back, function returns False
    """
    # Setup: Modification will fail
    mock_storage.get_position_metadata = Mock(return_value={
        'sl_modifications_count': 5,
        'last_modification_timestamp': (datetime.now() - timedelta(hours=1)).isoformat()
    })
    
    # Mock failure
    mock_connector.modify_position = Mock(return_value={'success': False, 'error': 'INVALID_STOPS'})
    
    # Execute
    result = position_manager._modify_with_validation(
        ticket=12345678,
        symbol='EURUSD',
        new_sl=1.08300,
        reason="TEST"
    )
    
    # Assert: Function returns False
    assert result is False
    
    # Assert: Rollback called
    mock_storage.rollback_position_modification.assert_called_once_with(12345678)


# Integration Test

def test_full_monitor_cycle_integration(position_manager, mock_position, mock_connector, mock_storage, mock_regime_classifier):
    """
    Integration test: Full monitor_positions() cycle.
    
    Scenario: System has 1 open position
    Expected: 
    - Regime checked
    - Max drawdown checked
    - Time-based exit checked
    - No errors
    """
    # Setup: One healthy position
    mock_position['profit'] = -10.0  # Below max drawdown
    mock_connector.get_open_positions = Mock(return_value=[mock_position])
    
    # Mock metadata - recent position
    mock_storage.get_position_metadata = Mock(return_value={
        'ticket': 12345678,
        'initial_risk_usd': 100.0,
        'entry_regime': 'TREND',
        'entry_time': (datetime.now() - timedelta(hours=1)).isoformat(),
        'sl_modifications_count': 0
    })
    
    # Execute - should not raise exceptions
    result = position_manager.monitor_positions()
    
    # Assert: Regime classifier was called
    mock_regime_classifier.classify_regime.assert_called_with('EURUSD')
    
    # Assert: Summary returned
    assert 'total_positions' in result
    assert result['total_positions'] == 1
