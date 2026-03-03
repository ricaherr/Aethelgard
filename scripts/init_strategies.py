"""
Script de Inicialización: Registrar SESS_EXT_0001 en Base de Datos

Ejecutar una sola vez después de que el sistema se inicialice.
Registra la estrategia S-0005 (SESS_EXT_0001) en la base de datos con todos
sus metadatos, niveles de membresía y puntuaciones de afinidad.

TRACE_ID: INIT-STRATEGIES-001

Uso:
  python scripts/init_strategies.py
"""

import sys
import os
import logging
from datetime import datetime, timezone

# Añadir el repositorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_vault.storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def register_sess_ext_0001():
    """
    Registra S-0005 (SESS_EXT_0001) en la base de datos.
    
    Del MANIFESTO Sección X:
    - Class ID: SESS_EXT_0001
    - Mnemonic: SESS_EXT_DAILY_FLOW
    - Prime Assets: GBP/JPY (0.90 affinity), EUR/JPY (0.85 affinity), AUD/JPY (0.65 monitor)
    - Timeframes: H1, H4
    - Membership: Premium+
    - Status: 📋 Registrada
    - Operación: Proyecta extensiones Fibonacci 127% y 161% desde sesión Londres
    """
    
    try:
        storage = StorageManager()
        
        # Affinity scores
        affinity_scores = {
            "GBP/JPY": 0.90,  # Prime asset
            "EUR/JPY": 0.85,  # Secondary asset
            "AUD/JPY": 0.65   # Monitor only (no opera)
        }
        
        # Market whitelist (solo assets donde opera, no monitores)
        market_whitelist = ["GBP/JPY", "EUR/JPY"]
        
        # Descripción de la estrategia
        description = (
            "SESSION EXTENSION (S-0005 - SESS_EXT_0001)\n"
            "Proyecta extensiones Fibonacci 127% y 161% desde rango de sesión Londres.\n"
            "Operativo en H1/H4 esperando confluencia: elephant candle + Fibonacci + NY opening.\n"
            "Prime Asset: GBP/JPY (0.90 affinity) | Secondary: EUR/JPY (0.85).\n"
            "Nivel: Premium+. Modo: INSTITUTIONAL."
        )
        
        # Registrar la estrategia
        logger.info("[INIT-STRATEGIES-001] Registrando SESS_EXT_0001...")
        
        success = storage.create_strategy(
            class_id="SESS_EXT_0001",
            mnemonic="SESS_EXT_DAILY_FLOW",
            version="1.0",
            affinity_scores=affinity_scores,
            market_whitelist=market_whitelist,
            description=description
        )
        
        if success:
            logger.info(
                f"✅ SESS_EXT_0001 registrada exitosamente.\n"
                f"   - Affinity Scores: {affinity_scores}\n"
                f"   - Market Whitelist: {market_whitelist}\n"
                f"   - Membership: Premium+\n"
                f"   - Status: READY"
            )
            return True
        else:
            logger.error("❌ Error al registrar SESS_EXT_0001")
            return False
    
    except Exception as e:
        logger.error(f"❌ Excepción registrando estrategia: {e}", exc_info=True)
        return False


def check_existing_strategies():
    """Verifica qué estrategias ya están registradas."""
    try:
        storage = StorageManager()
        strategies = storage.get_all_strategies()
        
        logger.info(f"\n📋 Estrategias registradas en la BD ({len(strategies)} total):")
        for strat in strategies:
            logger.info(
                f"   - {strat.get('class_id')}: {strat.get('mnemonic')} "
                f"(v{strat.get('version')})"
            )
        
        return strategies
    except Exception as e:
        logger.error(f"Error consultando estrategias: {e}")
        return []


def main():
    """Punto de entrada principal."""
    logger.info("[INIT-STRATEGIES-001] Iniciando registro de estrategias...")
    
    # Verificar estrategias existentes
    existing = check_existing_strategies()
    
    # Verificar si SESS_EXT_0001 ya existe
    sess_ext_exists = any(s.get('class_id') == 'SESS_EXT_0001' for s in existing)
    
    if sess_ext_exists:
        logger.warning(
            "⚠️  SESS_EXT_0001 ya está registrada en la base de datos. "
            "Saltando registro."
        )
        return True
    
    # Registrar SESS_EXT_0001
    success = register_sess_ext_0001()
    
    if success:
        logger.info("\n✅ Inicialización completada exitosamente.")
        # Re-verificar
        logger.info("\n📋 Estrategias post-registro:")
        check_existing_strategies()
    else:
        logger.error("\n❌ Inicialización fallida.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
