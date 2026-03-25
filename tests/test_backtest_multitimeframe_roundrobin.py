"""
Tests: BacktestOrchestrator — multi-timeframe round-robin y pre-filtro de régimen
==================================================================================
Verifica que BacktestOrchestrator:
1. Lee required_timeframes de la estrategia y hace round-robin entre ellos.
2. En cada ciclo selecciona el siguiente timeframe de la rotación.
3. Vuelve al inicio cuando termina el ciclo (ciclicidad).
4. Si required_timeframes está vacío usa el default_timeframe.
5. Pre-filtro de régimen: si required_regime != 'ANY' y el régimen actual no coincide,
   omite el backtest y registra skip en log.
6. required_regime='ANY' siempre pasa el pre-filtro.
7. Si el data provider no tiene datos para el check de régimen, el pre-filtro permite
   el paso (fail-open para no bloquear evaluaciones).
"""

import json
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from core_brain.backtest_orchestrator import BacktestOrchestrator
from core_brain.scenario_backtester import ScenarioBacktester


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(n: int = 60, trend: bool = True) -> pd.DataFrame:
    base = 1.1000
    step = 0.0005 if trend else 0.0
    close = [base + i * step for i in range(n)]
    return pd.DataFrame({
        "open":   [c - 0.0002 for c in close],
        "high":   [c + 0.0008 for c in close],
        "low":    [c - 0.0008 for c in close],
        "close":  close,
        "volume": [1000.0] * n,
    })


