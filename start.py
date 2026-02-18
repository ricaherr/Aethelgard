"""
Aethelgard Trading System - Unified Launcher
=============================================

Comando único que inicia:
1. Servidor API (FastAPI/Uvicorn) - Backend + React UI
2. Motor de trading (Scanner + Orchestrator) - Lógica de negocio
3. EDGE Tuner - Auto-calibración

USO: python start.py
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
from datetime import datetime
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
from connectors.mt5_connector import MT5Connector
from models.signal import ConnectorType

# Core Brain Imports
from core_brain.data_provider_manager import DataProviderManager
from connectors.generic_data_provider import GenericDataProvider
from core_brain.notificator import get_notifier
from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
from core_brain.coherence_monitor import CoherenceMonitor
from core_brain.signal_expiration_manager import SignalExpirationManager
from core_brain.regime import RegimeClassifier
from core_brain.trade_closure_listener import TradeClosureListener
from core_brain.position_manager import PositionManager

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
        logger.info("[INFO] Iniciando Cerebro Aethelgard & UI Next-Gen (detached)...")
        # Verificar si la UI está compilada
        ui_dist = os.path.join(os.getcwd(), "ui", "dist")
        if not os.path.exists(ui_dist):
            logger.warning("[WARNING]  UI Next-Gen no compilada. Ejecutando build rápido...")
            try:
                subprocess.run(["npm", "run", "build"], cwd=os.path.join(os.getcwd(), "ui"), shell=True, check=True)
                logger.info("[OK] UI compilada correctamente.")
            except Exception as e:
                logger.error(f"[ERROR] Falló la compilación de la UI: {e}. Se servirá solo la API.")

        # Ejecutar uvicorn como módulo en subproceso detached
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core_brain.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        logger.info("[OK] Cerebro lanzado en proceso independiente")
        logger.info("[LINK] Interfaz Principal: http://localhost:8000")
        logger.info("[LINK] Documentación API: http://localhost:8000/docs")
        # NO esperar - continuar inmediatamente
        
    except Exception as e:
        logger.error(f"[ERROR] Error al iniciar servidor API: {e}")

async def main() -> None:
    """
    Lanzador unificado de Aethelgard.
    Inicializa motor de trading + dashboard.
    """
    logger.info("=" * 70)
    logger.info("[START] AETHELGARD TRADING SYSTEM - UNIFIED LAUNCHER")
    logger.info("=" * 70)
    
    # Crear directorios necesarios
    Path("logs").mkdir(exist_ok=True)
    Path("data_vault").mkdir(exist_ok=True)
    
    try:
        # 1. Storage Manager (SSOT - Regla 14)
        logger.info("[INIT] Inicializando Storage Manager...")
        storage = StorageManager()
        
        # 1.5. Configuración SSOT (Regla 14) 
        # Cargar configuraciones (StorageManager ya manejó la migración inicial en su __init__)
        system_state = storage.get_system_state()
        global_config = system_state.get("global_config", {})
        dynamic_params = storage.get_dynamic_params()

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
        async def run_edge_tuner_loop(edge_tuner: EdgeTuner, signal_factory: SignalFactory) -> None:
            """
            Tarea asíncrona que ejecuta el EDGE Tuner cada hora.
            Ajusta parámetros basándose en resultados de trades.
            """
            tuner_logger = logging.getLogger(__name__)
            
            while True:
                try:
                    # Esperar 1 hora
                    await asyncio.sleep(3600)  # 3600 segundos = 1 hora
                    
                    tuner_logger.info("[EDGE] Ejecutando ajuste EDGE de parámetros...")
                    adjustment = edge_tuner.adjust_parameters()
                    
                    if adjustment and not adjustment.get("skipped_reason"):
                        tuner_logger.info(f"[OK] Ajuste EDGE completado: {adjustment.get('trigger')}")
                        # En el nuevo SignalFactory (DI), los parámetros se cargan vía StorageManager
                        # pero si la estrategia es inyectada, puede que necesitemos avisar.
                        # El factory tiene su propio _load_parameters.
                        signal_factory._load_parameters()
                        tuner_logger.info("[INFO] Parámetros recargados en SignalFactory")
                    else:
                        reason = adjustment.get("skipped_reason") if adjustment else "unknown"
                        tuner_logger.info(f"[INFO] Sin ajustes: {reason}")
                        
                except Exception as e:
                    tuner_logger.error(f"[ERROR] Error en EDGE Tuner: {e}", exc_info=True)
                    # Continuar ejecutándose a pesar del error
                    await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar

        # 2. Risk Manager (Regla 1 - DI)
        logger.info("[INIT]  Inicializando Risk Manager...")
        from core_brain.position_size_monitor import PositionSizeMonitor
        risk_monitor = PositionSizeMonitor(
            max_consecutive_failures=3,
            circuit_breaker_timeout=300
        )
        
        risk_manager = RiskManager(
            storage=storage,
            initial_capital=10000.0, # TODO: Leer de la DB o inyectar
            monitor=risk_monitor
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade (SST): {risk_manager.risk_per_trade:.1%}")
        
        # 3. Data Provider & Scanner (Regla 2 - Agnóstico)
        logger.info("[INIT] Inicializando Data Provider Manager (DI)...")
        provider_manager = DataProviderManager(storage=storage)
        
        logger.info("[INIT] Inicializando Scanner Engine...")
        scanner = ScannerEngine(
            assets=symbols,
            data_provider=provider_manager,
            config_data=global_config, # Inyectar desde DB (SSOT)
            scan_mode="STANDARD",
            storage=storage
        )
        
        # 4. Connectors (Regla 3 - Agnóstico)
        logger.info("[INIT] Inicializando MT5 Connector (DI)...")
        mt5_connector = MT5Connector(storage=storage)
        
        # 5. Signal Factory - FASE DI (Regla 1)
        logger.info("[INIT] Inicializando Signal Factory (DI)...")
        from core_brain.strategies.oliver_velez import OliverVelezStrategy
        from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        
        ov_strategy = OliverVelezStrategy(dynamic_params)
        
        confluence_config = dynamic_params.get("confluence", {})
        confluence_analyzer = MultiTimeframeConfluenceAnalyzer(
            storage=storage,
            enabled=confluence_config.get("enabled", True)
        )
        
        trifecta_analyzer = TrifectaAnalyzer(
            storage=storage,
            config_data=global_config, # Inyectar desde DB (SSOT)
            auto_enable_tfs=True
        )
        
        signal_factory = SignalFactory(
            storage_manager=storage,
            strategies=[ov_strategy],
            confluence_analyzer=confluence_analyzer,
            trifecta_analyzer=trifecta_analyzer,
            mt5_connector=mt5_connector
        )
        
        # 6. Order Executor - FASE DI (Regla 1)
        logger.info("[INIT] Inicializando Order Executor (DI)...")
        
        multi_tf_limiter = MultiTimeframeLimiter(
            storage=storage,
            config=dynamic_params,
            mt5_connector=mt5_connector
        )
        
        order_executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            multi_tf_limiter=multi_tf_limiter,
            notificator=get_notifier(),
            connectors={ConnectorType.METATRADER5: mt5_connector}
        )
        
        # 7. Orchestrator Components - FASE DI (Regla 1)
        logger.info("[INIT] Inicializando Componentes del Orquestador...")
        
        coherence_monitor = CoherenceMonitor(storage=storage)
        expiration_manager = SignalExpirationManager(storage=storage)
        regime_classifier = RegimeClassifier()
        
        edge_tuner = EdgeTuner(storage=storage) 
        
        trade_closure_listener = TradeClosureListener(
            storage=storage,
            risk_manager=risk_manager,
            edge_tuner=edge_tuner
        )
        
        position_manager = PositionManager(
            storage=storage,
            connector=mt5_connector,
            regime_classifier=regime_classifier,
            config=dynamic_params.get("position_management", {})
        )
        
        # 8. Main Orchestrator (Unified DI)
        logger.info("[INIT] Inicializando Main Orchestrator (DI/SSOT)...")
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=signal_factory,
            risk_manager=risk_manager,
            executor=order_executor,
            storage=storage,
            position_manager=position_manager,
            trade_closure_listener=trade_closure_listener,
            coherence_monitor=coherence_monitor,
            expiration_manager=expiration_manager,
            regime_classifier=regime_classifier
        )
        
        # === INICIAR MT5 SINCRÓNICAMENTE (MT5 library doesn't share state across threads) ===
        logger.info("[CONNECT] Conectando a MT5 (sincrónico en thread principal)...")
        if mt5_connector:
            # Connect synchronously in main thread (MT5 library is thread-specific)
            # This ensures mt5.initialize() happens in the SAME thread that will call execute_signal()
            connected = mt5_connector.connect_blocking()
            if connected:
                logger.info(f"[OK] MT5 conectado exitosamente. Símbolos disponibles: {len(mt5_connector.available_symbols)}")
                
                # Cache account balance in system_state for API queries
                try:
                    account_balance = mt5_connector.get_account_balance()
                    storage.update_system_state({
                        "account_balance": account_balance,
                        "balance_source": "MT5_LIVE",
                        "balance_last_update": datetime.now().isoformat()
                    })
                    logger.info(f"   Balance cacheado: ${account_balance:,.2f} (MT5_LIVE)")
                except Exception as e:
                    logger.warning(f"[WARNING]  No se pudo cachear balance de MT5: {e}")
            else:
                logger.error("[ERROR] MT5 connection failed!")
            
            # Set MT5 connector in SignalFactory for reconciliation
            signal_factory.set_mt5_connector(mt5_connector)
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("[OK] SISTEMA COMPLETO INICIADO")
        logger.info("=" * 70)
        logger.info("")
        
        # Iniciar Servidor API en hilo separado
        server_thread = threading.Thread(target=launch_server,daemon=True)
        server_thread.start()
        
        # Scanner thread: SIEMPRE arranca (verifica toggle internamente con hot-reload)
        logger.info("[INFO] Iniciando Scanner (con hot-reload toggle)...")
        scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        scanner_thread.start()
        
        modules_enabled = storage.get_global_modules_enabled()
        if modules_enabled.get("scanner", True):
            logger.info("[OK] Scanner ejecutándose (habilitado)")
        else:
            logger.warning("[WARNING]  Scanner en espera (deshabilitado - activar desde UI para iniciar)")
        
        # Iniciar Closing Monitor en tarea asíncrona
        logger.info("[INFO] Inicializando Closing Monitor...")
        closing_monitor = ClosingMonitor(
            storage=storage,
            connectors={ConnectorType.METATRADER5: mt5_connector},
            interval_seconds=60
        )
        monitor_task = asyncio.create_task(closing_monitor.start())
        logger.info("[OK] Closing Monitor activo (Feedback Loop)")
        
        # Iniciar EDGE Monitor (inject MT5 connector & trade listener for reconciliation)
        logger.info("[INFO] Iniciando EDGE Monitor...")
        edge_monitor = EdgeMonitor(
            storage=storage,
            mt5_connector=mt5_connector,
            trade_listener=trade_closure_listener
        )
        edge_monitor.start()
        logger.info("[OK] EDGE Monitor activo (Observabilidad + Reconciliación Automática)")
        
        logger.info("")
        logger.info("   -> [PRINCIPAL] Command Center Next-Gen: http://localhost:8000")
        logger.info("")
        logger.info("[STOP] Presiona Ctrl+C para detener todo el ecosistema")
        
        # Crear tarea asíncrona del EDGE Tuner
        tuner_task = asyncio.create_task(run_edge_tuner_loop(edge_tuner, signal_factory))
        logger.info("[AUTO] EDGE Tuner: ajustes automáticos cada 1 hora")
        
        # Ejecutar loop principal
        await orchestrator.run()
        
    except KeyboardInterrupt:
        logger.info("\n[STOP]  Deteniendo sistema...")
        scanner.stop()
        if 'closing_monitor' in locals():
            await closing_monitor.stop()
        # Cleanup
    except Exception as e:
        logger.error(f"[FATAL] Error crítico: {e}", exc_info=True)
        raise
    finally:
        if server_process and server_process.poll() is None:
            server_process.terminate()
        logger.info("[STOP] Sistema detenido completamente.")


if __name__ == "__main__":
    asyncio.run(main())
