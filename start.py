"""
Aethelgard Trading System - Unified Launcher
=============================================

Comando único que inicia:
1. Motor de trading (scanner + orchestrator)
2. Dashboard Streamlit (UI)
3. Todo en procesos paralelos

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

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.scanner import ScannerEngine
from core_brain.signal_factory import SignalFactory
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from core_brain.tuner import EdgeTuner
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

# Variable global para el proceso de Streamlit
streamlit_process = None


def launch_dashboard():
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
        time.sleep(3)
        
        if streamlit_process.poll() is None:
            logger.info("✅ Dashboard disponible en: http://localhost:8503")
        else:
            logger.warning("⚠️  Dashboard no pudo iniciarse correctamente")
            
    except Exception as e:
        logger.error(f"❌ Error al iniciar dashboard: {e}")


async def main():
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
        
        # 3. Data Provider (Yahoo Finance)
        logger.info("📡 Inicializando Data Provider (Yahoo Finance)...")
        data_provider = GenericDataProvider()
        
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
        async def run_edge_tuner_loop(edge_tuner: EdgeTuner):
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
        
        # 6. Order Executor
        logger.info("🎯 Inicializando Order Executor...")
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors={}  # Paper trading
        )
        
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
        
        # Iniciar Dashboard en hilo separado
        dashboard_thread = threading.Thread(target=launch_dashboard, daemon=True)
        dashboard_thread.start()
        
        # Iniciar Scanner en hilo separado
        logger.info("🔄 Iniciando Scanner...")
        scanner_thread = threading.Thread(target=scanner.run, daemon=True)
        scanner_thread.start()
        logger.info("✅ Scanner ejecutándose")
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
        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
            logger.info("✅ Dashboard detenido")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}", exc_info=True)
        raise
    finally:
        if streamlit_process and streamlit_process.poll() is None:
            streamlit_process.terminate()
        logger.info("💾 Sistema detenido completamente.")


if __name__ == "__main__":
    asyncio.run(main())
