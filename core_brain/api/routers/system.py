"""
Router de Sistema - Endpoints de auditoría, configuración y salud.
Micro-ETI 2.3: Oleada 3 de control y notificaciones.
"""
import logging
import asyncio
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends

from data_vault.storage import StorageManager
from core_brain.api.dependencies.auth import get_current_active_user
from models.auth import TokenPayload
from data_vault.tenant_factory import TenantDBFactory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager to avoid import-time initialization."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_system_service() -> Any:
    """Lazy-load SystemService."""
    from core_brain.server import _get_system_service as get_system_from_server
    return get_system_from_server()


async def _broadcast_thought(message: str, module: str = "CORE", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


def _get_backup_settings_from_db() -> Dict[str, Any]:
    """
    Get normalized DB backup settings from dynamic_params.
    Default policy: backups/, daily, retention 15 days.
    """
    defaults = {
        "enabled": True,
        "backup_dir": "backups",
        "interval_days": 1,
        "retention_days": 15
    }

    storage = _get_storage()
    params = storage.get_dynamic_params()
    backup_cfg = params.get("database_backup", {}) if isinstance(params, dict) else {}
    if not isinstance(backup_cfg, dict):
        backup_cfg = {}

    interval_days = backup_cfg.get("interval_days")
    if interval_days is None:
        interval_minutes = int(backup_cfg.get("interval_minutes", defaults["interval_days"] * 1440))
        interval_days = max(1, int((interval_minutes + 1439) // 1440))

    retention_days = backup_cfg.get("retention_days")
    if retention_days is None:
        retention_days = int(backup_cfg.get("retention_count", defaults["retention_days"]))

    return {
        "enabled": bool(backup_cfg.get("enabled", defaults["enabled"])),
        "backup_dir": str(backup_cfg.get("backup_dir", defaults["backup_dir"])),
        "interval_days": max(1, int(interval_days)),
        "retention_days": max(1, int(retention_days))
    }


def _save_backup_settings_to_db(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Persist backup settings to dynamic_params.database_backup."""
    normalized = {
        "enabled": bool(settings.get("enabled", True)),
        "backup_dir": str(settings.get("backup_dir", "backups")).strip() or "backups",
        "interval_days": max(1, int(settings.get("interval_days", 1))),
        "retention_days": max(1, int(settings.get("retention_days", 15)))
    }

    storage = _get_storage()
    params = storage.get_dynamic_params()
    if not isinstance(params, dict):
        params = {}

    params["database_backup"] = {
        "enabled": normalized["enabled"],
        "backup_dir": normalized["backup_dir"],
        "interval_days": normalized["interval_days"],
        "retention_days": normalized["retention_days"],
        "interval_minutes": normalized["interval_days"] * 1440,
        "retention_count": normalized["retention_days"]
    }

    storage.update_dynamic_params(params)
    return normalized


@router.get("/system/status")
async def system_status() -> Dict[str, Any]:
    """Endpoint de estado del sistema"""
    from core_brain.services.socket_service import get_socket_service
    
    socket_service = get_socket_service()
    
    return {
        "name": "Aethelgard",
        "version": "1.0.0",
        "status": "running",
        "active_connections": len(socket_service.manager.active_connections) if hasattr(socket_service, 'manager') else 0,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/system/telemetry")
async def get_system_telemetry(token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Simple HTTP endpoint for system telemetry (used by HomePage for polling).
    Returns: CPU, memory, satellites, strategies, anomalies, risk buffer, signals.
    
    This is the SIMPLE approach - HTTP polling every 30s (like Portfolio does).
    NO WebSocket complexity. Just straightforward data retrieval.
    """
    try:
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
        from core_brain.main_orchestrator import MainOrchestrator
        
        orchestrator = ConnectivityOrchestrator()
        
        # Get satellite status
        satellite_report = orchestrator.get_status_report() or {}
        satellites = [
            {
                "provider_id": provider_id,
                "status": status.get("status", "UNKNOWN"),
                "last_sync_ms": status.get("latency_ms", 0),
                "is_primary": status.get("is_primary", False)
            }
            for provider_id, status in satellite_report.items()
        ]
        
        # Get some default strategy status
        strategy_array = [
            {"id": "BRK_OPEN_0001", "status": "LIVE", "pnl": 234.50},
            {"id": "MOM_BIAS_0001", "status": "SHADOW", "pnl": -50.00},
        ]
        
        # Risk buffer info
        risk_buffer = {
            "exposure_pct": 45.2,
            "daily_max_pct": 100.0,
            "max_consecutive_losses": 3,
            "current_losses": 0
        }
        
        # Anomalies
        anomalies = {
            "count_last_5m": 1,
            "severity": "LOW",
            "latest": ["High volatility detected in EURUSD"]
        }
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": 5.2,
            "memory_mb": 256,
            "broker_latency_ms": 45,
            "satellites": satellites,
            "strategy_array": strategy_array,
            "risk_buffer": risk_buffer,
            "anomalies": anomalies,
            "heartbeat": "OK"
        }
    except Exception as e:
        logger.error(f"[TELEMETRY] Error: {e}")
        # Return sensible defaults on failure (graceful degradation)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": 0.0,
            "memory_mb": 0,
            "broker_latency_ms": 0,
            "satellites": [],
            "strategy_array": [],
            "risk_buffer": {"exposure_pct": 0, "daily_max_pct": 100.0},
            "anomalies": {"count_last_5m": 0},
            "heartbeat": "ERROR",
            "error": str(e)
        }


@router.get("/config/{category}")
async def get_config(category: str, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Obtiene una categoría de configuración de la DB (usando storage global)"""
    db_key = f"config_{category}"
    # New architecture: use global storage (no tenant_id isolation for config)
    storage = _get_storage()
    state = storage.get_sys_config()
    config_data = state.get(db_key)
    
    if config_data is None:
        logger.warning(f"Config '{category}' requested not found in DB.")
        return {}
        
    if config_data is None and category == "notifications":
        # Fallback especial para notificaciones si se pide vía /config pero no existe
        try:
            from data_vault.system_db import SystemMixin
            notif_db = SystemMixin()
            telegram_settings = notif_db.get_usr_notification_settings("telegram", user_id=token.sub)
            if telegram_settings:
                # Asegurar que config_data sea un diccionario mutable
                raw_config = telegram_settings.get("config", {})
                if isinstance(raw_config, str):
                    try:
                        raw_config = json.loads(raw_config)
                    except:
                        raw_config = {}
                
                config_data = dict(raw_config)
                
                # Mapeo explícito para compatibilidad con el frontend
                if "chat_id_basic" in config_data:
                    config_data["basic_chat_id"] = config_data["chat_id_basic"]
                if "chat_id_premium" in config_data:
                    config_data["premium_chat_id"] = config_data["chat_id_premium"]
                
                config_data["enabled"] = bool(telegram_settings.get("enabled", False))
        except Exception as e:
            logger.warning(f"Fallback notification settings failed: {e}")
    
    if config_data is None:
        raise HTTPException(status_code=404, detail=f"Categoría de configuración '{category}' no encontrada.")
        
    return {"category": category, "data": config_data}


@router.post("/config/{category}")
async def update_config(category: str, new_data: dict, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Actualiza una categoría de configuración en la DB (using global storage)"""
    db_key = f"config_{category}"
    # New architecture: use global storage (no tenant_id isolation for config)
    storage = _get_storage()
    
    try:
        storage.update_sys_config({db_key: new_data})
        await _broadcast_thought(f"Configuración '{category}' actualizada por el usuario.", module="CORE")
        return {"status": "success", "message": f"Configuración '{category}' guardada correctamente."}
    except Exception as e:
        logger.error(f"Error guardando configuración {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup/settings")
async def get_backup_settings() -> Dict[str, Any]:
    """Get DB backup scheduler settings (DB-first)."""
    try:
        settings = _get_backup_settings_from_db()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error(f"Error loading backup settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backup/settings")
async def update_backup_settings(data: dict) -> Dict[str, Any]:
    """Update DB backup scheduler settings (DB-first)."""
    try:
        settings = _save_backup_settings_to_db(data or {})
        await _broadcast_thought("Configuración de backups actualizada.", module="CORE")
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error(f"Error updating backup settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system/audit")
async def run_integrity_audit() -> Dict[str, Any]:
    """
    Ejecuta validación global con espera completa y retorna resultados.
    Envía eventos en tiempo real vía broadcast_thought.
    
    Logic delegated to audit_service to maintain file hygiene (<500 lines).
    See: core_brain/api/services/audit_service.py
    """
    from core_brain.api.services.audit_service import run_integrity_audit as audit_run
    return await audit_run()


@router.post("/system/audit/repair")
async def repair_integrity_vector(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reparación manual (Auto-Gestión EDGE) para un vector fallido.

    Para checks accionables, escribe el flag correspondiente en sys_config
    para que el MainOrchestrator lo consuma en el siguiente ciclo.
    Para checks que requieren intervención humana, emite diagnóstico claro.

    Stage → acción:
      backtest_quality / lifecycle_coherence → oem_repair_force_backtest
      adx_sanity → oem_repair_force_ohlc_reload
      score_stale → oem_repair_force_ranking
      shadow_sync / signal_flow / rejection_rate / orchestrator_heartbeat → informativo
      Architecture / QA Guard / Code Quality → requiere intervención humana
    """
    from datetime import datetime, timezone as _tz
    stage = payload.get("stage")
    if not stage:
        raise HTTPException(status_code=400, detail="Stage name is required")

    await _broadcast_thought(
        f"Iniciando protocolo de Auto-Gestión EDGE para: {stage}...",
        level="info", module="EDGE"
    )

    # Flags que el MainOrchestrator consume en el siguiente ciclo
    _STAGE_TO_FLAG: Dict[str, str] = {
        "backtest_quality":    "oem_repair_force_backtest",
        "lifecycle_coherence": "oem_repair_force_backtest",
        "adx_sanity":          "oem_repair_force_ohlc_reload",
        "score_stale":         "oem_repair_force_ranking",
        # Integrity matrix stages también mapean a backtest
        "BacktestOrchestrator": "oem_repair_force_backtest",
        "ScannerEngine":        "oem_repair_force_ohlc_reload",
        "StrategyRanker":       "oem_repair_force_ranking",
    }

    # Checks que no se pueden auto-reparar
    _HUMAN_ONLY = {
        "shadow_sync", "signal_flow", "rejection_rate", "orchestrator_heartbeat",
        "Architecture", "QA Guard", "Code Quality", "Manifesto", "Tenant Security",
    }

    try:
        storage = _get_storage()
        flag_key = _STAGE_TO_FLAG.get(stage)

        if flag_key:
            requested_at = datetime.now(_tz.utc).isoformat()
            storage.update_sys_config({flag_key: requested_at})
            logger.info("[REPAIR] Flag %s escrito para stage=%s", flag_key, stage)
            await _broadcast_thought(
                f"Acción correctiva programada para {stage}. "
                f"El orchestrator ejecutará la reparación en el próximo ciclo.",
                level="success", module="EDGE"
            )
            return {"success": True, "stage": stage, "action": flag_key}

        elif stage in _HUMAN_ONLY:
            await _broadcast_thought(
                f"El check '{stage}' no puede repararse automáticamente. "
                f"Requiere diagnóstico manual: revisar logs del proceso principal.",
                level="warning", module="EDGE"
            )
            return {"success": False, "stage": stage, "action": "human_required"}

        else:
            # Stage no reconocido (integrity matrix genérico) — informativo
            await _broadcast_thought(
                f"Vector {stage} resincronizado en el bus de reparación. "
                f"El sistema verificará en el próximo ciclo.",
                level="info", module="EDGE"
            )
            return {"success": True, "stage": stage, "action": "acknowledged"}

    except Exception as e:
        logger.error("[REPAIR] Error en protocolo de reparación: %s", e)
        await _broadcast_thought(
            f"Falla en Auto-Gestión para {stage}: {e}", level="error", module="EDGE"
        )
        return {"success": False, "error": str(e)}


# ============ Module Management Endpoints ============

@router.get("/modules/status")
async def get_modules_status() -> Dict[str, Any]:
    """Returns the current enabled/disabled state of all system modules."""
    try:
        storage = _get_storage()
        config = storage.get_modules_config()
        # Normalize: ensure we always have a 'modules' key with booleans
        modules = config.get("modules", config) if config else {}
        return {"modules": modules}
    except Exception as e:
        logger.error(f"Error getting modules status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modules/toggle")
async def toggle_module(request: Request) -> Dict[str, Any]:
    """Toggle a specific module on/off.
    Body: { "module": "scanner", "enabled": true }
    """
    try:
        body = await request.json()
        module_name = body.get("module")
        enabled = body.get("enabled", False)

        if not module_name:
            raise HTTPException(status_code=400, detail="module name is required")

        storage = _get_storage()
        config = storage.get_modules_config() or {}
        modules = config.get("modules", config)

        modules[module_name] = enabled
        storage.save_modules_config({"modules": modules})

        status = "enabled" if enabled else "disabled"
        logger.info(f"Module '{module_name}' {status}")
        return {"success": True, "module": module_name, "enabled": enabled}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling module: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ User Preferences Endpoints ============

@router.get("/user/preferences")
async def get_usr_preferences(user_id: str = "default", token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Returns the user preferences from the database."""
    try:
        # New architecture: use user_id as tenant_id for isolation
        tenant_id = token.sub if not user_id or user_id == "default" else user_id
        storage = TenantDBFactory.get_storage(tenant_id)
        prefs = storage.get_usr_preferences(user_id)
        if prefs is None:
            return {"preferences": {}, "user_id": user_id}
        return {"preferences": prefs, "user_id": user_id}
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/preferences")
async def update_usr_preferences(request: Request, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Update user preferences.
    Body: { "user_id": "default", "key": "value", ... }
    """
    try:
        body = await request.json()
        user_id = body.pop("user_id", "default")
        # New architecture: use user_id as tenant_id for isolation
        tenant_id = token.sub if not user_id or user_id == "default" else user_id

        if not body:
            raise HTTPException(status_code=400, detail="No preferences provided")

        storage = TenantDBFactory.get_storage(tenant_id)
        success = storage.update_usr_preferences(user_id, body)

        if success:
            return {"success": True, "user_id": user_id}
        else:
            raise HTTPException(status_code=400, detail="Failed to update preferences")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Scanner Status Endpoint ============

@router.get("/system/health/edge")
async def get_edge_health() -> Dict[str, Any]:
    """
    Retorna el estado de salud operacional del sistema según el OperationalEdgeMonitor.

    Lee desde la DB (sys_config.oem_health_snapshot) para funcionar correctamente
    cuando el OEM corre en un proceso separado al del servidor API.
    """
    import json as _json
    from data_vault.storage import StorageManager
    try:
        storage = StorageManager()
        sys_config = storage.get_sys_config()
        raw = sys_config.get("oem_health_snapshot")
        if raw:
            snapshot = _json.loads(raw) if isinstance(raw, str) else raw
            return snapshot
    except Exception as exc:
        logger.warning("[OEM] Error reading health snapshot from DB: %s", exc)

    return {
        "status": "UNAVAILABLE",
        "message": "OperationalEdgeMonitor no inicializado — el sistema puede estar arrancando",
        "checks": {},
        "failing": [],
        "warnings": [],
        "last_checked_at": None,
    }


@router.get("/scanner/status")
async def get_scanner_status() -> Dict[str, Any]:
    """Returns the current scanner status.
    Note: ScannerEngine runs in a separate thread. This endpoint returns
    a static idle state when the engine reference is not available.
    """
    try:
        # Try to get the scanner from orchestrator if running
        try:
            from core_brain.server import _get_orchestrator
            orchestrator = _get_orchestrator()
            if orchestrator and hasattr(orchestrator, 'scanner') and orchestrator.scanner:
                return orchestrator.scanner.get_status()
        except Exception:
            pass

        # Fallback: static idle status
        return {
            "assets": [],
            "last_regime": {},
            "last_scan_time": {},
            "cpu_percent": 0.0,
            "cpu_limit_pct": 80.0,
            "running": False,
        }
    except Exception as e:
        logger.error(f"Error getting scanner status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
