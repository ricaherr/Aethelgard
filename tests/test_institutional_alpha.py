"""
Test Suite: Institutional Alpha (Milestone 6.3)
================================================

Tests for:
1. Fair Value Gap (FVG) Detection
2. Volatility Disconnect (RV vs HV)
3. PriceSnapshot Creation

Uses isolated in-memory data (no external dependencies).
"""
import sys
from pathlib import Path
from dataclasses import fields

import pytest
import pandas as pd
import numpy as np

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from core_brain.tech_utils import TechnicalAnalyzer
from core_brain.main_orchestrator import PriceSnapshot


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def bullish_fvg_data():
    """DataFrame with a clear bullish FVG: High[0] < Low[2]."""
    return pd.DataFrame({
        'open':  [100.0, 102.0, 106.0],
        'high':  [101.0, 104.0, 108.0],  # high[0]=101
        'low':   [99.0,  101.0, 103.0],  # low[2]=103 > high[0]=101 → bullish FVG
        'close': [100.5, 103.0, 107.0],
    })


@pytest.fixture
def bearish_fvg_data():
    """DataFrame with a clear bearish FVG: Low[0] > High[2]."""
    return pd.DataFrame({
        'open':  [108.0, 105.0, 100.0],
        'high':  [109.0, 106.0, 101.0],  # high[2]=101
        'low':   [107.0, 104.0, 99.0],   # low[0]=107 > high[2]=101 → bearish FVG
        'close': [107.5, 104.5, 100.5],
    })


@pytest.fixture
def flat_market_data():
    """DataFrame with no significant gaps (flat market)."""
    return pd.DataFrame({
        'open':  [100.0, 100.1, 100.2, 100.1, 100.0],
        'high':  [100.5, 100.6, 100.7, 100.6, 100.5],
        'low':   [99.5,  99.6,  99.7,  99.6,  99.5],
        'close': [100.2, 100.3, 100.4, 100.3, 100.2],
    })


@pytest.fixture
def volatile_data():
    """DataFrame with 120 candles where recent 20 are 3x more volatile than historical 100."""
    np.random.seed(42)
    
    # 100 calm candles (small moves)
    calm_prices = 100 + np.cumsum(np.random.normal(0, 0.05, 100))
    
    # 20 volatile candles (big moves — 5x the calm volatility)
    volatile_prices = calm_prices[-1] + np.cumsum(np.random.normal(0, 0.25, 20))
    
    all_prices = np.concatenate([calm_prices, volatile_prices])
    
    return pd.DataFrame({
        'open':  all_prices,
        'high':  all_prices + abs(np.random.normal(0.02, 0.01, 120)),
        'low':   all_prices - abs(np.random.normal(0.02, 0.01, 120)),
        'close': all_prices + np.random.normal(0, 0.01, 120),
    })


@pytest.fixture
def normal_volatility_data():
    """DataFrame with 120 candles of consistent, normal volatility."""
    np.random.seed(99)
    prices = 100 + np.cumsum(np.random.normal(0, 0.05, 120))
    
    return pd.DataFrame({
        'open':  prices,
        'high':  prices + abs(np.random.normal(0.02, 0.01, 120)),
        'low':   prices - abs(np.random.normal(0.02, 0.01, 120)),
        'close': prices + np.random.normal(0, 0.01, 120),
    })


# ═══════════════════════════════════════════════════════════════
# FVG TESTS
# ═══════════════════════════════════════════════════════════════

