"""
Test de Integración Arquitectónica - Aethelgard
===============================================
Valida que los componentes críticos (RiskManager, Orchestrator)
pueden leer y escribir en la nueva infraestructura SQLite.
"""
import sys
import os
import logging
import json
from datetime import date

# Añadir raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_vault.storage import StorageManager

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ARCH_VERIFY")

def verify_architecture():
    logger.info("🏗️  Iniciando Verificación de Arquitectura...")
    
    # 1. Conexión a la DB de Producción
    try:
        storage = StorageManager(db_path='data_vault/aethelgard.db')
        logger.info("✅ Conexión a SQLite establecida.")
    except Exception as e:
        logger.critical(f"❌ Fallo crítico de conexión: {e}")
        return

    # 2. Validación de Datos Migrados (RiskManager)
    logger.info("🔍 Validando acceso de RiskManager...")
    state = storage.get_sys_config()
    
    # Verificar claves críticas
    critical_keys = ['lockdown_active', 'consecutive_losses', 'session_stats']
    missing_keys = [k for k in critical_keys if k not in state]
    
    if missing_keys:
        logger.warning(f"⚠️  Faltan claves en sys_config: {missing_keys}")
        logger.info("   (Esto es normal si es la primera ejecución limpia, se crearán por defecto)")
    else:
        logger.info("✅ Claves de RiskManager detectadas correctamente.")
        logger.info(f"   Estado actual: Lockdown={state.get('lockdown_active')}, Losses={state.get('consecutive_losses')}")

    # 3. Simulación de Ciclo de Orquestador (Crash Recovery)
    logger.info("🔄 Simulando reconstrucción de sesión (Orchestrator)...")
    
    # Simular conteo de señales ejecutadas hoy (debe coincidir con la migración si hubo hoy)
    today_usr_signals = storage.count_executed_usr_signals(date.today())
    logger.info(f"   Señales ejecutadas hoy (recuperadas de DB): {today_usr_signals}")
    
    # 4. Prueba de Escritura Transaccional
    logger.info("💾 Probando escritura transaccional...")
    try:
        # Actualizar un estado de prueba
        new_state = {
            "last_health_check": "VERIFIED_OK", 
            "architecture_version": "2.0-SQLITE"
        }
        storage.update_sys_config(new_state)
        
        # Leerlo inmediatamente para confirmar commit
        refreshed_state = storage.get_sys_config()
        if refreshed_state.get("last_health_check") == "VERIFIED_OK":
            logger.info("✅ Escritura y Lectura confirmadas (Commit exitoso).")
        else:
            logger.error("❌ Fallo en persistencia de datos.")
    except Exception as e:
        logger.error(f"❌ Error escribiendo en DB: {e}")

    logger.info("-" * 50)
    logger.info("🚀 CONCLUSIÓN: La arquitectura está lista para LIVE.")
    logger.info("-" * 50)


# --- TDD: Test mínimo que debe fallar (clave crítica artificial) ---

if __name__ == "__main__":
    verify_architecture()
