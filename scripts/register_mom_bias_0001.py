"""
Register MOM_BIAS_0001 Strategy in Database
============================================

Script para registrar la estrategia MOM_BIAS_0001 con sus scores de afinidad.

Uso:
  python scripts/register_mom_bias_0001.py

TRACE_ID: SETUP-STRAT-MOM-BIAS-001
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


def register_mom_bias_0001() -> bool:
    """
    Registra MOM_BIAS_0001 en la base de datos.
    
    Affinity Scores:
    - GBP/JPY: 0.85 (EXCELLENT)
    - EUR/USD: 0.65 (GOOD)
    - GBP/USD: 0.72 (GOOD)
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
            "GBP/JPY": 0.85,
            "EUR/USD": 0.65,
            "GBP/USD": 0.72,
            "USD/JPY": 0.60,
        }
        
        market_whitelist = list(affinity_scores.keys())
        
        # Registrar estrategia
        success = storage_manager.create_strategy(
            class_id="MOM_BIAS_0001",
            mnemonic="MOMENTUM_STRIKE",
            version="1.0",
            affinity_scores=affinity_scores,
            market_whitelist=market_whitelist,
            description=(
                "Momentum Strike - Ruptura de compresión SMA20/SMA200 con vela elefante. "
                "Stop Loss = OPEN de la vela (regla de ORO para maximizar lotaje). "
                "Risk/Reward: 1:2 a 1:3. "
                "Requiere compresión <= 15 pips y cierre 2% lejos de SMA20."
            )
        )
        
        if success:
            logger.info("✅ MOM_BIAS_0001 registered successfully!")
            logger.info(f"   Affinity scores: {affinity_scores}")
            logger.info(f"   Market whitelist: {market_whitelist}")
            return True
        else:
            logger.error("❌ Failed to register MOM_BIAS_0001")
            return False
    
    except Exception as e:
        logger.error(f"❌ Error registering strategy: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = register_mom_bias_0001()
    sys.exit(0 if success else 1)