class TestFVGDetection:
    """Tests for TechnicalAnalyzer.detect_fvg()."""

    def test_detect_fvg_bullish(self, bullish_fvg_data):
        """Bullish FVG: High[i-2] < Low[i] should be detected."""
        result = TechnicalAnalyzer.detect_fvg(bullish_fvg_data)
        
        assert 'fvg_bullish' in result.columns
        assert 'fvg_bearish' in result.columns
        assert 'fvg_gap_size' in result.columns
        
        # Last row should have bullish FVG
        last = result.iloc[-1]
        assert last['fvg_bullish'] == True
        assert last['fvg_bearish'] == False
        assert last['fvg_gap_size'] > 0  # gap = low[2] - high[0] = 103 - 101 = 2

    def test_detect_fvg_bearish(self, bearish_fvg_data):
        """Bearish FVG: Low[i-2] > High[i] should be detected."""
        result = TechnicalAnalyzer.detect_fvg(bearish_fvg_data)
        
        last = result.iloc[-1]
        assert last['fvg_bearish'] == True
        assert last['fvg_bullish'] == False
        assert last['fvg_gap_size'] > 0  # gap = low[0] - high[2] = 107 - 101 = 6

    def test_no_fvg_in_flat_market(self, flat_market_data):
        """No FVG should be detected in a flat/range-bound market."""
        result = TechnicalAnalyzer.detect_fvg(flat_market_data)
        
        assert result['fvg_bullish'].sum() == 0
        assert result['fvg_bearish'].sum() == 0

    def test_fvg_with_insufficient_data(self):
        """FVG detection should return empty results with < 3 candles."""
        tiny_df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [102.0, 103.0],
            'low':  [98.0,  99.0],
            'close': [101.0, 102.0],
        })
        result = TechnicalAnalyzer.detect_fvg(tiny_df)
        
        assert len(result) == 2
        assert result['fvg_bullish'].sum() == 0
        assert result['fvg_bearish'].sum() == 0


# ═══════════════════════════════════════════════════════════════
# VOLATILITY DISCONNECT TESTS
# ═══════════════════════════════════════════════════════════════

class TestVolatilityDisconnect:
    """Tests for TechnicalAnalyzer.calculate_volatility_disconnect()."""

    def test_volatility_disconnect_burst(self, volatile_data):
        """RV significantly > HV should trigger is_burst=True."""
        result = TechnicalAnalyzer.calculate_volatility_disconnect(volatile_data)
        
        assert 'rv' in result
        assert 'hv' in result
        assert 'disconnect_ratio' in result
        assert 'is_burst' in result
        
        assert result['rv'] > 0
        assert result['hv'] > 0
        assert result['disconnect_ratio'] > 2.0
        assert result['is_burst'] == True

    def test_volatility_disconnect_normal(self, normal_volatility_data):
        """Consistent volatility should NOT trigger a burst."""
        result = TechnicalAnalyzer.calculate_volatility_disconnect(normal_volatility_data)
        
        assert result['rv'] > 0
        assert result['hv'] > 0
        # Normal: ratio should be close to 1.0
        assert result['disconnect_ratio'] < 2.0
        assert result['is_burst'] == False

    def test_volatility_disconnect_insufficient_data(self):
        """Short data should return safe defaults."""
        short_df = pd.DataFrame({
            'open':  [100.0] * 10,
            'high':  [101.0] * 10,
            'low':   [99.0] * 10,
            'close': [100.5] * 10,
        })
        result = TechnicalAnalyzer.calculate_volatility_disconnect(short_df)
        
        assert result['rv'] == 0.0
        assert result['hv'] == 0.0
        assert result['is_burst'] == False


# ═══════════════════════════════════════════════════════════════
# PRICE SNAPSHOT TESTS
# ═══════════════════════════════════════════════════════════════

class TestPriceSnapshot:
    """Tests for PriceSnapshot dataclass."""

    def test_price_snapshot_creation(self):
        """PriceSnapshot should be created with all required fields."""
        df = pd.DataFrame({'close': [100, 101, 102]})
        
        snapshot = PriceSnapshot(
            symbol="EURUSD",
            timeframe="M5",
            df=df,
            provider_source="MT5"
        )
        
        assert snapshot.symbol == "EURUSD"
        assert snapshot.timeframe == "M5"
        assert snapshot.provider_source == "MT5"
        assert snapshot.df is not None
        assert len(snapshot.df) == 3
        assert snapshot.timestamp is not None
        assert snapshot.regime is None  # Optional, defaults to None

    def test_price_snapshot_has_all_fields(self):
        """PriceSnapshot dataclass should have the expected field names."""
        field_names = {f.name for f in fields(PriceSnapshot)}
        expected = {'symbol', 'timeframe', 'df', 'provider_source', 'timestamp', 'regime'}
        assert field_names == expected
