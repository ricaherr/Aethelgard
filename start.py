"""
Aethelgard Trading System - Unified Launcher
=============================================

Comando único que inicia:
1. Servidor API (FastAPI/Uvicorn) - Cerebro y WebSockets
2. Motor de trading (Scanner + Orchestrator) - Lógica de negocio
3. Dashboard Streamlit (UI) - Visualización
4. EDGE Tuner - Auto-calibración

USO: py start.py
"""
import sys
import os

# Añadir el directorio raíz al path para importar módulos
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
import webbrowser

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from core_brain.monitor import ClosingMonitor
from core_brain.tuner import EdgeTuner
from core_brain.edge_monitor import EdgeMonitor
from data_vault.storage import StorageManager
from connectors.paper_connector import PaperConnector
from models.signal import ConnectorType

# Core Brain Imports
from core_brain.data_provider_manager import DataProviderManager
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

# server_process global
server_process = None


# launch_dashboard eliminada - UI unificada en puerto 8000

def launch_server() -> None:
    """Lanza el servidor FastAPI (Uvicorn) en un proceso COMPLETAMENTE INDEPENDIENTE (detached)."""
    global server_process
    try:
        logger.info("🌐 Iniciando Cerebro Aethelgard & UI Next-Gen (detached)...")
        # Verificar si la UI está compilada
        ui_dist = os.path.join(os.getcwd(), "ui", "dist")
        if not os.path.exists(ui_dist):
            logger.warning("⚠️  UI Next-Gen no compilada. Ejecutando build rápido...")
            try:
                subprocess.run(["npm", "run", "build"], cwd=os.path.join(os.getcwd(), "ui"), shell=True, check=True)
                logger.info("✅ UI compilada correctamente.")
            except Exception as e:
                logger.error(f"❌ Falló la compilación de la UI: {e}. Se servirá solo la API.")

        # Ejecutar uvicorn como módulo en subproceso detached
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core_brain.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        logger.info("✅ Cerebro lanzado en proceso independiente")
        logger.info("🔗 Interfaz Principal: http://localhost:8000")
        logger.info("🔗 Documentación API: http://localhost:8000/docs")
        # NO esperar - continuar inmediatamente
        
    except Exception as e:
        logger.error(f"❌ Error al iniciar servidor API: {e}")

