"""
Tests for dynamic spread cost calculation in breakeven (multi-asset).

Test coverage:
- Forex (EURUSD): contract_size=100,000
- Metals (XAUUSD): contract_size=100
- Crypto (BTCUSD): contract_size=1
- Indices (US30): contract_size=10

Expected behavior:
- Spread cost should use dynamic contract_size from symbol_info
- Breakeven should be accurate for all asset types
- No hardcoded 100,000 multiplier
"""

import pytest
from unittest.mock import MagicMock
from core_brain.position_manager import PositionManager
from conftest import MockSymbolInfo


@pytest.fixture
def mock_connector():
    """Creates a mock connector with configurable symbol info"""
    connector = MagicMock()
    connector.get_positions = MagicMock(return_value=[])
    connector.get_account_info = MagicMock(return_value=MagicMock(balance=10000.0))
    return connector


@pytest.fixture
def mock_storage():
    """Creates a mock storage manager"""
    storage = MagicMock()
    storage.get_all_positions = MagicMock(return_value=[])
    return storage


@pytest.fixture
def mock_regime_classifier():
    """Creates a mock regime classifier"""
    classifier = MagicMock()
    classifier.get_current_regime = MagicMock(return_value="TREND")
    return classifier


@pytest.fixture
def mock_config():
    """Standard configuration"""
    return {
        "check_interval_seconds": 10,
        "max_consecutive_losses": 3,
        "breakeven": {
            "enabled": True,
            "trigger_rr": 1.0,
            "preserve_pips": 2.0,
            "include_commission": True,
            "include_swap": True,
            "include_spread": True
        }
    }


def test_eurusd_breakeven_spread_cost(mock_connector, mock_storage, mock_regime_classifier, mock_config):
    """
    EURUSD breakeven should use contract_size=100,000
    
    Given: EURUSD, contract_size=100,000, volume=0.10, spread=1 pip, commission=$7
    Expected spread cost: 1.0 * 0.10 * 0.00001 * 100,000 = $1.00
    Total cost: $7 + $1 = $8
    Breakeven offset: $8 / ($10 per pip * 0.10 lots) = 8 pips
    """
    symbol_info = MockSymbolInfo(
        symbol='EURUSD',
        contract_size=100000,
        point=0.00001,
        ask=1.10010,
        bid=1.10000
    )
    mock_connector.get_symbol_info = MagicMock(return_value=symbol_info)
    
    position = {
        'symbol': 'EURUSD',
        'type': 0,
        'volume': 0.10,
        'price_open': 1.10000,
        'sl': 1.09800,
        'tp': 1.10200,
        'commission': -7.0,
        'swap': 0.0,
        'profit': 15.0,
        'ticket': 12345
    }
    
    metadata = {
        'entry_price': 1.10000,
        'commission_total': 7.0
    }
    
    manager = PositionManager(
        connector=mock_connector,
        storage=mock_storage,
        regime_classifier=mock_regime_classifier,
        config=mock_config
    )
    
    breakeven_price = manager._calculate_breakeven_real(position, metadata)
    
    assert breakeven_price is not None
    expected_breakeven = 1.10080
    assert abs(breakeven_price - expected_breakeven) < 0.00001


