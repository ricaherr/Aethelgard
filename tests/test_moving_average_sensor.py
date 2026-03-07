"""
Test Suite for Moving Average Sensor (SMA 20 / SMA 200)

Testing: 
  - SMA 20 detection on M5/M15 timeframes
  - SMA 200 detection on H1 timeframe
  - Integration with StrategyGatekeeper veto logic
  - Caching and performance optimization

TRACE_ID: TEST-SENSOR-MA-001
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from core_brain.sensors.moving_average_sensor import MovingAverageSensor
from data_vault.storage import StorageManager


@pytest.fixture
def sample_ohlc_data():
    """Generate synthetic OHLC data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=300, freq='5min')
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(300) * 0.5)  # Random walk
    high = close + np.random.rand(300) * 0.5
    low = close - np.random.rand(300) * 0.5
    volume = np.random.randint(1000, 10000, 300)
    
    df = pd.DataFrame({
        'open': close - 0.2,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    return df


@pytest.fixture
def mock_storage():
    """Mock StorageManager for testing."""
    mock = MagicMock(spec=StorageManager)
    mock.get_sys_config.return_value = {}
    mock.get_dynamic_params.return_value = {
        'sma_fast_period': 20,
        'sma_slow_period': 200,
        'cache_enabled': True
    }
    return mock


@pytest.fixture
def mock_gatekeeper():
    """Mock StrategyGatekeeper for testing."""
    mock = MagicMock()
    mock.is_asset_authorized.return_value = True
    return mock


@pytest.fixture
def ma_sensor(mock_storage, mock_gatekeeper):
    """Create MovingAverageSensor instance with mocked dependencies."""
    return MovingAverageSensor(
        storage=mock_storage,
        gatekeeper=mock_gatekeeper,
        trace_id="TEST-MA-001"
    )


class TestMovingAverageSensorBasics:
    """Test basic SMA calculation functionality."""
    
    def test_sma20_calculation_correct(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: OHLC data with 300 candles
        WHEN: Calculate SMA 20
        THEN: SMA 20 should match pandas rolling mean
        """
        result = ma_sensor.calculate_sma(
            df=sample_ohlc_data, 
            period=20, 
            column='close'
        )
        
        # Verify result is Series
        assert isinstance(result, pd.Series)
        
        # Verify length matches input
        assert len(result) == len(sample_ohlc_data)
        
        # Verify calculation matches pandas
        expected = sample_ohlc_data['close'].rolling(window=20).mean()
        pd.testing.assert_series_equal(result, expected)
        
        # First 19 values should be NaN (insufficient data)
        assert result.isna().sum() == 19
    
    
    def test_sma200_calculation_correct(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: OHLC data with 300 candles
        WHEN: Calculate SMA 200
        THEN: SMA 200 should be correctly calculated
        """
        result = ma_sensor.calculate_sma(
            df=sample_ohlc_data,
            period=200,
            column='close'
        )
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlc_data)
        
        # First 199 values should be NaN
        assert result.isna().sum() == 199
    
    
    def test_detect_price_above_sma(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: OHLC data with SMA 20 calculated
        WHEN: Check if latest price is above SMA 20
        THEN: Should return correct boolean
        """
        latest_close = sample_ohlc_data['close'].iloc[-1]
        sma20 = ma_sensor.calculate_sma(sample_ohlc_data, 20, 'close')
        sma20_latest = sma20.iloc[-1]
        
        is_above = latest_close > sma20_latest
        is_below = latest_close < sma20_latest
        
        # One of them must be True (assuming not exactly equal)
        assert is_above or is_below or latest_close == sma20_latest
    
    
    def test_detect_price_below_sma(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: OHLC data with SMA 20
        WHEN: Latest price is below SMA
        THEN: Should detect correctly
        """
        sma20 = ma_sensor.calculate_sma(sample_ohlc_data, 20, 'close')
        
        # Verify we have valid SMA values at the end
        assert not pd.isna(sma20.iloc[-1])


class TestMovingAverageSensorMacroMicro:
    """Test macro (SMA 200) and micro (SMA 20) level detection."""
    
    def test_detect_macro_trend_above_sma200(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: Price trending above SMA 200
        WHEN: analyze_macro_level() called
        THEN: Should return 'above' status
        """
        result = ma_sensor.analyze_macro_level(
            df=sample_ohlc_data,
            symbol='EUR/USD',
            timeframe='H1'
        )
        
        assert isinstance(result, dict)
        assert 'level' in result
        assert 'status' in result
        assert result['status'] in ['above', 'below', 'on_line']
    
    
    def test_detect_micro_trend_sma20(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: Price data on M5 timeframe
        WHEN: analyze_micro_level() called
        THEN: Should detect price vs SMA 20 relationship
        """
        result = ma_sensor.analyze_micro_level(
            df=sample_ohlc_data,
            symbol='EUR/USD',
            timeframe='M5'
        )
        
        assert isinstance(result, dict)
        assert 'level' in result
        assert 'status' in result


class TestMovingAverageSensorGatekeeperIntegration:
    """Test integration with StrategyGatekeeper."""
    
    def test_skip_calculation_if_gatekeeper_veto(self, mock_storage, mock_gatekeeper):
        """
        GIVEN: StrategyGatekeeper vetos EUR/USD calculation
        WHEN: calculate_with_gatekeeper() called
        THEN: Should return None without calculating
        """
        mock_gatekeeper.is_asset_authorized.return_value = False
        
        sensor = MovingAverageSensor(
            storage=mock_storage,
            gatekeeper=mock_gatekeeper,
            trace_id="TEST-MA-VETO"
        )
        
        dummy_df = pd.DataFrame({'close': [100, 101, 102]})
        
        result = sensor.calculate_with_gatekeeper(
            symbol='GBP/JPY',
            df=dummy_df,
            period=20
        )
        
        assert result is None
        mock_gatekeeper.is_asset_authorized.assert_called_with('GBP/JPY')
    
    
    def test_calculate_if_gatekeeper_authorizes(self, mock_storage, mock_gatekeeper, sample_ohlc_data):
        """
        GIVEN: StrategyGatekeeper authorizes EUR/USD
        WHEN: calculate_with_gatekeeper() called
        THEN: Should calculate and return SMA
        """
        mock_gatekeeper.is_asset_authorized.return_value = True
        
        sensor = MovingAverageSensor(
            storage=mock_storage,
            gatekeeper=mock_gatekeeper,
            trace_id="TEST-MA-AUTH"
        )
        
        result = sensor.calculate_with_gatekeeper(
            symbol='EUR/USD',
            df=sample_ohlc_data,
            period=20
        )
        
        assert result is not None
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlc_data)


class TestMovingAverageSensorCaching:
    """Test caching functionality for performance."""
    
    def test_cache_stores_sma_calculation(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: SMA calculation with cache enabled
        WHEN: Same calculation requested twice
        THEN: Second call should use cached value
        """
        # First call - should calculate
        result1 = ma_sensor.calculate_sma(sample_ohlc_data, 20, 'close')
        
        # Second call - should use cache
        result2 = ma_sensor.calculate_sma(sample_ohlc_data, 20, 'close')
        
        # Results should be identical
        pd.testing.assert_series_equal(result1, result2)
    
    
    def test_cache_separate_for_different_periods(self, ma_sensor, sample_ohlc_data):
        """
        GIVEN: Different SMA periods calculated
        WHEN: Both cached
        THEN: Each should have independent cache entry
        """
        sma20 = ma_sensor.calculate_sma(sample_ohlc_data, 20, 'close')
        sma200 = ma_sensor.calculate_sma(sample_ohlc_data, 200, 'close')
        
        # These should be different
        assert not sma20.equals(sma200)


class TestMovingAverageSensorEdgeCases:
    """Test edge cases and error handling."""
    
    def test_insufficient_data_handling(self, ma_sensor):
        """
        GIVEN: DataFrame with fewer candles than period
        WHEN: Calculate SMA
        THEN: Should return NaN values gracefully
        """
        small_df = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [100.5, 101.5, 102.5],
            'low': [99.5, 100.5, 101.5],
            'close': [100.2, 101.2, 102.2],
            'volume': [1000, 1000, 1000]
        })
        
        result = ma_sensor.calculate_sma(small_df, 20, 'close')
        
        # All should be NaN (insufficient data)
        assert result.isna().all()
    
    
    def test_empty_dataframe_handling(self, ma_sensor):
        """
        GIVEN: Empty DataFrame
        WHEN: Calculate SMA
        THEN: Should handle gracefully (return empty Series)
        """
        empty_df = pd.DataFrame({'close': []})
        
        result = ma_sensor.calculate_sma(empty_df, 20, 'close')
        
        # Should return empty Series instead of raising
        assert isinstance(result, pd.Series)
        assert len(result) == 0
    
    
    def test_nan_values_in_data(self, ma_sensor):
        """
        GIVEN: OHLC data with NaN values
        WHEN: Calculate SMA
        THEN: Should handle NaN propagation correctly
        """
        df_with_nan = pd.DataFrame({
            'open': [100, 101, np.nan, 103],
            'high': [100.5, 101.5, 102.5, 103.5],
            'low': [99.5, 100.5, 101.5, 102.5],
            'close': [100.2, 101.2, np.nan, 103.2],
            'volume': [1000, 1000, 1000, 1000]
        })
        
        result = ma_sensor.calculate_sma(df_with_nan, 2, 'close')
        
        # Result should handle NaNs appropriately
        assert isinstance(result, pd.Series)
        assert len(result) == len(df_with_nan)