async def main() -> None:
    """
    Lanzador unificado de Aethelgard.
    Inicializa motor de trading + dashboard.
    """
    logger.info("=" * 70)
    logger.info("🚀 AETHELGARD TRADING SYSTEM - UNIFIED LAUNCHER")
    logger.info("=" * 70)
    
    # Crear directorios necesarios
    Path("logs").mkdir(exist_ok=True)
    Path("data_vault").mkdir(exist_ok=True)
    
    try:
        # === SISTEMA CORE ===
        logger.info("📦 Inicializando Storage Manager...")
        storage = StorageManager()
        
        logger.info("⚖️  Inicializando Risk Manager...")
        risk_manager = RiskManager(
            storage=storage,
            initial_capital=10000.0,
            config_path='config/dynamic_params.json'
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade: {risk_manager.risk_per_trade:.1%}")
        
        logger.info("📡 Inicializando Data Provider Manager (DB backend)...")
        provider_manager = DataProviderManager()
        data_provider = provider_manager
        
        # Símbolos a monitorear - FOREX MAJORS + MINORS + EXOTICS
        symbols = [
            # === MAJORS (6 pares - 85% del volumen forex) ===
            "EURUSD=X",  # Euro/USD
            "GBPUSD=X",  # Libra/USD
            "USDJPY=X",  # USD/Yen
            "AUDUSD=X",  # Dólar australiano/USD
            "USDCAD=X",  # USD/Dólar canadiense
            "USDCHF=X",  # USD/Franco suizo
            
            # === MINORS (6 pares - cruces sin USD) ===
            "EURGBP=X",  # Euro/Libra
            "EURJPY=X",  # Euro/Yen
            "GBPJPY=X",  # Libra/Yen
            "EURCHF=X",  # Euro/Franco suizo
            "EURAUD=X",  # Euro/Dólar australiano
            "GBPAUD=X",  # Libra/Dólar australiano
            
            # === COMMODITY CURRENCIES (4 pares) ===
            "NZDUSD=X",  # Dólar neozelandés/USD
            "AUDJPY=X",  # Dólar australiano/Yen
            "CADJPY=X",  # Dólar canadiense/Yen
            "NZDJPY=X",  # Dólar neozelandés/Yen
            
            # === EXOTICS (6 pares - alta volatilidad) ===
            "USDMXN=X",  # USD/Peso mexicano
            "USDZAR=X",  # USD/Rand sudafricano
            "USDTRY=X",  # USD/Lira turca
            "USDBRL=X",  # USD/Real brasileño
            "USDRUB=X",  # USD/Rublo ruso
            "USDCNH=X",  # USD/Yuan chino offshore
            
            # === SCANDINAVIAN (2 pares) ===
            "USDSEK=X",  # USD/Corona sueca
            "USDNOK=X",  # USD/Corona noruega
        ]
        logger.info(f"   Símbolos: {len(symbols)} pares forex")
        logger.info(f"   - Majors: 6 | Minors: 6 | Commodities: 4 | Exotics: 6 | Scandinavian: 2")
        
        # === FUNCIONES AUXILIARES EDGE ===
        async def run_edge_tuner_loop(edge_tuner: EdgeTuner) -> None:
            """
            Tarea asíncrona que ejecuta el EDGE Tuner cada hora.
            Ajusta parámetros basándose en resultados de trades.
            """
            tuner_logger = logging.getLogger(__name__)
            
            while True:
                try:
                    # Esperar 1 hora
                    await asyncio.sleep(3600)  # 3600 segundos = 1 hora
                    
                    tuner_logger.info("⏰ Ejecutando ajuste EDGE de parámetros...")
                    adjustment = edge_tuner.adjust_parameters()
                    
                    if adjustment and not adjustment.get("skipped_reason"):
                        tuner_logger.info(f"✅ Ajuste EDGE completado: {adjustment.get('trigger')}")
                        # Recargar parámetros en SignalFactory
                        signal_factory._load_parameters()
                        tuner_logger.info("🔄 Parámetros recargados en SignalFactory")
                    else:
                        reason = adjustment.get("skipped_reason") if adjustment else "unknown"
                        tuner_logger.info(f"⏸️ Sin ajustes: {reason}")
                        
                except Exception as e:
                    tuner_logger.error(f"❌ Error en EDGE Tuner: {e}", exc_info=True)
                    # Continuar ejecutándose a pesar del error
                    await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar
        
        # 4. Scanner Engine
        logger.info("🔍 Inicializando Scanner Engine...")
        scanner = ScannerEngine(
            assets=symbols,
            data_provider=data_provider,
            config_path='config/config.json',
            scan_mode="STANDARD"
        )
        
        # 5. Signal Factory
        logger.info("⚡ Inicializando Signal Factory...")
        signal_factory = SignalFactory(
            storage_manager=storage,
            strategy_id="oliver_velez_swing_v2"
        )
        
        # 6. Order Executor (carga cuentas habilitadas desde DB)
        logger.info("🎯 Inicializando Order Executor...")
        
        # Inyectar PaperConnector
        connectors = {ConnectorType.PAPER: PaperConnector()}
        
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors=connectors
        )
        
        # 7. Closing Monitor (Feedback Loop)
        logger.info("💰 Inicializando Closing Monitor...")
        monitor = ClosingMonitor(
            storage=storage,
            connectors=connectors,
            interval_seconds=60
        )
        logger.info("   Intervalo: 60 segundos | Estado: Activo")
        
        # 8. EDGE Tuner (Auto-calibración)
        logger.info("🤖 Inicializando EDGE Tuner...")
        edge_tuner = EdgeTuner(
            storage=storage,
            config_path="config/dynamic_params.json"
        )
        
        # 9. Main Orchestrator
        logger.info("🧠 Inicializando Main Orchestrator...")
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=signal_factory,
            risk_manager=risk_manager,
            executor=executor,
            storage=storage
        )
        
        # === INICIAR MT5 SINCRÓNICAMENTE (MT5 library doesn't share state across threads) ===
        logger.info("🔌 Conectando a MT5 (sincrónico en thread principal)...")
        mt5_connector = None
        if hasattr(executor, 'connectors') and ConnectorType.METATRADER5 in executor.connectors:
            mt5_connector = executor.connectors[ConnectorType.METATRADER5]
            # Connect synchronously in main thread (MT5 library is thread-specific)
            # This ensures mt5.initialize() happens in the SAME thread that will call execute_signal()
            connected = mt5_connector.connect_blocking()
            if connected:
                logger.info(f"✅ MT5 conectado exitosamente. Símbolos disponibles: {len(mt5_connector.available_symbols)}")
            else:
                logger.error("❌ MT5 connection failed!")
            
            # Set MT5 connector in SignalFactory for reconciliation
            signal_factory.set_mt5_connector(mt5_connector)
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("✅ SISTEMA COMPLETO INICIADO")
        logger.info("=" * 70)
        logger.info("")
        
        # Iniciar Servidor API en hilo separado
        server_thread = threading.Thread(target=launch_server,daemon=True)
        server_thread.start()
        
        # MODULE TOGGLE: Verificar si scanner está habilitado antes de iniciar
        modules_enabled = storage.get_global_modules_enabled()
        
        if modules_enabled.get("scanner", True):
            # Iniciar Scanner en hilo separado
            logger.info("🔄 Iniciando Scanner...")
            scanner_thread = threading.Thread(target=scanner.run, daemon=True)
            scanner_thread.start()
            logger.info("✅ Scanner ejecutándose")
        else:
            logger.warning("⚠️  Scanner DESHABILITADO globalmente - thread NO iniciado")
        
        # Iniciar Closing Monitor en tarea asíncrona
        logger.info("🔄 Iniciando Closing Monitor...")
        monitor_task = asyncio.create_task(monitor.start())
        logger.info("✅ Closing Monitor activo (Feedback Loop)")
        
        # Iniciar EDGE Monitor (inject MT5 connector recomendation to avoid creating new instance)
        logger.info("🔄 Iniciando EDGE Monitor...")
        edge_monitor = EdgeMonitor(storage=storage, mt5_connector=mt5_connector)
        edge_monitor.start()
        logger.info("✅ EDGE Monitor activo (Observabilidad Autónoma)")
        
        logger.info("")
        logger.info("   -> [PRINCIPAL] Command Center Next-Gen: http://localhost:8000")
        logger.info("")
        logger.info("🛑 Presiona Ctrl+C para detener todo el ecosistema")
        
        # Crear tarea asíncrona del EDGE Tuner
        tuner_task = asyncio.create_task(run_edge_tuner_loop(edge_tuner))
        logger.info("🤖 EDGE Tuner: ajustes automáticos cada 1 hora")
        
        # Ejecutar loop principal
        await orchestrator.run()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Deteniendo sistema...")
        scanner.stop()
        if 'monitor' in locals():
            await monitor.stop()
        # Cleanup
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)
        raise
    finally:
        if server_process and server_process.poll() is None:
            server_process.terminate()
        logger.info("💾 Sistema detenido completamente.")


if __name__ == "__main__":
    asyncio.run(main())
