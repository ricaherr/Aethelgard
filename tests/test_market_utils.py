"""
Tests for Market Utilities and Agnostic Rounding Logic.
"""
import pytest
from types import SimpleNamespace
from core_brain.market_utils import normalize_price, normalize_volume, calculate_pip_size
from core_brain.instrument_manager import InstrumentManager

# Using MockSymbolInfo from conftest.py

def test_normalize_price_with_broker_digits():
    # Case: Broker provides digits
    info = MockSymbolInfo(digits=5)
    assert normalize_price(1.080009, info) == 1.08001
    
    info_jpy = MockSymbolInfo(digits=3)
    assert normalize_price(150.12345, info_jpy) == 150.123

def test_normalize_price_fallback_to_point():
    # Case: No digits, but point exists
    info = MockSymbolInfo(point=0.001) # JPY-like
    assert normalize_price(150.12345, info) == 150.123
    
    info_fx = MockSymbolInfo(point=0.00001)
    assert normalize_price(1.080009, info_fx) == 1.08001

def test_normalize_price_fallback_to_instrument_manager():
    # Case: No broker info, use InstrumentManager category fallback
    im = InstrumentManager()
    assert normalize_price(1.080009, symbol="EURUSD", instrument_manager=im) == 1.08001
    assert normalize_price(150.12345, symbol="USDJPY", instrument_manager=im) == 150.123
    assert normalize_price(2050.1234, symbol="XAUUSD", instrument_manager=im) == 2050.12

def test_normalize_volume():
    info = MockSymbolInfo(v_min=0.1, v_max=10.0, v_step=0.1)
    assert normalize_volume(0.55, info) == pytest.approx(0.6)
    assert normalize_volume(0.05, info) == pytest.approx(0.1) # Below min
    assert normalize_volume(15.0, info) == pytest.approx(10.0) # Above max

def test_calculate_pip_size_agnostic():
    im = InstrumentManager()
    
    # Forex Standard (5 digits) -> Point=0.00001, Pip=0.0001
    info_fx = MockSymbolInfo(digits=5, point=0.00001)
    assert calculate_pip_size(info_fx, "EURUSD", im) == pytest.approx(0.0001)
    
    # JPY (3 digits) -> Point=0.001, Pip=0.01
    info_jpy = MockSymbolInfo(digits=3, point=0.001)
    assert calculate_pip_size(info_jpy, "USDJPY", im) == pytest.approx(0.01)
    
    # Metals (2 digits) -> Point=0.01, Pip=0.01
    info_gold = MockSymbolInfo(digits=2, point=0.01)
    assert calculate_pip_size(info_gold, "XAUUSD", im) == pytest.approx(0.01)

def test_instrument_manager_default_precision():
    im = InstrumentManager()
    assert im.get_default_precision("EURUSD") == 5
    assert im.get_default_precision("USDJPY") == 3
    assert im.get_default_precision("BTCUSD") == 2
    assert im.get_default_precision("US30") == 2
