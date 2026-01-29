"""
Tests for Data Provider Manager and Multiple Data Providers
Testing TDD-first: Alpha Vantage, Twelve Data, Polygon.io, IEX Cloud
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime

from core_brain.data_provider_manager import DataProviderManager


@pytest.fixture
def mock_config():
    """Mock configuration for data providers"""
    return {
        "yahoo": {
            "enabled": True,
            "priority": 1,
            "requires_auth": False
        },
        "alpha_vantage": {
            "enabled": False,
            "priority": 2,
            "requires_auth": True,
            "api_key": "demo"
        },
        "twelve_data": {
            "enabled": False,
            "priority": 3,
            "requires_auth": True,
            "api_key": "demo"
        }
    }


@pytest.fixture
def sample_dataframe():
    """Sample OHLC dataframe for testing"""
    return pd.DataFrame({
        'time': pd.date_range('2026-01-01', periods=100, freq='5min'),
        'open': [100.0 + i for i in range(100)],
        'high': [101.0 + i for i in range(100)],
        'low': [99.0 + i for i in range(100)],
        'close': [100.5 + i for i in range(100)],
        'volume': [1000 + i*10 for i in range(100)]
    })


class TestDataProviderManager:
    """Test Data Provider Manager"""
    
    def test_manager_initialization(self, mock_config):
        """Test that manager initializes correctly"""
        with patch('connectors.data_provider_manager._load_provider_config', return_value=mock_config):
            manager = DataProviderManager()
            assert manager is not None
            assert len(manager.providers) > 0
    
    def test_get_enabled_providers(self, mock_config):
        """Test getting only enabled providers"""
        with patch('connectors.data_provider_manager._load_provider_config', return_value=mock_config):
            manager = DataProviderManager()
            enabled = manager.get_enabled_providers()
            assert all(p['enabled'] for p in enabled)
    
    def test_provider_fallback(self, mock_config, sample_dataframe):
        """Test that manager falls back to next provider on failure"""
        with patch('connectors.data_provider_manager._load_provider_config', return_value=mock_config):
            manager = DataProviderManager()
            
            if len(manager.providers) < 2:
                pytest.skip("Need at least 2 providers for fallback test")
            
            # Mock first provider to fail
            with patch.object(manager.providers[0]['instance'], 'fetch_ohlc', return_value=None):
                # Mock second provider to succeed
                with patch.object(manager.providers[1]['instance'], 'fetch_ohlc', return_value=sample_dataframe):
                    result = manager.fetch_ohlc("AAPL", "M5", 100)
                    assert result is not None
                    assert len(result) == 100
    
    def test_all_providers_fail(self, mock_config):
        """Test that manager returns None when all providers fail"""
        with patch('connectors.data_provider_manager._load_provider_config', return_value=mock_config):
            manager = DataProviderManager()
            
            # Mock all providers to fail
            patches = []
            for provider_info in manager.providers:
                p = patch.object(provider_info['instance'], 'fetch_ohlc', return_value=None)
                patches.append(p)
                p.start()
            
            try:
                result = manager.fetch_ohlc("INVALID", "M5", 100)
                assert result is None
            finally:
                for p in patches:
                    p.stop()


class TestAlphaVantageProvider:
    """Test Alpha Vantage Data Provider"""
    
    @patch('connectors.alpha_vantage_provider.requests.get')
    def test_fetch_ohlc_success(self, mock_get):
        """Test successful data fetch from Alpha Vantage"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Time Series (5min)": {
                "2026-01-27 09:00:00": {
                    "1. open": "100.0",
                    "2. high": "101.0",
                    "3. low": "99.0",
                    "4. close": "100.5",
                    "5. volume": "1000"
                }
            }
        }
        mock_get.return_value = mock_response
        
        from connectors.alpha_vantage_provider import AlphaVantageProvider
        provider = AlphaVantageProvider(api_key="demo")
        result = provider.fetch_ohlc("AAPL", "M5", 100)
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)
    
    def test_fetch_ohlc_no_api_key(self):
        """Test that provider fails without API key"""
        from connectors.alpha_vantage_provider import AlphaVantageProvider
        
        with pytest.raises(ValueError):
            provider = AlphaVantageProvider(api_key=None)


class TestTwelveDataProvider:
    """Test Twelve Data Provider"""
    
    @patch('connectors.twelve_data_provider.requests.get')
    def test_fetch_ohlc_success(self, mock_get):
        """Test successful data fetch from Twelve Data"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "values": [
                {
                    "datetime": "2026-01-27 09:00:00",
                    "open": "100.0",
                    "high": "101.0",
                    "low": "99.0",
                    "close": "100.5",
                    "volume": "1000"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        from connectors.twelve_data_provider import TwelveDataProvider
        provider = TwelveDataProvider(api_key="demo")
        result = provider.fetch_ohlc("AAPL", "M5", 100)
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)


class TestPolygonProvider:
    """Test Polygon.io Data Provider"""
    
    @patch('connectors.polygon_provider.requests.get')
    def test_fetch_ohlc_success(self, mock_get):
        """Test successful data fetch from Polygon.io"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "t": 1706349600000,  # timestamp
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                    "v": 1000
                }
            ]
        }
        mock_get.return_value = mock_response
        
        from connectors.polygon_provider import PolygonProvider
        provider = PolygonProvider(api_key="demo")
        result = provider.fetch_ohlc("AAPL", "M5", 100)
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)


class TestIEXCloudProvider:
    """Test IEX Cloud Data Provider"""
    
    @patch('connectors.iex_cloud_provider.requests.get')
    def test_fetch_ohlc_success(self, mock_get):
        """Test successful data fetch from IEX Cloud"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "date": "2026-01-27",
                "minute": "09:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000
            }
        ]
        mock_get.return_value = mock_response
        
        from connectors.iex_cloud_provider import IEXCloudProvider
        provider = IEXCloudProvider(api_key="demo")
        result = provider.fetch_ohlc("AAPL", "M5", 100)
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)


class TestFinnhubProvider:
    """Test Finnhub Data Provider"""
    
    @patch('connectors.finnhub_provider.requests.get')
    def test_fetch_ohlc_success(self, mock_get):
        """Test successful data fetch from Finnhub"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "t": [1706349600],  # timestamps
            "o": [100.0],
            "h": [101.0],
            "l": [99.0],
            "c": [100.5],
            "v": [1000]
        }
        mock_get.return_value = mock_response
        
        from connectors.finnhub_provider import FinnhubProvider
        provider = FinnhubProvider(api_key="demo")
        result = provider.fetch_ohlc("AAPL", "M5", 100)
        
        assert result is not None
        assert isinstance(result, pd.DataFrame)
