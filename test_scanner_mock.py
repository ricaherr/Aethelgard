"""
Test del Escáner con DataProvider mock (sin MT5).
Ejecutar: python test_scanner_mock.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core_brain.scanner import ScannerEngine, CPUMonitor, _load_config


class MockDataProvider:
    """Devuelve OHLC sintético para pruebas."""

    def fetch_ohlc(self, symbol: str, timeframe: str = "M5", count: int = 500):
        t = np.arange(count)[::-1].astype(float) * 300  # 5min entre velas
        base = 100.0 if "USD" in symbol or "EUR" in symbol else 150.0
        close = base + np.cumsum(np.random.randn(count) * 0.1)
        high = close + np.abs(np.random.randn(count) * 0.05)
        low = close - np.abs(np.random.randn(count) * 0.05)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        return pd.DataFrame({
            "time": t.astype(int),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        })


def main():
    cfg = _load_config("config/config.json")
    sc = cfg.get("scanner", {})
    assets = sc.get("assets", ["EURUSD", "AAPL"])[:2]

    provider = MockDataProvider()
    engine = ScannerEngine(assets=assets, data_provider=provider, config_path="config/config.json")

    # Un ciclo
    engine._run_cycle()
    st = engine.get_status()
    print("Status:", st)
    assert "last_regime" in st
    assert all(s in st["last_regime"] for s in assets)
    print("OK: escáner con mock funciona.")


if __name__ == "__main__":
    main()
