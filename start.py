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
import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
import sys
import os
import webbrowser

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from core_brain.monitor import ClosingMonitor
from core_brain.tuner import EdgeTuner
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

# Variable global para el proceso de Streamlit
streamlit_process = None
server_process = None


def launch_dashboard() -> None:
    """Lanza el dashboard de Streamlit en un proceso separado."""
    global streamlit_process
    try:
        logger.info("📊 Iniciando Dashboard Streamlit...")
        
        # Ejecutar streamlit en proceso separado
        streamlit_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "ui/dashboard.py", 
             "--server.port", "8503",
             "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        # Esperar a que Streamlit esté listo
        time.sleep(10)
        
        if streamlit_process.poll() is None:
            logger.info("✅ Dashboard disponible en: http://localhost:8503")
            # Abrir navegador automáticamente
            threading.Timer(1.0, lambda: webbrowser.open('http://localhost:8503')).start()
        else:
            # Si el proceso terminó, capturar error
            stderr = None
            if streamlit_process.stderr:
                stderr = streamlit_process.stderr.read().decode()
            logger.warning(f"⚠️  Dashboard no pudo iniciarse correctamente: {stderr if stderr else 'Sin información de error disponible.'}")
            
    except Exception as e:
        logger.error(f"❌ Error al iniciar dashboard: {e}")