_CFG_ROW = (json.dumps({
    "cooldown_hours": 0,
    "min_trades_per_cluster": 1,
    "bars_per_window": 30,
    "bars_fetch_initial": 60,
    "bars_fetch_max": 120,
    "bars_fetch_retry": 30,
    "promotion_min_score": 0.75,
    "default_symbol": "EURUSD",
    "default_timeframe": "H1",
    "score_weights": {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
}),)


def _make_strategy(
    required_timeframes=None,
    required_regime="ANY",
    market_whitelist=None,
) -> dict:
    return {
        "class_id": "TEST_STRAT",
        "mnemonic": "TEST",
        "market_whitelist": json.dumps(market_whitelist or ["EURUSD"]),
        "affinity_scores": "{}",
        "mode": "BACKTEST",
        "score_backtest": 0.0,
        "score_shadow": 0.0,
        "score_live": 0.0,
        "score": 0.0,
        "updated_at": "2020-01-01T00:00:00",
        "last_backtest_at": None,
        "required_timeframes": json.dumps(required_timeframes or []),
        "required_regime": required_regime,
    }


def _make_orchestrator(strategy: dict, df: pd.DataFrame):
    """Build BacktestOrchestrator with mocked storage and data provider."""
    storage = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    storage._get_conn.return_value = conn

    # sys_config
    cursor.fetchone.return_value = _CFG_ROW

    dpm = MagicMock()
    dpm.fetch_ohlc.return_value = df

    backtester = MagicMock(spec=ScenarioBacktester)
    backtester._detect_regime.return_value = "TREND"
    backtester.run_scenario_backtest.return_value = MagicMock(
        overall_score=0.8, passes_threshold=True
    )

    orc = BacktestOrchestrator(
        storage=storage,
        data_provider_manager=dpm,
        scenario_backtester=backtester,
    )
    return orc, dpm, backtester


# ── Tests: round-robin de timeframes ─────────────────────────────────────────

class TestMultiTimeframeRoundRobin:

    def test_get_timeframes_returns_required_timeframes_when_configured(self):
        """Si required_timeframes tiene valores, los devuelve en orden."""
        strat = _make_strategy(required_timeframes=["M15", "H1", "H4"])
        orc, _, _ = _make_orchestrator(strat, _make_df())
        tfs = orc._get_timeframes_for_backtest(strat)
        assert tfs == ["M15", "H1", "H4"]

    def test_get_timeframes_falls_back_to_default_when_empty(self):
        """Si required_timeframes está vacío, usa default_timeframe del config."""
        strat = _make_strategy(required_timeframes=[])
        orc, _, _ = _make_orchestrator(strat, _make_df())
        tfs = orc._get_timeframes_for_backtest(strat)
        assert tfs == ["H1"]  # default_timeframe del config

    def test_round_robin_cycles_through_timeframes(self):
        """Cada llamada sucesiva devuelve el siguiente timeframe en rotación."""
        strat = _make_strategy(required_timeframes=["M15", "H1", "H4"])
        orc, _, _ = _make_orchestrator(strat, _make_df())
        tfs = ["M15", "H1", "H4"]

        t1 = orc._next_timeframe_round_robin("TEST_STRAT", tfs)
        t2 = orc._next_timeframe_round_robin("TEST_STRAT", tfs)
        t3 = orc._next_timeframe_round_robin("TEST_STRAT", tfs)
        assert t1 == "M15"
        assert t2 == "H1"
        assert t3 == "H4"

    def test_round_robin_wraps_back_to_first(self):
        """Tras agotar la lista vuelve al primer timeframe."""
        strat = _make_strategy(required_timeframes=["M15", "H1"])
        orc, _, _ = _make_orchestrator(strat, _make_df())
        tfs = ["M15", "H1"]

        orc._next_timeframe_round_robin("TEST_STRAT", tfs)  # M15
        orc._next_timeframe_round_robin("TEST_STRAT", tfs)  # H1
        t3 = orc._next_timeframe_round_robin("TEST_STRAT", tfs)  # wrap → M15
        assert t3 == "M15"

    def test_round_robin_independent_per_strategy(self):
        """El índice de round-robin es independiente por strategy_id."""
        strat = _make_strategy(required_timeframes=["M15", "H1"])
        orc, _, _ = _make_orchestrator(strat, _make_df())
        tfs = ["M15", "H1"]

        # Advance STRAT_A
        orc._next_timeframe_round_robin("STRAT_A", tfs)
        orc._next_timeframe_round_robin("STRAT_A", tfs)

        # STRAT_B starts fresh at M15
        t = orc._next_timeframe_round_robin("STRAT_B", tfs)
        assert t == "M15"

    def test_build_scenario_slices_uses_round_robin_timeframe(self):
        """_build_scenario_slices usa el timeframe del round-robin, no siempre H1."""
        strat = _make_strategy(required_timeframes=["M15", "H4"])
        orc, dpm, _ = _make_orchestrator(strat, _make_df(120))

        # Primera llamada → M15
        orc._build_scenario_slices(strat, {"confidence_threshold": 0.001})
        first_call_tf = dpm.fetch_ohlc.call_args_list[0][0][1]
        assert first_call_tf == "M15"

        dpm.fetch_ohlc.reset_mock()
        dpm.fetch_ohlc.return_value = _make_df(120)

        # Segunda llamada → H4
        orc._build_scenario_slices(strat, {"confidence_threshold": 0.001})
        second_call_tf = dpm.fetch_ohlc.call_args_list[0][0][1]
        assert second_call_tf == "H4"


# ── Tests: pre-filtro de régimen ──────────────────────────────────────────────

class TestRegimenPrefilter:

    def test_prefilter_any_always_passes(self):
        """required_regime='ANY' nunca bloquea."""
        strat = _make_strategy(required_regime="ANY")
        orc, _, _ = _make_orchestrator(strat, _make_df())
        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True

    def test_prefilter_matching_regime_passes(self):
        """Si el régimen detectado coincide con el requerido, pasa."""
        strat = _make_strategy(required_regime="TREND")
        orc, dpm, backtester = _make_orchestrator(strat, _make_df())
        backtester._detect_regime.return_value = "TREND"
        dpm.fetch_ohlc.return_value = _make_df(50)

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True

    def test_prefilter_mismatched_regime_blocks(self):
        """Si el régimen detectado no coincide con el requerido, bloquea."""
        strat = _make_strategy(required_regime="RANGE")
        orc, dpm, backtester = _make_orchestrator(strat, _make_df())
        backtester._detect_regime.return_value = "TREND"
        dpm.fetch_ohlc.return_value = _make_df(50)

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is False

    def test_prefilter_no_data_fails_open(self):
        """Sin datos del data provider, el pre-filtro permite el paso (fail-open)."""
        strat = _make_strategy(required_regime="TREND")
        orc, dpm, _ = _make_orchestrator(strat, _make_df())
        dpm.fetch_ohlc.return_value = None

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True  # fail-open

    def test_prefilter_insufficient_data_fails_open(self):
        """Con datos insuficientes (<14 bars), el pre-filtro permite el paso."""
        strat = _make_strategy(required_regime="RANGE")
        orc, dpm, _ = _make_orchestrator(strat, _make_df())
        dpm.fetch_ohlc.return_value = _make_df(5)  # muy pocos

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True

    def test_prefilter_volatile_matches_volatile(self):
        """VOLATILE y variantes se normalizan correctamente."""
        strat = _make_strategy(required_regime="VOLATILE")
        orc, dpm, backtester = _make_orchestrator(strat, _make_df())
        backtester._detect_regime.return_value = "VOLATILE"
        dpm.fetch_ohlc.return_value = _make_df(50)

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True

    def test_prefilter_volatility_alias_matches_volatile(self):
        """required_regime='VOLATILITY' debe coincidir con detected='VOLATILE'."""
        strat = _make_strategy(required_regime="VOLATILITY")
        orc, dpm, backtester = _make_orchestrator(strat, _make_df())
        backtester._detect_regime.return_value = "VOLATILE"
        dpm.fetch_ohlc.return_value = _make_df(50)

        result = orc._passes_regime_prefilter(strat, "EURUSD", "H1")
        assert result is True

    def test_execute_backtest_skips_when_prefilter_blocks(self):
        """_build_scenario_slices retorna UNTESTED si el pre-filtro bloquea."""
        strat = _make_strategy(
            required_timeframes=["H1"],
            required_regime="RANGE",
        )
        orc, dpm, backtester = _make_orchestrator(strat, _make_df(60))
        backtester._detect_regime.return_value = "TREND"  # no coincide
        dpm.fetch_ohlc.return_value = _make_df(50)

        slices = orc._build_scenario_slices(strat, {"confidence_threshold": 0.001})
        # Todos los slices deben ser UNTESTED cuando el régimen no coincide
        assert all(not s.is_real_data for s in slices)
