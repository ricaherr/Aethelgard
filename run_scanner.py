"""
Entrypoint del Escáner Proactivo Multihilo.
Sistema 100% autónomo que usa GenericDataProvider (Yahoo Finance) por defecto.
No requiere MT5 ni software externo, solo pip install yfinance.

Uso:
    python run_scanner.py                    # Usa GenericDataProvider (autónomo)
    python run_scanner.py --provider mt5     # Usa MT5DataProvider (requiere MT5)
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

# Asegurar que el proyecto está en el path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core_brain.scanner import ScannerEngine, _load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # Parsear argumentos
    parser = argparse.ArgumentParser(description="Aethelgard Scanner Proactivo")
    parser.add_argument(
        "--provider",
        choices=["generic", "mt5"],
        default="generic",
        help="Data provider a usar: 'generic' (Yahoo Finance, autónomo) o 'mt5' (requiere MT5)"
    )
    args = parser.parse_args()
    
    cfg = _load_config("config/config.json")
    sc = cfg.get("scanner", {})
    assets = list(sc.get("assets", ["AAPL", "TSLA", "EURUSD", "GOLD"]))

    # Seleccionar provider
    if args.provider == "mt5":
        logger.info("Usando MT5DataProvider (requiere MetaTrader 5 instalado)")
        from connectors.mt5_data_provider import MT5DataProvider
        provider = MT5DataProvider(init_mt5=True)
        if not provider.is_available():
            logger.error("MT5 no disponible. Usa --provider generic o instala MT5.")
            sys.exit(1)
    else:
        logger.info("🌐 Usando GenericDataProvider (Yahoo Finance - 100% autónomo)")
        from connectors.generic_data_provider import GenericDataProvider
        provider = GenericDataProvider()

    engine = ScannerEngine(assets=assets, data_provider=provider, config_path="config/config.json")

    def shutdown(*_):  # type: ignore
        logger.info("Deteniendo escáner...")
        engine.stop()
        if hasattr(provider, 'shutdown'):
            provider.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        logger.info(f"🚀 Scanner iniciado con {len(assets)} activos: {', '.join(assets)}")
        logger.info("Presiona Ctrl+C para detener")
        engine.run()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
