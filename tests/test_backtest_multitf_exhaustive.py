"""
Tests TDD: Multi-TF exhaustivo en BacktestOrchestrator.

P5 — _execute_backtest() debe evaluar TODOS los timeframes de la estrategia
     en cada ejecución (no round-robin de 1 TF por run) y retener el mejor score.

RED state: falla porque actualmente usa _next_timeframe_round_robin que devuelve
           solo 1 TF por run.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call
from core_brain.backtest_orchestrator import BacktestOrchestrator


def _make_orchestrator(timeframes: list, symbols: list = None):
    """Crea un BacktestOrchestrator mínimo con stubs."""
    orc = object.__new__(BacktestOrchestrator)
    orc._cfg = {
        "cooldown_hours": 24,
        "default_timeframe": "H1",
        "confidence_k": 20,
        "score_weights": {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
    }
    orc._tf_rr_index = {}
    orc.mode_manager = None
    orc.shadow_manager = None

    strategy = {
        "class_id": "STRAT_TEST",
        "required_timeframes": timeframes,
        "required_regime": None,
        "market_whitelist": symbols or ["EURUSD"],
        "execution_params": "{}",
        "parameter_overrides": "{}",
        "score_backtest": 0.0,
    }

    orc._load_strategy = MagicMock(return_value=strategy)
    orc._get_symbols_for_backtest = MagicMock(return_value=symbols or ["EURUSD"])
    orc._get_timeframes_for_backtest = MagicMock(return_value=timeframes)
    orc._passes_regime_prefilter = MagicMock(return_value=True)
    orc._build_strategy_for_backtest = MagicMock(return_value=MagicMock())
    orc._extract_parameter_overrides = MagicMock(return_value={})

    # backtester — devuelve scores distintos por TF para validar selección del mejor
    tf_scores = {tf: 0.4 + i * 0.1 for i, tf in enumerate(timeframes)}

    def fake_run_scenario_backtest(**kwargs):
        m = MagicMock()
        # Devuelve score según el TF que fue pasado en slices (mock de slices lleva tf)
        m.overall_score = 0.5
        return m

    orc.backtester = MagicMock()
    orc.backtester.MIN_REGIME_SCORE = 0.75
    orc.backtester.run_scenario_backtest = MagicMock(side_effect=fake_run_scenario_backtest)

    # _build_scenario_slices necesita retornar algo
    orc._build_scenario_slices = MagicMock(return_value=[MagicMock()])

    # storage
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    conn.execute.return_value = MagicMock()
    conn.execute.return_value.fetchone.return_value = [0]
    orc.storage = MagicMock()
    orc.storage._get_conn.return_value = conn
    orc.storage._close_conn = MagicMock()
    orc.storage.update_strategy_score = MagicMock()

    orc._write_regime_incompatible = MagicMock()
    orc._write_pair_affinity = MagicMock()
    orc._promote_to_shadow = MagicMock()
    orc._detect_overfitting_risk = MagicMock(return_value=False)
    orc._write_overfitting_alert = MagicMock()

    return orc, strategy


class TestBacktestMultiTFExhaustive:
    def test_evaluates_all_timeframes_per_symbol(self):
        """Para un símbolo con 3 TFs, run_scenario_backtest se llama 3 veces (una por TF)."""
        timeframes = ["M15", "H1", "H4"]
        orc, _ = _make_orchestrator(timeframes, symbols=["EURUSD"])

        asyncio.run(
            orc._execute_backtest(orc._load_strategy("STRAT_TEST"))
        )

        # Debe haberse llamado run_scenario_backtest exactamente 3 veces (M15, H1, H4)
        assert orc.backtester.run_scenario_backtest.call_count == 3, (
            f"Se esperaban 3 llamadas (una por TF), "
            f"se obtuvieron {orc.backtester.run_scenario_backtest.call_count}"
        )

    def test_evaluates_all_tfs_for_multiple_symbols(self):
        """2 símbolos × 3 TFs = 6 llamadas a run_scenario_backtest."""
        timeframes = ["M15", "H1", "H4"]
        orc, _ = _make_orchestrator(timeframes, symbols=["EURUSD", "GBPUSD"])

        asyncio.run(
            orc._execute_backtest(orc._load_strategy("STRAT_TEST"))
        )

        assert orc.backtester.run_scenario_backtest.call_count == 6

    def test_round_robin_is_not_used(self):
        """_next_timeframe_round_robin NO debe ser llamado en el nuevo flujo exhaustivo."""
        timeframes = ["M15", "H1", "H4"]
        orc, _ = _make_orchestrator(timeframes)
        orc._next_timeframe_round_robin = MagicMock(
            side_effect=AssertionError("round-robin no debe usarse en flujo exhaustivo")
        )

        # No debe lanzar excepción
        asyncio.run(
            orc._execute_backtest(orc._load_strategy("STRAT_TEST"))
        )

        orc._next_timeframe_round_robin.assert_not_called()

    def test_single_tf_still_works(self):
        """Con un solo TF la ejecución es idéntica — sin errores."""
        orc, _ = _make_orchestrator(["H1"])

        asyncio.run(
            orc._execute_backtest(orc._load_strategy("STRAT_TEST"))
        )

        assert orc.backtester.run_scenario_backtest.call_count == 1
