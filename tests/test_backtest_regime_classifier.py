"""
Tests: BacktestOrchestrator — RegimeClassifier real en pipeline de clasificación de ventanas
=============================================================================================
Verifica que BacktestOrchestrator usa RegimeClassifier (ADX/ATR/SMA) para
clasificar ventanas en _split_into_cluster_slices(), en lugar de la heurística
simple de ATR ratio + trend slope.

Casos de prueba:
1. _classify_window_regime() usa RegimeClassifier para clasificar ventanas.
2. El resultado de RegimeClassifier se mapea correctamente a StressCluster vía
   REGIME_TO_CLUSTER (incluyendo CRASH → HIGH_VOLATILITY y NORMAL → STAGNANT_RANGE).
3. _split_into_cluster_slices() llama a _classify_window_regime() en lugar de
   backtester._detect_regime() para cada ventana.
4. Si RegimeClassifier falla (excepción), hace fallback a _detect_regime().
5. MarketRegime.CRASH se mapea a HIGH_VOLATILITY.
6. MarketRegime.NORMAL se mapea a STAGNANT_RANGE.
7. Con datos insuficientes (<28 bars) RegimeClassifier cae al fallback.
"""

import json
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
import pytest

from core_brain.backtest_orchestrator import BacktestOrchestrator, REGIME_TO_CLUSTER
from core_brain.scenario_backtester import ScenarioBacktester, StressCluster


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trend_df(n: int = 130) -> pd.DataFrame:
    close = [1.1000 + i * 0.0005 for i in range(n)]
    return pd.DataFrame({
        "open":  [c - 0.0001 for c in close],
        "high":  [c + 0.0004 for c in close],
        "low":   [c - 0.0004 for c in close],
        "close": close,
        "volume": [1000.0] * n,
    })


def _make_range_df(n: int = 130) -> pd.DataFrame:
    import math
    close = [1.1000 + 0.0010 * math.sin(i * 0.3) for i in range(n)]
    return pd.DataFrame({
        "open":  [c - 0.0001 for c in close],
        "high":  [c + 0.0004 for c in close],
        "low":   [c - 0.0004 for c in close],
        "close": close,
        "volume": [1000.0] * n,
    })


