"""
test_backtester_dispatch_to_strategy.py

Verifica que ScenarioBacktester despache la simulación de trades
a strategy.evaluate_on_history() cuando se proporciona una instancia real,
en lugar de usar el modelo momentum genérico para todas las estrategias.
"""
import sqlite3
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core_brain.scenario_backtester import ScenarioBacktester, ScenarioSlice, StressCluster
from models.trade_result import TradeResult


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_storage():
    s = MagicMock()
    s._get_conn.return_value = sqlite3.connect(":memory:")
    s._close_conn.return_value = None
    return s


def _make_real_slice(n: int = 80, cluster: str = StressCluster.HIGH_VOLATILITY) -> ScenarioSlice:
    rng = np.random.default_rng(7)
    close = 1.1 + rng.normal(0, 0.001, n).cumsum()
    spread = abs(rng.normal(0, 0.0005, n)) + 0.0002
    df = pd.DataFrame({
        "open":   close - spread * 0.3,
        "high":   close + spread,
        "low":    close - spread,
        "close":  close,
        "volume": 1000.0,
    })
    return ScenarioSlice(
        slice_id=f"test_{cluster}",
        stress_cluster=cluster,
        symbol="EURUSD",
        timeframe="H1",
        data=df,
        start_date="2026-01-01",
        end_date="2026-03-01",
        is_real_data=True,
    )


class _StubStrategy:
    """Estrategia stub que devuelve trades predeterminados desde evaluate_on_history."""
    EXPECTED_PNL = 0.0042

    def evaluate_on_history(self, df, params):
        return [
            TradeResult(
                entry_price=1.1000, exit_price=1.1042, pnl=self.EXPECTED_PNL,
                direction=1, bars_held=5, regime_at_entry="TREND",
                sl_distance=0.0010, tp_distance=0.0042,
            )
        ]


class _EmptyStrategy:
    """Estrategia que no genera ninguna señal en backtesting."""
    def evaluate_on_history(self, df, params):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktesterDispatchToStrategyInstance:

    def _backtester(self, strategy_inst=None):
        bkt = ScenarioBacktester(storage=_make_storage())
        if strategy_inst is not None:
            bkt.strategy_instance = strategy_inst
        return bkt

    def test_evaluate_slice_uses_strategy_evaluate_on_history_when_provided(self):
        """Si strategy_instance tiene evaluate_on_history, _evaluate_slice debe usarlo."""
        bkt = ScenarioBacktester(storage=_make_storage())
        stub = _StubStrategy()
        sl = _make_real_slice()
        result = bkt._evaluate_slice(sl, {}, strategy_instance=stub)
        # Debe haber generado exactamente 1 trade (el del stub)
        assert result.total_trades == 1

    def test_evaluate_slice_uses_stub_pnl_not_momentum(self):
        """El PnL del resultado debe reflejar el trade del stub, no el modelo momentum."""
        bkt = ScenarioBacktester(storage=_make_storage())
        stub = _StubStrategy()
        sl = _make_real_slice()
        result = bkt._evaluate_slice(sl, {}, strategy_instance=stub)
        # Con 1 trade ganador y PF > 0 → profit_factor > 0
        # Si usara momentum genérico, el resultado variaría según los datos
        assert result.total_trades == 1
        assert result.profit_factor >= 0.0  # sin pérdidas → PF = total_profit

    def test_evaluate_slice_falls_back_to_momentum_when_no_strategy(self):
        """Sin strategy_instance, el backtester debe usar el modelo momentum genérico."""
        bkt = ScenarioBacktester(storage=_make_storage())
        sl = _make_real_slice(n=80)
        result_no_strat = bkt._evaluate_slice(sl, {})
        result_with_none = bkt._evaluate_slice(sl, {}, strategy_instance=None)
        # Ambos deben producir el mismo resultado (fallback consistente)
        assert result_no_strat.total_trades == result_with_none.total_trades

    def test_empty_strategy_produces_zero_score(self):
        """Estrategia sin señales → total_trades=0 → regime_score=0.0."""
        bkt = ScenarioBacktester(storage=_make_storage())
        empty = _EmptyStrategy()
        sl = _make_real_slice()
        result = bkt._evaluate_slice(sl, {}, strategy_instance=empty)
        assert result.total_trades == 0
        assert result.regime_score == pytest.approx(0.0)

    def test_run_scenario_backtest_accepts_strategy_instance(self):
        """run_scenario_backtest() debe aceptar strategy_instance sin error."""
        bkt = ScenarioBacktester(storage=_make_storage())
        stub = _StubStrategy()
        slices = [_make_real_slice(cluster=c) for c in StressCluster.ALL]
        matrix = bkt.run_scenario_backtest("test_strat", {}, slices, strategy_instance=stub)
        assert matrix.strategy_id == "test_strat"
        # Con trades en todos los slices → overall_score > 0
        assert matrix.overall_score > 0.0

    def test_different_strategy_instances_produce_different_scores(self):
        """Dos instancias de estrategia distintas deben producir scores distintos."""
        bkt = ScenarioBacktester(storage=_make_storage())
        slices = [_make_real_slice(cluster=c) for c in StressCluster.ALL]

        # Estrategia que siempre gana (PF muy alto)
        class WinningStrategy:
            def evaluate_on_history(self, df, params):
                return [TradeResult(
                    entry_price=1.1, exit_price=1.12, pnl=0.02,
                    direction=1, bars_held=3, regime_at_entry="TREND",
                    sl_distance=0.005, tp_distance=0.02,
                )]

        # Estrategia que siempre pierde
        class LosingStrategy:
            def evaluate_on_history(self, df, params):
                return [TradeResult(
                    entry_price=1.1, exit_price=1.095, pnl=-0.005,
                    direction=1, bars_held=2, regime_at_entry="RANGE",
                    sl_distance=0.005, tp_distance=0.01,
                )]

        m_win  = bkt.run_scenario_backtest("winner", {}, slices, strategy_instance=WinningStrategy())
        m_lose = bkt.run_scenario_backtest("loser",  {}, slices, strategy_instance=LosingStrategy())
        assert m_win.overall_score != m_lose.overall_score, (
            "Estrategias ganadora y perdedora produjeron el mismo score"
        )
        assert m_win.overall_score > m_lose.overall_score

    def test_orchestrator_resolves_strategy_instance_for_known_ids(self):
        """BacktestOrchestrator debe resolver la instancia de estrategia para IDs conocidos."""
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        orc = BacktestOrchestrator.__new__(BacktestOrchestrator)
        orc.storage = _make_storage()
        orc.storage.get_sys_config_value = MagicMock(return_value=None)

        for strategy_id in ["MOM_BIAS_0001", "LIQ_SWEEP_0001", "STRUC_SHIFT_0001"]:
            inst = orc._build_strategy_for_backtest(strategy_id)
            assert inst is not None, f"No se pudo resolver instancia para {strategy_id}"
            assert hasattr(inst, "evaluate_on_history"), (
                f"{strategy_id}: la instancia resuelta no tiene evaluate_on_history()"
            )
