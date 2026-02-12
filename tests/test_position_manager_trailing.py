"""
Tests for PositionManager - ATR-Based Trailing Stop

FASE 4: Trailing stop dinámico que se adapta a volatilidad (ATR)

Tests TDD (Red-Green-Refactor):
1. Calcular trailing stop con ATR para BUY
2. Calcular trailing stop con ATR para SELL
3. Trailing stop solo mejora SL (nunca empeora)
4. Requiere profit mínimo (10 pips)
5. Respeta cooldown entre modificaciones
6. Respeta freeze level
7. Integración en monitor_positions()
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
    connector.modify_position = Mock(return_value={'success': True})
    return connector


@pytest.fixture
def mock_regime_classifier():
    """Mock RegimeClassifier with ATR data"""
    classifier = Mock()
    classifier.classify_regime = Mock(return_value=MarketRegime.TREND)
    # ATR = 0.00050 = 50 points = 5 pips for EURUSD
    classifier.get_regime_data = Mock(return_value={'atr': 0.00050})
    return classifier


@pytest.fixture
def trailing_config():
    """Config for trailing stop with ATR"""
    return {
        'max_drawdown_multiplier': 2.0,
        'cooldown_seconds': 300,
        'max_modifications_per_day': 10,
        'time_based_exit_enabled': True,
        'stale_thresholds_hours': {'TREND': 72, 'RANGE': 4},
        'breakeven': {
            'enabled': True,
            'min_profit_distance_pips': 5,
            'min_time_minutes': 15,
            'include_commission': True,
            'include_swap': True,
            'include_spread': True
        },
        'trailing_stop': {
            'enabled': True,
            'atr_multiplier': 2.0,
            'min_profit_pips': 10,
            'apply_after_breakeven': False  # Apply always if profit > min
        }
    }


@pytest.fixture
def position_manager(mock_storage, mock_connector, mock_regime_classifier, trailing_config):
    """Create PositionManager with trailing stop config"""
    return PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=trailing_config
    )


# Tests FASE 4.1

def test_calculate_trailing_stop_atr_for_buy(position_manager, mock_regime_classifier):
    """
    Test: Calcular trailing stop basado en ATR para posición BUY
    
    Scenario:
    - Position BUY en profit
    - Entry: 1.08500
    - Current price: 1.08800 (+30 pips)
    - ATR: 0.00050 (5 pips)
    - Multiplier: 2.0
    - Trailing SL = current_price - (ATR * 2.0) = 1.08800 - 0.00100 = 1.08700
    
    Expected:
    - Trailing SL debe estar 10 pips (2*ATR) debajo del precio actual
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08800,
        'sl': 1.08500,  # Current SL at breakeven
        'tp': 1.09000,
        'profit': 30.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat()
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.08800 - (0.00050 * 2.0) = 1.08700
    expected_sl = 1.08700
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"Expected {expected_sl}, got {trailing_sl}"


