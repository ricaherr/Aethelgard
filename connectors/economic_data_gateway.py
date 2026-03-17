"""
Economic Data Gateway: Central orchestrator for economic calendar data providers.

FASE C.2: Data Provider Gateway

Purpose:
---------
Acts as a factory and facade for multiple economic data providers (Investing, Bloomberg, ForexFactory).
Handles provider selection, normalization, error handling, and caching.

Architecture:
---------
- EconomicDataGateway: Main class with method fetch_economic_events()
- Provider Registry: Maps provider names to adapter classes
- Cache Layer: Optional in-memory caching with TTL
- Error Handling: Fallback to cache if provider fails

Usage:
---------
gateway = EconomicDataGateway(config_path="config/data_providers.json")
events = await gateway.fetch_economic_events(
    provider="INVESTING",
    days_back=7
)
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from abc import ABC, abstractmethod
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseEconomicDataAdapter(ABC):
    """
    Base class for all economic data provider adapters.
    
    Ensures consistent interface across all providers (Investing, Bloomberg, ForexFactory).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize adapter with optional configuration.
        
        Args:
            config: Provider-specific configuration (API keys, endpoints, etc.)
        """
        self.config = config or {}
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.provider_name = self.__class__.__name__
        self.last_fetch_time = None
        self.last_error = None
    
    @abstractmethod
    async def fetch_events(
        self, 
        days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch economic calendar events from the provider.
        
        Must return normalized events with schema:
        {
            "event_id": "generated-uuid",
            "event_name": "US CPI",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH|MEDIUM|LOW",
            "event_time_utc": "2026-03-05T10:30:00Z",
            "provider_source": "INVESTING|BLOOMBERG|FOREXFACTORY",
            "forecast": 3.2,
            "actual": null,
            "previous": 3.1
        }
        
        Args:
            days_back: Include events from last N days
            
        Returns:
            List of normalized economic events
            
        Raises:
            TimeoutError: If fetch exceeds timeout
            ConnectionError: If provider is unreachable
            ValueError: If response cannot be parsed
        """
        pass
    
    def normalize_country_code(self, country_raw: str) -> str:
        """
        Normalize country name/code to ISO 3166-1 alpha-2 code.
        
        Args:
            country_raw: Raw country name or code from provider
            
        Returns:
            ISO 3166-1 alpha-2 code (e.g., "USA", "EUR", "GBP")
        """
        # Override in subclass if provider uses different coding
        return country_raw.upper()
    
    def normalize_impact_score(self, impact_raw: str) -> str:
        """
        Normalize impact level to enum: HIGH|MEDIUM|LOW.
        
        Args:
            impact_raw: Raw impact level from provider
            
        Returns:
            Normalized impact score
        """
        # Override in subclass for provider-specific normalization
        if impact_raw.lower() in ['high', 'alto', '높음']:
            return 'HIGH'
        elif impact_raw.lower() in ['medium', 'medio', '중간']:
            return 'MEDIUM'
        elif impact_raw.lower() in ['low', 'bajo', '낮음']:
            return 'LOW'
        return 'MEDIUM'  # Default
    
    async def health_check(self) -> bool:
        """
        Check if provider is reachable and responding.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to fetch 1 event with short timeout
            events = await asyncio.wait_for(self.fetch_events(days_back=1), timeout=5)
            return True
        except Exception as e:
            logger.warning(f"[{self.provider_name}] Health check failed: {e}")
            self.last_error = str(e)
            return False


class EconomicDataProviderRegistry:
    """Registry mapping provider names to adapter classes."""
    
    # Import real adapters (lazy import to avoid circular dependencies)
    @staticmethod
    def _get_real_providers() -> Dict[str, type]:
        """Get real adapter classes, importing on demand."""
        try:
            from connectors.economic_adapters import (
                InvestingAdapter,
                BloombergAdapter,
                ForexFactoryAdapter
            )
            return {
                'INVESTING': InvestingAdapter,
                'BLOOMBERG': BloombergAdapter,
                'FOREXFACTORY': ForexFactoryAdapter,
            }
        except ImportError:
            # Fallback to stub implementations if real adapters not available
            logger.warning(
                "[EconomicDataProviderRegistry] Real adapters not found, "
                "using stub implementations"
            )
            
            # Create minimal stubs
            class StubAdapter(BaseEconomicDataAdapter):
                async def fetch_events(self, days_back: int = 7) -> List[Dict[str, Any]]:
                    return []
            
            return {
                'INVESTING': StubAdapter,
                'BLOOMBERG': StubAdapter,
                'FOREXFACTORY': StubAdapter,
            }
    
    # Supported providers (loaded lazily)
    PROVIDERS: Dict[str, type] = {}
    
    @classmethod
    def get_adapter_class(cls, provider_name: str) -> Optional[type]:
        """
        Get adapter class for provider name.
        
        Args:
            provider_name: Name of provider (INVESTING, BLOOMBERG, FOREXFACTORY)
            
        Returns:
            Adapter class or None if provider not supported
        """
        # Lazy-load providers on first access
        if not cls.PROVIDERS:
            cls.PROVIDERS = cls._get_real_providers()
        
        return cls.PROVIDERS.get(provider_name.upper())
    
    @classmethod
    def get_all_providers(cls) -> List[str]:
        """Get list of supported provider names."""
        # Lazy-load providers on first access
        if not cls.PROVIDERS:
            cls.PROVIDERS = cls._get_real_providers()
        
        return list(cls.PROVIDERS.keys())
    
    @classmethod
    def register_provider(cls, provider_name: str, adapter_class: type) -> None:
        """
        Register a new provider adapter (for extensibility).
        
        Args:
            provider_name: Name of new provider
            adapter_class: Adapter class (must inherit from BaseEconomicDataAdapter)
        """
        if not issubclass(adapter_class, BaseEconomicDataAdapter):
            raise TypeError("Adapter must inherit from BaseEconomicDataAdapter")
        
        cls.PROVIDERS[provider_name.upper()] = adapter_class
        logger.info(f"Registered provider: {provider_name}")


class EconomicDataGateway:
    """
    Main gateway for fetching economic calendar data from multiple providers.
    
    Features:
    - Factory pattern for provider selection
    - Error handling and fallback
    - Optional caching layer (TTL)
    - Rate limiting awareness
    - Logging and metrics
    """
    
    def __init__(
        self, 
        config_path: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl_minutes: int = 30
    ):
        """
        Initialize Economic Data Gateway.
        
        Args:
            config_path: Path to JSON config with provider credentials
            use_cache: Enable in-memory caching with TTL
            cache_ttl_minutes: Cache validity time in minutes
        """
        self.config = self._load_config(config_path)
        self.use_cache = use_cache
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.cache = {}  # {provider_name: {"timestamp": datetime, "data": List}}
        self.adapters = {}  # {provider_name: adapter_instance}
        self._initialize_adapters()
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load provider configuration from JSON file."""
        if not config_path:
            return {}
        
        try:
            path = Path(config_path)
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
        
        return {}
    
    def _initialize_adapters(self) -> None:
        """Instantiate adapters for all supported providers."""
        for provider_name in EconomicDataProviderRegistry.get_all_providers():
            adapter_class = EconomicDataProviderRegistry.get_adapter_class(provider_name)
            if adapter_class:
                provider_config = self.config.get(provider_name.lower(), {})
                self.adapters[provider_name] = adapter_class(provider_config)
                logger.info(f"Initialized adapter: {provider_name}")
    
    async def fetch_economic_events(
        self,
        provider: str,
        days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Fetch economic calendar events from a specific provider.
        
        Args:
            provider: Provider name (INVESTING, BLOOMBERG, FOREXFACTORY)
            days_back: Include events from last N days (default 7)
            
        Returns:
            List of normalized economic events
            
        Raises:
            ValueError: If provider not supported
        """
        provider_upper = provider.upper()
        
        # Check cache first
        if self.use_cache and self._is_cache_valid(provider_upper):
            logger.info(f"[{provider_upper}] Returning cached data")
            return self.cache[provider_upper]["data"]
        
        # Get adapter
        if provider_upper not in self.adapters:
            raise ValueError(f"Provider {provider} not supported")
        
        adapter = self.adapters[provider_upper]
        
        try:
            logger.info(f"[{provider_upper}] Fetching economic events (days_back={days_back})")
            events = await asyncio.wait_for(
                adapter.fetch_events(days_back=days_back),
                timeout=adapter.timeout
            )
            
            # Cache result
            if self.use_cache:
                self._update_cache(provider_upper, events)
            
            logger.info(f"[{provider_upper}] Fetched {len(events)} events")
            return events
            
        except asyncio.TimeoutError:
            logger.error(f"[{provider_upper}] Request timeout after {adapter.timeout}s")
            # Return cached data if available
            return self._get_cached_data(provider_upper)
        
        except Exception as e:
            logger.error(f"[{provider_upper}] Fetch failed: {e}")
            # Return cached data if available
            return self._get_cached_data(provider_upper)
    
    async def fetch_all_providers(self, days_back: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch from all enabled providers concurrently.
        
        Args:
            days_back: Include events from last N days
            
        Returns:
            Dict mapping provider names to event lists
        """
        tasks = {
            provider: self.fetch_economic_events(provider, days_back)
            for provider in EconomicDataProviderRegistry.get_all_providers()
        }
        
        results = {}
        for provider, task in tasks.items():
            try:
                results[provider] = await task
            except Exception as e:
                logger.error(f"Failed to fetch from {provider}: {e}")
                results[provider] = []
        
        return results
    
    def _is_cache_valid(self, provider_name: str) -> bool:
        """Check if cached data exists and is still valid (non-expired)."""
        if provider_name not in self.cache:
            return False
        
        cached_time = self.cache[provider_name]["timestamp"]
        if datetime.now(timezone.utc) - cached_time > self.cache_ttl:
            logger.info(f"[{provider_name}] Cache expired")
            # DON'T delete - keep it for fallback use
            return False
        
        return True
    
    def _update_cache(self, provider_name: str, events: List[Dict[str, Any]]) -> None:
        """Update cache with new data."""
        self.cache[provider_name] = {
            "timestamp": datetime.now(timezone.utc),
            "data": events
        }
    
    def _get_cached_data(self, provider_name: str) -> List[Dict[str, Any]]:
        """Get cached data regardless of expiration."""
        if provider_name in self.cache:
            logger.info(f"[{provider_name}] Using stale cache as fallback")
            return self.cache[provider_name]["data"]
        return []
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of all providers.
        
        Returns:
            Dict mapping provider names to health status
        """
        results = {}
        for provider_name, adapter in self.adapters.items():
            results[provider_name] = await adapter.health_check()
        
        return results
    
    def get_supported_providers(self) -> List[str]:
        """Get list of supported providers."""
        return EconomicDataProviderRegistry.get_all_providers()


# Example usage (for testing)
if __name__ == "__main__":
    async def main() -> None:
        gateway = EconomicDataGateway(use_cache=True)
        
        # Test single provider
        events = await gateway.fetch_economic_events("INVESTING", days_back=7)
        print(f"Investing events: {len(events)}")
        
        # Test all providers
        all_events = await gateway.fetch_all_providers(days_back=7)
        for provider, events in all_events.items():
            print(f"{provider}: {len(events)} events")
        
        # Health check
        health = await gateway.health_check()
        print(f"Health: {health}")
    
    # Run example
    asyncio.run(main())
