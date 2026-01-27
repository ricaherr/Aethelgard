"""
Data Provider Manager - Sistema de múltiples proveedores con fallback
Administra varios proveedores de datos con prioridad y fallback automático
"""
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


def _load_provider_config(config_path: str = "config/data_providers.json") -> dict:
    """Load data provider configuration"""
    p = Path(config_path)
    if not p.exists():
        logger.warning(f"Config file {config_path} not found. Using defaults.")
        return {
            "yahoo": {
                "enabled": True,
                "priority": 1,
                "requires_auth": False
            }
        }
    
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading provider config: {e}")
        return {}


class DataProviderManager:
    """
    Manages multiple data providers with automatic fallback.
    
    Priority order:
    1. Yahoo Finance (free, no auth)
    2. Alpha Vantage (free tier available)
    3. Twelve Data (free tier available)
    4. Polygon.io (requires paid plan)
    5. IEX Cloud (free tier available)
    6. Finnhub (free tier available)
    7. MT5 (requires MT5 installation)
    """
    
    def __init__(self, config_path: str = "config/data_providers.json"):
        """
        Initialize Data Provider Manager
        
        Args:
            config_path: Path to provider configuration file
        """
        self.config = _load_provider_config(config_path)
        self.providers = []
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all enabled providers"""
        provider_classes = {
            "yahoo": ("connectors.generic_data_provider", "GenericDataProvider"),
            "alpha_vantage": ("connectors.alpha_vantage_provider", "AlphaVantageProvider"),
            "twelve_data": ("connectors.twelve_data_provider", "TwelveDataProvider"),
            "polygon": ("connectors.polygon_provider", "PolygonProvider"),
            "iex_cloud": ("connectors.iex_cloud_provider", "IEXCloudProvider"),
            "finnhub": ("connectors.finnhub_provider", "FinnhubProvider"),
            "mt5": ("connectors.mt5_data_provider", "MT5DataProvider"),
        }
        
        # Sort by priority
        sorted_providers = sorted(
            self.config.items(),
            key=lambda x: x[1].get("priority", 999)
        )
        
        for provider_name, provider_config in sorted_providers:
            if not provider_config.get("enabled", False):
                continue
            
            if provider_name not in provider_classes:
                logger.warning(f"Unknown provider: {provider_name}")
                continue
            
            module_name, class_name = provider_classes[provider_name]
            
            try:
                # Dynamic import
                module = __import__(module_name, fromlist=[class_name])
                provider_class = getattr(module, class_name)
                
                # Initialize provider with config
                if provider_config.get("requires_auth", False):
                    api_key = provider_config.get("api_key")
                    if not api_key or api_key == "YOUR_API_KEY_HERE":
                        logger.warning(f"Provider {provider_name} requires API key but none provided")
                        continue
                    provider_instance = provider_class(api_key=api_key)
                else:
                    provider_instance = provider_class()
                
                self.providers.append({
                    "name": provider_name,
                    "instance": provider_instance,
                    "priority": provider_config.get("priority", 999),
                    "config": provider_config
                })
                
                logger.info(f"✓ Initialized provider: {provider_name} (priority {provider_config.get('priority')})")
                
            except ImportError as e:
                logger.debug(f"Provider {provider_name} not available: {e}")
            except Exception as e:
                logger.error(f"Error initializing provider {provider_name}: {e}")
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data with automatic fallback across providers
        
        Args:
            symbol: Symbol to fetch
            timeframe: Timeframe (M5, H1, etc.)
            count: Number of candles
        
        Returns:
            DataFrame with OHLC data or None if all providers fail
        """
        if not self.providers:
            logger.error("No data providers available")
            return None
        
        for provider_info in self.providers:
            provider_name = provider_info["name"]
            provider_instance = provider_info["instance"]
            
            try:
                logger.debug(f"Trying provider: {provider_name}")
                data = provider_instance.fetch_ohlc(symbol, timeframe, count)
                
                if data is not None and not data.empty:
                    logger.info(f"✓ Data fetched from {provider_name}: {len(data)} candles")
                    return data
                else:
                    logger.debug(f"Provider {provider_name} returned no data")
                    
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}")
                continue
        
        logger.error(f"All providers failed to fetch data for {symbol}")
        return None
    
    def get_enabled_providers(self) -> List[Dict[str, Any]]:
        """Get list of enabled providers with their status"""
        return [
            {
                "name": p["name"],
                "priority": p["priority"],
                "enabled": True,
                "requires_auth": p["config"].get("requires_auth", False)
            }
            for p in self.providers
        ]
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers"""
        status = {}
        for provider_info in self.providers:
            name = provider_info["name"]
            instance = provider_info["instance"]
            
            # Try to fetch a small sample to check status
            try:
                test_data = instance.fetch_ohlc("AAPL", "D1", 1)
                is_working = test_data is not None and not test_data.empty
            except:
                is_working = False
            
            status[name] = {
                "enabled": True,
                "working": is_working,
                "priority": provider_info["priority"]
            }
        
        return status
