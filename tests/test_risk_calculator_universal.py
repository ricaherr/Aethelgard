"""
Tests for RiskCalculator - Universal risk calculation for multi-asset trading.

Tests cover:
- Forex major pairs (EURUSD, GBPUSD)
- Forex JPY pairs (USDJPY)
- Forex cross pairs (EURGBP, EURCHF)
- Precious metals (XAUUSD, XAGUSD)
- Crypto (BTCUSD)
- Indices (US30)
"""
import pytest
from unittest.mock import Mock, MagicMock
from core_brain.risk_calculator import RiskCalculator


class MockSymbolInfo:
    """Mock MT5 SymbolInfo for testing"""
    def __init__(self, contract_size, trade_mode=None):
        self.trade_contract_size = contract_size
        self.trade_mode = trade_mode or 4  # TRADE_MODE_FULL


class MockTick:
    """Mock MT5 Tick for testing"""
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask


@pytest.fixture
def mock_connector():
    """Mock MT5Connector with realistic symbol info"""
    connector = Mock()
    
    # Setup symbol info for different asset types
    symbol_info_map = {
        'EURUSD': MockSymbolInfo(100000),    # Standard Forex
        'GBPUSD': MockSymbolInfo(100000),
        'USDJPY': MockSymbolInfo(100000),
        'USDCAD': MockSymbolInfo(100000),
        'EURGBP': MockSymbolInfo(100000),
        'EURCHF': MockSymbolInfo(100000),
        'XAUUSD': MockSymbolInfo(100),       # Gold - 100 oz
        'XAGUSD': MockSymbolInfo(5000),      # Silver - 5000 oz
        'BTCUSD': MockSymbolInfo(1),         # Bitcoin - 1 BTC
        'US30': MockSymbolInfo(10),          # Dow Jones Index
    }
    
    # Setup current prices (realistic values for conversion)
    price_map = {
        'EURUSD': MockTick(1.0800, 1.0802),
        'GBPUSD': MockTick(1.2600, 1.2602),
        'USDJPY': MockTick(149.50, 149.52),
        'USDCAD': MockTick(1.3500, 1.3502),
        'USDCHF': MockTick(0.8800, 0.8802),
        'EURGBP': MockTick(0.8570, 0.8572),
        'EURCHF': MockTick(0.9500, 0.9502),
        'XAUUSD': MockTick(2050.00, 2050.50),
        'XAGUSD': MockTick(24.00, 24.02),
        'BTCUSD': MockTick(52000.00, 52010.00),
        'US30': MockTick(38500.00, 38505.00),
    }
    
    def get_symbol_info_side_effect(symbol):
        return symbol_info_map.get(symbol)
    
    def get_current_price_side_effect(symbol):
        tick = price_map.get(symbol)
        return tick.bid if tick else None
    
    connector.get_symbol_info = Mock(side_effect=get_symbol_info_side_effect)
    connector.get_current_price = Mock(side_effect=get_current_price_side_effect)
    
    return connector


@pytest.fixture
def calculator(mock_connector):
    """RiskCalculator instance with mocked connector"""
    return RiskCalculator(mock_connector)


# ============================================================================
# FOREX MAJOR PAIRS (Quote Currency = USD)
# ============================================================================

def test_eurusd_risk_calculation(calculator):
    """
    EURUSD: Quote=USD, no conversion needed.
    Entry: 1.0800, SL: 1.0750, Volume: 0.1 lots
    Risk = (0.0050) * 0.1 * 100,000 = $50 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='EURUSD',
        entry_price=1.0800,
        stop_loss=1.0750,
        volume=0.1
    )
    expected = 50.0  # (0.0050) * 0.1 * 100,000
    assert abs(risk_usd - expected) < 0.01, f"Expected {expected}, got {risk_usd}"


def test_gbpusd_risk_calculation(calculator):
    """
    GBPUSD: Quote=USD, no conversion needed.
    Entry: 1.2600, SL: 1.2550, Volume: 0.2 lots
    Risk = (0.0050) * 0.2 * 100,000 = $100 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='GBPUSD',
        entry_price=1.2600,
        stop_loss=1.2550,
        volume=0.2
    )
    expected = 100.0
    assert abs(risk_usd - expected) < 0.01


# ============================================================================
# FOREX INVERSE PAIRS (Base Currency = USD)
# ============================================================================

def test_usdjpy_risk_calculation(calculator):
    """
    USDJPY: Base=USD, Quote=JPY. Risk in JPY, convert to USD.
    Entry: 150.00, SL: 149.00, Volume: 0.1 lots
    Risk_JPY = (1.00) * 0.1 * 100,000 = 10,000 JPY
    Risk_USD = 10,000 / 149.50 (current rate) ≈ $66.89
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='USDJPY',
        entry_price=150.00,
        stop_loss=149.00,
        volume=0.1
    )
    # Risk in JPY: (150-149) * 0.1 * 100,000 = 10,000 JPY
    # Convert: 10,000 / 149.50 (current USDJPY bid) = 66.89 USD
    expected = 10000 / 149.50
    assert abs(risk_usd - expected) < 0.5, f"Expected ~{expected:.2f}, got {risk_usd:.2f}"


def test_usdcad_risk_calculation(calculator):
    """
    USDCAD: Base=USD, Quote=CAD. Risk in CAD, convert to USD.
    Entry: 1.3500, SL: 1.3400, Volume: 0.1 lots
    Risk_CAD = (0.0100) * 0.1 * 100,000 = 100 CAD
    Risk_USD = 100 / 1.3500 ≈ $74.07
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='USDCAD',
        entry_price=1.3500,
        stop_loss=1.3400,
        volume=0.1
    )
    expected = 100 / 1.3500
    assert abs(risk_usd - expected) < 0.5


