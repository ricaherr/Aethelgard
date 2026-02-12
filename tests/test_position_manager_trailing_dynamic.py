"""
Tests for PositionManager - Dynamic ATR Multiplier by Regime

FASE 4B: Trailing stop inteligente con multiplicador adaptativo

Tests TDD (Red-Green-Refactor):
1. TREND usa multiplicador 3.0x ATR (aguantar pullbacks)
2. VOLATILE usa multiplicador 1.5x ATR (asegurar rápido)
3. CRASH usa multiplicador 1.5x ATR (salir antes de reversión)
4. RANGE usa multiplicador 2.0x ATR (balance intermedio)
5. Activación con 1x ATR dinámico (no pips fijos)
6. Cambio de régimen actualiza multiplicador en tiempo real
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
    # Default: TREND regime
    classifier.classify_regime = Mock(return_value=MarketRegime.TREND)
    # ATR = 0.00050 = 50 points = 5 pips for EURUSD
    classifier.get_regime_data = Mock(return_value={'atr': 0.00050})
    return classifier


@pytest.fixture
def dynamic_trailing_config():
    """Config for dynamic trailing stop with regime-based multipliers"""
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
            'atr_multipliers_by_regime': {
                'TREND': 3.0,
                'RANGE': 2.0,
                'VOLATILE': 1.5,
                'CRASH': 1.5
            },
            'min_profit_atr_multiplier': 1.0,  # 1x ATR antes de activar
            'apply_after_breakeven': False
        }
    }


@pytest.fixture
def position_manager(mock_storage, mock_connector, mock_regime_classifier, dynamic_trailing_config):
    """Create PositionManager with dynamic trailing stop config"""
    return PositionManager(
        storage=mock_storage,
        connector=mock_connector,
        regime_classifier=mock_regime_classifier,
        config=dynamic_trailing_config
    )


# Tests FASE 4B.1

def test_trend_uses_wide_multiplier_3x(position_manager, mock_regime_classifier):
    """
    Test: TREND usa multiplicador amplio (3.0x ATR) para aguantar pullbacks
    
    Scenario:
    - Position BUY en TREND
    - Entry: 1.08500
    - Current price: 1.09000 (+50 pips profit)
    - ATR: 0.00050 (5 pips)
    - Regime: TREND → Multiplier 3.0x
    - Expected trailing SL = 1.09000 - (0.00050 * 3.0) = 1.08850
    
    Rationale: En TREND, pullbacks de 15 pips (3x ATR) son normales.
    Con 2.0x (FASE 4) te sacaría en pullback de 10 pips.
    """
    # Setup TREND regime
    mock_regime_classifier.classify_regime.return_value = MarketRegime.TREND
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.09000,  # +50 pips profit
        'sl': 1.08500,
        'tp': 1.09500,
        'profit': 50.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'entry_regime': 'TREND'
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.09000 - (0.00050 * 3.0) = 1.08850
    expected_sl = 1.08850
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"TREND should use 3.0x multiplier. Expected {expected_sl}, got {trailing_sl}"


def test_volatile_uses_tight_multiplier_1_5x(position_manager, mock_regime_classifier):
    """
    Test: VOLATILE usa multiplicador ajustado (1.5x ATR) para asegurar ganancias rápido
    
    Scenario:
    - Position BUY en VOLATILE
    - Current price: 1.09000
    - ATR: 0.00050 (5 pips)
    - Regime: VOLATILE → Multiplier 1.5x
    - Expected trailing SL = 1.09000 - (0.00050 * 1.5) = 1.08925
    
    Rationale: En VOLATILE, reversiones violentas pueden eliminar profit rápido.
    Usar 2.0x (10 pips) es demasiado riesgo. 1.5x (7.5 pips) es más seguro.
    """
    # Setup VOLATILE regime
    mock_regime_classifier.classify_regime.return_value = MarketRegime.VOLATILE
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.09000,
        'sl': 1.08500,
        'tp': 1.09500,
        'profit': 50.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'entry_regime': 'VOLATILE'
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.09000 - (0.00050 * 1.5) = 1.08925
    expected_sl = 1.08925
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"VOLATILE should use 1.5x multiplier. Expected {expected_sl}, got {trailing_sl}"


def test_crash_uses_tight_multiplier_1_5x(position_manager, mock_regime_classifier):
    """
    Test: CRASH usa multiplicador ajustado (1.5x ATR) para salir antes de reversión
    
    Scenario:
    - Position SELL en CRASH (precio cayendo)
    - Current price: 1.08000 (entry 1.08500, -50 pips = profit for SELL)
    - ATR: 0.00050
    - Regime: CRASH → Multiplier 1.5x
    - Expected trailing SL = 1.08000 + (0.00050 * 1.5) = 1.08075
    
    Rationale: En CRASH, reversiones son explosivas. Asegurar profit rápido.
    """
    # Setup CRASH regime
    mock_regime_classifier.classify_regime.return_value = MarketRegime.CRASH
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    position = {
        'ticket': 87654321,
        'symbol': 'EURUSD',
        'type': 'SELL',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08000,  # Profit for SELL
        'sl': 1.08500,
        'tp': 1.07500,
        'profit': 50.0
    }
    
    metadata = {
        'ticket': 87654321,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'entry_regime': 'CRASH'
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.08000 + (0.00050 * 1.5) = 1.08075
    expected_sl = 1.08075
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"CRASH should use 1.5x multiplier. Expected {expected_sl}, got {trailing_sl}"


def test_range_uses_balanced_multiplier_2x(position_manager, mock_regime_classifier):
    """
    Test: RANGE usa multiplicador balanceado (2.0x ATR)
    
    Scenario:
    - Position BUY en RANGE
    - ATR: 0.00050
    - Regime: RANGE → Multiplier 2.0x
    - Expected distance = 0.00050 * 2.0 = 0.00100 (10 pips)
    
    Rationale: En RANGE, ni muy amplio ni muy ajustado. Balance.
    """
    # Setup RANGE regime
    mock_regime_classifier.classify_regime.return_value = MarketRegime.RANGE
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08700,
        'sl': 1.08500,
        'tp': 1.09000,
        'profit': 20.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'entry_regime': 'RANGE'
    }
    
    # Execute
    trailing_sl = position_manager._calculate_trailing_stop_atr(position, metadata)
    
    # Assert: Trailing SL = 1.08700 - (0.00050 * 2.0) = 1.08600
    expected_sl = 1.08600
    assert trailing_sl is not None
    assert abs(trailing_sl - expected_sl) < 0.00001, \
        f"RANGE should use 2.0x multiplier. Expected {expected_sl}, got {trailing_sl}"


def test_activation_with_dynamic_1x_atr(position_manager, mock_regime_classifier, mock_connector):
    """
    Test: Activación con 1x ATR dinámico (no pips fijos)
    
    Scenario ANTES (FASE 4):
    - min_profit_pips: 10 (fijo)
    - ATR: 0.00050 (5 pips)
    - Profit: 8 pips → NO ACTIVA (< 10 pips) ❌ Demasiado estricto
    
    Scenario DESPUÉS (FASE 4B):
    - min_profit_atr_multiplier: 1.0
    - ATR: 0.00050 (5 pips)
    - Profit: 20 pips → SÍ ACTIVA (> 1x ATR = 5 pips) ✅ Adaptativo
    
    Rationale: Activación debe adaptarse a volatilidad, no ser fija.
    """
    # Use VOLATILE regime (1.5x multiplier)
    mock_regime_classifier.classify_regime.return_value = MarketRegime.VOLATILE
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    # Override symbol info to reduce freeze level requirement
    mock_connector.get_symbol_info.return_value = {
        'trade_stops_level': 10,  # 1 pip minimum
        'point': 0.00001,
        'digits': 5,
        'ask': 1.08720,
        'bid': 1.08700
    }
    
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.08700,  # +20 pips profit
        'sl': 1.08500,
        'tp': 1.09000,
        'profit': 20.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(minutes=30)).isoformat(),
        'entry_regime': 'VOLATILE'
    }
    
    # Execute
    should_apply, reason = position_manager._should_apply_trailing_stop(position, metadata)
    
    # Assert: Should activate (20 pips > 1x ATR = 5 pips)
    assert should_apply is True, \
        f"Expected activation with 20 pips (> 1x ATR = 5 pips). Reason: {reason}"


def test_regime_change_updates_multiplier(
    position_manager,
    mock_connector,
    mock_storage,
    mock_regime_classifier
):
    """
    Test: Cambio de régimen actualiza multiplicador en tiempo real
    
    Scenario:
    - Position abierta en TREND (multiplier 3.0x)
    - Régimen cambia a VOLATILE durante ejecución
    - Próximo trailing debe usar 1.5x (no 3.0x)
    
    Rationale: Trailing stop debe adaptarse a condiciones actuales, no históricas.
    """
    position = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'type': 'BUY',
        'entry_price': 1.08500,
        'volume': 0.10,
        'current_price': 1.09000,
        'sl': 1.08500,
        'tp': 1.09500,
        'profit': 50.0,
        'swap': 0.0,
        'commission': -2.0
    }
    
    metadata = {
        'ticket': 12345678,
        'entry_price': 1.08500,
        'entry_time': (datetime.now() - timedelta(hours=2)).isoformat(),
        'entry_regime': 'TREND',  # Entró en TREND
        'last_modification_timestamp': (datetime.now() - timedelta(minutes=10)).isoformat(),
        'commission_total': 2.0
    }
    
    # Mock responses
    mock_connector.get_open_positions.return_value = [position]
    mock_storage.get_position_metadata.return_value = metadata
    
    # CAMBIO DE RÉGIMEN: Ahora es VOLATILE (no TREND)
    mock_regime_classifier.classify_regime.return_value = MarketRegime.VOLATILE
    mock_regime_classifier.get_regime_data.return_value = {'atr': 0.00050}
    
    # Execute monitor cycle
    result = position_manager.monitor_positions()
    
    # Assert: modify_position llamado
    assert mock_connector.modify_position.called
    
    # Assert: New SL usa multiplier VOLATILE (1.5x), no TREND (3.0x)
    call_args = mock_connector.modify_position.call_args[0]
    new_sl = call_args[1]
    
    # Expected con VOLATILE 1.5x: 1.09000 - (0.00050 * 1.5) = 1.08925
    expected_volatile_sl = 1.08925
    # Expected con TREND 3.0x: 1.09000 - (0.00050 * 3.0) = 1.08850
    expected_trend_sl = 1.08850
    
    # Debe estar cerca de VOLATILE (1.08925), NO de TREND (1.08850)
    assert abs(new_sl - expected_volatile_sl) < abs(new_sl - expected_trend_sl), \
        f"Expected VOLATILE multiplier (SL ~{expected_volatile_sl}), got {new_sl}"
