"""
Ejemplo de uso del MainOrchestrator
Demuestra cómo inicializar y ejecutar el sistema completo de trading.

Este script muestra:
1. Inicialización de todos los componentes
2. Configuración del orquestrador
3. Ejecución del loop principal
4. Manejo de Ctrl+C para shutdown graceful
"""
import asyncio
import logging
from pathlib import Path

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from data_vault.storage import StorageManager
from connectors.mt5_data_provider import MT5DataProvider


# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/orchestrator.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """
    Punto de entrada principal del sistema.
    Inicializa todos los componentes y ejecuta el orquestador.
    """
    logger.info("="*60)
    logger.info("Iniciando Aethelgard Trading System")
    logger.info("="*60)
    
    # Crear directorio de logs si no existe
    Path("logs").mkdir(exist_ok=True)
    
    try:
        # 1. Inicializar Storage Manager
        logger.info("Inicializando Storage Manager...")
        storage = StorageManager()
        
        # 2. Inicializar Risk Manager
        logger.info("Inicializando Risk Manager...")
        risk_manager = RiskManager(
            initial_capital=10000.0,  # Capital inicial
            config_path='config/dynamic_params.json'
        )
        
        # 3. Inicializar Data Provider (MT5)
        logger.info("Inicializando MT5 Data Provider...")
        data_provider = MT5DataProvider()
        
        # Verificar conexión MT5
        if not data_provider.is_connected():
            logger.error("No se pudo conectar con MetaTrader 5")
            logger.error("Asegúrate de que MT5 esté en ejecución")
            return
        
        # 4. Inicializar Scanner Engine
        logger.info("Inicializando Scanner Engine...")
        scanner = ScannerEngine(
            data_provider=data_provider,
            config_path='config/config.json'
        )
        
        # 5. Inicializar Signal Factory
        logger.info("Inicializando Signal Factory...")
        signal_factory = SignalFactory(
            storage_manager=storage,
            strategy_id="oliver_velez_swing_v2"
        )
        
        # 6. Inicializar Order Executor
        logger.info("Inicializando Order Executor...")
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors={}  # Se añadirían conectores reales aquí
        )
        
        # 7. Crear Main Orchestrator
        logger.info("Inicializando Main Orchestrator...")
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=signal_factory,
            risk_manager=risk_manager,
            executor=executor,
            storage=storage,
            config_path='config/config.json'
        )
        
        # 8. Iniciar el loop principal
        logger.info("="*60)
        logger.info("Sistema iniciado. Presiona Ctrl+C para detener.")
        logger.info("="*60)
        logger.info("")
        
        # Ejecutar el orquestador
        await orchestrator.run()
        
    except KeyboardInterrupt:
        logger.info("Interrupción manual detectada")
    except Exception as e:
        logger.critical(f"Error fatal en el sistema: {e}", exc_info=True)
    finally:
        logger.info("="*60)
        logger.info("Sistema detenido")
        logger.info("="*60)


if __name__ == "__main__":
    # Ejecutar el sistema
    asyncio.run(main())