def test_xauusd_breakeven_spread_cost(mock_connector, mock_storage, mock_regime_classifier, mock_config):
    """
    XAUUSD (Gold) breakeven should use contract_size=100
    
    Given: XAUUSD, contract_size=100, volume=0.10, spread=0.50, commission=$7
    Expected spread cost: 50 points * 0.10 * 0.01 * 100 = $5.00
    Total cost: $7 + $5 = $12
    Pip value: 0.10 * 100 * 0.01 = $0.10 per point
    Breakeven offset: $12 / $0.10 = 120 points = $1.20
    """
    symbol_info = MockSymbolInfo(
        symbol='XAUUSD',
        contract_size=100,
        point=0.01,
        ask=2050.50,
        bid=2050.00
    )
    mock_connector.get_symbol_info = MagicMock(return_value=symbol_info)
    
    position = {
        'symbol': 'XAUUSD',
        'type': 0,
        'volume': 0.10,
        'price_open': 2050.00,
        'sl': 2040.00,
        'tp': 2060.00,
        'commission': -7.0,
        'swap': 0.0,
        'profit': 15.0,
        'ticket': 12346
    }
    
    metadata = {
        'entry_price': 2050.00,
        'commission_total': 7.0
    }
    
    manager = PositionManager(
        connector=mock_connector,
        storage=mock_storage,
        regime_classifier=mock_regime_classifier,
        config=mock_config
    )
    
    breakeven_price = manager._calculate_breakeven_real(position, metadata)
    
    assert breakeven_price is not None
    expected_breakeven = 2051.20
    assert abs(breakeven_price - expected_breakeven) < 0.01


def test_btcusd_breakeven_spread_cost(mock_connector, mock_storage, mock_regime_classifier, mock_config):
    """
    BTCUSD (Crypto) breakeven should use contract_size=1
    
    Given: BTCUSD, contract_size=1, volume=0.10, spread=$10, commission=$7
    Expected spread cost: 10 points * 0.10 * 1.0 * 1 = $1.00
    Total cost: $7 + $1 = $8
    Pip value: 0.10 * 1 * 1.0 = $0.10 per point
    Breakeven offset: $8 / $0.10 = 80 points = $80
    """
    symbol_info = MockSymbolInfo(
        symbol='BTCUSD',
        contract_size=1,
        point=1.0,
        ask=50010.0,
        bid=50000.0
    )
    mock_connector.get_symbol_info = MagicMock(return_value=symbol_info)
    
    position = {
        'symbol': 'BTCUSD',
        'type': 0,
        'volume': 0.10,
        'price_open': 50000.0,
        'sl': 49500.0,
        'tp': 50500.0,
        'commission': -7.0,
        'swap': 0.0,
        'profit': 50.0,
        'ticket': 12347
    }
    
    metadata = {
        'entry_price': 50000.0,
        'commission_total': 7.0
    }
    
    manager = PositionManager(
        connector=mock_connector,
        storage=mock_storage,
        regime_classifier=mock_regime_classifier,
        config=mock_config
    )
    
    breakeven_price = manager._calculate_breakeven_real(position, metadata)
    
    assert breakeven_price is not None
    expected_breakeven = 50080.0
    assert abs(breakeven_price - expected_breakeven) < 1.0


def test_us30_breakeven_spread_cost(mock_connector, mock_storage, mock_regime_classifier, mock_config):
    """
    US30 (Index) breakeven should use contract_size=10
    
    Given: US30, contract_size=10, volume=0.10, spread=2 points, commission=$7
    Expected spread cost: 2 * 0.10 * 1.0 * 10 = $2.00
    Total cost: $7 + $2 = $9
    Pip value: 0.10 * 10 * 1.0 = $1.00 per point
    Breakeven offset: $9 / $1.00 = 9 points
    """
    symbol_info = MockSymbolInfo(
        symbol='US30',
        contract_size=10,
        point=1.0,
        ask=39002.0,
        bid=39000.0
    )
    mock_connector.get_symbol_info = MagicMock(return_value=symbol_info)
    
    position = {
        'symbol': 'US30',
        'type': 0,
        'volume': 0.10,
        'price_open': 39000.0,
        'sl': 38900.0,
        'tp': 39100.0,
        'commission': -7.0,
        'swap': 0.0,
        'profit': 20.0,
        'ticket': 12348
    }
    
    metadata = {
        'entry_price': 39000.0,
        'commission_total': 7.0
    }
    
    manager = PositionManager(
        connector=mock_connector,
        storage=mock_storage,
        regime_classifier=mock_regime_classifier,
        config=mock_config
    )
    
    breakeven_price = manager._calculate_breakeven_real(position, metadata)
    
    assert breakeven_price is not None
    expected_breakeven = 39009.0
    assert abs(breakeven_price - expected_breakeven) < 1.0
