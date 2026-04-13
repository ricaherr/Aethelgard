"""
Tests TDD: Umbral de promoción adaptativo por estrategia.

P5b — El umbral de promoción a SHADOW debe:
  1. Leerse de execution_params['promotion_threshold'] si existe.
  2. Descubrirse y guardarse tras un backtest exitoso.
  3. Arrancar con MIN_REGIME_SCORE como valor inicial (bootstrap).
  4. Reducirse gradualmente (factor 0.95) cuando una estrategia lleva N runs
     sin superar el umbral (estrategia bloqueada).

RED state: falla porque actualmente usa self.backtester.MIN_REGIME_SCORE fijo.
"""
import pytest
import json
import asyncio
from unittest.mock import MagicMock
from core_brain.backtest_orchestrator import BacktestOrchestrator


def _make_orchestrator_with_params(execution_params: dict, overall_score: float = 0.8):
    """Crea BacktestOrchestrator con execution_params y score controlado."""
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
        "class_id": "STRAT_PROMO",
        "required_timeframes": ["H1"],
        "required_regime": None,
        "market_whitelist": ["EURUSD"],
        "execution_params": json.dumps(execution_params),
        "parameter_overrides": "{}",
        "score_backtest": 0.0,
    }

    orc._load_strategy = MagicMock(return_value=strategy)
    orc._get_symbols_for_backtest = MagicMock(return_value=["EURUSD"])
    orc._get_timeframes_for_backtest = MagicMock(return_value=["H1"])
    orc._passes_regime_prefilter = MagicMock(return_value=True)
    orc._build_strategy_for_backtest = MagicMock(return_value=MagicMock())
    orc._extract_parameter_overrides = MagicMock(return_value={})
    orc._build_scenario_slices = MagicMock(return_value=[MagicMock()])

    m = MagicMock()
    m.overall_score = overall_score
    orc.backtester = MagicMock()
    orc.backtester.MIN_REGIME_SCORE = 0.75
    orc.backtester.run_scenario_backtest = MagicMock(return_value=m)

    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    conn.execute.return_value = MagicMock()
    conn.execute.return_value.fetchone.return_value = [0]
    orc.storage = MagicMock()
    orc.storage._get_conn.return_value = conn
    orc.storage._close_conn = MagicMock()
    orc.storage.update_strategy_score = MagicMock()
    orc.storage.update_strategy_execution_params = MagicMock()

    orc._write_regime_incompatible = MagicMock()
    orc._write_pair_affinity = MagicMock()
    orc._promote_to_shadow = MagicMock()
    orc._detect_overfitting_risk = MagicMock(return_value=False)
    orc._write_overfitting_alert = MagicMock()

    return orc, strategy


class TestBacktestAdaptivePromotion:
    def test_uses_execution_params_threshold_when_present(self):
        """Si execution_params tiene promotion_threshold, debe usarse en lugar de MIN_REGIME_SCORE."""
        # Score 0.65 < MIN_REGIME_SCORE (0.75) pero >= promotion_threshold (0.60)
        orc, strategy = _make_orchestrator_with_params(
            {"promotion_threshold": 0.60}, overall_score=0.65
        )

        asyncio.run(orc._execute_backtest(strategy))

        orc._promote_to_shadow.assert_called_once(), (
            "Con threshold=0.60 y score=0.65, debe promover a SHADOW"
        )

    def test_does_not_promote_when_below_execution_params_threshold(self):
        """Score < promotion_threshold de execution_params → no promover."""
        orc, strategy = _make_orchestrator_with_params(
            {"promotion_threshold": 0.80}, overall_score=0.72
        )

        asyncio.run(orc._execute_backtest(strategy))

        orc._promote_to_shadow.assert_not_called()

    def test_bootstrap_uses_min_regime_score_when_no_threshold(self):
        """Sin promotion_threshold en execution_params, usa MIN_REGIME_SCORE (0.75) como bootstrap."""
        # score=0.80 >= 0.75 → debe promover
        orc, strategy = _make_orchestrator_with_params({}, overall_score=0.80)

        asyncio.run(orc._execute_backtest(strategy))

        orc._promote_to_shadow.assert_called_once()

    def test_saves_discovered_threshold_after_successful_run(self):
        """Tras un run exitoso, el threshold efectivo se persiste en execution_params via storage."""
        orc, strategy = _make_orchestrator_with_params({}, overall_score=0.82)

        asyncio.run(orc._execute_backtest(strategy))

        # Debe haber llamado update_strategy_execution_params para guardar el threshold
        orc.storage.update_strategy_execution_params.assert_called_once()
        saved_params = json.loads(
            orc.storage.update_strategy_execution_params.call_args[0][1]
        )
        assert "promotion_threshold" in saved_params, (
            "El threshold descubierto debe guardarse en execution_params"
        )

    def test_threshold_relaxes_after_consecutive_failures(self):
        """Tras 3 runs sin pasar el umbral, el threshold baja un 5% (factor 0.95)."""
        # Simula 3 failures previas en execution_params
        orc, strategy = _make_orchestrator_with_params(
            {"promotion_threshold": 0.75, "consecutive_failures": 3},
            overall_score=0.71,
        )

        asyncio.run(orc._execute_backtest(strategy))

        # threshold relaxado = 0.75 * 0.95 = 0.7125 → score 0.71 sigue sin pasar → no promover
        # pero el threshold guardado debe ser menor que el original
        orc.storage.update_strategy_execution_params.assert_called()
        saved_params = json.loads(
            orc.storage.update_strategy_execution_params.call_args[0][1]
        )
        assert saved_params.get("promotion_threshold", 0.75) < 0.75, (
            "El threshold debe haberse reducido tras 3 failures consecutivos"
        )

    def test_threshold_floor_prevents_zero_or_absurd_values(self):
        """Si el threshold base llega a 0.0, debe aplicarse floor mínimo configurable."""
        orc, strategy = _make_orchestrator_with_params(
            {"promotion_threshold": 0.0, "consecutive_failures": 9},
            overall_score=0.02,
        )
        # floor default from orchestrator config path in production code
        orc._cfg["promotion_threshold_floor"] = 0.15

        asyncio.run(orc._execute_backtest(strategy))

        saved_params = json.loads(
            orc.storage.update_strategy_execution_params.call_args[0][1]
        )
        assert saved_params.get("promotion_threshold", 0.0) >= 0.15, (
            "promotion_threshold no debe persistirse por debajo del floor mínimo"
        )
        assert saved_params.get("promotion_threshold_floor") == 0.15