# ============================================================================
# FOREX CROSS PAIRS (Neither USD)
# ============================================================================

def test_eurgbp_risk_calculation(calculator):
    """
    EURGBP: Quote=GBP. Risk in GBP, convert to USD via GBPUSD.
    Entry: 0.8600, SL: 0.8550, Volume: 0.1 lots
    Risk_GBP = (0.0050) * 0.1 * 100,000 = 50 GBP
    Risk_USD = 50 * 1.2600 (GBPUSD) = $63.00
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='EURGBP',
        entry_price=0.8600,
        stop_loss=0.8550,
        volume=0.1
    )
    # Risk in GBP: 50 GBP
    # Convert: 50 * 1.2600 (GBPUSD bid) = 63.00 USD
    expected = 50 * 1.2600
    assert abs(risk_usd - expected) < 1.0, f"Expected ~{expected:.2f}, got {risk_usd:.2f}"


def test_eurchf_risk_calculation(calculator):
    """
    EURCHF: Quote=CHF. Risk in CHF, convert to USD via USDCHF (inverse).
    Entry: 0.9500, SL: 0.9450, Volume: 0.1 lots
    Risk_CHF = (0.0050) * 0.1 * 100,000 = 50 CHF
    Risk_USD = 50 / 0.8800 (USDCHF) ≈ $56.82
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='EURCHF',
        entry_price=0.9500,
        stop_loss=0.9450,
        volume=0.1
    )
    # Risk in CHF: 50 CHF
    # Convert: 50 / 0.8800 (USDCHF bid) = 56.82 USD
    expected = 50 / 0.8800
    assert abs(risk_usd - expected) < 1.0


# ============================================================================
# PRECIOUS METALS (contract_size != 100,000)
# ============================================================================

def test_xauusd_risk_calculation(calculator):
    """
    XAUUSD (Gold): contract_size = 100 oz, Quote=USD.
    Entry: 2050.00, SL: 2040.00, Volume: 0.1 lots (10 oz)
    Risk = (10.00) * 0.1 * 100 = $100 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='XAUUSD',
        entry_price=2050.00,
        stop_loss=2040.00,
        volume=0.1
    )
    # (2050 - 2040) * 0.1 * 100 = 10 * 0.1 * 100 = 100 USD
    expected = 100.0
    assert abs(risk_usd - expected) < 0.01


def test_xagusd_risk_calculation(calculator):
    """
    XAGUSD (Silver): contract_size = 5000 oz, Quote=USD.
    Entry: 24.00, SL: 23.00, Volume: 0.1 lots (500 oz)
    Risk = (1.00) * 0.1 * 5000 = $500 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='XAGUSD',
        entry_price=24.00,
        stop_loss=23.00,
        volume=0.1
    )
    expected = 500.0
    assert abs(risk_usd - expected) < 0.01


# ============================================================================
# CRYPTO (contract_size = 1)
# ============================================================================

def test_btcusd_risk_calculation(calculator):
    """
    BTCUSD: contract_size = 1 BTC, Quote=USD.
    Entry: 52000, SL: 51000, Volume: 0.1 lots (0.1 BTC)
    Risk = (1000) * 0.1 * 1 = $100 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='BTCUSD',
        entry_price=52000.00,
        stop_loss=51000.00,
        volume=0.1
    )
    expected = 100.0
    assert abs(risk_usd - expected) < 0.01


# ============================================================================
# INDICES (contract_size varies by broker)
# ============================================================================

def test_us30_risk_calculation(calculator):
    """
    US30 (Dow Jones): contract_size = 10 per point, Quote=USD.
    Entry: 38500, SL: 38400, Volume: 0.1 lots
    Risk = (100 points) * 0.1 * 10 = $100 USD
    """
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='US30',
        entry_price=38500.00,
        stop_loss=38400.00,
        volume=0.1
    )
    expected = 100.0
    assert abs(risk_usd - expected) < 0.01


# ============================================================================
# EDGE CASES
# ============================================================================

def test_unknown_symbol_returns_zero(calculator):
    """Unknown symbol returns 0 (fallback)"""
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='XXXYYY',
        entry_price=1.0,
        stop_loss=0.9,
        volume=0.1
    )
    assert risk_usd == 0.0


def test_zero_volume_returns_zero(calculator):
    """Zero volume returns 0 risk"""
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='EURUSD',
        entry_price=1.0800,
        stop_loss=1.0750,
        volume=0.0
    )
    assert risk_usd == 0.0


def test_entry_equals_sl_returns_zero(calculator):
    """Entry price = SL returns 0 risk"""
    risk_usd = calculator.calculate_initial_risk_usd(
        symbol='EURUSD',
        entry_price=1.0800,
        stop_loss=1.0800,
        volume=0.1
    )
    assert risk_usd == 0.0
