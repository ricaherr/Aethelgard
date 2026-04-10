"""
Data Provider Manager - Multi-source data provider management system
Manages multiple data providers with automatic fallback, priority, and configuration
Follows Rule #2: Agnóstico de código - lógica agnóstica de plataforma
"""
from __future__ import annotations

import inspect
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core_brain.symbol_coverage_policy import SymbolCoveragePolicy
from core_brain.symbol_taxonomy_engine import SymbolTaxonomy
from data_vault.storage import StorageManager

logger: logging.Logger = logging.getLogger(__name__)


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


@runtime_checkable
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
            "requires_auth": False,
            "priority": 50,  # Lower priority (fallback) 
            "free_tier": True,
            "module": "connectors.generic_data_provider",
            "class": "GenericDataProvider",
            "description": "Yahoo Finance - Totalmente gratuito, sin API key",
            "supports": ["stocks", "forex", "crypto", "commodities", "indices"],
            "is_system": True
        },
        "alphavantage": {
            "name": "alphavantage",
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
            "requires_auth": True,
            "priority": 70,  # Alternative FOREX connector (needs local MT5 install)
            "free_tier": True,
            "module": "connectors.mt5_data_provider",
            "class": "MT5DataProvider",
            "description": "MetaTrader 5 - Requiere instalación local",
            "supports": ["forex", "stocks", "commodities", "indices"]
        },
        "ctrader": {
            "name": "ctrader",
            "requires_auth": True,
            "priority": 100,  # Primary FOREX connector (WebSocket, no DLL, M1 viable)
            "free_tier": False,
            "module": "connectors.ctrader_connector",
            "class": "CTraderConnector",
            "description": "cTrader Open API - WebSocket streaming, <100ms latency, M1 viable",
            "supports": ["forex"]
        }
    }
    
    def __init__(self, storage: Optional[StorageManager] = None, config_path: Optional[str] = None) -> None:
        """
        Initialize DataProviderManager
        
        Args:
            storage: StorageManager instance (DI)
            config_path: Optional path to legacy provider configuration file for migration
        """
        self.config_path: Optional[Path] = Path(config_path) if config_path else None
        
        if storage is None:
            # Fallback to internal instantiation for backward compatibility (Violates DI)
            # This is temporary to stabilize the system before full refactoring
            logger.warning("DataProviderManager initialized without explicit storage! Violates strict DI.")
            self.storage = StorageManager()
        else:
            self.storage = storage
            
        self.providers: Dict[str, ProviderConfig] = {}
        self.provider_instances: Dict[str, Any] = {}
        self.provider_metadata: Dict[str, Dict] = self.DEFAULT_PROVIDERS.copy()
        
        # Cache of initialized provider instances
        self._instances: Dict[str, Any] = {}
        
        # Provider selection cache - selected ONCE at startup
        self._selected_provider: Optional[Any] = None
        self._selected_provider_name: Optional[str] = None
        self._provider_selection_initialized: bool = False
        self._coverage_policy: SymbolCoveragePolicy = SymbolCoveragePolicy(storage=self.storage)

        self._load_configuration()

    def register_provider_instance(self, name: str, instance: Any) -> None:
        """
        Manually register an already initialized provider instance.
        Useful for dependency injection (e.g., sharing MT5 connector).
        
        Args:
            name: Provider name (e.g., 'mt5')
            instance: Initialized provider instance
        """
        self.provider_instances[name.lower()] = instance
        # Ensure provider is marked as enabled in memory if injected
        if name.lower() in self.providers:
            self.providers[name.lower()].enabled = True
            
        logger.info(f"Registered external provider instance for: {name}")

    def _load_configuration(self) -> None:
        """Load provider configuration from DB with fallback to JSON migration"""
        try:
            db_providers = self.storage.get_sys_data_providers()
            
            if db_providers:
                # Load from DB
                for p_data in db_providers:
                    name = p_data['name']
                    config_data = p_data.get('config', {})
                    
                    # Handle additional_config - read from top-level of p_data (not nested in config)
                    # get_sys_data_providers() returns both config{} and additional_config{} at top level
                    additional_config = p_data.get('additional_config', {})
                    if isinstance(additional_config, str):
                        try:
                            additional_config = json.loads(additional_config) if additional_config else {}
                        except (json.JSONDecodeError, TypeError):
                            additional_config = {}
                    
                    # CRITICAL: Use DEFAULT_PROVIDERS as fallback for priority
                    # This ensures code changes to priorities take effect immediately
                    # WITHOUT being overridden by old DB values
                    default_config = self.DEFAULT_PROVIDERS.get(name, {})

                    # For all providers, prefer DB priority and fallback to metadata default.
                    db_priority = config_data.get('priority')
                    priority = db_priority if db_priority is not None else default_config.get('priority', 50)
                    
                    self.providers[name] = ProviderConfig(
                        name=name,
                        enabled=bool(p_data['enabled']),
                        priority=priority,
                        requires_auth=bool(config_data.get('requires_auth', False)),
                        api_key=config_data.get('api_key'),
                        api_secret=config_data.get('api_secret'),
                        additional_config=additional_config,
                        is_system=bool(config_data.get('is_system', 0))
                    )
                logger.info(f"Loaded {len(self.providers)} providers from database with priority defaults from code")
                enabled_summary = " | ".join(
                    f"{n}: {c.priority}{'✓' if c.enabled else '✗'}"
                    for n, c in sorted(self.providers.items(), key=lambda x: -x[1].priority)
                    if c.enabled
                )
                logger.info(f"[PROVIDER PRIORITY] Active (by priority): {enabled_summary}")
                self._backfill_provider_loader_metadata(db_providers)
            else:
                # No DB config - initialize with defaults
                logger.info("No provider configuration in DB - initializing with defaults")
                self._initialize_defaults()
        except Exception as e:
            logger.error(f"Error loading provider config from DB: {e}")
            self._initialize_defaults()

    def _backfill_provider_loader_metadata(self, db_providers: List[Dict[str, Any]]) -> None:
        """Ensure connector module/class metadata is persisted in DB for dynamic loading."""
        providers_by_name = {str(p.get("name", "")).lower(): p for p in db_providers}
        updated_count = 0

        for name, metadata in self.provider_metadata.items():
            db_row = providers_by_name.get(name.lower())
            if not db_row:
                continue

            if db_row.get("connector_module") and db_row.get("connector_class"):
                continue

            self.storage.save_data_provider(
                name=name,
                enabled=bool(db_row.get("enabled", False)),
                priority=int(db_row.get("priority", metadata.get("priority", 50))),
                requires_auth=bool(db_row.get("requires_auth", metadata.get("requires_auth", False))),
                api_key=db_row.get("api_key"),
                api_secret=db_row.get("api_secret"),
                additional_config=db_row.get("additional_config") or {},
                is_system=bool(db_row.get("is_system", metadata.get("is_system", False))),
                connector_module=metadata.get("module"),
                connector_class=metadata.get("class"),
            )
            updated_count += 1

        if updated_count:
            logger.info(
                "[PROVIDER-METADATA] Backfilled connector loader metadata for %d provider(s)",
                updated_count,
            )
    
    def _initialize_defaults(self) -> None:
        """Initialize default provider configurations and save to DB"""
        for name, metadata in self.provider_metadata.items():
            config = ProviderConfig(
                name=name,
                enabled=True,
                requires_auth=metadata.get("requires_auth", False),
                priority=metadata.get("priority", 50),
                free_tier=metadata.get("free_tier", True),
                is_system=metadata.get("is_system", False)
            )
            self.providers[name] = config
            # Save to DB
            self.storage.save_data_provider(
                name=name,
                enabled=None,
                priority=config.priority,
                requires_auth=config.requires_auth,
                api_key=config.api_key,
                api_secret=config.api_secret,
                additional_config=config.additional_config,
                is_system=config.is_system,
                connector_module=metadata.get("module"),
                connector_class=metadata.get("class"),
                insert_only=True,
            )
        
        logger.info("Initialized default provider configurations in database")
    
    def save_configuration(self) -> None:
        """Save current provider configuration to DB"""
        try:
            for name, config in self.providers.items():
                metadata = self.provider_metadata.get(name, {})
                self.storage.save_data_provider(
                    name=name,
                    enabled=config.enabled,
                    priority=config.priority,
                    requires_auth=config.requires_auth,
                    api_key=config.api_key,
                    api_secret=config.api_secret,
                    additional_config=config.additional_config,
                    is_system=config.is_system,
                    connector_module=metadata.get("module"),
                    connector_class=metadata.get("class"),
                )
            logger.info("Provider configuration saved to database")
        except Exception as e:
            logger.error(f"Error saving provider config to DB: {e}")
    
    def get_available_providers(self) -> List[str]:
        """Get list of all available provider names"""
        return list(self.providers.keys())
    
    def get_active_providers(self, force_reload: bool = False) -> List[Dict]:
        """
        Get list of currently enabled providers with metadata.
        
        Args:
            force_reload: If True, reload from DB (use sparingly - performance critical)
        
        PERFORMANCE: By default, uses cached configuration.
        Only reload when explicitly needed (e.g., after Dashboard updates).
        """
        active = []
        
        # OPTIMIZATION: Only reload if explicitly requested
        # This prevents 1000+ DB queries per scan cycle
        if force_reload:
            self._load_configuration()
            logger.debug("Reloaded provider configuration from DB (force_reload=True)")
        
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
        
        # FALLBACK: If no providers enabled, use Yahoo as default
        if not active and "yahoo" in self.providers:
            logger.info("No providers enabled - using Yahoo as automatic fallback")
            yahoo_metadata = self.provider_metadata.get("yahoo", {})
            active.append({
                "name": "yahoo",
                "priority": self.providers["yahoo"].priority,
                "requires_auth": False,
                "is_system": False,
                "free_tier": True,
                "description": yahoo_metadata.get("description", ""),
                "supports": yahoo_metadata.get("supports", [])
            })
        
        return active
    
    def enable_provider(self, name: str) -> bool:
        """Enable a provider"""
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return False

        self.providers[name].enabled = True
        self.storage.update_provider_enabled(name, True)
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

        self.storage.update_provider_enabled(name, False)
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
    
    def reload_providers(self) -> None:
        """
        Reload provider configuration from DB and clear provider instance cache.
        
        Use this when provider configuration changes (API keys updated, providers enabled/disabled).
        PERFORMANCE WARNING: This clears all cached provider instances.
        """
        logger.info("Reloading provider configuration and clearing cache...")
        self._load_configuration()
        # Clear provider instances so they get recreated with new config
        self.provider_instances.clear()
        logger.info(f"Reloaded {len(self.providers)} providers from database")
    
    def is_provider_enabled(self, name: str) -> bool:
        """Check if provider is enabled"""
        if name not in self.providers:
            return False
        return self.providers[name].enabled
    
    def configure_provider(self, name: str, **kwargs) -> bool:
        """
        Configure provider with sys_credentials/settings
        
        Args:
            name: Provider name
            **kwargs: Configuration parameters (api_key, api_secret, etc.)
        """
        if name not in self.providers:
            logger.error(f"Provider '{name}' not found")
            return False
        
        config: ProviderConfig = self.providers[name]
        
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
        
        config: ProviderConfig = self.providers[name]
        
        # Check if provider is available
        available: bool = self._check_provider_availability(name)
        
        # Check if sys_credentials are configured
        credentials_configured = True
        if config.requires_auth:
            if name == "mt5":
                # Special check for MT5 (requires login, password, and server)
                mt5_cfg: Dict[str, Any] = config.additional_config
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
            config: ProviderConfig = self.providers[name]
            
            # Build kwargs from config
            kwargs = {}
            if config.api_key:
                kwargs['api_key'] = config.api_key
            if config.api_secret:
                kwargs['api_secret'] = config.api_secret
            kwargs.update(config.additional_config)

            # Inject storage if available
            if self.storage and 'storage' not in kwargs:
                kwargs['storage'] = self.storage

            # Selective injection: filter kwargs to only accepted constructor params
            # (prevents TypeError when additional_config has fields unknown to the provider)
            try:
                sig = inspect.signature(provider_class.__init__)
                params = sig.parameters
                accepted = {p for p in params if p != 'self'}
                has_var_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in params.values()
                )
                if not has_var_kwargs:
                    filtered = {k: v for k, v in kwargs.items() if k in accepted}
                    if len(filtered) < len(kwargs):
                        ignored = set(kwargs) - set(filtered)
                        logger.debug(
                            f"[PROVIDER] Filtered {len(ignored)} unsupported kwargs for "
                            f"{class_name}: {ignored}"
                        )
                    kwargs = filtered
            except (ValueError, TypeError) as e:
                logger.debug(f"[PROVIDER] Could not introspect {class_name} signature: {e}. Passing all kwargs.")

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
        """
        Get best available provider based on priority.
        Selection is cached at startup - only changes on failure (fallback).
        This prevents repeated log messages and ensures deterministic behavior.
        """
        # First call: perform selection and cache it
        if not self._provider_selection_initialized:
            self._select_best_provider_once()
        
        # Return cached selection
        return self._selected_provider
    
    def _select_best_provider_once(self) -> None:
        """
        Perform the provider selection ONCE at startup.
        Logs the selected provider and caches it.
        """
        self._provider_selection_initialized = True
        
        # Get active providers sorted by priority
        active = self.get_active_providers()
        
        for provider_info in active:
            name = provider_info["name"]
            supports = [str(s).lower() for s in provider_info.get("supports", [])]

            # Generic startup selection should prefer multi-asset/general providers.
            # Crypto-only providers are considered by symbol-specific routing.
            if supports and all(asset == "crypto" for asset in supports):
                logger.debug(f"Skipping {name}: crypto-only provider for generic startup selection")
                continue
            
            # Check if sys_credentials configured if required
            config: ProviderConfig = self.providers[name]
            
            # Determine whether credentials are configured per-provider storage strategy
            has_creds = bool(config.api_key)
            if name == "ctrader":
                # cTrader credentials live in sys_data_providers.additional_config.
                # access_token is the minimum required field.
                has_creds = bool(config.additional_config.get("access_token"))
            elif name == "mt5":
                login = config.additional_config.get("login")
                server = config.additional_config.get("server")
                has_creds = bool(login and server)
            
            # If instance is already injected/cached, we assume it's valid regardless of config
            is_injected = name in self.provider_instances
            
            if config.requires_auth and not has_creds and not is_injected:
                logger.debug(f"Skipping {name}: sys_credentials not configured")
                continue
            
            # Try to get instance — only accept it if it reports as available right now
            instance: Any | None = self._get_provider_instance(name)
            if instance:
                provider_ready = (
                    not hasattr(instance, "is_available") or instance.is_available()
                )
                if not provider_ready:
                    logger.debug(
                        f"[STARTUP] Skipping {name}: instance created but is_available()=False"
                    )
                    continue
                # Cache the selection and log it ONCE
                self._selected_provider = instance
                self._selected_provider_name = name
                logger.info(f"[STARTUP] Selected primary provider: {name} (priority: {config.priority})")
                return
        
        # FALLBACK: Try yahoo directly if no other provider worked
        if "yahoo" in self.providers:
            logger.info("[STARTUP] No configured providers available - forcing Yahoo fallback")
            # Temporarily enable yahoo for fallback (don't save to DB)
            yahoo_was_enabled: bool = self.providers["yahoo"].enabled
            self.providers["yahoo"].enabled = True
            
            try:
                instance: Any | None = self._get_provider_instance("yahoo")
                if instance:
                    self._selected_provider = instance
                    self._selected_provider_name = "yahoo"
                    logger.info("[STARTUP] Yahoo fallback activated successfully")
                    return
            finally:
                # Restore original state (in memory only)
                self.providers["yahoo"].enabled = yahoo_was_enabled
        
        logger.warning("[STARTUP] No available providers found (all fallbacks exhausted)")
        self._selected_provider = None
        self._selected_provider_name = None
    
    def get_provider_for_symbol(self, symbol: str) -> Optional[Any]:
        """Get best provider for a specific symbol type"""
        # Detect symbol type using SSOT
        symbol_type: str = SymbolTaxonomy.get_symbol_type(symbol)
        
        # Get active providers that support this type
        active = self.get_active_providers()
        
        for provider_info in active:
            if symbol_type in provider_info.get("supports", []):
                name = provider_info["name"]
                instance: Any | None = self._get_provider_instance(name)
                if instance:
                    return instance
        
        # Fallback to best general provider
        return self.get_best_provider()
    
    def force_reselect_provider(self) -> Optional[Any]:
        """
        Force reselection of provider (used when current provider fails).
        Resets cache and performs selection again.
        
        Returns:
            New selected provider instance or None
        """
        logger.warning(f"[FALLBACK] Current provider ({self._selected_provider_name}) failed. Reselecting...")
        self._provider_selection_initialized = False
        self._selected_provider = None
        self._selected_provider_name = None
        return self.get_best_provider()
    
    # NOTE: Symbol type detection moved to SymbolTaxonomy (SSOT)
    # Use SymbolTaxonomy.get_symbol_type() instead of local implementation

    def _provider_supports_symbol(self, instance: Any, symbol: str) -> bool:
        """
        Return True if provider instance can handle symbol.

        Providers that do not expose `is_symbol_supported` are treated as compatible
        to preserve backward compatibility.
        """
        checker = getattr(instance, "is_symbol_supported", None)
        if not callable(checker):
            return True

        try:
            return bool(checker(symbol))
        except Exception as exc:
            provider_name = getattr(instance, "provider_id", instance.__class__.__name__)
            logger.debug("Provider %s support check failed for %s: %s", provider_name, symbol, exc)
            return False
    
    def validate_provider(self, name: str) -> bool:
        """Validate provider connection and sys_credentials"""
        instance: Any | None = self._get_provider_instance(name)
        
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
    
    def is_local(self) -> bool:
        """
        Check if the best available provider is local (fast access).
        Used by ScannerEngine to optimize sleep intervals.
        """
        provider = self.get_best_provider()
        if provider and hasattr(provider, 'is_local'):
            return provider.is_local()
        return False
    
    def is_available(self) -> bool:
        """
        Check if data service is available (at least one provider working).
        Satisfies DataProvider protocol.
        """
        # Quick check: do we have any active provider capable of fetching data?
        best = self.get_best_provider()
        if not best:
             return False
        
        # If best provider has is_available, use it
        if hasattr(best, 'is_available'):
             return best.is_available()
             
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
    
    def set_provider_priority(self, name: str, priority: int) -> None:
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

    def get_connected_active_provider(self) -> Optional[Dict[str, Any]]:
        """
        Resolve the first active provider that is connected and currently available.

        Returns:
            Provider descriptor with minimal telemetry metadata, or None if unavailable.
        """
        for provider_info in self.get_active_providers():
            provider_name = provider_info["name"]
            instance = self._get_provider_instance(provider_name)
            if not instance:
                continue

            is_connected = bool(getattr(instance, "is_connected", True))
            is_available = True
            if hasattr(instance, "is_available"):
                try:
                    is_available = bool(instance.is_available())
                except Exception:
                    is_available = False

            if not is_connected and is_available:
                connect_fn = getattr(instance, "connect_blocking", None) or getattr(instance, "connect", None)
                if callable(connect_fn):
                    try:
                        is_connected = bool(connect_fn())
                    except Exception:
                        is_connected = False

            if not (is_connected and is_available):
                continue

            return {
                "name": provider_name,
                "instance": instance,
                "priority": provider_info.get("priority", 0),
                "supports": provider_info.get("supports", []),
                "is_connected": is_connected,
                "is_available": is_available,
            }

        return None

    def get_active_provider(self) -> Optional[Dict[str, Any]]:
        """
        Backward-compatible singular accessor for active connected provider.

        Returns:
            Same descriptor structure as get_connected_active_provider().
        """
        return self.get_connected_active_provider()
    
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
        symbol_type = SymbolTaxonomy.get_symbol_type(symbol)

        if provider_name:
            # Use specific provider (bypass coverage policy for explicit requests)
            instance: Any | None = self._get_provider_instance(provider_name)
            if instance:
                if not self._provider_supports_symbol(instance, symbol):
                    logger.warning("Provider %s does not support symbol %s", provider_name, symbol)
                    return None
                try:
                    return instance.fetch_ohlc(symbol, timeframe, count)
                except Exception as e:
                    logger.error(f"Error fetching from {provider_name}: {e}")
                    return None

        # --- Coverage policy pre-check: skip iteration for excluded symbols ---
        if self._coverage_policy.is_temporarily_excluded(symbol):
            logger.debug(
                "[COVERAGE-POLICY] Skipping %s: symbol is temporarily excluded (cooldown active)",
                symbol,
            )
            return None

        # Try providers in priority order with fallback
        active = self.get_active_providers()
        
        # Filter by system if requested
        if only_system:
            active = [p for p in active if p.get("is_system", False)]
        
        for provider_info in active:
            name = provider_info["name"]
            supports = [str(asset).lower() for asset in provider_info.get("supports", [])]
            if supports and symbol_type not in supports:
                logger.debug("Skipping provider %s for %s: symbol_type=%s not in supports=%s", name, symbol, symbol_type, supports)
                continue

            instance: Any | None = self._get_provider_instance(name)
            
            if instance:
                if not self._provider_supports_symbol(instance, symbol):
                    logger.debug("Skipping provider %s for %s: provider-specific unsupported symbol", name, symbol)
                    continue
                try:
                    data = instance.fetch_ohlc(symbol, timeframe, count)
                    if data is not None:
                        logger.debug(f"Successfully fetched data from {name}")
                        # --- Coverage policy: reset failure state on success ---
                        self._coverage_policy.register_success(symbol, provider_name=name)
                        return data
                except Exception as e:
                    logger.warning(f"Provider {name} failed: {e}, trying next...")
                    continue

        # All fallbacks exhausted — register failure and conditionally log warning.
        # Coverage policy tracks backoff; warning is throttled to avoid operational noise.
        exclusion_triggered = self._coverage_policy.register_failure(
            symbol, reason_code="all_fallbacks_exhausted"
        )
        if self._coverage_policy.should_emit_warning(symbol):
            logger.warning(
                "[DATA-FALLBACK] Providers unavailable for symbol %s (all fallbacks exhausted)%s",
                symbol,
                " — exclusion activated" if exclusion_triggered else "",
            )
        return None

    def get_provider_coverage_snapshot(self) -> Dict[str, Any]:
        """
        Read-only snapshot of current per-symbol coverage state.
        Intended for operational observability (health endpoints, dashboards).
        """
        return self._coverage_policy.get_snapshot()