def launch_server() -> None:
    """Lanza el servidor FastAPI (Uvicorn) en un proceso separado."""
    global server_process
    try:
        logger.info("🌐 Iniciando Servidor API (Cerebro)...")
        # Ejecutar uvicorn como módulo en subproceso
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core_brain.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
            cwd=os.getcwd()
        )
        time.sleep(2) # Dar tiempo para arrancar
        if server_process.poll() is None:
            logger.info("✅ Servidor API activo en: http://localhost:8000")
        else:
            logger.warning("⚠️  El servidor API no pudo iniciarse.")
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
        # EDGE: Validar y provisionar cuentas demo maestras solo si es óptimo
        # Inicializar componentes core
        # 1. Storage Manager
        logger.info("📦 Inicializando Storage Manager...")
        storage = StorageManager()
        # 2. Risk Manager
        logger.info("⚖️  Inicializando Risk Manager...")
        risk_manager = RiskManager(
            initial_capital=10000.0,
            config_path='config/dynamic_params.json'
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade: {risk_manager.risk_per_trade:.1%}")
        # 3. Data Provider Manager (DB Backend)
        logger.info("📡 Inicializando Data Provider Manager (DB backend)...")
        provider_manager = DataProviderManager()
        data_provider = provider_manager
        # Símbolos a monitorear
        symbols = [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X",
            "EURGBP=X", "EURJPY=X", "GBPJPY=X", "EURCHF=X", "EURAUD=X", "GBPAUD=X",
            "NZDUSD=X", "AUDJPY=X", "CADJPY=X"
        ]
        orchestrator = None
        try:
            from core_brain.main_orchestrator import MainOrchestrator
            scanner = ScannerEngine(assets=symbols, data_provider=data_provider)
            signal_factory = SignalFactory(storage_manager=storage)
            executor = OrderExecutor(risk_manager=risk_manager, storage=storage)
            orchestrator = MainOrchestrator(
                scanner=scanner,
                signal_factory=signal_factory,
                risk_manager=risk_manager,
                executor=executor,
                storage=storage
            )
            # Validar y provisionar cuentas demo EDGE solo si es óptimo
            await orchestrator.ensure_optimal_demo_accounts()
        except Exception as e:
            logger.error(f"Error inicializando orquestador o provisión EDGE: {e}")
        logger.info("📦 Inicializando Storage Manager...")
        storage = StorageManager()
        
        # 2. Risk Manager
        logger.info("⚖️  Inicializando Risk Manager...")
        risk_manager = RiskManager(
            initial_capital=10000.0,
            config_path='config/dynamic_params.json'
        )
        logger.info(f"   Capital: ${risk_manager.capital:,.2f}")
        logger.info(f"   Riesgo por trade: {risk_manager.risk_per_trade:.1%}")
        
        # 3. Data Provider Manager (DB Backend)
        logger.info("📡 Inicializando Data Provider Manager (DB backend)...")
        provider_manager = DataProviderManager()
        # Inyectar el manager como provider (implementa el mismo protocolo fetch_ohlc)
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
        
        # Cargar cuentas de brokers habilitadas desde la base de datos
        enabled_accounts = storage.get_broker_accounts(enabled_only=True)
        connectors = {}
        
        if enabled_accounts:
            logger.info(f"   Cargando {len(enabled_accounts)} cuenta(s) habilitada(s)...")
            for account in enabled_accounts:
                broker_name = account['broker_id']
                platform = account['platform_id']
                acc_type = account['account_type']
                
                logger.info(f"      {broker_name} ({platform}) - {acc_type}")
                
                # TODO: Instanciar conectores según platform_id
                # Por ahora, solo paper trading hasta implementar conectores completos
            
            logger.info("   ⚠️  Conectores en desarrollo - usando Paper Trading temporalmente")
        else:
            logger.info("   Sin cuentas configuradas - usando Paper Trading")
            logger.info("   💡 Configura cuentas en: Dashboard → Configuración de Brokers")
        
        # Inyectar PaperConnector
        connectors[ConnectorType.PAPER] = PaperConnector()
        
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors=connectors  # Por ahora vacío, se implementará con conectores
        )
        
        # 7. Closing Monitor (Feedback Loop)
        logger.info("💰 Inicializando Closing Monitor...")
        monitor = ClosingMonitor(
            storage=storage,
            connectors=connectors,
            interval_seconds=60
        )
        logger.info("   Intervalo: 60 segundos | Estado: Activo")
        
        # 7. EDGE Tuner (Auto-calibración)
        logger.info("🤖 Inicializando EDGE Tuner...")
        edge_tuner = EdgeTuner(
            storage=storage,
            config_path="config/dynamic_params.json"
        )
        
        # 8. Main Orchestrator
        logger.info("🧠 Inicializando Main Orchestrator...")
        orchestrator = MainOrchestrator(
            scanner=scanner,
            signal_factory=signal_factory,
            risk_manager=risk_manager,
            executor=executor,
            storage=storage
        )
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("✅ SISTEMA COMPLETO INICIADO")
        logger.info("=" * 70)
        logger.info("")
        
        # Iniciar Servidor API en hilo separado (lanza subproceso)
        server_thread = threading.Thread(target=launch_server, daemon=True)
        server_thread.start()
        
        # Iniciar Dashboard en hilo separado
        dashboard_thread = threading.Thread(target=launch_dashboard, daemon=True)
        dashboard_thread.start()
        
        # Iniciar Scanner en hilo separado
        logger.info("🔄 Iniciando Scanner...")
        scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        scanner_thread.start()
        logger.info("✅ Scanner ejecutándose")
        logger.info("")
        
        # Iniciar Closing Monitor en tarea asíncrona
        logger.info("🔄 Iniciando Closing Monitor...")
        monitor_task = asyncio.create_task(monitor.start())
        logger.info("✅ Closing Monitor activo (Feedback Loop)")
        logger.info("")
        
        # Esperar a que dashboard esté listo
        time.sleep(2)
        
        logger.info("🌐 Dashboard: http://localhost:8503")
        logger.info("🛑 Presiona Ctrl+C para detener")
        logger.info("")
        
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
        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
            logger.info("✅ Dashboard detenido")
        if server_process and server_process.poll() is None:
            server_process.terminate()
            logger.info("✅ Servidor API detenido")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)
        raise
    finally:
        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
        if server_process and server_process.poll() is None:
            server_process.terminate()
        logger.info("💾 Sistema detenido completamente.")


if __name__ == "__main__":
    asyncio.run(main())
