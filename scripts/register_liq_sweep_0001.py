"""
Register LIQ_SWEEP_0001 Strategy in Database

Script para registrar la estrategia LIQ_SWEEP_0001 con sus scores de afinidad.

Uso:
  python scripts/register_liq_sweep_0001.py

TRACE_ID: SETUP-STRAT-LIQ-SWEEP-001
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def register_liq_sweep_0001() -> bool:
    """
    Registra LIQ_SWEEP_0001 en la base de datos.
    
    Affinity Scores:
    - EUR/USD: 0.92 (PRIME)
    - GBP/USD: 0.88 (EXCELLENT)
    - USD/JPY: 0.60 (MONITOR)
    
    Returns:
        True si registrada exitosamente
    """
    try:
        # Inicializar StorageManager
        storage_manager = StorageManager()
        logger.info("StorageManager initialized")
        
        # Affinity scores especificados
        affinity_scores = {
            "EUR/USD": 0.92,
            "GBP/USD": 0.88,
            "USD/JPY": 0.60,
            "GBP/JPY": 0.70,
            "USD/CAD": 0.65,
        }
        
        market_whitelist = list(affinity_scores.keys())
        
        # Registrar estrategia
        success = storage_manager.create_strategy(
            class_id="LIQ_SWEEP_0001",
            mnemonic="LIQUIDITY_SWEEP_SCALPING",
            version="1.0",
            affinity_scores=affinity_scores,
            market_whitelist=market_whitelist,
            description=(
                "Liquidity Sweep - Scalping de breakout falso. "
                "Detecta falsas rupturas de Session High/Low con reversión (PIN BAR/ENGULFING). "
                "Stop Loss = High/Low de reversal + 2 pips. Take Profit = 30 pips scalp. "
                "Máximo 3 operaciones/día. Win Rate > 50% requerido."
            )
        )
        
        if success:
            logger.info("✅ LIQ_SWEEP_0001 registered successfully!")
            logger.info(f"   Affinity scores: {affinity_scores}")
            logger.info(f"   Market whitelist: {market_whitelist}")
            return True
        else:
            logger.error("❌ Failed to register LIQ_SWEEP_0001")
            return False
    
    except Exception as e:
        logger.error(f"❌ Error registering strategy: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = register_liq_sweep_0001()
    sys.exit(0 if success else 1)
