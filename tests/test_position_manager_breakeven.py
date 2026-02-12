"""
Tests for PositionManager - Breakeven REAL

FASE 3: Breakeven real considerando commissions, swap y spread

Tests TDD (Red-Green-Refactor):
1. Calcular breakeven real con commissions
2. Incluir swap acumulado en cálculo
3. Incluir spread en cálculo
4. Validar distancia mínima (5 pips)
5. NO modificar si profit < breakeven_real
6. Modificar SL a breakeven_real cuando profit >threshold
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from decimal import Decimal

from core_brain.position_manager import PositionManager
from models.signal import MarketRegime


# Fixtures

@pytest.fixture
def mock_storage():
    """Mock StorageManager"""
    storage = Mock()
    storage.get_position_metadata = Mock(return_value={})
    storage.update_position_metadata = Mock(return_value=True)
    return storage


@pytest.fixture
def mock_connector():
    """Mock MT5Connector"""
    connector = Mock()
    connector.get_open_positions = Mock(return_value=[])
    connector.get_symbol_info = Mock(return_value={
        'trade_stops_level': 50,
        'point': 0.00001,
        'digits': 5,
        'ask': 1.08520,
        'bid': 1.08500
    })
    connector.get_current_price = Mock(return_value=1.08600)
    # modify_position should return dict with success key
    connector.modify_position = Mock(return_value={'success': True})
    return connector


@pytest.fixture
def mock_regime_classifier():
    """Mock RegimeClassifier"""
    classifier = Mock()
    classifier.classify_regime = Mock(return_value=MarketRegime.TREND)
    return classifier


@pytest.fixture
def breakeven_config():
    """Config for breakeven with all costs enabled"""
    return {
        'max_drawdown_multiplier': 2.0,
        'modification_cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'time_based_exit_enabled': True,
        'stale_position_thresholds': {'TREND': 72, 'RANGE': 4},
        'breakeven': {
            'enabled': True,
            'min_profit_distance_pips': 5,
            'min_time_minutes': 15,
            'include_commission': True,
            'include_swap': True,
            'include_spread': True
        }
    }


@pytest.fixture
def position_manager(mock_storage, mock_connector, mock_regime_classifier, breakeven_config):
    """Create PositionManager with breakeven config"""
    return PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=breakeven_config
    )


# Tests FASE 3.1

def test_calculate_breakeven_real_with_commissions(mock_storage, mock_connector, mock_regime_classifier):
    """
    Test: Calcular breakeven real incluyendo SOLO commissions (sin swap ni spread)
    
    Scenario:
    - Entry: 1.08500 (BUY)
    - Volume: 0.10 lots
    - Commission: $7.00 (ida) + $7.00 (vuelta) = $14 total
    - Point value: $1 per pip (EURUSD 0.01 lots)
    
    Expected:
    - Breakeven real = 1.08500 + (14 / (0.10 * 10)) = 1.08514 (14 pips)
    """
    # Create position_manager with commission-only config
    config = {
        'max_drawdown_multiplier': 2.0,
        'cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'breakeven': {
            'enabled': True,
            'min_profit_distance_pips': 5,
            'min_time_minutes': 15,
            'include_commission': True,
            'include_swap': False,  # Disabled for this test
            'include_spread': False  # Disabled for this test
        }
    }
    position_manager = PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=config
    )
    
    # Setup position data
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08600,  # +10 pips profit
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 10.0,  # $10 gross profit
        'swap': 0.0,  # No swap yet
        'commission': -14.0  # -$7 open, -$7 close
    }
    
    # Metadata has commission
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'commission_total': 14.0  # Both sides
    }
    
    # Execute calculation
    breakeven_price = position_manager._calculate_breakeven_real(position, metadata)
    
    # Assert: Breakeven includes commission cost
    # Pip value for 0.10 lots = $1.00 per pip
    # 14 pips = $14 / $1 = 14 pips
    # breakeven = 1.08500 + 0.00140 = 1.08640
    expected_breakeven = 1.08640
    assert abs(breakeven_price - expected_breakeven) < 0.00001, \
        f"Expected {expected_breakeven}, got {breakeven_price}"


def test_calculate_breakeven_real_includes_swap(mock_storage, mock_connector, mock_regime_classifier):
    """
    Test: Incluir swap acumulado en cálculo de breakeven (commission + swap, sin spread)
    
    Scenario:
    - Entry: 1.08500    - Volume: 0.10 lots
    - Commission: $14
    - Swap: -$3.50 (negative = cost)
    
    Expected:
    - Total cost = $14 + $3.50 = $17.50
    - Breakeven = 1.08500 + 17.5 pips
    """
    # Create position_manager with commission+swap config
    config = {
        'max_drawdown_multiplier': 2.0,
        'cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'breakeven': {
            'enabled': True,
            'min_profit_distance_pips': 5,
            'min_time_minutes': 15,
            'include_commission': True,
            'include_swap': True,  # Enabled for this test
            'include_spread': False  # Disabled for this test
        }
    }
    position_manager = PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=config
    )
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08700,
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 20.0,
        'swap': -3.50,  # Negative swap (cost)
        'commission': -14.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(days=3)).isoformat(),
        'commission_total': 14.0
    }
    
    # Execute
    breakeven_price = position_manager._calculate_breakeven_real(position, metadata)
    
    # Assert: Breakeven includes commission + swap
    # Total cost: $14 + $3.50 = $17.50
    # Pip value: $1.00 per pip
    # 17.5 pips = 1.08500 + 0.00175 = 1.08675
    expected_breakeven = 1.08675
    assert abs(breakeven_price - expected_breakeven) < 0.00001


def test_calculate_breakeven_real_includes_spread(mock_storage, mock_connector, mock_regime_classifier):
    """
    Test: Incluir spread en cálculo de breakeven (commission + spread, sin swap)
    
    Scenario:
    - Entry: 1.08500 (BUY at ASK)
    - Current Ask: 1.08520, Bid: 1.08500
    - Spread: 20 points = 2 pips
    - Volume: 0.10 lots
    - Commission: $14
    - Swap: $0
    
    Expected:
    - Spread cost = 2 pips * $1 per pip = $2.00 (for 0.10 lots)
    - Total cost = $14 + $2.00 = $16.00
    - Breakeven = 1.08500 + 16 pips = 1.08516
    """
    # Create position_manager with commission+spread config
    config = {
        'max_drawdown_multiplier': 2.0,
        'cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'breakeven': {
            'enabled': True,
            'min_profit_distance_pips': 5,
            'min_time_minutes': 15,
            'include_commission': True,
            'include_swap': False,  # Disabled for this test
            'include_spread': True  # Enabled for this test
        }
    }
    position_manager = PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=config
    )
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08600,
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 10.0,
        'swap': 0.0,
        'commission': -14.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'commission_total': 14.0
    }
    
    # Mock symbol info with spread
    mock_connector.get_symbol_info.return_value = {
        'ask': 1.08520,
        'bid': 1.08500,
        'point': 0.00001
    }
    
    # Execute
    breakeven_price = position_manager._calculate_breakeven_real(position, metadata)
    
    # Assert: Breakeven includes commission + spread
    # Spread cost: 2 pips * $1 per pip = $2.00
    # Total: ($14 + $2) / $1 per pip = 16 pips
    # Breakeven: 1.08500 + 0.00160 = 1.08660
    expected_breakeven = 1.08660
    assert abs(breakeven_price - expected_breakeven) < 0.00001


def test_should_move_to_breakeven_validates_min_distance(position_manager):
    """
    Test: Validar distancia mínima (5 pips) antes de mover a breakeven
    
    Scenario:
    - Entry: 1.08500
    - Commission: $1.0 = 1 pip cost
    - Breakeven real: 1.08500 + 1 pip = 1.08600
    - Current price: 1.08700 (+20 pips from entry, +10 pips from breakeven)
    - Distance to breakeven: 10 pips (well above min 5 pips + freeze level 5.5 pips)
    
    Expected: Should return True (cumple mínimo y freeze level)
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08700,  # Breakeven (1.08600) + 10 pips = well above freeze level
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 20.0,  # $20 gross profit
        'swap': 0.0,
        'commission': -1.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'commission_total': 1.0
    }
    
    # Execute
    should_move, reason = position_manager._should_move_to_breakeven(position, metadata)
    
    # Assert: Should move (distance >= 5 pips AND passes freeze level)
    assert should_move is True, f"Expected True, got False. Reason: {reason}"


