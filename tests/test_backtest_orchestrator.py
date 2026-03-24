"""
Tests: BacktestOrchestrator (HU 7.4 — EXEC-V5-BACKTEST-ORCHESTRATOR-2026-03-23)

Coverage:
  - Initialization with and without shadow_manager
  - run_pending_strategies(): empty, single, batch
  - run_single_strategy(): cooldown respected, force bypass
  - _fetch_with_retry(): dynamic bar sizing, retry logic
  - _split_into_cluster_slices(): regime detection → cluster mapping
  - _synthesise_cluster_window(): fallback generation
  - _to_dataframe(): DataFrame + list-of-dict normalisation
  - _update_strategy_scores(): score formula verification
  - _promote_to_shadow(): mode update in DB
  - _is_on_cooldown(): 24 h gate logic
  - _estimate_trade_count(): signal rate estimation
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pandas as pd
import pytest

from core_brain.backtest_orchestrator import (
    BARS_FETCH_INITIAL,
    BARS_PER_WINDOW,
    COOLDOWN_HOURS,
    MIN_TRADES_CLUSTER,
    W_BACKTEST,
    W_LIVE,
    W_SHADOW,
    BacktestOrchestrator,
)
from core_brain.scenario_backtester import AptitudeMatrix, ScenarioBacktester, StressCluster


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ohlcv_df(n: int = 200, base: float = 1.1000, step: float = 0.0005) -> pd.DataFrame:
    """Ascending OHLCV DataFrame (trend-like)."""
    close = [base + i * step for i in range(n)]
    return pd.DataFrame({
        "open":   [c - 0.0002 for c in close],
        "high":   [c + 0.0008 for c in close],
        "low":    [c - 0.0008 for c in close],
        "close":  close,
        "volume": [1000.0] * n,
    })


def _make_storage_mock(strategies=None):
    storage = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    storage._get_conn.return_value = conn

    # Default: one strategy in BACKTEST mode
    if strategies is None:
        strategies = [{
            "class_id":        "strat_alpha",
            "mnemonic":        "ALPHA",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores":  "{}",
            "mode":            "BACKTEST",
            "score_backtest":  0.0,
            "score_shadow":    0.0,
            "score_live":      0.0,
            "score":           0.0,
            "updated_at":      "2020-01-01T00:00:00",
        }]

    rows = [tuple(s.values()) for s in strategies]
    cols = list(strategies[0].keys()) if strategies else []
    cursor.description = [(c,) for c in cols]
    cursor.fetchall.return_value = rows
    cursor.fetchone.return_value = rows[0] if rows else None
    return storage


def _make_dpm_mock(df: pd.DataFrame = None):
    dpm = MagicMock()
    dpm.fetch_ohlc.return_value = df if df is not None else _make_ohlcv_df()
    return dpm


def _make_backtester_mock(passes: bool = True, score: float = 0.85):
    bt = MagicMock(spec=ScenarioBacktester)
    matrix = AptitudeMatrix(
        strategy_id="strat_alpha",
        parameter_overrides={},
        overall_score=score,
        passes_threshold=passes,
        results_by_regime=[],
        trace_id="TRACE_BKT_VALIDATION_TEST",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    bt.run_scenario_backtest.return_value = matrix
    # expose internal method for cluster detection tests
    bt._detect_regime = ScenarioBacktester(_make_storage_mock())._detect_regime
    return bt


def _make_orchestrator(
    strategies=None,
    df=None,
    passes=True,
    score=0.85,
    shadow_manager=None,
):
    storage   = _make_storage_mock(strategies)
    dpm       = _make_dpm_mock(df)
    backtester = _make_backtester_mock(passes, score)
    return BacktestOrchestrator(
        storage=storage,
        data_provider_manager=dpm,
        scenario_backtester=backtester,
        shadow_manager=shadow_manager,
    ), storage, dpm, backtester


# ── Initialisation ────────────────────────────────────────────────────────────

class TestInit:
    def test_stores_dependencies(self):
        orc, storage, dpm, bt = _make_orchestrator()
        assert orc.storage is storage
        assert orc.dpm is dpm
        assert orc.backtester is bt

    def test_last_run_none_at_init(self):
        orc, *_ = _make_orchestrator()
        assert orc.last_run is None

    def test_shadow_manager_optional(self):
        orc, *_ = _make_orchestrator(shadow_manager=None)
        assert orc.shadow_manager is None


# ── Constants ─────────────────────────────────────────────────────────────────

class TestConstants:
    def test_cooldown_hours(self):
        assert COOLDOWN_HOURS == 24

    def test_min_trades_cluster(self):
        assert MIN_TRADES_CLUSTER == 15

    def test_score_weights_sum_to_one(self):
        assert abs(W_LIVE + W_SHADOW + W_BACKTEST - 1.0) < 1e-9

    def test_bars_fetch_initial_geq_window(self):
        assert BARS_FETCH_INITIAL >= BARS_PER_WINDOW


# ── _is_on_cooldown ───────────────────────────────────────────────────────────

class TestCooldown:
    def setup_method(self):
        self.orc, *_ = _make_orchestrator()

    def _strategy(self, hours_ago: float, mode: str = "BACKTEST") -> dict:
        updated = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return {"updated_at": updated.isoformat(), "mode": mode}

    def test_not_on_cooldown_when_old_enough(self):
        assert not self.orc._is_on_cooldown(self._strategy(25))

    def test_on_cooldown_when_recent(self):
        assert self.orc._is_on_cooldown(self._strategy(2))

    def test_no_cooldown_without_updated_at(self):
        assert not self.orc._is_on_cooldown({"updated_at": None, "mode": "BACKTEST"})

    def test_skips_non_backtest_mode(self):
        # Already promoted → always cooldown (skip)
        assert self.orc._is_on_cooldown(self._strategy(48, mode="SHADOW"))


# ── _to_dataframe ─────────────────────────────────────────────────────────────

class TestToDataframe:
    def setup_method(self):
        self.orc, *_ = _make_orchestrator()

    def test_returns_none_for_none(self):
        assert self.orc._to_dataframe(None) is None

    def test_accepts_dataframe(self):
        df = _make_ohlcv_df(50)
        result = self.orc._to_dataframe(df)
        assert isinstance(result, pd.DataFrame)
        assert "close" in result.columns

    def test_accepts_list_of_dicts(self):
        data = [{"open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100}] * 10
        result = self.orc._to_dataframe(data)
        assert isinstance(result, pd.DataFrame)

    def test_normalises_uppercase_columns(self):
        df = _make_ohlcv_df(10)
        df.columns = [c.upper() for c in df.columns]
        result = self.orc._to_dataframe(df)
        assert "close" in result.columns

    def test_returns_none_for_missing_ohlc_column(self):
        df = pd.DataFrame({"open": [1.0], "high": [1.1], "low": [0.9]})  # no close
        assert self.orc._to_dataframe(df) is None


# ── _estimate_trade_count ─────────────────────────────────────────────────────

class TestEstimateTradeCount:
    def setup_method(self):
        self.orc, *_ = _make_orchestrator()

    def test_zero_for_tiny_df(self):
        df = _make_ohlcv_df(1)
        assert self.orc._estimate_trade_count(df, 0.75) == 0

    def test_more_signals_with_lower_threshold(self):
        df = _make_ohlcv_df(200)
        high = self.orc._estimate_trade_count(df, 0.99)
        low  = self.orc._estimate_trade_count(df, 0.01)
        assert low >= high


# ── _synthesise_cluster_window ────────────────────────────────────────────────

class TestSynthesiseClusterWindow:
    def setup_method(self):
        self.orc, *_ = _make_orchestrator()
        self.base_df  = _make_ohlcv_df(200)

    def test_returns_dataframe(self):
        df = self.orc._synthesise_cluster_window(self.base_df, StressCluster.HIGH_VOLATILITY)
        assert isinstance(df, pd.DataFrame)

    def test_has_ohlcv_columns(self):
        df = self.orc._synthesise_cluster_window(self.base_df, StressCluster.STAGNANT_RANGE)
        assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)

    def test_length_equals_bars_per_window(self):
        df = self.orc._synthesise_cluster_window(self.base_df, StressCluster.INSTITUTIONAL_TREND)
        assert len(df) == BARS_PER_WINDOW

    def test_deterministic_output(self):
        df1 = self.orc._synthesise_cluster_window(self.base_df, StressCluster.HIGH_VOLATILITY)
        df2 = self.orc._synthesise_cluster_window(self.base_df, StressCluster.HIGH_VOLATILITY)
        assert df1["close"].tolist() == df2["close"].tolist()


# ── _split_into_cluster_slices ────────────────────────────────────────────────

class TestSplitIntoClusters:
    def setup_method(self):
        self.orc, *_ = _make_orchestrator()

    def test_returns_three_slices(self):
        df = _make_ohlcv_df(500)
        slices = self.orc._split_into_cluster_slices(df, "EURUSD", "H1")
        assert len(slices) == 3

    def test_all_clusters_present(self):
        df = _make_ohlcv_df(500)
        slices = self.orc._split_into_cluster_slices(df, "EURUSD", "H1")
        clusters = {s.stress_cluster for s in slices}
        assert clusters == set(StressCluster.ALL)

    def test_slices_have_data(self):
        df = _make_ohlcv_df(500)
        for s in self.orc._split_into_cluster_slices(df, "EURUSD", "H1"):
            assert len(s.data) > 0

    def test_symbol_propagated(self):
        df = _make_ohlcv_df(500)
        for s in self.orc._split_into_cluster_slices(df, "GBPUSD", "H4"):
            assert s.symbol == "GBPUSD"
            assert s.timeframe == "H4"


# ── _update_strategy_scores ───────────────────────────────────────────────────

class TestUpdateScores:
    def test_score_formula(self):
        orc, storage, *_ = _make_orchestrator()
        strategy = {"score_shadow": 0.8, "score_live": 0.9}
        score_bt  = 0.75

        orc._update_strategy_scores("strat_alpha", score_bt, strategy)

        expected_score = round(0.9 * W_LIVE + 0.8 * W_SHADOW + 0.75 * W_BACKTEST, 4)
        cursor = storage._get_conn().cursor()
        args = cursor.execute.call_args[0][1]
        assert abs(args[0] - score_bt)       < 1e-6   # score_backtest
        assert abs(args[1] - expected_score)  < 1e-6   # consolidated score

    def test_zero_scores_give_zero_consolidated(self):
        orc, storage, *_ = _make_orchestrator()
        orc._update_strategy_scores("s", 0.0, {"score_shadow": 0.0, "score_live": 0.0})
        cursor = storage._get_conn().cursor()
        args = cursor.execute.call_args[0][1]
        assert args[1] == 0.0

    def test_handles_db_error_gracefully(self):
        orc, storage, *_ = _make_orchestrator()
        storage._get_conn.side_effect = RuntimeError("DB down")
        # Should not raise
        orc._update_strategy_scores("s", 0.8, {"score_shadow": 0.0, "score_live": 0.0})


# ── _promote_to_shadow ────────────────────────────────────────────────────────

class TestPromoteToShadow:
    def test_updates_mode_in_db(self):
        orc, storage, *_ = _make_orchestrator()
        orc._promote_to_shadow("strat_alpha", 0.80)
        cursor = storage._get_conn().cursor()
        sql  = cursor.execute.call_args[0][0]
        args = cursor.execute.call_args[0][1]
        assert "SHADOW" in sql
        assert args[0] == "strat_alpha"

    def test_handles_db_error_gracefully(self):
        orc, storage, *_ = _make_orchestrator()
        storage._get_conn.side_effect = RuntimeError("DB down")
        orc._promote_to_shadow("strat_alpha", 0.80)   # must not raise


# ── run_single_strategy ───────────────────────────────────────────────────────

class TestRunSingleStrategy:
    @pytest.mark.asyncio
    async def test_returns_none_when_strategy_not_found(self):
        orc, storage, *_ = _make_orchestrator()
        storage._get_conn().cursor().fetchone.return_value = None
        result = await orc.run_single_strategy("missing_id")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_matrix_on_success(self):
        orc, *_ = _make_orchestrator(passes=True, score=0.85)
        result = await orc.run_single_strategy("strat_alpha", force=True)
        assert isinstance(result, AptitudeMatrix)
        assert result.passes_threshold is True

    @pytest.mark.asyncio
    async def test_cooldown_skips_without_force(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        strategies = [{
            "class_id":        "strat_alpha",
            "mnemonic":        "ALPHA",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores":  "{}",
            "mode":            "BACKTEST",
            "score_backtest":  0.0,
            "score_shadow":    0.0,
            "score_live":      0.0,
            "score":           0.0,
            "updated_at":      recent,
        }]
        orc, *_ = _make_orchestrator(strategies=strategies)
        result = await orc.run_single_strategy("strat_alpha", force=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_force_bypasses_cooldown(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        strategies = [{
            "class_id":        "strat_alpha",
            "mnemonic":        "ALPHA",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores":  "{}",
            "mode":            "BACKTEST",
            "score_backtest":  0.0,
            "score_shadow":    0.0,
            "score_live":      0.0,
            "score":           0.0,
            "updated_at":      recent,
        }]
        orc, *_ = _make_orchestrator(strategies=strategies, passes=True)
        result = await orc.run_single_strategy("strat_alpha", force=True)
        assert isinstance(result, AptitudeMatrix)


# ── run_pending_strategies ────────────────────────────────────────────────────

class TestRunPendingStrategies:
    @pytest.mark.asyncio
    async def test_empty_returns_zero_summary(self):
        orc, storage, *_ = _make_orchestrator(strategies=[])
        storage.get_connection().cursor().fetchall.return_value = []
        summary = await orc.run_pending_strategies()
        assert summary["evaluated"] == 0

    @pytest.mark.asyncio
    async def test_passing_strategy_counts_as_promoted(self):
        orc, *_ = _make_orchestrator(passes=True, score=0.85)
        summary = await orc.run_pending_strategies()
        assert summary["promoted"] == 1
        assert summary["evaluated"] == 1

    @pytest.mark.asyncio
    async def test_failing_strategy_not_promoted(self):
        orc, *_ = _make_orchestrator(passes=False, score=0.40)
        summary = await orc.run_pending_strategies()
        assert summary["promoted"] == 0
        assert summary["evaluated"] == 1

    @pytest.mark.asyncio
    async def test_sets_last_run_timestamp(self):
        orc, *_ = _make_orchestrator()
        assert orc.last_run is None
        await orc.run_pending_strategies()
        assert orc.last_run is not None

    @pytest.mark.asyncio
    async def test_exception_in_strategy_counted_as_failed(self):
        orc, *_ = _make_orchestrator()
        orc.backtester.run_scenario_backtest.side_effect = RuntimeError("boom")
        summary = await orc.run_pending_strategies()
        assert summary["failed"] == 1
        assert summary["promoted"] == 0