_CFG_ROW = (json.dumps({
    "cooldown_hours": 0,
    "min_trades_per_cluster": 1,
    "bars_per_window": 60,
    "bars_fetch_initial": 130,
    "bars_fetch_max": 260,
    "bars_fetch_retry": 60,
    "promotion_min_score": 0.75,
    "default_symbol": "EURUSD",
    "default_timeframe": "H1",
    "score_weights": {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
}),)


def _make_orchestrator(df: pd.DataFrame):
    storage = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    storage._get_conn.return_value = conn
    cursor.fetchone.return_value = _CFG_ROW

    dpm = MagicMock()
    dpm.fetch_ohlc.return_value = df

    backtester = MagicMock(spec=ScenarioBacktester)
    backtester._detect_regime.return_value = "RANGE"  # fallback value

    return BacktestOrchestrator(
        storage=storage,
        data_provider_manager=dpm,
        scenario_backtester=backtester,
    ), backtester


# ── Tests: REGIME_TO_CLUSTER mapping completo ─────────────────────────────────

class TestRegimeToClusterMapping:

    def test_crash_maps_to_high_volatility(self):
        assert REGIME_TO_CLUSTER.get("CRASH") == StressCluster.HIGH_VOLATILITY

    def test_normal_maps_to_stagnant_range(self):
        assert REGIME_TO_CLUSTER.get("NORMAL") == StressCluster.STAGNANT_RANGE

    def test_trend_maps_to_institutional_trend(self):
        assert REGIME_TO_CLUSTER.get("TREND") == StressCluster.INSTITUTIONAL_TREND

    def test_range_maps_to_stagnant_range(self):
        assert REGIME_TO_CLUSTER.get("RANGE") == StressCluster.STAGNANT_RANGE

    def test_volatile_maps_to_high_volatility(self):
        assert REGIME_TO_CLUSTER.get("VOLATILE") == StressCluster.HIGH_VOLATILITY


# ── Tests: _classify_window_regime ───────────────────────────────────────────

class TestClassifyWindowRegime:

    def test_method_exists(self):
        """BacktestOrchestrator debe tener _classify_window_regime()."""
        orc, _ = _make_orchestrator(_make_trend_df())
        assert hasattr(orc, "_classify_window_regime")

    def test_returns_string(self):
        """_classify_window_regime() retorna un string de régimen."""
        orc, _ = _make_orchestrator(_make_trend_df())
        result = orc._classify_window_regime(_make_trend_df(60))
        assert isinstance(result, str)
        assert result in {"TREND", "RANGE", "VOLATILE", "CRASH", "NORMAL"}

    def test_uses_regime_classifier_not_detect_regime(self):
        """Debe usar RegimeClassifier, no backtester._detect_regime()."""
        orc, backtester = _make_orchestrator(_make_trend_df())
        from models.signal import MarketRegime

        with patch("core_brain.backtest_orchestrator.RegimeClassifier") as MockRC:
            instance = MagicMock()
            instance.classify.return_value = MarketRegime.TREND
            MockRC.return_value = instance

            result = orc._classify_window_regime(_make_trend_df(60))

        MockRC.assert_called_once()
        instance.load_ohlc.assert_called_once()
        instance.classify.assert_called_once()
        assert result == "TREND"
        backtester._detect_regime.assert_not_called()

    def test_falls_back_when_regime_classifier_raises(self):
        """Si RegimeClassifier lanza excepción, hace fallback a _detect_regime()."""
        orc, backtester = _make_orchestrator(_make_trend_df())
        backtester._detect_regime.return_value = "RANGE"

        with patch("core_brain.backtest_orchestrator.RegimeClassifier", side_effect=Exception("import error")):
            result = orc._classify_window_regime(_make_trend_df(60))

        backtester._detect_regime.assert_called_once()
        assert result == "RANGE"

    def test_crash_regime_returned_as_string(self):
        """MarketRegime.CRASH debe convertirse al string 'CRASH'."""
        orc, _ = _make_orchestrator(_make_trend_df())
        from models.signal import MarketRegime

        with patch("core_brain.backtest_orchestrator.RegimeClassifier") as MockRC:
            instance = MagicMock()
            instance.classify.return_value = MarketRegime.CRASH
            MockRC.return_value = instance

            result = orc._classify_window_regime(_make_trend_df(60))

        assert result == "CRASH"

    def test_normal_regime_returned_as_string(self):
        """MarketRegime.NORMAL debe convertirse al string 'NORMAL'."""
        orc, _ = _make_orchestrator(_make_trend_df())
        from models.signal import MarketRegime

        with patch("core_brain.backtest_orchestrator.RegimeClassifier") as MockRC:
            instance = MagicMock()
            instance.classify.return_value = MarketRegime.NORMAL
            MockRC.return_value = instance

            result = orc._classify_window_regime(_make_trend_df(60))

        assert result == "NORMAL"


# ── Tests: _split_into_cluster_slices usa RegimeClassifier ────────────────────

class TestSplitIntoClusterSlicesUsesClassifier:

    def test_split_calls_classify_window_regime_not_detect_regime(self):
        """_split_into_cluster_slices debe llamar _classify_window_regime()."""
        orc, backtester = _make_orchestrator(_make_trend_df())
        from models.signal import MarketRegime

        with patch.object(orc, "_classify_window_regime", return_value="TREND") as mock_classify:
            orc._split_into_cluster_slices(_make_trend_df(130), "EURUSD", "H1")

        assert mock_classify.call_count > 0
        # backtester._detect_regime should NOT be called for window classification
        backtester._detect_regime.assert_not_called()

    def test_split_maps_crash_windows_to_high_volatility(self):
        """Ventanas clasificadas como CRASH deben ir al cluster HIGH_VOLATILITY."""
        orc, _ = _make_orchestrator(_make_trend_df())

        with patch.object(orc, "_classify_window_regime", return_value="CRASH"):
            slices = orc._split_into_cluster_slices(_make_trend_df(130), "EURUSD", "H1")

        hv_slices = [s for s in slices if s.stress_cluster == StressCluster.HIGH_VOLATILITY and s.is_real_data]
        assert len(hv_slices) >= 1

    def test_split_maps_normal_windows_to_stagnant_range(self):
        """Ventanas clasificadas como NORMAL deben ir al cluster STAGNANT_RANGE."""
        orc, _ = _make_orchestrator(_make_range_df())

        with patch.object(orc, "_classify_window_regime", return_value="NORMAL"):
            slices = orc._split_into_cluster_slices(_make_range_df(130), "EURUSD", "H1")

        sr_slices = [s for s in slices if s.stress_cluster == StressCluster.STAGNANT_RANGE and s.is_real_data]
        assert len(sr_slices) >= 1
