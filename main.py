"""
Punto de entrada principal para Aethelgard
Incluye gestión de módulos activos y verificación de permisos
"""
import uvicorn
import logging
import os
from pathlib import Path
from core_brain.server import app
from core_brain.module_manager import get_module_manager, MembershipLevel
from core_brain.notificator import initialize_notifier, get_notifier

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_telegram_config() -> None:
    """Carga la configuración de Telegram desde variables de entorno"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    basic_chat_id = os.getenv("TELEGRAM_BASIC_CHAT_ID")
    premium_chat_id = os.getenv("TELEGRAM_PREMIUM_CHAT_ID")
    enabled = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
    
    if bot_token:
        initialize_notifier(
            bot_token=bot_token,
            basic_chat_id=basic_chat_id,
            premium_chat_id=premium_chat_id,
            enabled=enabled
        )
        logger.info("Notificador de Telegram inicializado")
    else:
        logger.info("Notificador de Telegram no configurado (TELEGRAM_BOT_TOKEN no encontrado)")


def verify_active_modules() -> None:
    """Verifica y muestra los módulos activos al iniciar"""
    module_manager = get_module_manager()
    
    # Verificar módulos para membresía básica
    basic_modules = module_manager.get_active_modules(MembershipLevel.BASIC)
    logger.info(f"Módulos activos (Básico): {', '.join(basic_modules) if basic_modules else 'Ninguno'}")
    
    # Verificar módulos para membresía premium
    premium_modules = module_manager.get_active_modules(MembershipLevel.PREMIUM)
    logger.info(f"Módulos activos (Premium): {', '.join(premium_modules) if premium_modules else 'Ninguno'}")
    
    # Verificar módulos deshabilitados
    all_modules = module_manager.get_all_modules_info()
    disabled_modules = [
        name for name, config in all_modules.items()
        if not config.get("enabled", False)
    ]
    if disabled_modules:
        logger.info(f"Módulos deshabilitados: {', '.join(disabled_modules)}")


if __name__ == "__main__":
    # Cargar configuración de Telegram
    load_telegram_config()
    
    # Verificar módulos activos
    verify_active_modules()
    
    # Iniciar servidor
    logger.info("Iniciando servidor Aethelgard en http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
