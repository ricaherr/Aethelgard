"""
Tests para Economic Data Gateway (FASE C.2).

Includes:
- Factory pattern validation
- Provider routing
- Caching logic
- Error handling and fallback
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from connectors.economic_data_gateway import (
    EconomicDataGateway,
    EconomicDataProviderRegistry,
    BaseEconomicDataAdapter,
    InvestingAdapterStub,
    BloombergAdapterStub,
    ForexFactoryAdapterStub,
)


class TestEconomicDataProviderRegistry:
    """Test provider registry and factory pattern."""
    
    def test_registry_has_all_providers(self):
        """Validate all 3 providers are registered."""
        providers = EconomicDataProviderRegistry.get_all_providers()
        assert len(providers) == 3
        assert 'INVESTING' in providers
        assert 'BLOOMBERG' in providers
        assert 'FOREXFACTORY' in providers
    
    def test_registry_returns_correct_adapter_class(self):
        """Validate adapter class resolution."""
        investing_class = EconomicDataProviderRegistry.get_adapter_class('INVESTING')
        assert investing_class == InvestingAdapterStub
        
        bloomberg_class = EconomicDataProviderRegistry.get_adapter_class('BLOOMBERG')
        assert bloomberg_class == BloombergAdapterStub
        
        forexfactory_class = EconomicDataProviderRegistry.get_adapter_class('FOREXFACTORY')
        assert forexfactory_class == ForexFactoryAdapterStub
    
    def test_registry_case_insensitive(self):
        """Validate provider names are case-insensitive."""
        assert EconomicDataProviderRegistry.get_adapter_class('investing') == InvestingAdapterStub
        assert EconomicDataProviderRegistry.get_adapter_class('INVESTING') == InvestingAdapterStub
        assert EconomicDataProviderRegistry.get_adapter_class('Investing') == InvestingAdapterStub
    
    def test_registry_returns_none_for_unknown_provider(self):
        """Validate unknown provider returns None."""
        result = EconomicDataProviderRegistry.get_adapter_class('UNKNOWN')
        assert result is None
    
    def test_library_registration(self):
        """Validate that providers can be registered dynamically."""
        class CustomAdapter(BaseEconomicDataAdapter):
            async def fetch_events(self, days_back: int = 7) -> List[Dict[str, Any]]:
                return []
        
        # Register new provider
        EconomicDataProviderRegistry.register_provider('CUSTOM', CustomAdapter)
        
        # Verify it's registered
        assert EconomicDataProviderRegistry.get_adapter_class('CUSTOM') == CustomAdapter
        providers = EconomicDataProviderRegistry.get_all_providers()
        assert 'CUSTOM' in providers
        
        # Cleanup: remove CUSTOM provider for next tests
        del EconomicDataProviderRegistry.PROVIDERS['CUSTOM']


class TestEconomicDataGateway:
    """Test main gateway functionality."""
    
    @pytest.fixture
    def gateway(self):
        """Create gateway instance for testing."""
        return EconomicDataGateway(use_cache=True, cache_ttl_minutes=1)
    
    @pytest.mark.asyncio
    async def test_gateway_can_fetch_from_investing(self, gateway):
        """Validate gateway can call Investing adapter."""
        events = await gateway.fetch_economic_events('INVESTING', days_back=7)
        # Stub returns empty list
        assert isinstance(events, list)
    
    @pytest.mark.asyncio
    async def test_gateway_can_fetch_from_bloomberg(self, gateway):
        """Validate gateway can call Bloomberg adapter."""
        events = await gateway.fetch_economic_events('BLOOMBERG', days_back=7)
        # Stub returns empty list
        assert isinstance(events, list)
    
    @pytest.mark.asyncio
    async def test_gateway_can_fetch_from_forexfactory(self, gateway):
        """Validate gateway can call ForexFactory adapter."""
        events = await gateway.fetch_economic_events('FOREXFACTORY', days_back=7)
        # Stub returns empty list
        assert isinstance(events, list)
    
    @pytest.mark.asyncio
    async def test_gateway_raises_error_for_unknown_provider(self, gateway):
        """Validate gateway rejects unknown provider."""
        with pytest.raises(ValueError):
            await gateway.fetch_economic_events('UNKNOWN')
    
    @pytest.mark.asyncio
    async def test_gateway_caching_works(self, gateway):
        """Validate caching is enabled."""
        # Mock adapter that tracks call count
        call_count = 0
        
        original_fetch = gateway.adapters['INVESTING'].fetch_events
        async def mock_fetch(days_back=7):
            nonlocal call_count
            call_count += 1
            return []
        
        gateway.adapters['INVESTING'].fetch_events = mock_fetch
        
        # First call
        await gateway.fetch_economic_events('INVESTING', days_back=7)
        assert call_count == 1
        
        # Second call (should use cache)
        await gateway.fetch_economic_events('INVESTING', days_back=7)
        assert call_count == 1  # No new call made
        
        # Restore
        gateway.adapters['INVESTING'].fetch_events = original_fetch
    
    @pytest.mark.asyncio
    async def test_gateway_cache_expiration(self, gateway):
        """Validate cache respects TTL."""
        call_count = 0
        
        original_fetch = gateway.adapters['INVESTING'].fetch_events
        async def mock_fetch(days_back=7):
            nonlocal call_count
            call_count += 1
            return []
        
        gateway.adapters['INVESTING'].fetch_events = mock_fetch
        
        # First call
        await gateway.fetch_economic_events('INVESTING', days_back=7)
        assert call_count == 1
        
        # Manually expire cache
        if 'INVESTING' in gateway.cache:
            gateway.cache['INVESTING']['timestamp'] = datetime.utcnow() - timedelta(minutes=2)
        
        # Next call (cache expired)
        await gateway.fetch_economic_events('INVESTING', days_back=7)
        assert call_count == 2  # New call made
        
        # Restore
        gateway.adapters['INVESTING'].fetch_events = original_fetch
    
    @pytest.mark.asyncio
    async def test_gateway_fallback_to_stale_cache_on_error(self, gateway):
        """Validate fallback to stale cache when provider fails."""
        # Populate cache with some data
        gateway.cache['INVESTING'] = {
            "timestamp": datetime.utcnow() - timedelta(minutes=2),
            "data": [{"event_id": "cached-event"}]
        }
        
        # Mock adapter to raise error
        async def mock_fetch(days_back=7):
            raise RuntimeError("Provider error")
        
        gateway.adapters['INVESTING'].fetch_events = mock_fetch
        
        # Fetch should return cached data on error
        events = await gateway.fetch_economic_events('INVESTING', days_back=7)
        assert len(events) == 1
        assert events[0]["event_id"] == "cached-event"
    
    @pytest.mark.asyncio
    async def test_gateway_fetch_all_providers(self, gateway):
        """Validate concurrent fetch from all providers."""
        results = await gateway.fetch_all_providers(days_back=7)
        
        assert isinstance(results, dict)
        assert 'INVESTING' in results
        assert 'BLOOMBERG' in results
        assert 'FOREXFACTORY' in results
        
        # All should be lists (empty in stub implementation)
        for provider, events in results.items():
            assert isinstance(events, list)
    
    @pytest.mark.asyncio
    async def test_gateway_health_check(self, gateway):
        """Validate health check for allproviders."""
        results = await gateway.health_check()
        
        assert isinstance(results, dict)
        assert len(results) == 3
        
        # All should be bool
        for provider, status in results.items():
            assert isinstance(status, bool)
    
    def test_gateway_retrieves_supported_providers(self, gateway):
        """Validate get_supported_providers returns all providers."""
        providers = gateway.get_supported_providers()
        assert len(providers) == 3
        assert set(providers) == {'INVESTING', 'BLOOMBERG', 'FOREXFACTORY'}


class TestBaseEconomicDataAdapter:
    """Test base adapter class."""
    
    @pytest.mark.asyncio
    async def test_adapter_normalization_work(self):
        """Validate country and impact normalization."""
        adapter = InvestingAdapterStub()
        
        # Country normalization
        assert adapter.normalize_country_code('USA') == 'USA'
        assert adapter.normalize_country_code('usa') == 'USA'
        
        # Impact normalization
        assert adapter.normalize_impact_score('high') == 'HIGH'
        assert adapter.normalize_impact_score('HIGH') == 'HIGH'
        assert adapter.normalize_impact_score('medium') == 'MEDIUM'
        assert adapter.normalize_impact_score('low') == 'LOW'
        assert adapter.normalize_impact_score('unknown') == 'MEDIUM'  # Default
    
    @pytest.mark.asyncio
    async def test_adapter_health_check_fails_gracefully(self):
        """Validate health check handles errors."""
        adapter = InvestingAdapterStub()
        
        # Stub's health check should fail (empty fetch)
        # but should not raise an exception
        result = await adapter.health_check()
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
