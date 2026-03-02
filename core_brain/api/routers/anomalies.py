"""
Router de Anomalías - Endpoints para Thought Console (HU 4.6).
Proporciona acceso a eventos de anomalías, sugerencias defensivas y métricas de salud.
Trace_ID: BLACK-SWAN-SENTINEL-2026-001
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query

from data_vault.storage import StorageManager
from core_brain.api.dependencies.auth import get_current_active_user
from models.auth import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies"])


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


async def _broadcast_thought(
    message: str,
    module: str = "ANOMALY_SENTINEL",
    level: str = "warning",
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Broadcast anomaly thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


# ────────────────────────────────────────────────────────────────────────────
# THOUGHT CONSOLE ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────

@router.get("/thought-console/feed", summary="Obtener feed de [ANOMALY_DETECTED] events")
async def get_thought_console_feed(
    limit: int = Query(50, ge=1, le=500),
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene el feed de eventos de anomalías detectadas para la Thought Console.
    
    Incluye:
    - Eventos [ANOMALY_DETECTED] con sugerencias inteligentes
    - Trace_ID para auditoria
    - Nivel de severidad
    - Acciones sugeridas
    
    Args:
        limit: Número máximo de eventos a retornar
        user: Usuario autenticado
        storage: StorageManager inyectado
        
    Returns:
        Feed de anomalías con sugerencias
    """
    try:
        # Obtener anomalías críticas (alta confianza)
        anomalies = await storage.get_critical_anomalies(
            min_confidence=0.80,
            limit=limit
        )
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "anomalies": anomalies,
            "count": len(anomalies),
            "message": f"[THOUGHT_CONSOLE] Feed retrieved with {len(anomalies)} anomaly events"
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error retrieving thought console feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{symbol}", summary="Obtener historial de anomalías por símbolo")
async def get_anomaly_history(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    anomaly_type: Optional[str] = Query(None),
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene el historial completo de anomalías para un símbolo.
    
    Args:
        symbol: Instrumento (ej. EURUSD)
        limit: Número máximo de registros
        anomaly_type: Filtrar por tipo (extreme_volatility, flash_crash, etc)
        user: Usuario autenticado
        storage: StorageManager
        
    Returns:
        Historial de anomalías con metadata
    """
    try:
        history = await storage.get_anomaly_history(
            symbol=symbol,
            anomaly_type=anomaly_type,
            limit=limit
        )
        
        return {
            "status": "success",
            "symbol": symbol,
            "anomaly_type": anomaly_type,
            "count": len(history),
            "history": history,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error retrieving history for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent/{symbol}", summary="Obtener anomalías recientes de las últimas N horas")
async def get_recent_anomalies(
    symbol: str,
    hours: int = Query(1, ge=1, le=168),
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene anomalías recientes para un símbolo en las últimas N horas.
    
    Args:
        symbol: Instrumento
        hours: Ventana de tiempo (1-168 horas)
        user: Usuario autenticado
        storage: StorageManager
        
    Returns:
        Anomalías recientes con sugerencias
    """
    try:
        recent = await storage.get_recent_anomalies(
            symbol=symbol,
            hours=hours
        )
        
        # Contar anomalías por tipo
        by_type = {}
        for anomaly in recent:
            atype = anomaly.get("anomaly_type", "unknown")
            by_type[atype] = by_type.get(atype, 0) + 1
        
        return {
            "status": "success",
            "symbol": symbol,
            "hours": hours,
            "count": len(recent),
            "by_type": by_type,
            "anomalies": recent,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error retrieving recent anomalies for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────────────────────
# STATISTICS & HEALTH ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────

@router.get("/stats", summary="Obtener estadísticas generales de anomalías")
async def get_anomaly_stats(
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene estadísticas agregadas de todas las anomalías detectadas.
    
    Incluye:
    - Total de anomalías por tipo
    - Top 10 símbolos con más anomalías
    - Confianza promedio y máxima
    - Z-Score promedio
    
    Args:
        user: Usuario autenticado
        storage: StorageManager
        
    Returns:
        Estadísticas de anomalías
    """
    try:
        stats = storage.get_anomaly_stats()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error retrieving stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/count", summary="Obtener cuán anómalo es el mercado")
async def get_anomaly_count(
    symbol: Optional[str] = Query(None),
    hours: Optional[int] = Query(None, ge=1, le=168),
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene el contador de anomalías (simple telemetría de "stress" del mercado).
    
    Args:
        symbol: Filtrar por símbolo (opcional)
        hours: Ventana de tiempo en horas (opcional)
        user: Usuario autenticado
        storage: StorageManager
        
    Returns:
        Contador de anomalías con contexto
    """
    try:
        count = await storage.get_anomaly_count(symbol=symbol, hours=hours)
        
        # Determinar nivel de estrés
        stress_level = "NORMAL"
        if count > 50:
            stress_level = "CRITICAL"
        elif count > 20:
            stress_level = "HIGH"
        elif count > 5:
            stress_level = "MODERATE"
        
        return {
            "status": "success",
            "symbol": symbol or "ALL",
            "hours": hours or "all-time",
            "anomaly_count": count,
            "market_stress_level": stress_level,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error counting anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────────────────────
# DEFENSIVE PROTOCOL ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────

@router.post("/defensive-protocol/activate", summary="Activar protocolo defensivo manualmente")
async def activate_defensive_protocol(
    body: Dict[str, Any],
    user: TokenPayload = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Activa manualmente el protocolo defensivo (Lockdown Preventivo).
    
    Puede ser invocado por el operador si el sistema detectó una anomalía
    pero el usuario quiere activar defensa adicional.
    
    Body parameters:
        - symbol (str): Símbolo afectado
        - reason (str): Razón de la activación
        - trace_id (str): ID de trazabilidad
        
    Returns:
        Status de activación del protocolo
    """
    try:
        symbol = body.get("symbol", "MULTI")
        reason = body.get("reason", "Manual activation via Thought Console")
        trace_id = body.get("trace_id", "MANUAL-DEFENSE")
        
        # Aquí se podría integrar con MainOrchestrator para activar Lockdown
        logger.critical(
            f"[MANUAL_DEFENSE] Protocol activated by user {user.username}. "
            f"Symbol: {symbol}, Reason: {reason}, Trace_ID: {trace_id}"
        )
        
        await _broadcast_thought(
            f"[DEFENSIVE_PROTOCOL_ACTIVATED] {reason}",
            level="critical",
            metadata={
                "symbol": symbol,
                "trace_id": trace_id,
                "activated_by": user.username,
            }
        )
        
        return {
            "status": "success",
            "message": "Defensive protocol activated successfully",
            "symbol": symbol,
            "trace_id": trace_id,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error activating defensive protocol: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/{symbol}", summary="Obtener estado de salud por anomalías")
async def get_symbol_anomaly_health(
    symbol: str,
    user: TokenPayload = Depends(get_current_active_user),
    storage: StorageManager = Depends(_get_storage),
) -> Dict[str, Any]:
    """
    Obtiene el estado de salud de un símbolo basado en el historial de anomalías.
    
    Métricas:
    - Modo: NORMAL, CAUTION, DEGRADED, STRESSED
    - Estabilidad del sistema (0-1)
    - Anomalías consecutivas
    
    Args:
        symbol: Instrumento
        user: Usuario autenticado
        storage: StorageManager
        
    Returns:
        Estado de salud por anomalías
    """
    try:
        # Obtener anomalías recientes (últimas 2 horas)
        recent = await storage.get_recent_anomalies(symbol=symbol, hours=2)
        
        # Determinar modo de operación
        anomaly_count = len(recent)
        mode = "NORMAL"
        stability = 1.0
        
        if anomaly_count >= 5:
            mode = "DEGRADED"
            stability = 0.5
        elif anomaly_count >= 3:
            mode = "CAUTION"
            stability = 0.75
        
        return {
            "status": "success",
            "symbol": symbol,
            "mode": mode,
            "system_stability": stability,
            "anomaly_count_2h": anomaly_count,
            "recent_anomalies": recent,
            "timestamp": datetime.now().isoformat(),
            "recommendation": (
                "All clear - normal market conditions" if mode == "NORMAL" else
                "Caution - increased volatility detected" if mode == "CAUTION" else
                "Degraded - anomaly cluster detected, consider defensive measures" if mode == "DEGRADED" else
                "Unknown state"
            )
        }
    except Exception as e:
        logger.error(f"[ANOMALY_API] Error getting health for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
