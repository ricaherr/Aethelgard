"""
Data Provider Manager - Multi-source data provider management system
Manages multiple data providers with automatic fallback, priority, and configuration
Follows Rule #2: Agnóstico de código - lógica agnóstica de plataforma
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a data provider"""
    name: str
    enabled: bool = True
    requires_auth: bool = False
    priority: int = 50  # Higher = more priority
    free_tier: bool = True
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    additional_config: Dict[str, Any] = field(default_factory=dict)
    is_system: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return asdict(self)


@dataclass
class ProviderStatus:
    """Status information for a provider"""
    name: str
    enabled: bool
    available: bool
    requires_auth: bool
    last_check: Optional[datetime] = None
    error_message: Optional[str] = None
    credentials_configured: bool = False


class DataProvider(Protocol):
    """Protocol for data providers"""
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[Any]:
        """Fetch OHLC data"""
        ...
    
    def is_available(self) -> bool:
        """Check if provider is available"""
        ...


class DataProviderManager:
    """
    Manages multiple data providers with automatic fallback and priority
    
    Features:
    - Multiple provider support (Yahoo, Alpha Vantage, Twelve Data, etc.)
    - Automatic fallback when primary provider fails
    - Priority-based provider selection
    - Configuration persistence
    - Free/paid provider filtering
    """
    
    DEFAULT_PROVIDERS = {
        "yahoo": {
            "name": "yahoo",
            "enabled": True,
            "requires_auth": False,
            "priority": 100,  # Highest priority (free, no auth)
            "free_tier": True,
            "module": "connectors.generic_data_provider",
            "class": "GenericDataProvider",
            "description": "Yahoo Finance - Totalmente gratuito, sin API key",
            "supports": ["stocks", "forex", "crypto", "commodities", "indices"]
        },
        "alphavantage": {
            "name": "alphavantage",
            "enabled": False,
            "requires_auth": True,
            "priority": 80,
            "free_tier": True,
            "module": "connectors.alphavantage_provider",
            "class": "AlphaVantageProvider",
            "description": "Alpha Vantage - Gratuito con API key (500 req/día)",
            "supports": ["stocks", "forex", "crypto"]
        },
        "twelvedata": {
            "name": "twelvedata",
            "enabled": False,
            "requires_auth": True,
            "priority": 70,
            "free_tier": True,
            "module": "connectors.twelvedata_provider",
            "class": "TwelveDataProvider",
            "description": "Twelve Data - Gratuito con API key (800 req/día)",
            "supports": ["stocks", "forex", "crypto", "commodities"]
        },
        "ccxt": {
            "name": "ccxt",
            "enabled": False,
            "requires_auth": False,
            "priority": 90,
            "free_tier": True,
            "module": "connectors.ccxt_provider",
            "class": "CCXTProvider",
            "description": "CCXT - Gratuito para crypto (100+ exchanges)",
            "supports": ["crypto"]
        },
        "polygon": {
            "name": "polygon",
            "enabled": False,
            "requires_auth": True,
            "priority": 60,
            "free_tier": True,
            "module": "connectors.polygon_provider",
            "class": "PolygonProvider",
            "description": "Polygon.io - Tier gratuito limitado",
            "supports": ["stocks", "forex", "crypto"]
        },
        "mt5": {
            "name": "mt5",
            "enabled": False,
            "requires_auth": True,
            "priority": 95,
            "free_tier": True,
            "module": "connectors.mt5_data_provider",
            "class": "MT5DataProvider",
            "description": "MetaTrader 5 - Requiere instalación local",
            "supports": ["forex", "stocks", "commodities", "indices"]
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize DataProviderManager
        
        Args:
            config_path: Optional path to legacy provider configuration file for migration
        """
        self.config_path = Path(config_path) if config_path else None
        self.storage = StorageManager()
        self.providers: Dict[str, ProviderConfig] = {}
        self.provider_instances: Dict[str, Any] = {}
        self.provider_metadata: Dict[str, Dict] = self.DEFAULT_PROVIDERS.copy()
        
        self._load_configuration()
    
    def _load_configuration(self):
        """Load provider configuration from DB with fallback to JSON migration"""
        try:
            db_providers = self.storage.get_data_providers()
            
            if db_providers:
                # Load from DB
                for p_data in db_providers:
                    name = p_data['name']
                    self.providers[name] = ProviderConfig(
                        name=name,
                        enabled=bool(p_data['enabled']),
                        priority=p_data['priority'],
                        requires_auth=bool(p_data['requires_auth']),
                        api_key=p_data.get('api_key'),
                        api_secret=p_data.get('api_secret'),
                        additional_config=p_data.get('additional_config', {}),
                        is_system=bool(p_data.get('is_system', 0))
                    )
                logger.info(f"Loaded {len(self.providers)} providers from database")
            elif self.config_path.exists():
                # Migrate from JSON
                logger.info(f"Migrating provider configuration from {self.config_path} to DB")
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for name, config_data in data.items():
                        self.providers[name] = ProviderConfig(**config_data)
                        # Save to DB immediately
                        self.storage.save_data_provider(
                            name=name,
                            enabled=self.providers[name].enabled,
                            priority=self.providers[name].priority,
                            requires_auth=self.providers[name].requires_auth,
                            api_key=self.providers[name].api_key,
                            api_secret=self.providers[name].api_secret,
                            additional_config=self.providers[name].additional_config,
                            is_system=self.providers[name].is_system
                        )
                    logger.info(f"Successfully migrated {len(self.providers)} providers to DB")
                    # Optional: rename JSON file after migration
                    # self.config_path.rename(self.config_path.with_suffix('.json.bak'))
                except Exception as e:
                    logger.error(f"Error during JSON migration: {e}")
                    self._initialize_defaults()
            else:
                self._initialize_defaults()
        except Exception as e:
            logger.error(f"Error loading provider config from DB: {e}")
            self._initialize_defaults()
    
    def _initialize_defaults(self):
        """Initialize default provider configurations and save to DB"""
        for name, metadata in self.provider_metadata.items():
            config = ProviderConfig(
                name=name,
                enabled=metadata.get("enabled", False),
                requires_auth=metadata.get("requires_auth", False),
                priority=metadata.get("priority", 50),
                free_tier=metadata.get("free_tier", True)
            )
            self.providers[name] = config
            # Save to DB
            self.storage.save_data_provider(
                name=name,
                enabled=config.enabled,
                priority=config.priority,
                requires_auth=config.requires_auth,
                api_key=config.api_key,
                api_secret=config.api_secret,
                additional_config=config.additional_config,
                is_system=config.is_system
            )
        
        logger.info("Initialized default provider configurations in database")
    
    def save_configuration(self):
        """Save current provider configuration to DB"""
        try:
            for name, config in self.providers.items():
                self.storage.save_data_provider(
                    name=name,
                    enabled=config.enabled,
                    priority=config.priority,
                    requires_auth=config.requires_auth,
                    api_key=config.api_key,
                    api_secret=config.api_secret,
                    additional_config=config.additional_config,
                    is_system=config.is_system
                )
            logger.info("Provider configuration saved to database")
        except Exception as e:
            logger.error(f"Error saving provider config to DB: {e}")
    
    def get_available_providers(self) -> List[str]:
        """Get list of all available provider names"""
        return list(self.providers.keys())
    
    def get_active_providers(self) -> List[Dict]:
        """Get list of currently enabled providers with metadata, reloading from DB for real-time updates"""
        active = []
        
        # Reload from DB to catch changes from other processes (Dashboard)
        self._load_configuration()
        
        for name, config in self.providers.items():
            if config.enabled:
                metadata = self.provider_metadata.get(name, {})
                active.append({
                    "name": name,
                    "priority": config.priority,
                    "requires_auth": config.requires_auth,
                    "is_system": config.is_system,
                    "free_tier": config.free_tier,
                    "description": metadata.get("description", ""),
                    "supports": metadata.get("supports", [])
                })
        
        # Sort by priority (highest first)
        active.sort(key=lambda x: x["priority"], reverse=True)
        return active
    
    def enable_provider(self, name: str) -> bool:
        """Enable a provider"""
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return False
        
        self.providers[name].enabled = True
        self.save_configuration()
        logger.info(f"Enabled provider: {name}")
        return True
    
    def disable_provider(self, name: str) -> bool:
        """Disable a provider"""
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return False
        
        self.providers[name].enabled = False
        
        # Remove instance if cached
        if name in self.provider_instances:
            del self.provider_instances[name]
        
        self.save_configuration()
        logger.info(f"Disabled provider: {name}")
        return True

    def set_system_provider(self, name: str, is_system: bool) -> bool:
        """Set or unset a provider as system-level"""
        if name not in self.providers:
            return False
            
        self.providers[name].is_system = is_system
        self.save_configuration()
        logger.info(f"Provider '{name}' system status set to: {is_system}")
        return True
    
    def is_provider_enabled(self, name: str) -> bool:
        """Check if provider is enabled"""
        if name not in self.providers:
            return False
        return self.providers[name].enabled
    
    def configure_provider(self, name: str, **kwargs) -> bool:
        """
        Configure provider with credentials/settings
        
        Args:
            name: Provider name
            **kwargs: Configuration parameters (api_key, api_secret, etc.)
        """
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return False
        
        config = self.providers[name]
        
        if 'api_key' in kwargs:
            config.api_key = kwargs['api_key']
        if 'api_secret' in kwargs:
            config.api_secret = kwargs['api_secret']
        
        # Store additional config
        for key, value in kwargs.items():
            if key not in ['api_key', 'api_secret']:
                config.additional_config[key] = value
        
        self.save_configuration()
        logger.info(f"Configured provider: {name}")
        return True
    
    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider"""
        return self.providers.get(name)
    
    def get_provider_status(self, name: str) -> Optional[ProviderStatus]:
        """Get status information for a provider"""
        if name not in self.providers:
            return None
        
        config = self.providers[name]
        
        # Check if provider is available
        available = self._check_provider_availability(name)
        
        # Check if credentials are configured
        credentials_configured = True
        if config.requires_auth:
            if name == "mt5":
                # Special check for MT5 (requires login, password, and server)
                mt5_cfg = config.additional_config
                credentials_configured = bool(mt5_cfg.get("login") and mt5_cfg.get("server"))
                # Note: password might be empty if already saved, but login/server are mandatory
            else:
                credentials_configured = bool(config.api_key)
        
        return ProviderStatus(
            name=name,
            enabled=config.enabled,
            available=available,
            requires_auth=config.requires_auth,
            credentials_configured=credentials_configured,
            last_check=datetime.now()
        )
    
    def _check_provider_availability(self, name: str) -> bool:
        """Check if provider is available (module can be imported)"""
        metadata = self.provider_metadata.get(name, {})
        module_path = metadata.get("module")
        
        if not module_path:
            return False
        
        try:
            __import__(module_path)
            return True
        except ImportError:
            return False
    
    def _get_provider_instance(self, name: str) -> Optional[Any]:
        """Get or create provider instance"""
        # Return cached instance if available
        if name in self.provider_instances:
            return self.provider_instances[name]
        
        # Check if enabled
        if not self.is_provider_enabled(name):
            return None
        
        # Get metadata
        metadata = self.provider_metadata.get(name, {})
        module_path = metadata.get("module")
        class_name = metadata.get("class")
        
        if not module_path or not class_name:
            logger.error(f"Missing module/class for provider: {name}")
            return None
        
        try:
            # Import module
            module = __import__(module_path, fromlist=[class_name])
            provider_class = getattr(module, class_name)
            
            # Get configuration
            config = self.providers[name]
            
            # Create instance with configuration
            kwargs = {}
            if config.api_key:
                kwargs['api_key'] = config.api_key
            if config.api_secret:
                kwargs['api_secret'] = config.api_secret
            kwargs.update(config.additional_config)
            
            instance = provider_class(**kwargs)
            
            # Cache instance only if successfully initialized
            if hasattr(instance, 'is_available') and not instance.is_available():
                logger.info(f"Provider {name} instance created but not available. Not caching to allow retry.")
                return instance
                
            self.provider_instances[name] = instance
            logger.info(f"Created instance for provider: {name}")
            return instance
            
        except Exception as e:
            logger.error(f"Error creating provider instance '{name}': {e}")
            return None
    
    def get_best_provider(self) -> Optional[Any]:
        """Get best available provider based on priority"""
        # Get active providers sorted by priority
        active = self.get_active_providers()
        
        for provider_info in active:
            name = provider_info["name"]
            
            # Check if credentials configured if required
            config = self.providers[name]
            if config.requires_auth and not config.api_key:
                logger.debug(f"Skipping {name}: credentials not configured")
                continue
            
            # Try to get instance
            instance = self._get_provider_instance(name)
            if instance:
                logger.info(f"Selected provider: {name} (priority: {config.priority})")
                return instance
        
        logger.warning("No available providers found")
        return None
    
    def get_provider_for_symbol(self, symbol: str) -> Optional[Any]:
        """Get best provider for a specific symbol type"""
        # Detect symbol type
        symbol_type = self._detect_symbol_type(symbol)
        
        # Get active providers that support this type
        active = self.get_active_providers()
        
        for provider_info in active:
            if symbol_type in provider_info.get("supports", []):
                name = provider_info["name"]
                instance = self._get_provider_instance(name)
                if instance:
                    return instance
        
        # Fallback to best general provider
        return self.get_best_provider()
    
    def _detect_symbol_type(self, symbol: str) -> str:
        """Detect symbol type (stock, forex, crypto, etc.)"""
        symbol_upper = symbol.upper()
        
        # Crypto patterns
        if "BTC" in symbol_upper or "ETH" in symbol_upper or symbol_upper.endswith("USD"):
            if any(crypto in symbol_upper for crypto in ["BTC", "ETH", "XRP", "LTC", "ADA"]):
                return "crypto"
        
        # Forex patterns (6 chars, currency pairs)
        if len(symbol_upper) == 6 and all(c.isalpha() for c in symbol_upper):
            return "forex"
        
        # Commodities
        if "GOLD" in symbol_upper or "SILVER" in symbol_upper or "OIL" in symbol_upper:
            return "commodities"
        
        # Default to stocks
        return "stocks"
    
    def validate_provider(self, name: str) -> bool:
        """Validate provider connection and credentials"""
        instance = self._get_provider_instance(name)
        
        if not instance:
            return False
        
        # Check if provider has is_available method
        if hasattr(instance, 'is_available'):
            try:
                return instance.is_available()
            except Exception as e:
                logger.error(f"Error validating provider '{name}': {e}")
                return False
        
        # If no is_available method, just check if instance exists
        return True
    
    def get_free_providers(self) -> List[Dict]:
        """Get list of providers that don't require authentication"""
        free = []
        
        for name, config in self.providers.items():
            if not config.requires_auth:
                metadata = self.provider_metadata.get(name, {})
                free.append({
                    "name": name,
                    "enabled": config.enabled,
                    "description": metadata.get("description", ""),
                    "supports": metadata.get("supports", [])
                })
        
        return free
    
    def get_auth_required_providers(self) -> List[Dict]:
        """Get list of providers requiring authentication"""
        auth_required = []
        
        for name, config in self.providers.items():
            if config.requires_auth:
                metadata = self.provider_metadata.get(name, {})
                auth_required.append({
                    "name": name,
                    "enabled": config.enabled,
                    "configured": bool(config.api_key),
                    "description": metadata.get("description", ""),
                    "supports": metadata.get("supports", [])
                })
        
        return auth_required
    
    def set_provider_priority(self, name: str, priority: int):
        """Set provider priority (higher = more priority)"""
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return
        
        self.providers[name].priority = priority
        self.save_configuration()
        logger.info(f"Set priority for {name}: {priority}")
    
    def get_provider_capabilities(self, name: str) -> Optional[Dict]:
        """Get provider capabilities"""
        metadata = self.provider_metadata.get(name, {})
        
        if not metadata:
            return None
        
        return {
            "name": name,
            "asset_types": metadata.get("supports", []),
            "description": metadata.get("description", ""),
            "requires_auth": metadata.get("requires_auth", False),
            "free_tier": metadata.get("free_tier", True)
        }
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500,
        provider_name: Optional[str] = None,
        only_system: bool = False
    ) -> Optional[Any]:
        """
        Fetch OHLC data with automatic fallback
        
        Args:
            symbol: Symbol to fetch
            timeframe: Timeframe (M5, H1, etc.)
            count: Number of candles
            provider_name: Specific provider to use (optional)
            only_system: If True, only use providers marked as system-level (optional)
        
        Returns:
            OHLC data or None
        """
        if provider_name:
            # Use specific provider
            instance = self._get_provider_instance(provider_name)
            if instance:
                try:
                    return instance.fetch_ohlc(symbol, timeframe, count)
                except Exception as e:
                    logger.error(f"Error fetching from {provider_name}: {e}")
                    return None
        
        # Try providers in priority order with fallback
        active = self.get_active_providers()
        
        # Filter by system if requested
        if only_system:
            active = [p for p in active if p.get("is_system", False)]
        
        for provider_info in active:
            name = provider_info["name"]
            instance = self._get_provider_instance(name)
            
            if instance:
                try:
                    data = instance.fetch_ohlc(symbol, timeframe, count)
                    if data is not None:
                        logger.debug(f"Successfully fetched data from {name}")
                        return data
                except Exception as e:
                    logger.warning(f"Provider {name} failed: {e}, trying next...")
                    continue
        
        logger.error(f"All providers failed for symbol {symbol}")
        return None
