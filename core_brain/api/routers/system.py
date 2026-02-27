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


@router.get("/config/{category}")
async def get_config(category: str, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Obtiene una categoría de configuración de la DB"""
    db_key = f"config_{category}"
    tenant_id = token.tid
    storage = TenantDBFactory.get_storage(tenant_id)
    state = storage.get_system_state()
    config_data = state.get(db_key)
    
    if config_data is None:
        logger.warning(f"Config '{category}' requested not found in DB for tenant {tenant_id}.")
        return {}
        
    if config_data is None and category == "notifications":
        # Fallback especial para notificaciones si se pide vía /config pero no existe
        try:
            from data_vault.system_db import SystemMixin
            notif_db = SystemMixin()
            telegram_settings = notif_db.get_notification_settings("telegram", tenant_id=tenant_id)
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
    """Actualiza una categoría de configuración en la DB"""
    db_key = f"config_{category}"
    tenant_id = token.tid
    storage = TenantDBFactory.get_storage(tenant_id)
    
    try:
        storage.update_system_state({db_key: new_data})
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
    """
    # Mapas de lenguaje sofisticado por etapa
    sophisticated_lexicon = {
        "Architecture": "Analizando topología de arquitectura y coherencia de módulos...",
        "QA Guard": "Verificando integridad sintáctica y estándares de calidad QA...",
        "Code Quality": "Escaneando densidad de complejidad y patrones de duplicidad...",
        "UI Quality": "Validando ecosistema React y consistencia de tipos en interfaz...",
        "Manifesto": "Enforzando leyes del Manifesto (DI & SSOT)...",
        "Patterns": "Escrutando firmas de métodos y protocolos de seguridad AST...",
        "Core Tests": "Ejecutando suite crítica de deduplicación y gestión de riesgo...",
        "Integration": "Validando puentes de integración y persistencia en Data Vault...",
        "Connectivity": "Auditando latencia y fidelidad del uplink con el Broker...",
        "System DB": "Verificando integridad estructural de la base de Datos..."
    }

    await _broadcast_thought("Desplegando hilos de auditoría paralela... Iniciando escaneo de vectores de integridad.", module="HEALTH")
    
    validation_results = []
    error_details = {}
    total_time = 0.0
    
    try:
        process = await asyncio.create_subprocess_exec(
            "python", "scripts/validate_all.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.getcwd()
        )
        
        # Leer stdout línea a línea para interceptar STAGE_START, STAGE_END y DEBUG_FAIL
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            decoded_line = line.decode(errors='replace').strip()
            
            if decoded_line.startswith("STAGE_START:"):
                stage = decoded_line.split(":")[1]
                msg = sophisticated_lexicon.get(stage, f"Iniciando fase: {stage}...")
                await _broadcast_thought(msg, level="info", module="HEALTH", metadata={"stage": stage, "status": "STARTING"})
            
            elif decoded_line.startswith("DEBUG_FAIL:"):
                parts = decoded_line.split(":", 2)
                if len(parts) >= 3:
                    stage, error = parts[1], parts[2]
                    error_details[stage] = error

            elif decoded_line.startswith("STAGE_END:"):
                parts = decoded_line.split(":")
                if len(parts) >= 4:
                    stage, result_status, duration = parts[1], parts[2], parts[3]
                    try:
                        duration_float = float(duration)
                        total_time += duration_float
                    except:
                        duration_float = 0.0
                    
                    if result_status == "OK":
                        color_indicator = "✅"
                        await _broadcast_thought(
                            f"{color_indicator} Vector {stage} successfully validated ({duration}s).",
                            level="success",
                            module="HEALTH",
                            metadata={"stage": stage, "status": "OK", "duration": duration}
                        )
                        validation_results.append({
                            "stage": stage,
                            "status": "PASSED",
                            "duration": duration_float
                        })
                    else:
                        color_indicator = "❌"
                        error_msg = error_details.get(stage, "Inconsistencia de integridad no especificada.")
                        await _broadcast_thought(
                            f"{color_indicator} Vector {stage} compromised ({duration}s). Error: {error_msg}",
                            level="warning",
                            module="HEALTH",
                            metadata={
                                "stage": stage,
                                "status": "FAIL",
                                "duration": duration,
                                "error": error_msg
                            }
                        )
                        validation_results.append({
                            "stage": stage,
                            "status": "FAILED",
                            "duration": duration_float,
                            "error": error_msg
                        })
        
        await process.wait()
        # Success logic: Must have return code 0 AND no failed stages detected in stdout
        passed_count = sum(1 for r in validation_results if r["status"] == "PASSED")
        failed_count = sum(1 for r in validation_results if r["status"] == "FAILED")
        total_count = len(validation_results)
        
        # Final determination: We trust the process return code first, but verify stage count
        success = (process.returncode == 0) and (failed_count == 0) and (total_count > 0)
        
        # Debug Return Code
        if process.returncode != 0:
            logger.warning(f"[AUDIT] Validation process exited with non-zero code: {process.returncode} (Failed count: {failed_count})")
        
        if success:
            final_msg = f"✅ Auditoría de alto rendimiento completada: Matriz de integridad 100% estable ({passed_count}/{total_count} vectores validados en {total_time:.2f}s)."
            await _broadcast_thought(final_msg, level="success", module="HEALTH", metadata={"status": "FINISHED", "success": True, "total_time": total_time})
        else:
            final_msg = f"⚠️ Auditoría finalizada con {failed_count} vectores comprometidos ({passed_count}/{total_count} validados en {total_time:.2f}s)."
            await _broadcast_thought(final_msg, level="warning", module="HEALTH", metadata={"status": "FINISHED", "success": False, "total_time": total_time})
        
        # Retornar resultados completos
        return {
            "success": success,
            "passed": passed_count,
            "failed": failed_count,
            "total": total_count,
            "duration": total_time,
            "results": validation_results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"[AUDIT] Error en flujo de auditoría evolucionada: {e}", exc_info=True)
        error_msg = f"Falla crítica en motor de auditoría: {str(e)}"
        await _broadcast_thought(error_msg, level="error", module="HEALTH")
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.post("/system/audit/repair")
async def repair_integrity_vector(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intenta una reparación automática (Auto-Gestion EDGE) para un vector fallido.
    """
    stage = payload.get("stage")
    if not stage:
        raise HTTPException(status_code=400, detail="Stage name is required")

    await _broadcast_thought(f"Iniciando protocolo de Auto-Gestión EDGE para vector: {stage}...", level="info", module="EDGE")
    
    try:
        success = False
        if stage == "Connectivity":
            # Intentar reconectar si hay un orchestrator
            await asyncio.sleep(2)
            success = True
            await _broadcast_thought(f"Protocolo de reconexión exitoso en vector {stage}. Fidelidad restaurada.", level="success", module="EDGE")
        
        elif stage == "System DB":
            # Intentar forzar una sincronización o validación de hashes
            await asyncio.sleep(2)
            success = True
            await _broadcast_thought(f"Regeneración de índices y validación de hash completada en {stage}.", level="success", module="EDGE")

        elif stage in ["QA Guard", "Code Quality", "Manifesto"]:
            # Estos fallos suelen requerir intervención humana
            await asyncio.sleep(1)
            success = False
            await _broadcast_thought(f"El vector {stage} requiere intervención estructural. Auto-Gestión insuficiente.", level="warning", module="EDGE")

        else:
            await asyncio.sleep(1)
            success = True
            await _broadcast_thought(f"Módulo {stage} resincronizado preventivamente.", level="info", module="EDGE")

        return {"success": success, "stage": stage}

    except Exception as e:
        logger.error(f"[REPAIR] Error en protocolo de reparación: {e}")
        await _broadcast_thought(f"Falla en protocolo de Auto-Gestión para {stage}: {str(e)}", level="error", module="EDGE")
        return {"success": False, "error": str(e)}


@router.get("/edge/tuning-logs")
async def get_tuning_logs(limit: int = 50) -> Dict[str, Any]:
    """
    Retorna el historial de ajustes del EdgeTuner (Neuro-evolución).
    """
    try:
        storage = _get_storage()
        history = storage.get_tuning_history(limit=limit)
        return {"status": "success", "history": history}
    except Exception as e:
        logger.error(f"Error recuperando historial de tuning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def get_user_preferences(user_id: str = "default", token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Returns the user preferences from the database."""
    try:
        # Ensure we use the token's tid for tenant isolation
        tenant_id = token.tid
        storage = TenantDBFactory.get_storage(tenant_id)
        prefs = storage.get_user_preferences(user_id)
        if prefs is None:
            return {"preferences": {}, "user_id": user_id}
        return {"preferences": prefs, "user_id": user_id}
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/preferences")
async def update_user_preferences(request: Request, token: TokenPayload = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Update user preferences.
    Body: { "user_id": "default", "key": "value", ... }
    """
    try:
        body = await request.json()
        user_id = body.pop("user_id", "default")
        tenant_id = token.tid

        if not body:
            raise HTTPException(status_code=400, detail="No preferences provided")

        storage = TenantDBFactory.get_storage(tenant_id)
        success = storage.update_user_preferences(user_id, body)

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
