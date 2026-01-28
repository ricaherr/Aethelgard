"""
Aethelgard Trading System - Production Launcher
================================================

Sistema completo de trading en producción con:
- Yahoo Finance como proveedor de datos (sin API key)
- Scanner proactivo de mercados
- Generación de señales reales
- Gestión de riesgo automática
- Persistencia completa en SQLite

PRODUCCIÓN REAL - NO SIMULACIONES
"""
import asyncio
import logging
import threading
from pathlib import Path

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from core_brain.monitor import ClosingMonitor
from data_vault.storage import StorageManager
from connectors.generic_data_provider import GenericDataProvider

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/production.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """
    Lanzador de producción de Aethelgard.
    Inicializa TODOS los componentes reales.
    """
    logger.info("=" * 70)
    logger.info("🚀 AETHELGARD TRADING SYSTEM - PRODUCTION MODE")
    logger.info("=" * 70)
    
    # Crear directorios necesarios
    Path("logs").mkdir(exist_ok=True)
    Path("data_vault").mkdir(exist_ok=True)
    
    try:
        # 1. Storage Manager (Base de datos SQLite)
        logger.info("📦 Inicializando Storage Manager...")
        storage = StorageManager()
        
        # 2. Risk Manager (Gestión de capital y riesgo)
        logger.info("⚖️  Inicializando Risk Manager...")
        risk_manager = RiskManager(
            initial_capital=10000.0,  # Capital inicial
            config_path='config/dynamic_params.json'
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade: {risk_manager.risk_per_trade:.1%}")
        
        # 3. Data Provider REAL (Yahoo Finance)
        logger.info("📡 Inicializando Data Provider (Yahoo Finance)...")
        data_provider = GenericDataProvider()
        
        # Símbolos reales de forex para escanear
        symbols = [
            "EURUSD=X",  # Euro/USD
            "GBPUSD=X",  # Libra/USD
            "USDJPY=X",  # USD/Yen
            "AUDUSD=X",  # Dólar australiano/USD
            "USDCAD=X",  # USD/Dólar canadiense
            "NZDUSD=X",  # Dólar neozelandés/USD
        ]
        logger.info(f"   Símbolos a monitorear: {len(symbols)}")
        for sym in symbols:
            logger.info(f"      - {sym}")
        
        # 4. Scanner Engine REAL (Busca oportunidades en el mercado)
        logger.info("🔍 Inicializando Scanner Engine...")
        scanner = ScannerEngine(
            assets=symbols,  # Lista de símbolos a monitorear
            data_provider=data_provider,
            config_path='config/config.json',
            scan_mode="STANDARD"  # ECO | STANDARD | AGRESSIVE
        )
        
        # 5. Signal Factory REAL (Genera señales de trading)
        logger.info("⚡ Inicializando Signal Factory...")
        signal_factory = SignalFactory(
            storage_manager=storage,
            strategy_id="oliver_velez_swing_v2"
        )
        
        # 6. Order Executor REAL (Ejecuta órdenes)
        logger.info("🎯 Inicializando Order Executor...")
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors={}  # Paper trading por defecto
        )
        logger.info("   Modo: Paper Trading (sin conexión a broker)")
        
        # 7. Closing Monitor (Feedback Loop)
        logger.info("💰 Inicializando Closing Monitor (Feedback Loop)...")
        monitor = ClosingMonitor(
            storage=storage,
            connectors={},  # Se agregarán cuando conectemos MT5/NT8
            interval_seconds=60  # Revisar cada minuto
        )
        logger.info("   Intervalo de monitoreo: 60 segundos")
        logger.info("   Estado: Activo (esperando trades para monitorear)")
        
        # 8. Main Orchestrator (Cerebro del sistema)
        logger.info("🧠 Inicializando Main Orchestrator...")
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=signal_factory,
            risk_manager=risk_manager,
            executor=e� Nueva pestaña: 'Análisis de Activos' - Ver resultados reales")
        logger.info("🛑 Presiona Ctrl+C para detener el sistema de forma segura")
        logger.info("")
        
        # Iniciar scanner en hilo separado
        logger.info("🔄 Iniciando Scanner en hilo de fondo...")
        scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        scanner_thread.start()
        logger.info("✅ Scanner ejecutándose en background")
        logger.info("")
        
        # Iniciar monitor en tarea asíncrona
        logger.info("🔄 Iniciando Closing Monitor...")
        monitor_task = asyncio.create_task(monitor.start())
        logger.info("✅ Closing Monitor ejecutándose (Feedback Loop activo)
        logger.info("")
        logger.info("📊 El Dashboard está disponible en: http://localhost:8503")
        logger.info("🛑 Presiona Ctrl+C para detener el sistema de forma segura")
        logger.info("")
        
        # Iniciar scanner en hilo separado
        logger.info("🔄 Iniciando Scanner en hilo de fondo...")
        scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        scanner_thread.start()
        logger.info("✅ Scanner ejecutándose en background")
        logger.info("")
        await monitor.stop()  # Detener monitor gracefully
        
        # Ejecutar el loop principal del orquestador
        await orchestrator.run()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupción detectada. Deteniendo sistema...")
        scanner.stop()  # Detener scanner gracefully
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)
        raise
    finally:
        logger.info("💾 Sistema detenido. Todos los datos han sido guardados.")


if __name__ == "__main__":
    asyncio.run(main())
