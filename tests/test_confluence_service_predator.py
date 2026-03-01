from typing import Any

import pandas as pd

from core_brain.services.confluence_service import ConfluenceService


class _StorageStub:
    def get_dynamic_params(self) -> dict:
        return {}


class _ConnectorStub:
    def __init__(self, symbol_data: dict[str, pd.DataFrame]):
        self.symbol_data = symbol_data

    def fetch_ohlc(self, symbol: str, timeframe: str = "M5", count: int = 80) -> pd.DataFrame:
        data = self.symbol_data.get(symbol, pd.DataFrame())
        if data.empty:
            return data
        return data.tail(count)


def _build_eurusd_stagnation_df() -> pd.DataFrame:
    rows = []
    base = 1.0800
    for i in range(36):
        if i < 24:
            high = base + (0.0008 if i % 2 == 0 else 0.0006)
            low = base - (0.0008 if i % 3 == 0 else 0.0006)
            close = base + (0.0002 if i % 2 == 0 else -0.0001)
        else:
            # Recent section = tighter/stagnant
            high = base + 0.00035
            low = base - 0.00035
            close = base + (0.00003 if i % 2 == 0 else -0.00002)
        rows.append({"open": base, "high": high, "low": low, "close": close, "volume": 1000})
    return pd.DataFrame(rows)


def _build_dxy_liquidity_sweep_df() -> pd.DataFrame:
    rows = []
    base = 104.0
    for i in range(36):
        if i < 24:
            high = base + 0.10 + (0.02 if i % 2 == 0 else 0.01)
            low = base - 0.08
            close = base + 0.03
        else:
            # Recent section sweeps prior highs
            high = base + 0.35 + (0.03 if i % 2 == 0 else 0.01)
            low = base - 0.05
            close = base + 0.12
        rows.append({"open": base, "high": high, "low": low, "close": close, "volume": 1500})
    return pd.DataFrame(rows)


def test_detect_predator_divergence_dxy_sweep_vs_eurusd_stagnation() -> None:
    service = ConfluenceService(storage=_StorageStub())  # type: ignore[arg-type]
    eurusd_df = _build_eurusd_stagnation_df()
    dxy_df = _build_dxy_liquidity_sweep_df()

    result = service.detect_predator_divergence(eurusd_df, dxy_df, inverse=True)

    assert result["detected"] is True
    assert result["signal_bias"] == "BUY"
    assert result["strength"] >= 55.0


def test_validate_confluence_vetoes_sell_when_predator_bias_is_buy() -> None:
    service = ConfluenceService(storage=_StorageStub())  # type: ignore[arg-type]
    eurusd_df = _build_eurusd_stagnation_df()
    dxy_df = _build_dxy_liquidity_sweep_df()
    connector = _ConnectorStub({"EURUSD": eurusd_df, "DXY": dxy_df})

    is_confirmed, reason, penalty = service.validate_confluence(
        symbol="EURUSD",
        side="SELL",
        connector=connector,
        timeframe="M5",
    )

    assert is_confirmed is False
    assert "PREDATOR_VETO" in reason
    assert penalty > 0
