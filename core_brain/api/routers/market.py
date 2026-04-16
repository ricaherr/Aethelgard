"""
Router de Datos de Mercado y Regímenes - Endpoints críticos de análisis.
Micro-ETI 2.2: Oleada 2 de migración - Market Data & Regime Detection.
Trace_ID: ARCH-DISSECT-2026-003-B
"""
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends

from data_vault.storage import StorageManager
from data_vault.market_db import MarketMixin
from core_brain.api.dependencies.auth import get_current_active_user
from core_brain.services.heatmap_service import HeatmapDataService
from core_brain.infrastructure import get_process_gateway
from models.auth import TokenPayload
from models.signal import MarketRegime
from models.market import PredatorRadarResponse
from data_vault.tenant_factory import TenantDBFactory
from data_vault.default_instruments import DEFAULT_INSTRUMENTS_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market"])


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager to avoid import-time initialization."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_regime_classifier() -> Any:
    """Lazy-load RegimeClassifier."""
    from core_brain.server import _get_regime_classifier as get_regime_from_server
    return get_regime_from_server()


def _get_scanner() -> Optional[Any]:
    """Lazy-load ScannerEngine (if available in same process)."""
    try:
        from core_brain.main_orchestrator import scanner
        return scanner
    except ImportError:
        return None


