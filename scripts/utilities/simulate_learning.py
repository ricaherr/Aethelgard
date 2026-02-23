import os
import sys
import json
import logging
from datetime import datetime, timezone

# Añadir el path del proyecto para poder importar módulos
sys.path.append(os.getcwd())

from data_vault.storage import StorageManager

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def simulate_learning():
    """
    Simula eventos de aprendizaje para el EdgeTuner y los guarda en la base de datos.
    Esto permite verificar que la UI muestra correctamente los eventos de 'Autonomous Learning'.
    """
    try:
        storage = StorageManager()
        
        # 1. Simular un aprendizaje positivo (Delta positivo)
        details_win = {
            "delta": 0.12,
            "regime": "TREND",
            "adjustment_made": True,
            "metric_adjusted": "profit_factor",
            "old_weight": 0.4,
            "new_weight": 0.412
        }
        
        storage.save_edge_learning(
            detection="Prediction accuracy high in TREND regime.",
            action_taken="Incremental weight adjustment for profit_factor (+3%).",
            learning="The model is currently underestimating the trend persistence. Increasing dominance of profit_factor.",
            details=json.dumps(details_win)
        )
        logger.info("✅ Simulación de aprendizaje POSITIVO guardada.")

        # 2. Simular un aprendizaje negativo (Delta negativo - Bajo rendimiento)
        details_loss = {
            "delta": -0.15,
            "regime": "RANGE",
            "adjustment_made": True,
            "metric_adjusted": "consecutive_losses",
            "old_weight": 0.2,
            "new_weight": 0.23
        }
        
        storage.save_edge_learning(
            detection="Model over-confidence in RANGE detected.",
            action_taken="Risk tightening: Increasing weight of consecutive_losses metric.",
            learning="Prediction error high. RANGE regimes are exhibiting more noise than expected. Adjusting protective metrics.",
            details=json.dumps(details_loss)
        )
        logger.info("✅ Simulación de aprendizaje NEGATIVO guardada.")

        # 3. Simular un evento estable (Sin ajuste necesario)
        details_stable = {
            "delta": 0.02,
            "regime": "VOLATILE",
            "adjustment_made": False
        }
        
        storage.save_edge_learning(
            detection="Prediction alignment optimal in VOLATILE.",
            action_taken="No adjustment required. Monitoring stability.",
            learning="System maintains high fidelity in volatile market conditions. Current weights remain valid.",
            details=json.dumps(details_stable)
        )
        logger.info("✅ Simulación de evento ESTABLE guardada.")

        print("\n" + "="*50)
        print("SIMULACIÓN COMPLETADA")
        print("Los eventos ahora deberían ser visibles en: EDGE Hub -> Neural History")
        print("="*50 + "\n")

    except Exception as e:
        logger.error(f"❌ Error en simulación: {e}")

if __name__ == "__main__":
    simulate_learning()