def test_calculate_trailing_stop_atr_for_sell(position_manager, mock_regime_classifier):
    """
    Test: Calcular trailing stop basado en ATR para posición SELL
    
    Scenario:
    - Position SELL en profit
    - Entry: 1.08500
    - Current price: 1.08200 (-30 pips = profit for SELL)
    - ATR: 0.00050 (5 pips)
    - Multiplier: 2.0
    - Trailing SL = current_price + (ATR * 2.0) = 1.08200 + 0.00100 = 1.08300
    
    Expected:
    - Trailing SL debe estar 10 pips (2*ATR) arriba del precio actual
    """
    position = {
        'ticket': 87654321,
        'symbol': 'EURUSD',
        'type': 'SELL',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08200,  # Price bajó = profit for SELL
        'sl': 1.08500,  # Current SL at breakeven
        'tp': 1.08000,
        'profit': 30.0
    }
    
    metadata = {
        'ticket': 87654321,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat()
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.08200 + (0.00050 * 2.0) = 1.08300
    expected_sl = 1.08300
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"Expected {expected_sl}, got {trailing_sl}"


def test_trailing_stop_only_improves_sl_for_buy(position_manager, mock_regime_classifier):
    """
    Test: Trailing stop solo mueve SL si MEJORA la posición (BUY)
    
    Scenario:
    - Position BUY
    - Current SL: 1.08700 (ya está alto)
    - Current price: 1.08750 (pequeño profit)
    - Calculated trailing SL: 1.08650 (price - 2*ATR)
    - 1.08650 < 1.08700 = NO MEJORÍA
    
    Expected:
    - _should_apply_trailing_stop() debe retornar False
    - Reason: New SL no mejora al actual
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08750,
        'sl': 1.08700,  # SL already high
        'tp': 1.09000,
        'profit': 25.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=10)).isoformat()
    }
    
    # Execute
    should_apply, reason = position_manager._should_apply_trailing_stop(position, metadata)
    
    # Assert: Should NOT apply (new SL worse than current)
    assert should_apply is False
    assert "does not improve" in reason.lower() or "no improvement" in reason.lower()


def test_trailing_stop_only_improves_sl_for_sell(position_manager, mock_regime_classifier):
    """
    Test: Trailing stop solo mueve SL si MEJORA la posición (SELL)
    
    Scenario:
    - Position SELL
    - Current SL: 1.08300 (ya está bajo)
    - Current price: 1.08250
    - Calculated trailing SL: 1.08350 (price + 2*ATR)
    - 1.08350 > 1.08300 = NO MEJORÍA (para SELL, mejor SL = más bajo)
    
    Expected:
    - _should_apply_trailing_stop() debe retornar False
    """
    position = {
        'ticket': 87654321,
        'symbol': 'EURUSD',
        'type': 'SELL',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08250,
        'sl': 1.08300,  # SL already low (good for SELL)
        'tp': 1.08000,
        'profit': 25.0
    }
    
    metadata = {
        'ticket': 87654321,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=10)).isoformat()
    }
    
    # Execute
    should_apply, reason = position_manager._should_apply_trailing_stop(position, metadata)
    
    # Assert: Should NOT apply
    assert should_apply is False


def test_trailing_stop_requires_min_profit(position_manager):
    """
    Test: Requiere profit mínimo (10 pips) para activar trailing
    
    Scenario:
    - Position con solo 5 pips de profit
    - Min profit required: 10 pips
    
    Expected:
    - _should_apply_trailing_stop() retorna False
    - Reason: Insufficient profit
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08550,  # Only 5 pips profit
        'sl': 1.08200,
        'tp': 1.09000,
        'profit': 5.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat()
    }
    
    # Execute
    should_apply, reason = position_manager._should_apply_trailing_stop(position, metadata)
    
    # Assert: Should NOT apply (profit < 10 pips)
    assert should_apply is False
    assert "insufficient profit" in reason.lower() or "min profit" in reason.lower()


def test_trailing_stop_respects_cooldown(position_manager):
    """
    Test: Respeta cooldown entre modificaciones (5 minutos)
    
    Scenario:
    - Position con profit adecuado
    - Última modificación hace 2 minutos
    - Cooldown: 5 minutos (300 segundos)
    
    Expected:
    - _should_apply_trailing_stop() retorna False
    - Reason: Cooldown not elapsed
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08700,  # 20 pips profit
        'sl': 1.08500,
        'tp': 1.09000,
        'profit': 20.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=2)).isoformat()
    }
    
    # Execute
    should_apply, reason = position_manager._should_apply_trailing_stop(position, metadata)
    
    # Assert: Should NOT apply (cooldown active)
    assert should_apply is False
    assert "cooldown" in reason.lower()


def test_monitor_positions_applies_trailing_stop(
    position_manager,
    mock_connector,
    mock_storage,
    mock_regime_classifier
):
    """
    Test: Integración - monitor_positions() aplica trailing stop
    
    Scenario:
    - Position BUY con 40 pips profit
    - Current SL: 1.08500 (breakeven)
    - Current price: 1.08900
    - ATR: 0.00050, Multiplier: 2.0
    - Calculated trailing SL: 1.08800 (mejora al actual)
    - Cooldown elapsed, profit > 10 pips
    
    Expected:
    - modify_position() llamado con new_sl = 1.08800
    - Action logged como "TRAILING_STOP_ATR"
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08900,  # 40 pips profit
        'sl': 1.08500,  # Current SL at breakeven
        'tp': 1.09000,
        'profit': 40.0,
        'swap': 0.0,
        'commission': -2.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=10)).isoformat(),
        'commission_total': 2.0
    }
    
    # Mock responses
    mock_connector.get_open_positions.return_value = [position]
    mock_storage.get_position_metadata.return_value = metadata
    # ATR = 0.00050 (5 pips)
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    # Execute
    result = position_manager.monitor_positions()
    
    # Assert: Position modified
    assert mock_connector.modify_position.called
    
    # Assert: Action recorded
    assert len(result['actions']) > 0
    trailing_actions = [a for a in result['actions'] if a['action'] == 'TRAILING_STOP_ATR']
    assert len(trailing_actions) >= 1
    
    # Assert: New SL is trailing (price - 2*ATR)
    call_args = mock_connector.modify_position.call_args[0]
    ticket_arg = call_args[0]
    new_sl = call_args[1]
    
    assert ticket_arg == 12345678
    # Trailing SL should be around 1.08800 (1.08900 - 0.00100)
    expected_sl = 1.08800
    assert abs(new_sl - expected_sl) < 0.00010, \
        f"Expected SL ~{expected_sl}, got {new_sl}"
