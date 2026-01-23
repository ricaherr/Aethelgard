"""
Entrypoint del Escáner Proactivo Multihilo.
Carga activos desde config/config.json, usa MT5DataProvider para datos autónomos
(mt5.copy_rates_from_pos) y ejecuta el ScannerEngine.
"""
from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

# Asegurar que el proyecto está en el path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core_brain.scanner import ScannerEngine, _load_config
from connectors.mt5_data_provider import MT5DataProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = _load_config("config/config.json")
    sc = cfg.get("scanner", {})
    assets = list(sc.get("assets", ["AAPL", "TSLA", "MES", "EURUSD"]))

    provider = MT5DataProvider(init_mt5=True)
    if not provider.is_available():
        logger.error("MT5 no disponible. Comprueba que MetaTrader 5 esté instalado y en ejecución.")
        sys.exit(1)

    engine = ScannerEngine(assets=assets, data_provider=provider, config_path="config/config.json")

    def shutdown(*_):  # type: ignore
        logger.info("Deteniendo escáner...")
        engine.stop()
        provider.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        engine.run()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
