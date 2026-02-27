"""
Router de Riesgo - Endpoints de gestión de riesgo y monitoreo.
Micro-ETI 2.1: Oleada 2 de migración de operaciones.
Micro-ETI 3.1: Refactored to delegate business logic to TradingService.
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends

from data_vault.storage import StorageManager
from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
from core_brain.api.dependencies.auth import get_current_active_user
from models.auth import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Risk"])


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager to avoid import-time initialization."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_trading_service() -> 'TradingService':
    """Lazy-load TradingService singleton."""
    from core_brain.server import _get_trading_service as get_ts_from_server
    return get_ts_from_server()


async def _broadcast_thought(message: str, module: str = "RISK", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


@router.get("/risk/status")
async def get_risk_status(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Obtiene el estado de riesgo en tiempo real y el modo de operación.
    Se apoya puramente en la base de datos para máxima resiliencia.
    """
    try:
        storage = _get_storage()
        tenant_id = token.tid
        
        # 1. Obtener stats de EdgeTuner desde la DB (SSOT)
        risk_mode = "NORMAL"
        last_adjustment = None
        
        # Intentar obtener el último ajuste de la DB (SSOT)
        adjustments = storage.get_tuning_history(limit=1, tenant_id=tenant_id)
        if adjustments:
            last_adjustment = adjustments[0]
            factor = last_adjustment.get("adjustment_factor", 1.0)
            if factor >= 1.5:
                risk_mode = "DEFENSIVE"
            elif factor <= 0.7:
                risk_mode = "AGGRESSIVE"
        
        # 2. Resumen de riesgos (Single Source of Truth)
        dynamic_params = {}
        state = storage.get_system_state(tenant_id=tenant_id)
        dynamic_params = state.get("config_trading", {})
        
        if not dynamic_params:
            # Fallback deshabilitado: StorageManager es la única fuente de verdad
            logger.warning("[SSOT] dynamic_params no encontrado en DB. Inicialice la configuración desde la UI/API.")

        # 3. Sanity Check Status (Rechazos recientes)
        rejections_today = 0
        last_rejection_reason = None
        
        try:
            pipeline_events = storage.get_signal_pipeline_history(limit=50, tenant_id=tenant_id)
            today = datetime.now().date()
            for event in pipeline_events:
                event_time = event.get('timestamp')
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time.replace(' ', 'T')).date()
                
                if event_time == today and event.get('decision') == 'REJECTED':
                    rejections_today += 1
                    if not last_rejection_reason:
                        last_rejection_reason = event.get('reason')
        except Exception as e:
            logger.warning(f"Error calculating sanity stats: {e}")

        return {
            "risk_mode": risk_mode,
            "current_risk_pct": dynamic_params.get("risk_per_trade", 0.01) * 100,
            "last_adjustment": last_adjustment,
            "sanity": {
                "rejections_today": rejections_today,
                "last_rejection_reason": last_rejection_reason,
                "status": "HEALTHY" if rejections_today < 5 else "CAUTIOUS"
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in /api/risk/status: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/risk/summary")
async def get_risk_summary(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Get account risk summary with distribution by asset type.
    Uses real MT5 balance if connected, otherwise cached or default value.
    Includes metadata about balance source (MT5_LIVE, CACHED, DEFAULT).
    Delegates to TradingService (Micro-ETI 3.1).
    """
    try:
        trading_service = _get_trading_service()
        tenant_id = token.tid
        
        # Get open positions via TradingService
        positions_response = await trading_service.get_open_positions(tenant_id=tenant_id)
        positions = positions_response.get("positions", [])
        total_risk = positions_response.get("total_risk_usd", 0.0)
        
        # Get REAL account balance from TradingService
        account_balance = trading_service.get_account_balance(tenant_id=tenant_id)
        balance_metadata = trading_service.get_balance_metadata(tenant_id=tenant_id)
        
        # Calculate risk percentage
        risk_percentage = (total_risk / account_balance * 100) if account_balance > 0 else 0.0
        max_allowed_risk = trading_service.get_max_account_risk_pct(tenant_id=tenant_id)
        
        # Distribution by asset type
        by_asset = {}
        for pos in positions:
            asset = pos["asset_type"]
            if asset not in by_asset:
                by_asset[asset] = {"count": 0, "risk": 0.0}
            by_asset[asset]["count"] += 1
            by_asset[asset]["risk"] += pos["initial_risk_usd"]
        
        # Round risk values
        for asset in by_asset:
            by_asset[asset]["risk"] = round(by_asset[asset]["risk"], 2)
        
        # Generate warnings
        warnings = []
        if risk_percentage > max_allowed_risk * 0.9:
            warnings.append(f"Total risk ({risk_percentage:.1f}%) approaching limit ({max_allowed_risk}%)")
        if risk_percentage > max_allowed_risk:
            warnings.append(f"⚠ CRITICAL: Risk ({risk_percentage:.1f}%) exceeds maximum ({max_allowed_risk}%)")
        
        return {
            "total_risk_usd": round(total_risk, 2),
            "account_balance": account_balance,
            "balance_metadata": balance_metadata,
            "risk_percentage": round(risk_percentage, 2),
            "max_allowed_risk_pct": max_allowed_risk,
            "positions_by_asset": by_asset,
            "warnings": warnings
        }
        
    except Exception as e:
        logger.error(f"Error getting risk summary: {e}")
        return {
            "total_risk_usd": 0.0,
            "account_balance": 0.0,
            "balance_metadata": {"source": "ERROR", "last_update": datetime.now().isoformat(), "is_live": False},
            "risk_percentage": 0.0,
            "max_allowed_risk_pct": 5.0,
            "positions_by_asset": {},
            "warnings": [f"Error: {str(e)}"]
        }


@router.get("/satellite/status")
async def get_satellite_status(token: TokenPayload = Depends(get_current_active_user)) -> Any:
    """
    Returns the status of all registered connectors from ConnectivityOrchestrator.
    """
    orchestrator = ConnectivityOrchestrator()
    return orchestrator.get_status_report()


@router.post("/satellite/toggle")
async def toggle_satellite(data: Dict[str, Any], token: TokenPayload = Depends(get_current_active_user)) -> Any:
    """
    Manually enable or disable a satellite connector.
    """
    provider_id = data.get("provider_id")
    enabled = data.get("enabled", True)
    
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id is required")
    
    orchestrator = ConnectivityOrchestrator()
    if enabled:
        orchestrator.enable_connector(provider_id)
        await _broadcast_thought(f"[USER ACTION] Conector {provider_id} habilitado manualmente.", module="CONNECTIVITY")
    else:
        orchestrator.disable_connector(provider_id)
        await _broadcast_thought(f"[USER ACTION] Conector {provider_id} deshabilitado manualmente. Conmutando a proveedor de respaldo si es necesario...", module="CONNECTIVITY")
        
    return {"success": True, "provider_id": provider_id, "enabled": enabled}


@router.get("/edge/tuning-logs")
async def get_tuning_logs(limit: int = 50, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Retorna el historial de ajustes del EdgeTuner (Neuro-evolución).
    """
    try:
        storage = _get_storage()
        history = storage.get_tuning_history(limit=limit, tenant_id=token.tid)
        return {"status": "success", "history": history}
    except Exception as e:
        logger.error(f"Error recuperando historial de tuning: {e}")
        raise HTTPException(status_code=500, detail=str(e))