async def _broadcast_thought(message: str, module: str = "MARKET", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


def _get_instrument_analysis_service(tenant_id: str) -> Any:
    """Lazy-load InstrumentAnalysisService."""
    from core_brain.analysis_service import InstrumentAnalysisService
    return InstrumentAnalysisService(storage=_get_storage(), tenant_id=tenant_id)


def _get_chart_service(tenant_id: str) -> Any:
    """Lazy-load ChartService."""
    from core_brain.chart_service import ChartService
    return ChartService(storage=_get_storage(), tenant_id=tenant_id)


def _get_heatmap_service(tenant_id: str) -> HeatmapDataService:
    """
    Lazy-load HeatmapDataService with injected dependencies.
    Follows Dependency Injection pattern from Aethelgard architecture.
    """
    storage = TenantDBFactory.get_storage(tenant_id)
    gateway = get_process_gateway(storage=storage, db_type="database")
    scanner = _get_scanner()
    return HeatmapDataService(
        process_gateway=gateway,
        storage=storage,
        scanner=scanner
    )


# ============ ENDPOINT: Análisis de Instrumento ============
@router.get("/instrument/{symbol}/analysis")
async def instrument_analysis(symbol: str, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna análisis completo de un instrumento (régimen, tendencia, trifecta, estrategias)"""
    try:
        service = _get_instrument_analysis_service(tenant_id=token.sub)
        result = service.get_analysis(symbol)
        return result
    except Exception as e:
        logger.error(f"Error en instrument_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT: Heatmap (CRÍTICO - Gracefully Degraded) ============
@router.get("/analysis/heatmap")
async def get_heatmap_data(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Retorna la matriz de calor (Heatmap) AGNÓSTICA de símbolos x timeframes.
    Recopila regímenes, métricas técnicas y señales activas.
    
    Implementa resilencia de 4 niveles sin lanzar nunca 503:
    1. Datos en tiempo real desde scanner local (si disponible)
    2. Fallback a base de datos cross-process
    3. Síntesis de datos vacíos (graceful degradation)
    4. Metadata de frescura para que el cliente sepa origen de datos
    
    **GARANTÍA**: Siempre retorna respuesta válida (NUNCA 503)
    """
    try:
        tenant_id = token.sub
        service = _get_heatmap_service(tenant_id)
        
        # HeatmapService maneja toda la resiliencia y fallbacks internamente
        heatmap_response = await service.get_heatmap()
        
        # Log de auditoría sin bloquear respuesta
        logger.info(
            f"Heatmap retrieved",
            extra={
                "tenant": tenant_id,
                "source": heatmap_response.get("metadata", {}).get("source", "unknown"),
                "freshness": heatmap_response.get("metadata", {}).get("freshness", "unknown"),
                "cell_count": len(heatmap_response.get("cells", []))
            }
        )
        
        return heatmap_response
        
    except Exception as e:
        # Este error NUNCA debería ocurrir si HeatmapService está correctamente implementado
        logger.error(f"Unexpected error in heatmap endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Heatmap service error (please investigate logs)"
        )



@router.get("/analysis/predator-radar", response_model=PredatorRadarResponse)
async def get_predator_radar(
    symbol: str = "EURUSD",
    timeframe: str = "M5",
    token: TokenPayload = Depends(get_current_active_user)
) -> PredatorRadarResponse:
    """
    Retorna snapshot de divergencia inter-mercado (Predator Radar) para HU 2.2.
    Detecta barridos de liquidez (SmT) y cuantifica fuerza de divergencia 0-100.
    """
    try:
        from core_brain.services.confluence_service import ConfluenceService
        from core_brain.data_provider_manager import DataProviderManager

        tenant_id = token.sub
        storage = TenantDBFactory.get_storage(tenant_id)
        confluence_service = ConfluenceService(storage=storage)

        scanner = _get_scanner()
        base_ohlcv = None
        if scanner is not None:
            key = f"{symbol}|{timeframe}"
            try:
                with scanner._lock:
                    base_ohlcv = scanner.last_dataframes.get(key)
            except Exception:
                base_ohlcv = None

        provider_manager = DataProviderManager(storage=storage)
        provider = provider_manager.get_active_data_provider()
        
        if provider is None:
            logger.warning(f"[PREDATOR_RADAR] No data provider available for {symbol}")
            # Proporcionar un resultado con datos insuficientes
            return PredatorRadarResponse(
                symbol=symbol,
                anchor=None,
                timeframe=timeframe,
                detected=False,
                state="UNMAPPED",
                divergence_strength=0.0,
                signal_bias="NEUTRAL",
                message="No data provider available. Cannot fetch market data.",
                timestamp=datetime.now().isoformat(),
                metrics={}
            )

        snapshot = confluence_service.get_predator_radar(
            symbol=symbol,
            timeframe=timeframe,
            connector=provider,
            base_ohlcv=base_ohlcv
        )
        return PredatorRadarResponse(**snapshot)
    except Exception as e:
        logger.error(f"Error en get_predator_radar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching predator radar: {str(e)}")


# ============ ENDPOINT: Historial de Régimen ============
@router.get("/regime/{symbol}/history")
async def regime_history(symbol: str, limit: int = 100, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna el historial de cambios de régimen para un símbolo"""
    try:
        tenant_id = token.sub
        storage = TenantDBFactory.get_storage(tenant_id)
        history = storage.get_sys_market_pulse_history(symbol, limit=limit)
        formatted = [
            {
                "regime": h["data"].get("regime"),
                "start": h["data"].get("timestamp"),
                "adx": h["data"].get("adx"),
                "volatility": h["data"].get("volatility"),
                "strength": h["data"].get("trend_strength"),
            }
            for h in history
        ]
        return {"symbol": symbol, "history": formatted}
    except Exception as e:
        logger.error(f"Error en regime_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT: Datos de Gráfica ============
@router.get("/chart/{symbol}/{timeframe}")
async def chart_data(symbol: str, timeframe: str = "M5", count: int = 500, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna datos de OHLC + indicadores para un símbolo y timeframe"""
    try:
        service = _get_chart_service(tenant_id=token.sub)
        return service.get_chart_data(symbol, timeframe, count)
    except Exception as e:
        logger.error(f"Error en chart_data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT: Régimen Actual ============
@router.get("/regime/{symbol}")
async def get_regime(symbol: str, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Obtiene el régimen de mercado actual para un símbolo"""
    try:
        classifier = _get_regime_classifier()
        regime = classifier.classify()
        return {
            "symbol": symbol,
            "regime": regime.value,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error en get_regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT: Configuraciones de Régimen ============
@router.get("/regime_configs")
async def get_sys_regime_configs(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna los pesos y configuraciones dinámicas de cada régimen (sys_regime_configs table).
    Usado por UI para visualizar WeightedMetricsVisualizer (Darwinismo Algorítmico).
    
    Estructura respuesta GARANTIZADA:
    {
        "regime_weights": {
            "TREND": {"profit_factor": 0.4, "win_rate": 0.3, ...},
            "RANGE": {...},
            "VOLATILE": {...}
        },
        "timestamp": "ISO8601",
        "description": "..."
    }
    
    CONTRATO: regime_weights NUNCA es null/undefined. Si no hay datos, retorna {} (dict vacío).
    """
    try:
        tenant_id = token.sub
        storage = TenantDBFactory.get_storage(tenant_id)
        # Obtener todos los sys_regime_configs agrupados por régimen (por tenant o global)
        all_configs = storage.get_all_sys_regime_configs(tenant_id=tenant_id)
        
        # Transformar formato: all_configs es Dict[regime -> Dict[metric_name -> weight]]
        regime_weights = {}
        if all_configs:  # Defensiva: verifica que all_configs no sea None
            for regime, metrics_dict in all_configs.items():
                if metrics_dict:  # Defensiva: verifica que metrics_dict no sea None
                    regime_weights[regime] = {}
                    for metric_name, weight in metrics_dict.items():
                        regime_weights[regime][metric_name] = float(weight)
        
        return {
            "regime_weights": regime_weights,  # GARANTÍA: nunca None, siempre dict
            "timestamp": datetime.now().isoformat(),
            "description": "Dynamic regime-specific metric weights for strategy ranking (Darwinismo Algorítmico)"
        }
    except Exception as e:
        logger.error(f"Error en get_sys_regime_configs: {e}")
        # Retorna estructura válida incluso en error (fail-safe)
        return {
            "regime_weights": {},
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "description": "Error fetching regime configs - returning empty weights"
        }


# ============ ENDPOINT: Instrumentos (Lectura) ============
def _build_markets_response(instruments_config: Dict[str, Any], all: bool) -> Dict[str, Any]:
    """Build markets dict from instruments_config; skip keys starting with _."""
    result = {}
    for market, categories in instruments_config.items():
        if market.startswith("_"):
            continue
        if not isinstance(categories, dict):
            continue
        result[market] = {}
        for cat, cat_data in categories.items():
            if not isinstance(cat_data, dict):
                continue
            if not all and not cat_data.get("enabled", False):
                continue
            instruments = cat_data.get("instruments", [])
            if not all:
                actives = cat_data.get("actives", {})
                instruments = [sym for sym in instruments if actives.get(sym, True)]
            if instruments or all:
                result[market][cat] = {
                    "description": cat_data.get("description", ""),
                    "instruments": instruments,
                    "priority": cat_data.get("priority", 0),
                    "min_score": cat_data.get("min_score", None),
                    "risk_multiplier": cat_data.get("risk_multiplier", None),
                    "enabled": cat_data.get("enabled", False),
                    "actives": cat_data.get("actives", {}),
                }
    return result


@router.get("/instruments")
async def get_instruments(all: bool = False, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna la lista de instrumentos agrupados por mercado/categoría desde la DB (SSOT).
    Si 'all' es True, incluye categorías e instrumentos inactivos (para Settings).
    Integridad: solo se persiste el default cuando la clave falta; nunca se sobrescriben datos existentes.
    """
    try:
        tenant_id = token.sub
        storage = TenantDBFactory.get_storage(tenant_id)
        state = storage.get_sys_config()
        instruments_config = state.get("instruments_config")
        # Solo sembrar cuando la clave NO existe (evitar borrar datos del usuario)
        if instruments_config is None:
            logger.warning(
                "[EDGE] instruments_config missing in DB for tenant %s; seeding once and persisting.",
                tenant_id,
            )
            storage.update_sys_config({"instruments_config": DEFAULT_INSTRUMENTS_CONFIG})
            instruments_config = DEFAULT_INSTRUMENTS_CONFIG
        elif isinstance(instruments_config, str):
            try:
                import json as _json
                instruments_config = _json.loads(instruments_config)
            except Exception as e:
                logger.error("Invalid instruments_config format in DB: %s. Returning default without overwriting.", e)
                return {"markets": _build_markets_response(DEFAULT_INSTRUMENTS_CONFIG, all)}
        if not isinstance(instruments_config, dict):
            logger.error("instruments_config is not a dict. Returning default without overwriting.")
            return {"markets": _build_markets_response(DEFAULT_INSTRUMENTS_CONFIG, all)}
        return {"markets": _build_markets_response(instruments_config, all)}
    except Exception as e:
        logger.error("Error loading instruments config: %s", e)
        return {"markets": _build_markets_response(DEFAULT_INSTRUMENTS_CONFIG, all)}


# ============ ENDPOINT: Instrumentos (Actualización) ============
@router.post("/instruments")
async def update_instruments(payload: dict, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Actualiza SOLO una categoría de instrumentos (más eficiente, DRY)
    
    CRITICAL: 
    1. Valida que instruments_config sea diccionario (no string JSON residual)
    2. Fusiona datos (no sobrescribe)
    3. Persiste en BD con json.dumps
    4. Retorna configuración actualizada para UI confirmation
    """
    try:
        tenant_id = token.sub
        storage = TenantDBFactory.get_storage(tenant_id)
        market = payload.get("market")
        category = payload.get("category")
        data = payload.get("data")
        if not (market and category and isinstance(data, dict)):
            raise HTTPException(status_code=400, detail="Faltan campos obligatorios: market, category, data")

        state = storage.get_sys_config()
        instruments_config = state.get("instruments_config")
        
        # === CRITICAL VALIDATION (same as GET endpoint) ===
        if instruments_config is None:
            logger.error(f"[ERROR] instruments_config is None for tenant {tenant_id}. Cannot update.")
            raise HTTPException(status_code=404, detail="instruments_config not found. Initialize first via GET /instruments.")
        
        # Handle residual JSON strings (deserialize)
        if isinstance(instruments_config, str):
            try:
                import json as _json
                instruments_config = _json.loads(instruments_config)
                logger.debug("Converted instruments_config from JSON string to dict")
            except Exception as e:
                logger.error(f"Invalid instruments_config JSON in DB: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid instruments_config format in DB: {str(e)}")
        
        # Validate structure
        if not isinstance(instruments_config, dict):
            logger.error(f"instruments_config is not a dict: {type(instruments_config)}")
            raise HTTPException(status_code=400, detail="Invalid instruments_config format (not a dict)")
        
        # Validate market exists
        if market not in instruments_config:
            logger.error(f"Market '{market}' not found in instruments_config")
            raise HTTPException(status_code=404, detail=f"Market '{market}' not found")
        
        # Validate category exists
        if category not in instruments_config[market]:
            logger.error(f"Category '{category}' not found in market '{market}'")
            raise HTTPException(status_code=404, detail=f"Category '{category}' not found in market '{market}'")
        
        # === MERGE UPDATE (preserve existing keys, update from data) ===
        # Get current category config
        current_category_config = instruments_config[market][category]
        
        # Merge: update existing dict with new data
        current_category_config.update(data)
        instruments_config[market][category] = current_category_config
        
        # === PERSIST TO DB (SSOT: data_vault/global/aethelgard.db) ===
        storage.update_sys_config({"instruments_config": instruments_config})
        logger.info(f"✅ Category {market}/{category} persisted. enabled={data.get('enabled')}, actives={data.get('actives', {})}")
        
        # === BROADCAST UI UPDATE ===
        await _broadcast_thought(
            f"Categoría {market}/{category} actualizada: enabled={data.get('enabled')}, " +
            f"{len(data.get('instruments', []))} instrumentos",
            module="MARKET"
        )
        
        # === RETURN UPDATED CONFIG (for UI confirmation) ===
        return {
            "status": "success",
            "message": f"Categoría {market}/{category} actualizada correctamente.",
            "updated_config": instruments_config[market][category]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error guardando categoría de instrumentos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
