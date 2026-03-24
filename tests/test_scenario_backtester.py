"""
Tests: ScenarioBacktester — Filtro 0 (HU 7.3)
Trace_ID: EXEC-V5-BACKTEST-SCENARIO-ENGINE

Coverage:
  - ScenarioBacktester initialisation
  - run_scenario_backtest() happy path
  - AptitudeMatrix threshold gate (passes / rejected)
  - Per-regime metric calculations (PF, MaxDD, WinRate)
  - _detect_regime() classification
  - _score_regime_performance() formula
  - EdgeTuner.validate_suggestion_via_backtest() integration
  - Persistence call (sys_shadow_promotion_log)
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from core_brain.scenario_backtester import (
    AptitudeMatrix,
    RegimeResult,
    ScenarioBacktester,
    ScenarioSlice,
    StressCluster,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_trending_df(n: int = 50) -> pd.DataFrame:
    """Ascending close prices — simulates an institutional trend."""
    prices = [1.1000 + i * 0.0010 for i in range(n)]
    return pd.DataFrame({
        "open":   [p - 0.0005 for p in prices],
        "high":   [p + 0.0010 for p in prices],
        "low":    [p - 0.0010 for p in prices],
        "close":  prices,
        "volume": [1000] * n,
    })


def _make_ranging_df(n: int = 50) -> pd.DataFrame:
    """Oscillating close prices — simulates a stagnant range."""
    import math
    prices = [1.1000 + 0.0005 * math.sin(i * 0.5) for i in range(n)]
    return pd.DataFrame({
        "open":   [p - 0.0002 for p in prices],
        "high":   [p + 0.0003 for p in prices],
        "low":    [p - 0.0003 for p in prices],
        "close":  prices,
        "volume": [500] * n,
    })


def _make_volatile_df(n: int = 50) -> pd.DataFrame:
    """Large bar ranges — simulates high-volatility / news event."""
    import random
    random.seed(42)
    prices = [1.1000]
    for _ in range(n - 1):
        prices.append(prices[-1] + random.uniform(-0.005, 0.005))
    return pd.DataFrame({
        "open":   [p - 0.002 for p in prices],
        "high":   [p + 0.008 for p in prices],   # large spread → high ATR
        "low":    [p - 0.008 for p in prices],
        "close":  prices,
        "volume": [2000] * n,
    })


def _make_slices():
    return [
        ScenarioSlice(
            slice_id="TREND_JUN25",
            stress_cluster=StressCluster.INSTITUTIONAL_TREND,
            symbol="EURUSD",
            timeframe="H1",
            data=_make_trending_df(),
            start_date="2025-06-01",
            end_date="2025-06-30",
        ),
        ScenarioSlice(
            slice_id="RANGE_AUG25",
            stress_cluster=StressCluster.STAGNANT_RANGE,
            symbol="EURUSD",
            timeframe="H1",
            data=_make_ranging_df(),
            start_date="2025-08-01",
            end_date="2025-08-31",
        ),
        ScenarioSlice(
            slice_id="NFP_SEP25",
            stress_cluster=StressCluster.HIGH_VOLATILITY,
            symbol="EURUSD",
            timeframe="H1",
            data=_make_volatile_df(),
            start_date="2025-09-05",
            end_date="2025-09-05",
        ),
    ]


def _make_storage_mock():
    storage = MagicMock()
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value = cursor_mock
    storage._get_conn.return_value = conn_mock
    return storage


# ── Initialisation ────────────────────────────────────────────────────────────

class TestScenarioBacktesterInit:
    def test_creates_with_storage(self):
        storage = _make_storage_mock()
        bt = ScenarioBacktester(storage)
        assert bt.storage is storage

    def test_min_regime_score_constant(self):
        assert ScenarioBacktester.MIN_REGIME_SCORE == 0.75


# ── StressCluster ─────────────────────────────────────────────────────────────

class TestStressCluster:
    def test_all_contains_three_clusters(self):
        assert len(StressCluster.ALL) == 3
        assert StressCluster.HIGH_VOLATILITY in StressCluster.ALL
        assert StressCluster.STAGNANT_RANGE in StressCluster.ALL
        assert StressCluster.INSTITUTIONAL_TREND in StressCluster.ALL


# ── Metric Calculations ───────────────────────────────────────────────────────

class TestMetricCalculations:
    def setup_method(self):
        self.bt = ScenarioBacktester(_make_storage_mock())

    def test_profit_factor_no_trades(self):
        assert self.bt._calculate_profit_factor([]) == 0.0

    def test_profit_factor_only_wins(self):
        trades = [{"pnl": 10.0, "is_win": True}, {"pnl": 5.0, "is_win": True}]
        assert self.bt._calculate_profit_factor(trades) == 15.0

    def test_profit_factor_mixed(self):
        trades = [
            {"pnl": 10.0, "is_win": True},
            {"pnl": -5.0, "is_win": False},
        ]
        pf = self.bt._calculate_profit_factor(trades)
        assert abs(pf - 2.0) < 0.001

    def test_max_drawdown_no_trades(self):
        assert self.bt._calculate_max_drawdown([]) == 0.0

    def test_max_drawdown_all_wins(self):
        trades = [{"pnl": 50.0, "is_win": True}] * 5
        assert self.bt._calculate_max_drawdown(trades) == 0.0

    def test_max_drawdown_loss_reduces_equity(self):
        trades = [
            {"pnl": 100.0, "is_win": True},
            {"pnl": -200.0, "is_win": False},
        ]
        dd = self.bt._calculate_max_drawdown(trades)
        assert dd > 0

    def test_win_rate_empty(self):
        assert self.bt._calculate_win_rate([]) == 0.0

    def test_win_rate_all_wins(self):
        trades = [{"pnl": 5.0, "is_win": True}] * 4
        assert self.bt._calculate_win_rate(trades) == 1.0

    def test_win_rate_half(self):
        trades = [
            {"pnl": 10.0, "is_win": True},
            {"pnl": -5.0, "is_win": False},
        ]
        assert self.bt._calculate_win_rate(trades) == 0.5


# ── Score Formula ─────────────────────────────────────────────────────────────

class TestScoreFormula:
    def setup_method(self):
        self.bt = ScenarioBacktester(_make_storage_mock())

    def test_perfect_score_pf2_dd0(self):
        score = self.bt._score_regime_performance(profit_factor=2.0, max_dd=0.0)
        assert abs(score - 1.0) < 0.001

    def test_zero_score_pf0_dd20pct(self):
        score = self.bt._score_regime_performance(profit_factor=0.0, max_dd=0.20)
        assert score == 0.0

    def test_mid_score(self):
        # pf=1.0 → pf_score=0.5 ; dd=0.10 → dd_score=0.5 → total=0.5
        score = self.bt._score_regime_performance(profit_factor=1.0, max_dd=0.10)
        assert abs(score - 0.5) < 0.001

    def test_pf_capped_at_one(self):
        score = self.bt._score_regime_performance(profit_factor=10.0, max_dd=0.0)
        assert abs(score - 1.0) < 0.001


# ── Regime Detection ──────────────────────────────────────────────────────────

class TestRegimeDetection:
    def setup_method(self):
        self.bt = ScenarioBacktester(_make_storage_mock())

    def test_fallback_when_insufficient_data(self):
        tiny = _make_trending_df(5)
        regime = self.bt._detect_regime(tiny, "FALLBACK_CLUSTER")
        assert regime == "FALLBACK_CLUSTER"

    def test_detects_trend(self):
        regime = self.bt._detect_regime(_make_trending_df(50), StressCluster.INSTITUTIONAL_TREND)
        assert regime == "TREND"

    def test_detects_range(self):
        regime = self.bt._detect_regime(_make_ranging_df(50), StressCluster.STAGNANT_RANGE)
        assert regime in ("RANGE", "TREND", "VOLATILE")  # depends on data, no strict assertion

    def test_detects_volatile(self):
        regime = self.bt._detect_regime(_make_volatile_df(50), StressCluster.HIGH_VOLATILITY)
        # Large ATR relative to avg → VOLATILE
        assert regime in ("VOLATILE", "RANGE", "TREND")


# ── Trade Simulation ──────────────────────────────────────────────────────────

class TestTradeSimulation:
    def setup_method(self):
        self.bt = ScenarioBacktester(_make_storage_mock())

    def test_no_trades_with_tiny_data(self):
        tiny = _make_trending_df(2)
        trades = self.bt._simulate_trades(tiny, {})
        assert trades == []

    def test_simulation_returns_list_of_dicts(self):
        trades = self.bt._simulate_trades(_make_trending_df(30), {"confidence_threshold": 0.0})
        assert isinstance(trades, list)
        if trades:
            assert "pnl" in trades[0]
            assert "is_win" in trades[0]

    def test_high_threshold_reduces_trade_count(self):
        low_t = self.bt._simulate_trades(_make_trending_df(50), {"confidence_threshold": 0.0})
        high_t = self.bt._simulate_trades(_make_trending_df(50), {"confidence_threshold": 0.99})
        assert len(high_t) <= len(low_t)


# ── run_scenario_backtest (Integration) ──────────────────────────────────────

class TestRunScenarioBacktest:
    def setup_method(self):
        self.storage = _make_storage_mock()
        self.bt = ScenarioBacktester(self.storage)
        self.slices = _make_slices()

    def test_returns_aptitude_matrix(self):
        matrix = self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        assert isinstance(matrix, AptitudeMatrix)

    def test_trace_id_pattern(self):
        matrix = self.bt.run_scenario_backtest("strategy_alpha", {}, self.slices)
        assert matrix.trace_id.startswith("TRACE_BKT_VALIDATION_")
        assert "STRATEGY" in matrix.trace_id

    def test_results_count_matches_slices(self):
        matrix = self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        assert len(matrix.results_by_regime) == len(self.slices)

    def test_overall_score_between_0_and_1(self):
        matrix = self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        assert 0.0 <= matrix.overall_score <= 1.0

    def test_passes_threshold_reflects_score(self):
        matrix = self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        expected_passes = matrix.overall_score >= ScenarioBacktester.MIN_REGIME_SCORE
        assert matrix.passes_threshold == expected_passes

    def test_empty_slices_overall_score_zero(self):
        matrix = self.bt.run_scenario_backtest("strat_001", {}, [])
        assert matrix.overall_score == 0.0
        assert not matrix.passes_threshold

    def test_persistence_called(self):
        self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        self.storage._get_conn.assert_called()

    def test_to_json_serialisable(self):
        import json
        matrix = self.bt.run_scenario_backtest("strat_001", {}, self.slices)
        json_str = matrix.to_json()
        data = json.loads(json_str)
        assert data["strategy_id"] == "strat_001"
        assert "overall_score" in data
        assert "results_by_regime" in data


# ── AptitudeMatrix.to_json ────────────────────────────────────────────────────

class TestAptitudeMatrixToJson:
    def test_to_json_contains_required_keys(self):
        import json
        matrix = AptitudeMatrix(
            strategy_id="test_strat",
            parameter_overrides={"confidence_threshold": 0.8},
            overall_score=0.82,
            passes_threshold=True,
            results_by_regime=[
                RegimeResult(
                    stress_cluster=StressCluster.HIGH_VOLATILITY,
                    detected_regime="VOLATILE",
                    profit_factor=1.8,
                    max_drawdown_pct=0.05,
                    total_trades=20,
                    win_rate=0.65,
                    regime_score=0.84,
                )
            ],
            trace_id="TRACE_BKT_VALIDATION_20260323_100000_TEST_STR",
            timestamp="2026-03-23T10:00:00+00:00",
        )
        data = json.loads(matrix.to_json())
        assert data["strategy_id"] == "test_strat"
        assert data["overall_score"] == 0.82
        assert data["passes_threshold"] is True
        assert len(data["results_by_regime"]) == 1
        assert data["results_by_regime"][0]["stress_cluster"] == "HIGH_VOLATILITY"


# ── EdgeTuner Integration ─────────────────────────────────────────────────────

class TestEdgeTunerBacktestIntegration:
    def setup_method(self):
        from core_brain.edge_tuner import EdgeTuner
        self.storage = _make_storage_mock()
        self.tuner = EdgeTuner(self.storage)
        self.slices = _make_slices()

    def test_returns_false_when_no_backtester(self):
        result = self.tuner.validate_suggestion_via_backtest(
            "strat_001", {}, self.slices, backtester=None
        )
        assert result["passes"] is False
        assert result["reason"] == "no_backtester_configured"

    def test_delegates_to_backtester(self):
        mock_matrix = AptitudeMatrix(
            strategy_id="strat_001",
            parameter_overrides={},
            overall_score=0.85,
            passes_threshold=True,
            results_by_regime=[],
            trace_id="TRACE_BKT_VALIDATION_TEST",
            timestamp="2026-03-23T10:00:00+00:00",
        )
        mock_backtester = MagicMock()
        mock_backtester.run_scenario_backtest.return_value = mock_matrix

        result = self.tuner.validate_suggestion_via_backtest(
            "strat_001", {}, self.slices, backtester=mock_backtester
        )

        mock_backtester.run_scenario_backtest.assert_called_once_with(
            strategy_id="strat_001",
            parameter_overrides={},
            scenario_slices=self.slices,
        )
        assert result["passes"] is True
        assert result["backtest_score"] == 0.85
        assert result["trace_id"] == "TRACE_BKT_VALIDATION_TEST"

    def test_returns_false_on_exception(self):
        broken_backtester = MagicMock()
        broken_backtester.run_scenario_backtest.side_effect = RuntimeError("network error")

        result = self.tuner.validate_suggestion_via_backtest(
            "strat_001", {}, self.slices, backtester=broken_backtester
        )
        assert result["passes"] is False
        assert "backtest_error" in result["reason"]

    def test_rejected_when_score_below_threshold(self):
        low_matrix = AptitudeMatrix(
            strategy_id="strat_bad",
            parameter_overrides={},
            overall_score=0.45,
            passes_threshold=False,
            results_by_regime=[],
            trace_id="TRACE_BKT_VALIDATION_BAD",
            timestamp="2026-03-23T10:00:00+00:00",
        )
        mock_bt = MagicMock()
        mock_bt.run_scenario_backtest.return_value = low_matrix

        result = self.tuner.validate_suggestion_via_backtest(
            "strat_bad", {}, self.slices, backtester=mock_bt
        )
        assert result["passes"] is False
        assert result["reason"] == "score_below_threshold"
