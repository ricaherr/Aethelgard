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


class AffinityRejectStrategy:
    """Simulates a strategy that rejects due to affinity threshold (SSOT-legit filter)."""
    last_rejection_reason = "affinity_below_threshold"

    async def analyze(self, symbol, df, regime):
        return None


class EngineErrorStrategy:
    """Simulates a strategy whose engine raises an unhandled exception."""

    async def analyze(self, symbol, df, regime):
        raise RuntimeError("db_connection_failed")


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


# ── HU 5.5: Tests focales ETI-HU5.5-RUNTIME-FUNNEL-SSOT-2026-04-14 ──────────


@pytest.mark.asyncio
async def test_funnel_reason_codes_are_emitted_for_raw_stage() -> None:
    """
    TDD HU5.5: Cuando una estrategia retorna None con last_rejection_reason explícito,
    ese código debe aparecer en funnel_summary.reasons con count >= 1.
    """
    storage = StorageManager(db_path=":memory:")
    confluence = SimpleNamespace(enabled=False)
    trifecta = MagicMock()

    with patch("core_brain.signal_factory.get_notifier", return_value=MagicMock()):
        factory = SignalFactory(
            storage_manager=storage,
            strategy_engines={"affinity_strat": AffinityRejectStrategy()},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            instrument_manager=None,
        )

    df = pd.DataFrame(
        {"open": [1.0], "high": [1.01], "low": [0.99], "close": [1.005]}
    )
    scan_results = {
        "EURUSD|M5": {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "regime": MarketRegime.TREND,
            "df": df,
        }
    }

    signals = await factory.generate_usr_signals_batch(scan_results, trace_id="TRACE-HU55-RAW")

    assert signals == []
    summary = factory.last_funnel_summary
    assert summary is not None
    assert summary["stages"]["STAGE_RAW_SIGNAL_GENERATION"]["in"] >= 1
    assert summary["stages"]["STAGE_RAW_SIGNAL_GENERATION"]["out"] == 0
    assert summary["reasons"].get("affinity_below_threshold", 0) >= 1


@pytest.mark.asyncio
async def test_funnel_distinguishes_legit_ssot_filters_from_infra_failures() -> None:
    """
    TDD HU5.5: El funnel debe distinguir bloqueo legítimo SSOT de falla de infraestructura.

    - infra_skip_reason presente → raw_zero_cause_category == "INFRA"
    - reasons solo con códigos SSOT-legítimos → raw_zero_cause_category == "LEGIT_SSOT"
    - reasons con código de error de infra (strategy_engine_error) → "INFRA_FAILURE"
    """
    storage = StorageManager(db_path=":memory:")
    confluence = SimpleNamespace(enabled=False)
    trifecta = MagicMock()

    # ── Case 1: infra_skip_reason → INFRA ─────────────────────────────────────
    with patch("core_brain.signal_factory.get_notifier", return_value=MagicMock()):
        factory_infra = SignalFactory(
            storage_manager=storage,
            strategy_engines={"s": SilentStrategy()},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            instrument_manager=None,
        )

    await factory_infra.generate_usr_signals_batch(
        {}, trace_id="TRACE-HU55-INFRA", infra_skip_reason="backpressure_db_latency"
    )
    summary_infra = factory_infra.last_funnel_summary
    assert summary_infra is not None
    assert summary_infra.get("raw_zero_cause_category") == "INFRA"

    # ── Case 2: SSOT-legítimo (affinity_below_threshold) → LEGIT_SSOT ─────────
    with patch("core_brain.signal_factory.get_notifier", return_value=MagicMock()):
        factory_ssot = SignalFactory(
            storage_manager=storage,
            strategy_engines={"affinity_strat": AffinityRejectStrategy()},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            instrument_manager=None,
        )

    df = pd.DataFrame({"open": [1.0], "high": [1.01], "low": [0.99], "close": [1.005]})
    await factory_ssot.generate_usr_signals_batch(
        {
            "EURUSD|M5": {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "regime": MarketRegime.TREND,
                "df": df,
            }
        },
        trace_id="TRACE-HU55-SSOT",
    )
    summary_ssot = factory_ssot.last_funnel_summary
    assert summary_ssot is not None
    assert summary_ssot.get("raw_zero_cause_category") == "LEGIT_SSOT"

    # ── Case 3: engine error (strategy_engine_error) → INFRA_FAILURE ──────────
    with patch("core_brain.signal_factory.get_notifier", return_value=MagicMock()):
        factory_err = SignalFactory(
            storage_manager=storage,
            strategy_engines={"err_strat": EngineErrorStrategy()},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            instrument_manager=None,
        )

    await factory_err.generate_usr_signals_batch(
        {
            "EURUSD|M5": {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "regime": MarketRegime.TREND,
                "df": df,
            }
        },
        trace_id="TRACE-HU55-ERR",
    )
    summary_err = factory_err.last_funnel_summary
    assert summary_err is not None
    assert summary_err.get("raw_zero_cause_category") == "INFRA_FAILURE"


@pytest.mark.asyncio
async def test_cycle_snapshot_persist_and_retrieve() -> None:
    """
    TDD HU5.5: StorageManager.persist_funnel_snapshot() almacena y
    get_latest_funnel_snapshot() recupera el snapshot con breakdown por etapa.
    """
    storage = StorageManager(db_path=":memory:")
    snapshot = {
        "trace_id": "TRACE-SNAP-HU55",
        "timestamp": "2026-04-14T00:00:00+00:00",
        "stages": {
            "STAGE_SCAN_INPUT": {"in": 5, "out": 5},
            "STAGE_RAW_SIGNAL_GENERATION": {"in": 5, "out": 0},
            "STAGE_STRATEGY_AUTH": {"in": 0, "out": 0},
        },
        "reasons": {"affinity_below_threshold": 4, "no_signal_generated": 1},
        "raw_zero_cause_category": "LEGIT_SSOT",
        "infra_skip_reason": None,
    }

    storage.persist_funnel_snapshot(snapshot)
    retrieved = storage.get_latest_funnel_snapshot()

    assert retrieved is not None
    assert retrieved["trace_id"] == "TRACE-SNAP-HU55"
    assert retrieved["stages"]["STAGE_RAW_SIGNAL_GENERATION"]["out"] == 0
    assert retrieved["reasons"]["affinity_below_threshold"] == 4
    assert retrieved.get("raw_zero_cause_category") == "LEGIT_SSOT"
