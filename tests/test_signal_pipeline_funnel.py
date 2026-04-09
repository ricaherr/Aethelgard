import pytest
import pandas as pd
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core_brain.signal_factory import SignalFactory
from core_brain.api.routers.telemetry import _get_signal_funnel_summary
from data_vault.storage import StorageManager
from models.signal import MarketRegime


class SilentStrategy:
    async def analyze(self, symbol, df, regime):
        return None


@pytest.mark.asyncio
async def test_funnel_counts_raw_zero_with_reasons() -> None:
    storage = StorageManager(db_path=":memory:")
    confluence = SimpleNamespace(enabled=False)
    trifecta = MagicMock()

    with patch("core_brain.signal_factory.get_notifier", return_value=MagicMock()):
        factory = SignalFactory(
            storage_manager=storage,
            strategy_engines={"silent": SilentStrategy()},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            instrument_manager=None,
        )

    df = pd.DataFrame(
        {
            "open": [1.0, 1.01, 1.02],
            "high": [1.01, 1.02, 1.03],
            "low": [0.99, 1.0, 1.01],
            "close": [1.005, 1.015, 1.025],
        }
    )

    scan_results = {
        "EURUSD|M5": {"symbol": "EURUSD", "timeframe": "M5", "regime": MarketRegime.TREND, "df": df},
        "XAUUSD|M5": {"symbol": "XAUUSD", "timeframe": "M5", "regime": None, "df": df},
        "GBPUSD|M5": {"symbol": "GBPUSD", "timeframe": "M5", "regime": MarketRegime.RANGE, "df": None},
    }

    signals = await factory.generate_usr_signals_batch(scan_results, trace_id="TRACE-RAW-0")

    assert signals == []
    summary = getattr(factory, "last_funnel_summary", None)
    assert summary is not None
    assert summary["stages"]["STAGE_SCAN_INPUT"]["in"] == 3
    assert summary["stages"]["STAGE_RAW_SIGNAL_GENERATION"]["out"] == 0
    assert summary["reasons"].get("regime_missing", 0) >= 1
    assert summary["reasons"].get("df_missing", 0) >= 1


@pytest.mark.asyncio
async def test_funnel_summary_visible_in_telemetry() -> None:
    storage = StorageManager(db_path=":memory:")
    storage.update_sys_config(
        {
            "session_stats": {
                "signal_funnel_recent": [
                    {
                        "trace_id": "TRACE-TELEM-01",
                        "stages": {
                            "STAGE_SCAN_INPUT": {"in": 4, "out": 4},
                            "STAGE_RAW_SIGNAL_GENERATION": {"in": 4, "out": 1},
                        },
                        "reasons": {"no_signal_generated": 3},
                    }
                ],
                "signal_funnel_last_cycle": {
                    "trace_id": "TRACE-TELEM-01",
                    "stages": {
                        "STAGE_SCAN_INPUT": {"in": 4, "out": 4},
                        "STAGE_RAW_SIGNAL_GENERATION": {"in": 4, "out": 1},
                    },
                    "reasons": {"no_signal_generated": 3},
                },
            }
        }
    )

    summary = await _get_signal_funnel_summary(storage)

    assert summary["last_cycle"]["trace_id"] == "TRACE-TELEM-01"
    assert summary["recent_count"] == 1
    assert summary["reason_totals"]["no_signal_generated"] == 3