def test_should_move_to_breakeven_rejects_insufficient_profit(position_manager):
    """
    Test: NO modificar si profit < breakeven_real + min_distance
    
    Scenario:
    - Current profit: +3 pips
    - Breakeven real: entry + 1 pip
    - Distance: 2 pips (< 5 pips minimum)
    
   Expected: Should return False (distancia insuficiente)
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08530,  # +3 pips
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 3.0,
        'swap': 0.0,
        'commission': -1.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'commission_total': 1.0
    }
    
    # Execute
    should_move, reason = position_manager._should_move_to_breakeven(position, metadata)
    
    # Assert: Should NOT move (distancia < 5 pips)
    assert should_move is False
    assert "insufficient" in reason.lower() or "distance" in reason.lower()


def test_monitor_positions_moves_sl_to_breakeven_real(
    position_manager,
    mock_connector,
    mock_storage
):
    """
    Test: Modificar SL a breakeven_real cuando profit > threshold
    
    Scenario:
    - Entry: 1.08500
    - Commission: $14 = 14 pips
    - Swap: -$1 = 1 pip
    - Spread: ~$2 = 2 pips
    - Breakeven real: 1.08500 + 17 pips = 1.08670
    - Current price: 1.08800 (+30 pips from entry, +13 pips from breakeven)
    - Distance: 13 pips (well above min 5 pips)
    
    Expected:
    - modify_position() llamado con new_sl = 1.08670
    - Action logged como "BREAKEVEN_REAL"
    """
    # Setup position with good profit
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08800,  # +30 pips from entry, +13 pips from breakeven
        'sl': 1.08200,  # Current SL below breakeven
        'tp': 1.09000,
        'profit': 30.0,  # $30 gross profit
        'swap': -1.0,
        'commission': -14.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'commission_total': 14.0,
        'initial_risk_usd': 30.0,
        'entry_regime': 'TREND'
    }
    
    # Mock connector responses
    mock_connector.get_open_positions.return_value = [position]
    mock_storage.get_position_metadata.return_value = metadata
    
    # Execute monitor cycle
    result = position_manager.monitor_positions()
    
    # Assert: Position modified
    assert mock_connector.modify_position.called
    
    # Assert: Action recorded
    assert len(result['actions']) > 0
    breakeven_actions = [a for a in result['actions'] if a['action'] == 'BREAKEVEN_REAL']
    assert len(breakeven_actions) == 1
    
    # Assert: New SL is at breakeven_real (entry + costs)
    call_args = mock_connector.modify_position.call_args[0]
    ticket_arg = call_args[0]
    new_sl = call_args[1]
    
    assert ticket_arg == 12345678
    # Breakeven real should be > entry price (includes costs)
    assert new_sl > 1.08500
    # But should be < current price
    assert new_sl < 1.08700
