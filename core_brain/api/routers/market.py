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
from models.auth import TokenPayload
from models.signal import MarketRegime

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


# ============ ENDPOINT: Análisis de Instrumento ============
@router.get("/instrument/{symbol}/analysis")
async def instrument_analysis(symbol: str, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna análisis completo de un instrumento (régimen, tendencia, trifecta, estrategias)"""
    try:
        service = _get_instrument_analysis_service(tenant_id=token.tid)
        result = service.get_analysis(symbol)
        return result
    except Exception as e:
        logger.error(f"Error en instrument_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT: Heatmap (CRÍTICO - El más pesado) ============
@router.get("/analysis/heatmap")
async def get_heatmap_data(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Retorna la matriz de calor (Heatmap) AGNÓSTICA de símbolos x timeframes.
    Recopila regímenes, métricas técnicas y señales activas.
    Implementa principios de RESILIENCIA y AUTOGESTIÓN con CROSS-PROCESS fallback.
    
    **Rendimiento OPTIMIZADO**: Ejecuta con lock-free reads cuando es posible.
    Si falla, fallback automático a BD (resilencia multi-proceso).
    """
    # RECOPILACIÓN DE DATOS RESILIENTE
    cells = []
    assets = []
    timeframes = []
    now_mono = time.monotonic()
    now_ts = time.time()
    tenant_id = token.tid

    scanner = _get_scanner()

    # Intento 1: Obtener datos del scanner local (si está en el mismo proceso)
    if scanner is not None:
        try:
            with scanner._lock:
                assets = list(scanner.assets)
                timeframes = list(scanner.active_timeframes)
                regimes = dict(scanner.last_regime)
                last_scans = dict(scanner.last_scan_time)
                
                for symbol in assets:
                    for tf in timeframes:
                        key = f"{symbol}|{tf}"
                        cl = scanner.classifiers.get(key)
                        
                        last_scan_val = last_scans.get(key, 0)
                        cell = {
                            "symbol": symbol,
                            "timeframe": tf,
                            "regime": regimes.get(key, MarketRegime.NORMAL).value,
                            "last_scan": last_scan_val,
                            "is_stale": (now_mono - last_scan_val) > 300 if last_scan_val > 0 else True,
                            "metrics": {},
                            "signal": None,
                            "source": "memory"
                        }
                        if cl:
                            try: cell["metrics"] = cl.get_metrics()
                            except Exception: pass
                        cells.append(cell)
        except Exception as e:
            logger.warning(f"Error leyendo scanner local: {e}")

    # Intento 2: Fallback a Base de Datos (Cross-Process Resilience)
    if not cells:
        try:
            db_states = _get_storage().get_latest_heatmap_state(tenant_id=tenant_id)
            if db_states:
                # Deducir assets y timeframes de los datos
                assets = sorted(list(set(s["symbol"] for s in db_states)))
                timeframes = sorted(list(set(s["timeframe"] for s in db_states)))
                
                for s in db_states:
                    ts_str = s.get("timestamp")
                    last_scan_ts = datetime.fromisoformat(ts_str).timestamp() if ts_str else 0
                    cells.append({
                        "symbol": s["symbol"],
                        "timeframe": s["timeframe"],
                        "regime": s["regime"],
                        "last_scan": last_scan_ts,
                        "is_stale": (now_ts - last_scan_ts) > 600 if last_scan_ts > 0 else True,
                        "metrics": s.get("metrics", {}),
                        "signal": None,
                        "source": "database"
                    })
        except Exception as e:
            logger.error(f"Error en fallback de base de datos para heatmap: {e}")

    if not cells:
        # DIAGNÓSTICO INTELIGENTE (Auto-gestión)
        diag = "Scanner offline."
        if scanner is not None:
            diag = "Scanner local activo pero sin datos (Verificar conexión a MT5/DataProv)."
        elif _get_storage():
            try:
                # Verificar si la tabla existe y tiene algo
                count = _get_storage().execute_query("SELECT COUNT(*) as c FROM market_state")[0]['c']
                if count == 0:
                    diag = "Scanner en otro proceso pero base de datos vacía (Iniciando primera recolección)."
                else:
                    diag = "Scanner en otro proceso pero datos en DB son demasiado antiguos (>24h)."
            except Exception as e:
                diag = f"Error de acceso a datos: {str(e)}"
        
        logger.warning(f"Heatmap 503 Diagnostic: {diag}")
        raise HTTPException(status_code=503, detail=f"Análisis no disponible: {diag}")

    # 2. Integrar Señales Recientes (CONFLUENCIA)
    # Buscamos señales PENDING de la última hora
    try:
        recent_signals = _get_storage().get_recent_signals(minutes=60, status='PENDING', tenant_id=tenant_id)
        # Indexar señales por clave para búsqueda rápida
        signals_lookup = {f"{s['symbol']}|{s['timeframe']}": s for s in recent_signals}
        
        for cell in cells:
            key = f"{cell['symbol']}|{cell['timeframe']}"
            sig = signals_lookup.get(key)
            if sig:
                cell["signal"] = {
                    "id": sig["id"],
                    "type": sig["signal_type"],
                    "score": sig["score"]
                }
    except Exception as e:
        logger.warning(f"Error agregando señales al heatmap: {e}")

    # 3. Cálculo de Confluencia Fractal (INTELIGENCIA)
    # Si un símbolo tiene el mismo sesgo (bias) en 2+ timeframes, marcar confluencia
    for symbol in assets:
        symbol_cells = [c for c in cells if c["symbol"] == symbol]
        biases = [c["metrics"].get("bias") for c in symbol_cells if c["metrics"].get("bias")]
        
        if len(biases) >= 2: # Al menos 2 para considerar confluencia mínima
            # Contar sesgo dominante
            bullish_count = biases.count("BULLISH")
            bearish_count = biases.count("BEARISH")
            
            confluence = None
            if bullish_count >= 2: confluence = "BULLISH"
            if bearish_count >= 2: confluence = "BEARISH"
            
            if confluence:
                for cell in symbol_cells:
                    cell["confluence"] = confluence
                    cell["confluence_strength"] = max(bullish_count, bearish_count)

    return {
        "symbols": assets,
        "timeframes": timeframes,
        "cells": cells,
        "timestamp": datetime.now().isoformat()
    }


# ============ ENDPOINT: Historial de Régimen ============
@router.get("/regime/{symbol}/history")
async def regime_history(symbol: str, limit: int = 100, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna el historial de cambios de régimen para un símbolo"""
    try:
        market_db = MarketMixin()
        history = market_db.get_market_state_history(symbol, limit=limit, tenant_id=token.tid)
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
        service = _get_chart_service(tenant_id=token.tid)
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
async def get_regime_configs(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna los pesos y configuraciones dinámicas de cada régimen (regime_configs table).
    Usado por UI para visualizar WeightedMetricsVisualizer (Darwinismo Algorítmico).
    
    Estructura respuesta:
    {
        "TREND": {"profit_factor": 0.4, "win_rate": 0.3, "drawdown_max": 0.2, "consecutive_losses": 0.1},
        "RANGE": {"profit_factor": 0.25, "win_rate": 0.4, "drawdown_max": 0.2, "consecutive_losses": 0.15},
        "VOLATILE": {"profit_factor": 0.2, "win_rate": 0.2, "drawdown_max": 0.4, "consecutive_losses": 0.2}
    }
    """
    try:
        storage = _get_storage()
        # Obtener todos los regime_configs agrupados por régimen
        all_configs = storage.get_all_regime_configs(tenant_id=token.tid)
        
        # Transformar formato: all_configs es Dict[regime -> Dict[metric_name -> weight]]
        regime_weights = {}
        for regime, metrics_dict in all_configs.items():
            regime_weights[regime] = {}
            for metric_name, weight in metrics_dict.items():
                regime_weights[regime][metric_name] = float(weight)
        
        return {
            "regime_weights": regime_weights,
            "timestamp": datetime.now().isoformat(),
            "description": "Dynamic regime-specific metric weights for strategy ranking (Darwinismo Algorítmico)"
        }
    except Exception as e:
        logger.error(f"Error en get_regime_configs: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching regime configs: {str(e)}")


# ============ ENDPOINT: Instrumentos (Lectura) ============
@router.get("/instruments")
async def get_instruments(all: bool = False, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Retorna la lista de instrumentos agrupados por mercado/categoría desde la DB (SSOT).
    Si 'all' es True, incluye categorías e instrumentos inactivos (para Settings).
    """
    try:
        storage = _get_storage()
        state = storage.get_system_state(tenant_id=token.tid)
        instruments_config = state.get("instruments_config")
        if instruments_config is None:
            raise ValueError("instruments_config no encontrado en DB. Inicialice la configuración desde la UI/API.")
        result = {}
        for market, categories in instruments_config.items():
            if market.startswith("_"):
                continue
            result[market] = {}
            for cat, cat_data in categories.items():
                # Si all=False, solo mostrar categorías activas
                if not all and not cat_data.get("enabled", False):
                    continue
                instruments = cat_data.get("instruments", [])
                # Si all=False, solo mostrar instrumentos activos
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
                        "actives": cat_data.get("actives", {})
                    }
        return {"markets": result}
    except Exception as e:
        logger.error(f"Error loading instruments config from DB: {e}")
        # Fallback: lista mínima hardcodeada
        return {
            "markets": {
                "FOREX": {
                    "majors": {
                        "description": "Fallback: Pares principales",
                        "instruments": ["EURUSD", "GBPUSD", "USDJPY"],
                        "priority": 1,
                        "min_score": 70,
                        "risk_multiplier": 1.0
                    }
                }
            },
            "error": f"No se pudo cargar instruments_config de la DB: {str(e)}"
        }


# ============ ENDPOINT: Instrumentos (Actualización) ============
@router.post("/instruments")
async def update_instruments(payload: dict, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Actualiza SOLO una categoría de instrumentos (más eficiente, DRY)"""
    try:
        storage = _get_storage()
        tenant_id = token.tid
        market = payload.get("market")
        category = payload.get("category")
        data = payload.get("data")
        if not (market and category and isinstance(data, dict)):
            raise HTTPException(status_code=400, detail="Faltan campos obligatorios: market, category, data")
        
        # Obtener estado actual
        state = storage.get_system_state(tenant_id=tenant_id)
        instruments_config = state.get("instruments_config")
        if not instruments_config or market not in instruments_config or category not in instruments_config[market]:
            raise HTTPException(status_code=404, detail="Categoría no encontrada en la configuración actual")
        
        # Actualizar categoría
        instruments_config[market][category].update(data)
        storage.update_system_state({"instruments_config": instruments_config}, tenant_id=tenant_id)
        
        await _broadcast_thought(f"Categoría {market}/{category} actualizada por el usuario.", module="MARKET")
        return {"status": "success", "message": f"Categoría {market}/{category} actualizada correctamente."}
    except Exception as e:
        logger.error(f"Error guardando categoría de instrumentos: {e}")
        raise HTTPException(status_code=500, detail=str(e))
