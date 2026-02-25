"""
Router de Notificaciones - Endpoints de notificaciones y Telegram.
Micro-ETI 2.3: Oleada 3 de control y notificaciones.
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Notifications"])

# Core notificador y servicio de notificaciones
_notification_service_instance = None
_telegram_provisioner_instance = None


def _get_storage() -> StorageManager:
    """Lazy-load StorageManager to avoid import-time initialization."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_notification_service() -> Any:
    """Lazy-load notification service."""
    global _notification_service_instance
    if _notification_service_instance is None:
        from core_brain.notification_service import NotificationService
        storage = _get_storage()
        _notification_service_instance = NotificationService(storage=storage)
    return _notification_service_instance


def _get_telegram_provisioner() -> Any:
    """Lazy-load TelegramProvisioner."""
    global _telegram_provisioner_instance
    if _telegram_provisioner_instance is None:
        from connectors.telegram_provisioner import TelegramProvisioner
        _telegram_provisioner_instance = TelegramProvisioner()
    return _telegram_provisioner_instance


async def _broadcast_thought(message: str, module: str = "CORE", level: str = "info", metadata: Optional[Dict[str, Any]] = None) -> None:
    """Broadcast thoughts to WebSocket clients."""
    from core_brain.server import broadcast_thought
    await broadcast_thought(message, module=module, level=level, metadata=metadata)


@router.get("/notifications/unread")
async def get_unread_notifications(user_id: str = 'default') -> Dict[str, Any]:
    """Obtiene notificaciones no leídas"""
    try:
        notification_service = _get_notification_service()
        notifications = notification_service.get_unread_notifications(user_id)
        return {"notifications": notifications, "count": len(notifications)}
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(notification_id: str) -> Dict[str, Any]:
    """Marca notificación como leída"""
    try:
        notification_service = _get_notification_service()
        success = notification_service.mark_as_read(notification_id)
        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Notification not found")
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/settings")
async def get_all_notification_settings() -> Dict[str, Any]:
    """Retorna la configuración de todos los proveedores de notificaciones"""
    try:
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        settings = notif_db.get_all_notification_settings()
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger.error(f"Error getting notification settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/settings/{provider}")
async def update_notification_provider_settings(provider: str, data: dict) -> Dict[str, Any]:
    """Actualiza la configuración de un proveedor específico"""
    enabled = data.get("enabled", False)
    config = data.get("config", {})
    
    try:
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        success = notif_db.update_notification_settings(provider, enabled, config)
        
        if success:
            from core_brain.notificator import initialize_notifier
            initialize_notifier(_get_storage())
            await _broadcast_thought(f"Notificaciones de {provider} actualizadas.", module="CORE")
            return {"status": "success", "message": f"Configuración de {provider} actualizada."}
        else:
            raise HTTPException(status_code=500, detail=f"Error al actualizar {provider}.")
    except Exception as e:
        logger.error(f"Error updating notification settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === TELEGRAM ENDPOINTS ===

@router.post("/telegram/validate")
async def validate_telegram_token(data: dict) -> Dict[str, Any]:
    """Validates Telegram bot token"""
    try:
        bot_token = data.get("bot_token", "")
        telegram_provisioner = _get_telegram_provisioner()
        is_valid, result = await telegram_provisioner.validate_bot_token(bot_token)
        
        if is_valid:
            return {"status": "success", "bot_info": result}
        else:
            return {"status": "error", "error": result.get("error")}
    except Exception as e:
        logger.error(f"Error validating Telegram token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/get-chat-id")
async def get_telegram_chat_id(data: dict) -> Dict[str, Any]:
    """Auto-detects user's chat_id from bot updates"""
    try:
        bot_token = data.get("bot_token", "")
        telegram_provisioner = _get_telegram_provisioner()
        success, result = await telegram_provisioner.get_chat_id_from_updates(bot_token)
        
        if success:
            return {"status": "success", "chat_info": result}
        else:
            if result.get("error") == "no_messages":
                return {
                    "status": "waiting",
                    "message": result.get("hint")
                }
            return {"status": "error", "error": result.get("error")}
    except Exception as e:
        logger.error(f"Error getting Telegram chat ID: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/test")
async def test_telegram_message(data: dict) -> Dict[str, Any]:
    """Sends test message to verify configuration"""
    try:
        bot_token = data.get("bot_token", "")
        chat_id = data.get("chat_id", "")
        
        telegram_provisioner = _get_telegram_provisioner()
        success, result = await telegram_provisioner.send_test_message(bot_token, chat_id)
        
        if success:
            return {"status": "success", "message_id": result.get("message_id")}
        else:
            return {"status": "error", "error": result.get("error")}
    except Exception as e:
        logger.error(f"Error sending Telegram test message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/save")
async def save_telegram_config(data: dict) -> Dict[str, Any]:
    """Saves Telegram configuration to specialized notification table"""
    try:
        bot_token = data.get("bot_token", "")
        chat_id = data.get("chat_id", "")
        enabled = data.get("enabled", True)
        
        telegram_config = {
            "bot_token": bot_token,
            "basic_chat_id": chat_id,
            "premium_chat_id": chat_id
        }
        
        # Guardar usando el nuevo SystemMixin
        from data_vault.system_db import SystemMixin
        notif_db = SystemMixin()
        success = notif_db.update_notification_settings("telegram", enabled, telegram_config)
        
        if success:
            # Re-inicializar el motor de notificaciones
            from core_brain.notificator import initialize_notifier
            initialize_notifier(_get_storage())
            
            await _broadcast_thought("Notificaciones de Telegram configuradas correctamente.", module="CORE")
            logger.info(f"✅ Telegram configurado: Chat ID {chat_id}")
            
            return {
                "status": "success",
                "message": "Configuración de Telegram guardada correctamente."
            }
        else:
            raise HTTPException(status_code=500, detail="Error al guardar la configuración en la base de datos.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Telegram config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telegram/instructions")
async def get_telegram_instructions() -> Dict[str, Any]:
    """Returns setup instructions in Spanish"""
    try:
        telegram_provisioner = _get_telegram_provisioner()
        return telegram_provisioner.get_setup_instructions()
    except Exception as e:
        logger.error(f"Error getting Telegram instructions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
