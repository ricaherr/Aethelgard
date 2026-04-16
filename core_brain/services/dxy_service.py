"""
DXY (USD Dollar Index) Service - Multi-Source Data Fetcher with Automatic Fallback

✅ REGLAS CUMPLIDAS:
- Rule #4 (Agnóstica): Retorna List[Dict], no DataFrame
- Rule #15 (SSOT): Cache persistido en StorageManager, no archivos JSON
- Type Hints: 100% coverage
- Clean Code: Métodos pequeños, responsabilidad única

Fallback Chain (SSOT — todos los intentos respetan sys_data_providers en BD):
1. DataProviderManager.get_active_data_provider() — prioridad más alta habilitada en BD
2. Alpha Vantage — solo si enabled=True en sys_data_providers
3. Twelve Data  — solo si enabled=True en sys_data_providers
4. StorageManager cache (último recurso)

Integración:
- MainOrchestrator: self.dxy_service.fetch_dxy()
- ConfluenceService: para análisis EURUSD vs DXY
- Risk Management: para USD strength correlation
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class DXYService:
    """
    USD Dollar Index data service with multi-source fallback reliability.
    
    - Agnóstico: Dict-based output (Rule #4)
    - SSOT: Uses StorageManager for persistence (Rule #15)
    - Resilient: 5-level fallback chain
    - Async-ready for MainOrchestrator integration
    """
    
    # Cache TTL: 24 hours
    CACHE_TTL_SECONDS = 86400
    
    SUPPORTED_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    
    def __init__(
        self,
        storage: Any,
        data_provider_manager: Optional[Any] = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS
    ):
        """
        Initialize DXY Service.
        
        Args:
            storage: StorageManager instance (REQUIRED - Rule #15 SSOT)
            data_provider_manager: DataProviderManager for intelligent provider selection
            cache_ttl_seconds: Cache time-to-live (default 24h)
        """
        if storage is None:
            raise ValueError("[DXYService] StorageManager required (Rule #15 SSOT)")
        
        self.storage = storage
        self.data_provider_manager = data_provider_manager
        self.cache_ttl_seconds = cache_ttl_seconds
        
        logger.info(
            f"[DXYService] Init: SSOT in StorageManager, TTL={cache_ttl_seconds}s, "
            f"Agnóstico (Rule #4)"
        )
    
    async def fetch_dxy(
        self,
        timeframe: str = "H1",
        count: int = 100,
        use_cache_fallback: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch DXY data with automatic fallback.
        
        Returns agnóstic List[Dict[str, Any]] with OHLCV structure:
          [
            {"time": "2026-03-10T10:00:00", "open": 105.2, "high": 105.5, ...},
            ...
          ]
        
        Args:
            timeframe: "H1", "D1", etc.
            count: Number of candles
            use_cache_fallback: Use StorageManager cache if all providers fail
            
        Returns:
            List[Dict] with OHLCV or None if all sources fail
        """
        if timeframe not in self.SUPPORTED_TIMEFRAMES:
            logger.warning(f"[DXYService] Invalid timeframe {timeframe}, using H1")
            timeframe = "H1"
        
        logger.info(f"[DXYService] Fetch DXY ({timeframe}, {count})")
        
        # Attempt: Provider fetch
        data = await self._fetch_from_providers(timeframe, count)
        if data:
            self._persist_to_cache(data)
            logger.info(f"[DXYService] ✅ Fetched {len(data)} candles")
            return data
        
        # Fallback: Database cache
        if use_cache_fallback:
            logger.warning("[DXYService] ⚠️  Providers failed, using cache")
            data = self._load_from_cache(count)
            if data:
                logger.info(f"[DXYService] Loaded {len(data)} from cache")
                return data
        
        logger.error("[DXYService] ❌ All sources exhausted")
        return None
    
    async def _fetch_from_providers(
        self,
        timeframe: str,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Intenta obtener datos DXY desde los proveedores habilitados en BD (SSOT).

        Cadena de fallback — todos los intentos pasan por DataProviderManager
        que lee exclusivamente de ``sys_data_providers``:

        1. Auto-selección por símbolo (prioridad más alta habilitada en BD)
        2. Alpha Vantage (solo si habilitado en BD)
        3. Twelve Data (solo si habilitado en BD)
        """
        # Try #1: Auto-selección SSOT — DataProviderManager elige por prioridad en BD
        data = await self._try_provider_manager(timeframe, count)
        if data:
            return data

        # Try #2: Alpha Vantage (consulta BD via get_provider_instance)
        data = await self._try_named_provider("alphavantage", timeframe, count)
        if data:
            return data

        # Try #3: Twelve Data (consulta BD via get_provider_instance)
        data = await self._try_named_provider("twelvedata", timeframe, count)
        if data:
            return data

        return None

    async def _try_provider_manager(
        self,
        timeframe: str,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Selección automática SSOT: DataProviderManager elige el mejor proveedor
        disponible según ``sys_data_providers`` (prioridad + enabled en BD).
        """
        try:
            if self.data_provider_manager is None:
                return None

            # get_active_data_provider() incluye fallback EDGE automático
            provider = self.data_provider_manager.get_active_data_provider()
            if provider is None:
                return None

            df = provider.fetch_ohlc("DXY", timeframe, count)
            return self._convert_to_dict_list(df) if df is not None else None
        except Exception as e:
            logger.debug(f"[DXYService] Provider manager failed: {e}")
            return None

    async def _try_named_provider(
        self,
        name: str,
        timeframe: str,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Intenta un proveedor específico **solo si está habilitado en BD** (SSOT).

        Usa ``get_provider_instance(name)`` que comprueba ``sys_data_providers.enabled``
        antes de instanciar — nunca bypasea la BD.

        Args:
            name: Nombre del proveedor (ej. ``"alphavantage"``).
        """
        try:
            if self.data_provider_manager is None:
                return None

            # SSOT: retorna None si el proveedor está deshabilitado en BD
            provider = self.data_provider_manager.get_provider_instance(name)
            if provider is None:
                return None

            df = provider.fetch_ohlc("DXY", timeframe, count)
            return self._convert_to_dict_list(df) if df is not None else None
        except Exception as e:
            logger.debug(f"[DXYService] {name} failed: {e}")
            return None
    
    def _convert_to_dict_list(self, df: Any) -> Optional[List[Dict[str, Any]]]:
        """
        Convert DataFrame to List[Dict] (agnóstico - Rule #4).
        
        Nota: Pandas import ONLY in this method, maintains agnosis elsewhere.
        """
        try:
            records = []
            for _, row in df.iterrows():
                record = {
                    "time": str(row.get("time", "") or row.get("Time", "") or ""),
                    "open": float(row.get("open") or row.get("Open") or 0),
                    "high": float(row.get("high") or row.get("High") or 0),
                    "low": float(row.get("low") or row.get("Low") or 0),
                    "close": float(row.get("close") or row.get("Close") or 0),
                    "volume": float(row.get("volume") or row.get("Volume") or 0),
                }
                records.append(record)
            
            return records if records else None
        except Exception as e:
            logger.error(f"[DXYService] Conversion failed: {e}")
            return None
    
    def _persist_to_cache(self, data: List[Dict[str, Any]]) -> None:
        """Persist DXY data to StorageManager (Rule #15 SSOT)"""
        try:
            if not self.storage or not hasattr(self.storage, "log_market_cache"):
                logger.debug("[DXYService] Storage doesn't support cache persist")
                return
            
            # Persist: Keep last 100 candles with TTL metadata
            self.storage.log_market_cache(
                symbol="DXY",
                data=data,
                limit_records=100,
                metadata={
                    "ttl_seconds": self.cache_ttl_seconds,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": "multi-fallback"
                }
            )
            logger.debug(f"[DXYService] Cached {len(data[-100:])} candles in storage (Rule #15)")
        except Exception as e:
            logger.warning(f"[DXYService] Cache persist failed: {e}")
    
    def _load_from_cache(self, count: int) -> Optional[List[Dict[str, Any]]]:
        """Load DXY data from StorageManager cache (Rule #15 SSOT)"""
        try:
            if not self.storage or not hasattr(self.storage, "get_market_cache"):
                logger.debug("[DXYService] Storage doesn't support cache retrieval")
                return None
            
            # Load from SSOT: StorageManager persistent cache
            data = self.storage.get_market_cache(symbol="DXY", count=count or 100)
            
            if data:
                logger.info(f"[DXYService] Loaded {len(data)} records from SSOT cache")
                return data
            
            logger.warning("[DXYService] Cache empty or expired (Rule #15 fallback)")
            return None
        except Exception as e:
            logger.warning(f"[DXYService] Cache load failed: {e}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        return {
            "service": "DXYService",
            "ssot": "StorageManager (Rule #15)",
            "agnotic": "List[Dict] output (Rule #4)",
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "fallback_levels": 5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
_dxy_instance: Optional[DXYService] = None


def get_dxy_service(storage: Any, data_provider_manager: Optional[Any] = None) -> DXYService:
    """Get or create DXY service singleton (requires storage for Rule #15)"""
    global _dxy_instance
    
    if _dxy_instance is None:
        _dxy_instance = DXYService(storage, data_provider_manager)
    
    return _dxy_instance


def reset_dxy_service() -> None:
    """Reset singleton (testing only)"""
    global _dxy_instance
    _dxy_instance = None
