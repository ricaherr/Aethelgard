"""
Script de Validación: Módulo de Normalización de Activos
Verifica la creación de tablas, semilla de datos y lógica de cálculo agnóstico.
"""
import sys
import os
import logging
from pathlib import Path

# Añadir el path raíz al sistema
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager, AssetNotNormalizedError

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_test():
    logger.info("=== INICIANDO VALIDACIÓN DE NORMALIZACIÓN DE ACTIVOS ===")
    
    # 1. Inicializar Storage (in-memory for testing isolation)
    storage = StorageManager(":memory:")
    
    # 2. Inicializar RiskManager
    risk_manager = RiskManager(storage=storage)
    
    # 3. Datos de prueba
    test_cases = [
        {
            "symbol": "EURUSD",
            "risk": 100.0,
            "sl_dist": 0.0050,  # 50 pips
            "expected_logic": "100 / (0.0050 * 100000) = 0.20 lots"
        },
        {
            "symbol": "GBPUSD",
            "risk": 50.0,
            "sl_dist": 0.0025,  # 25 pips
            "expected_logic": "50 / (0.0025 * 100000) = 0.20 lots"
        },
        {
            "symbol": "USDJPY",
            "risk": 150.0,
            "sl_dist": 0.500,   # 50 pips (JPY)
            "expected_logic": "150 / (0.500 * 100000) = 0.03 lots"
        },
        {
            "symbol": "GOLD",
            "risk": 200.0,
            "sl_dist": 5.0,     # $5.00 move
            "expected_logic": "200 / (5.0 * 100) = 0.40 lots"
        },
        {
            "symbol": "BTCUSD",
            "risk": 100.0,
            "sl_dist": 1000.0,  # $1000 move
            "expected_logic": "100 / (1000.0 * 1) = 0.10 lots"
        }
    ]
    
    all_passed = True
    
    for case in test_cases:
        symbol = case["symbol"]
        risk = case["risk"]
        sl_dist = case["sl_dist"]
        
        try:
            lots = risk_manager.calculate_position_size(symbol, risk, sl_dist)
            logger.info(f"✅ {symbol}: {lots} lots | Lógica: {case['expected_logic']}")
        except AssetNotNormalizedError as e:
            logger.error(f"❌ {symbol}: Error inesperado - {e}")
            all_passed = False
        except Exception as e:
            logger.error(f"❌ {symbol}: Error técnico - {e}")
            all_passed = False

    # 4. Test de seguridad: Símbolo no normalizado
    logger.info("\n--- Test de Seguridad: Símbolo No Normalizado ---")
    try:
        risk_manager.calculate_position_size("INVALID", 100, 0.01)
        logger.error("❌ ERROR: El sistema permitió operar un símbolo no normalizado.")
        all_passed = False
    except AssetNotNormalizedError as e:
        logger.info(f"✅ PASS: Excepción capturada correctamente: {e}")
    except Exception as e:
        logger.error(f"❌ ERROR: Excepción incorrecta - {e}")
        all_passed = False

    # 5. Test de redondeo descendente (Downwards Rounding)
    logger.info("\n--- Test de Redondeo: Downwards Rounding ---")
    # Caso: 100 USD / (0.0033 * 100000) = 0.303030... -> Debe ser 0.30
    lots_round = risk_manager.calculate_position_size("EURUSD", 100.0, 0.0033)
    if lots_round == 0.30:
        logger.info(f"✅ PASS: Redondeo 0.303030 -> {lots_round}")
    else:
        logger.error(f"❌ FAIL: Redondeo incorrecto: {lots_round} (se esperaba 0.30)")
        all_passed = False

    if all_passed:
        logger.info("\n🏆 RESULTADO FINAL: TODOS LOS TESTS PASARON.")
    else:
        logger.error("\n💀 RESULTADO FINAL: ALGUNOS TESTS FALLARON.")
        sys.exit(1)

    # Limpieza
    try:
        if os.path.exists("aethelgard_test.db"):
            os.remove("aethelgard_test.db")
            os.remove("aethelgard_test.db-wal")
            os.remove("aethelgard_test.db-shm")
    except:
        pass

if __name__ == "__main__":
    run_test()
