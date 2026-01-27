"""
Tests for DataProviderManager - Multi-source data provider management system
TDD: Write tests first, then implement functionality
"""
import pytest
from unittest.mock import Mock, patch
from core_brain.data_provider_manager import (
    DataProviderManager,
    ProviderStatus,
    ProviderConfig
)


class TestProviderConfig:
    """Test ProviderConfig data class"""
    
    def test_provider_config_creation(self):
        """Test creating a provider configuration"""
        config = ProviderConfig(
            name="yahoo",
            enabled=True,
            requires_auth=False,
            priority=1,
            free_tier=True
        )
        
        assert config.name == "yahoo"
        assert config.enabled is True
        assert config.requires_auth is False
        assert config.priority == 1
        assert config.free_tier is True
    
    def test_provider_config_with_credentials(self):
        """Test provider config with API credentials"""
        config = ProviderConfig(
            name="alphavantage",
            enabled=True,
            requires_auth=True,
            priority=2,
            free_tier=True,
            api_key="test_key_123"
        )
        
        assert config.requires_auth is True
        assert config.api_key == "test_key_123"


class TestDataProviderManager:
    """Test DataProviderManager functionality"""
    
    def test_manager_initialization(self):
        """Test manager initializes with default providers"""
        manager = DataProviderManager()
        
        assert manager is not None
        assert len(manager.get_available_providers()) > 0
        assert "yahoo" in manager.get_available_providers()
    
    def test_get_active_providers(self):
        """Test getting list of active/enabled providers"""
        manager = DataProviderManager()
        
        active = manager.get_active_providers()
        
        assert isinstance(active, list)
        # Yahoo should be active by default
        assert any(p["name"] == "yahoo" for p in active)
    
    def test_enable_provider(self):
        """Test enabling a provider"""
        manager = DataProviderManager()
        
        # Disable yahoo first
        manager.disable_provider("yahoo")
        assert not manager.is_provider_enabled("yahoo")
        
        # Now enable it
        result = manager.enable_provider("yahoo")
        
        assert result is True
        assert manager.is_provider_enabled("yahoo")
    
    def test_disable_provider(self):
        """Test disabling a provider"""
        manager = DataProviderManager()
        
        result = manager.disable_provider("yahoo")
        
        assert result is True
        assert not manager.is_provider_enabled("yahoo")
    
    def test_get_provider_status(self):
        """Test getting provider status information"""
        manager = DataProviderManager()
        
        status = manager.get_provider_status("yahoo")
        
        assert status is not None
        assert status.name == "yahoo"
        assert isinstance(status.enabled, bool)
        assert isinstance(status.available, bool)
    
    def test_get_best_provider(self):
        """Test automatic selection of best available provider"""
        manager = DataProviderManager()
        
        provider = manager.get_best_provider()
        
        assert provider is not None
        # Should return highest priority enabled provider
    
    def test_get_provider_for_symbol(self):
        """Test getting best provider for specific symbol"""
        manager = DataProviderManager()
        
        # Forex symbol
        provider = manager.get_provider_for_symbol("EURUSD")
        assert provider is not None
        
        # Crypto symbol
        provider = manager.get_provider_for_symbol("BTCUSD")
        assert provider is not None
    
    def test_configure_provider_credentials(self):
        """Test setting API credentials for a provider"""
        manager = DataProviderManager()
        
        result = manager.configure_provider(
            "alphavantage",
            api_key="test_api_key_123"
        )
        
        assert result is True
        config = manager.get_provider_config("alphavantage")
        assert config.api_key == "test_api_key_123"
    
    def test_validate_provider_connection(self):
        """Test validating provider connection"""
        manager = DataProviderManager()
        
        # Yahoo should validate successfully (no auth required)
        is_valid = manager.validate_provider("yahoo")
        
        assert isinstance(is_valid, bool)
    
    def test_get_free_providers(self):
        """Test getting list of free/no-auth providers"""
        manager = DataProviderManager()
        
        free_providers = manager.get_free_providers()
        
        assert isinstance(free_providers, list)
        assert len(free_providers) > 0
        assert "yahoo" in [p["name"] for p in free_providers]
    
    def test_get_auth_required_providers(self):
        """Test getting list of providers requiring authentication"""
        manager = DataProviderManager()
        
        auth_providers = manager.get_auth_required_providers()
        
        assert isinstance(auth_providers, list)
        # Should include alphavantage, twelvedata, etc.
    
    def test_fallback_provider_selection(self):
        """Test fallback when primary provider fails"""
        manager = DataProviderManager()
        
        # Disable top priority provider
        manager.disable_provider("yahoo")
        
        # Should fallback to next available
        provider = manager.get_best_provider()
        
        assert provider is not None
        assert provider.name != "yahoo"
    
    def test_save_and_load_configuration(self):
        """Test persisting provider configuration"""
        manager = DataProviderManager()
        
        # Configure some providers
        manager.disable_provider("yahoo")
        manager.configure_provider("alphavantage", api_key="test_key")
        
        # Save configuration
        manager.save_configuration()
        
        # Create new manager and load
        new_manager = DataProviderManager()
        
        assert not new_manager.is_provider_enabled("yahoo")
        config = new_manager.get_provider_config("alphavantage")
        assert config.api_key == "test_key"
    
    def test_get_provider_capabilities(self):
        """Test getting provider capabilities (symbols, timeframes, etc.)"""
        manager = DataProviderManager()
        
        capabilities = manager.get_provider_capabilities("yahoo")
        
        assert capabilities is not None
        assert "symbols" in capabilities or "asset_types" in capabilities
    
    def test_priority_based_selection(self):
        """Test provider selection respects priority order"""
        manager = DataProviderManager()
        
        # Set specific priorities
        manager.set_provider_priority("yahoo", 10)
        manager.set_provider_priority("alphavantage", 5)
        
        best = manager.get_best_provider()
        
        # Higher priority number = higher priority
        assert best.name == "yahoo"
    
    def test_fetch_data_with_fallback(self):
        """Test data fetching with automatic fallback"""
        manager = DataProviderManager()
        
        # This should try primary provider, fallback if needed
        data = manager.fetch_ohlc("AAPL", timeframe="M5", count=100)
        
        # Should return data or None, but not raise exception
        assert data is None or hasattr(data, '__len__')


class TestProviderStatus:
    """Test ProviderStatus data class"""
    
    def test_status_creation(self):
        """Test creating provider status"""
        status = ProviderStatus(
            name="yahoo",
            enabled=True,
            available=True,
            requires_auth=False,
            last_check=None,
            error_message=None
        )
        
        assert status.name == "yahoo"
        assert status.enabled is True
        assert status.available is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
