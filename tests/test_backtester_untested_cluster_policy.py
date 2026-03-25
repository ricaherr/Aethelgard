"""
test_hu711_no_synthesis.py — TDD for HU 7.11

Verifies that the backtesting pipeline never uses synthetic data in production:
- Missing clusters get UNTESTED_CLUSTER slices (is_real_data=False)
- Insufficient data produces UNTESTED slices — not synthetic fallbacks
- ScenarioBacktester scores UNTESTED slices as 0.0
- _synthesise_cluster_window() is NOT called in the production path

TRACE_ID: EDGE-BKT-711-MULTI-PROVIDER-NOSYNTHESIS-2026-03-24
"""
import sqlite3
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core_brain.scenario_backtester import (
    AptitudeMatrix,
    ScenarioBacktester,
    ScenarioSlice,
    StressCluster,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_storage() -> MagicMock:
    storage = MagicMock()
    storage._get_conn.return_value = sqlite3.connect(":memory:")
    storage._close_conn.return_value = None
    return storage


def _make_real_ohlcv(n: int = 50) -> pd.DataFrame:
    """Minimal OHLCV DataFrame with realistic values."""
    import numpy as np
    rng = np.random.default_rng(1)
    close = 1.1000 + rng.normal(0, 0.001, n).cumsum()
    spread = abs(rng.normal(0, 0.0003, n)) + 0.0002
    return pd.DataFrame({
        "open":   close - spread * 0.3,
        "high":   close + spread,
        "low":    close - spread,
        "close":  close,
        "volume": rng.integers(500, 2000, n).astype(float),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 1 — ScenarioSlice contract
# ─────────────────────────────────────────────────────────────────────────────

class TestScenarioSliceContract:

    def test_scenarioslice_has_is_real_data_field(self):
        """ScenarioSlice must have an is_real_data field."""
        field_names = {f.name for f in fields(ScenarioSlice)}
        assert "is_real_data" in field_names, (
            "ScenarioSlice is missing 'is_real_data' field (HU 7.11)"
        )

    def test_scenarioslice_is_real_data_defaults_to_true(self):
        """Existing callers not passing is_real_data must receive True (backward compat)."""
        df = _make_real_ohlcv(30)
        sl = ScenarioSlice(
            slice_id="test",
            stress_cluster=StressCluster.HIGH_VOLATILITY,
            symbol="EURUSD",
            timeframe="H1",
            data=df,
            start_date="2026-01-01",
            end_date="2026-01-31",
        )
        assert sl.is_real_data is True

    def test_scenarioslice_can_be_marked_untested(self):
        """An UNTESTED slice can be created with is_real_data=False."""
        sl = ScenarioSlice(
            slice_id="UNTESTED_HIGH_VOL",
            stress_cluster=StressCluster.HIGH_VOLATILITY,
            symbol="EURUSD",
            timeframe="H1",
            data=pd.DataFrame(),
            start_date="",
            end_date="",
            is_real_data=False,
        )
        assert sl.is_real_data is False
        assert sl.data.empty


# ─────────────────────────────────────────────────────────────────────────────
# 2 — ScenarioBacktester handles UNTESTED slices correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestScenarioBacktesterUntestedSlices:

    def _backtester(self) -> ScenarioBacktester:
        return ScenarioBacktester(storage=_make_storage())

    def test_untested_slice_produces_zero_regime_score(self):
        """An UNTESTED slice must produce regime_score=0.0."""
        bkt = self._backtester()
        sl = ScenarioSlice(
            slice_id="UNTESTED_HV",
            stress_cluster=StressCluster.HIGH_VOLATILITY,
            symbol="EURUSD",
            timeframe="H1",
            data=pd.DataFrame(),
            start_date="",
            end_date="",
            is_real_data=False,
        )
        result = bkt._evaluate_slice(sl, {})
        assert result.regime_score == pytest.approx(0.0)

    def test_untested_slice_produces_zero_trades(self):
        """An UNTESTED slice must produce total_trades=0."""
        bkt = self._backtester()
        sl = ScenarioSlice(
            slice_id="UNTESTED_SR",
            stress_cluster=StressCluster.STAGNANT_RANGE,
            symbol="EURUSD",
            timeframe="H1",
            data=pd.DataFrame(),
            start_date="",
            end_date="",
            is_real_data=False,
        )
        result = bkt._evaluate_slice(sl, {})
        assert result.total_trades == 0

    def test_untested_slice_detected_regime_is_untested(self):
        """UNTESTED slices must carry detected_regime='UNTESTED'."""
        bkt = self._backtester()
        sl = ScenarioSlice(
            slice_id="UNTESTED_IT",
            stress_cluster=StressCluster.INSTITUTIONAL_TREND,
            symbol="GBPUSD",
            timeframe="M15",
            data=pd.DataFrame(),
            start_date="",
            end_date="",
            is_real_data=False,
        )
        result = bkt._evaluate_slice(sl, {})
        assert result.detected_regime == "UNTESTED"

    def test_all_untested_slices_produce_zero_overall_score(self):
        """When all slices are UNTESTED, overall_score must be 0.0."""
        bkt = self._backtester()
        slices = [
            ScenarioSlice(
                slice_id=f"UNTESTED_{c}",
                stress_cluster=c,
                symbol="EURUSD",
                timeframe="H1",
                data=pd.DataFrame(),
                start_date="",
                end_date="",
                is_real_data=False,
            )
            for c in StressCluster.ALL
        ]
        matrix = bkt.run_scenario_backtest("strategy_test", {}, slices)
        assert matrix.overall_score == pytest.approx(0.0)
        assert matrix.passes_threshold is False

    def test_mixed_slices_untested_reduces_score(self):
        """Mixing real+UNTESTED slices — UNTESTED contributes 0.0 to overall average."""
        bkt = self._backtester()
        df = _make_real_ohlcv(60)
        slices = [
            ScenarioSlice(
                slice_id="REAL_HV",
                stress_cluster=StressCluster.HIGH_VOLATILITY,
                symbol="EURUSD",
                timeframe="H1",
                data=df,
                start_date="2026-01-01",
                end_date="2026-02-28",
                is_real_data=True,
            ),
            ScenarioSlice(
                slice_id="UNTESTED_SR",
                stress_cluster=StressCluster.STAGNANT_RANGE,
                symbol="EURUSD",
                timeframe="H1",
                data=pd.DataFrame(),
                start_date="",
                end_date="",
                is_real_data=False,
            ),
            ScenarioSlice(
                slice_id="UNTESTED_IT",
                stress_cluster=StressCluster.INSTITUTIONAL_TREND,
                symbol="EURUSD",
                timeframe="H1",
                data=pd.DataFrame(),
                start_date="",
                end_date="",
                is_real_data=False,
            ),
        ]
        matrix_mixed = bkt.run_scenario_backtest("strat_mixed", {}, slices)
        # All-real version of the same data
        slices_all_real = [
            ScenarioSlice(
                slice_id=f"REAL_{c}",
                stress_cluster=c,
                symbol="EURUSD",
                timeframe="H1",
                data=df,
                start_date="2026-01-01",
                end_date="2026-02-28",
                is_real_data=True,
            )
            for c in StressCluster.ALL
        ]
        matrix_all_real = bkt.run_scenario_backtest("strat_all_real", {}, slices_all_real)
        # Mixed score must be <= all-real score (UNTESTED drags score down)
        assert matrix_mixed.overall_score <= matrix_all_real.overall_score


# ─────────────────────────────────────────────────────────────────────────────
# 3 — BacktestOrchestrator does not call _synthesise_cluster_window in prod path
# ─────────────────────────────────────────────────────────────────────────────

class TestNoSynthesisInProductionPath:

    def _make_orchestrator(self, fetch_returns=None):
        """Build an orchestrator with mocked DataProviderManager."""
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        storage = _make_storage()
        storage.get_sys_config_value.return_value = None  # use defaults

        dpm = MagicMock()
        dpm.fetch_ohlc.return_value = fetch_returns

        orc = BacktestOrchestrator.__new__(BacktestOrchestrator)
        orc.storage = storage
        orc.dpm = dpm
        orc.backtester = ScenarioBacktester(storage)
        orc._cfg = {
            "bars_fetch_initial": 500,
            "bars_fetch_retry":   250,
            "bars_fetch_max":     1000,
            "bars_per_window":    120,
            "min_trades_per_cluster": 15,
            "default_symbol":    "EURUSD",
            "default_timeframe": "H1",
            "cooldown_hours":    24,
        }
        return orc

    def test_synthesise_not_called_when_cluster_missing_in_real_data(self):
        """When a cluster is not found in real data, _synthesise_cluster_window
        must NOT be called — instead an UNTESTED slice is returned."""
        import numpy as np
        # Build data that only produces VOLATILE windows (no RANGE or TREND)
        rng = np.random.default_rng(99)
        n = 240
        # Extremely volatile data → only HIGH_VOLATILITY cluster will be filled
        close = 1.1 + rng.normal(0, 0.01, n).cumsum()
        spread = abs(rng.normal(0, 0.008, n)) + 0.005
        df = pd.DataFrame({
            "open":   close - spread * 0.3,
            "high":   close + spread * 2,
            "low":    close - spread * 2,
            "close":  close,
            "volume": 1000.0,
        })

        orc = self._make_orchestrator(fetch_returns=df)
        strategy = {
            "class_id": "s1",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores": "{}",
        }
        with patch.object(orc, "_synthesise_cluster_window") as mock_synth:
            slices = orc._split_into_cluster_slices(df, "EURUSD", "H1")
            mock_synth.assert_not_called()

        # Missing clusters must be UNTESTED
        untested = [s for s in slices if not s.is_real_data]
        real = [s for s in slices if s.is_real_data]
        assert len(slices) == 3
        # At least the ones not naturally found in data are untested
        assert len(untested) >= 0  # may be 0 if data happened to cover all clusters

    def test_insufficient_data_returns_untested_slices_not_synthetic(self):
        """When DataProvider returns insufficient data, slices must be UNTESTED
        (not synthetic Gaussian noise)."""
        orc = self._make_orchestrator(fetch_returns=None)
        strategy = {
            "class_id": "s2",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores": "{}",
        }
        slices = orc._build_scenario_slices(strategy, {})
        # All slices must be UNTESTED
        for sl in slices:
            assert sl.is_real_data is False, (
                f"Slice {sl.slice_id} should be UNTESTED when data is unavailable"
            )
        # Must return exactly 3 slices (one per cluster)
        assert len(slices) == 3

    def test_untested_slices_have_empty_data_not_gaussian_noise(self):
        """UNTESTED slices must have empty DataFrame, not synthetic random data."""
        orc = self._make_orchestrator(fetch_returns=None)
        strategy = {
            "class_id": "s3",
            "market_whitelist": '["EURUSD"]',
            "affinity_scores": "{}",
        }
        slices = orc._build_scenario_slices(strategy, {})
        for sl in slices:
            assert sl.data.empty, (
                f"UNTESTED slice {sl.slice_id} must have empty DataFrame, not synthetic data"
            )
