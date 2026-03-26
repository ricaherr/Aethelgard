"""
Tests for HU 7.16 — Filtro de compatibilidad de régimen pre-evaluación
Trace_ID: EDGE-BKT-716-REGIME-FILTER-2026-03-24

Acceptance criteria:
  AC1: Estrategia con required_regime='TREND' NO fetchea datos de un par en RANGE
       → par queda marcado REGIME_INCOMPATIBLE con timestamp
  AC2: El par queda marcado REGIME_INCOMPATIBLE con timestamp (campo last_updated)
  AC3: Estrategias con required_regime='ANY' no aplican el filtro (siempre pasan)
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_ohlc_df(n: int = 50, trend: bool = True) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with `n` rows."""
    close = [1.1000 + (0.0010 * i if trend else 0) for i in range(n)]
    return pd.DataFrame({
        "open":   close,
        "high":   [c + 0.0005 for c in close],
        "low":    [c - 0.0005 for c in close],
        "close":  close,
        "volume": [1000] * n,
    })


def _make_strategy(required_regime: str = "ANY", symbols: Optional[List[str]] = None) -> Dict:
    if symbols is None:
        symbols = ["EURUSD"]
    return {
        "class_id":        "strat_regime_filter_test",
        "name":            "Regime Filter Test Strategy",
        "mode":            "BACKTEST",
        "required_regime": required_regime,
        "market_whitelist": json.dumps(symbols),
        "timeframes":      json.dumps(["M15"]),
        "affinity_scores": "{}",
        "execution_params": json.dumps({}),
        "updated_at":      "2026-01-01T00:00:00",
        "last_backtest_at": None,
    }


def _make_backtester_mock(detected_regime: str = "RANGE") -> MagicMock:
    """Mock ScenarioBacktester with _detect_regime returning `detected_regime`."""
    mock = MagicMock()
    mock.MIN_REGIME_SCORE = 0.75
    mock._detect_regime.return_value = detected_regime
    return mock


def _make_orchestrator(detected_regime: str = "RANGE"):
    """Build a BacktestOrchestrator with mocked storage and data providers."""
    from core_brain.backtest_orchestrator import BacktestOrchestrator

    storage = MagicMock()
    storage._get_conn.return_value = sqlite3.connect(":memory:")

    dpm = MagicMock()
    ohlc_df = _make_ohlc_df(50)
    dpm.fetch_ohlc.return_value = ohlc_df.to_dict("records")

    orc = BacktestOrchestrator.__new__(BacktestOrchestrator)
    orc.storage      = storage
    orc.dpm          = dpm
    orc.backtester   = _make_backtester_mock(detected_regime)
    orc._cfg         = {"cooldown_hours": 0, "confidence_k": 20, "max_bars": 200}
    orc._rr_state    = {}
    orc._rr_lock     = __import__("threading").Lock()
    return orc


# ──────────────────────────────────────────────────────────────────────────────
# AC3: required_regime='ANY' — filtro no aplica nunca
# ──────────────────────────────────────────────────────────────────────────────

class TestRegimeFilterAny:
    """AC3: Estrategias con required_regime='ANY' no aplican el filtro."""

    def test_any_regime_always_passes_regardless_of_detected(self):
        """ANY always returns True even if detected regime is RANGE."""
        orc = _make_orchestrator(detected_regime="RANGE")
        strategy = _make_strategy(required_regime="ANY")
        result = orc._passes_regime_prefilter(strategy, "EURUSD", "M15")
        assert result is True

    def test_any_regime_passes_when_detected_trend(self):
        orc = _make_orchestrator(detected_regime="TREND")
        strategy = _make_strategy(required_regime="ANY")
        assert orc._passes_regime_prefilter(strategy, "GBPUSD", "H1") is True

    def test_missing_required_regime_treated_as_any(self):
        """Missing required_regime key → treated as ANY → True."""
        orc = _make_orchestrator(detected_regime="RANGE")
        strategy = _make_strategy(required_regime="ANY")
        strategy.pop("required_regime")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True

    def test_none_required_regime_treated_as_any(self):
        orc = _make_orchestrator(detected_regime="VOLATILE")
        strategy = _make_strategy(required_regime="ANY")
        strategy["required_regime"] = None
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True


# ──────────────────────────────────────────────────────────────────────────────
# AC1: required_regime='TREND' → False when detected RANGE
# ──────────────────────────────────────────────────────────────────────────────

class TestRegimeFilterMismatch:
    """AC1: Estrategia con required_regime='TREND' no fetchea datos cuando el régimen es RANGE."""

    def test_trend_strategy_blocked_in_range_regime(self):
        """_passes_regime_prefilter returns False → symbol skipped."""
        orc = _make_orchestrator(detected_regime="RANGE")
        strategy = _make_strategy(required_regime="TREND")
        result = orc._passes_regime_prefilter(strategy, "EURUSD", "M15")
        assert result is False

    def test_range_strategy_blocked_in_trend_regime(self):
        orc = _make_orchestrator(detected_regime="TREND")
        strategy = _make_strategy(required_regime="RANGE")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is False

    def test_trend_strategy_passes_in_trend_regime(self):
        orc = _make_orchestrator(detected_regime="TREND")
        strategy = _make_strategy(required_regime="TREND")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True

    def test_regime_alias_trending_normalised_to_trend(self):
        """'TRENDING' alias → treated as 'TREND'."""
        orc = _make_orchestrator(detected_regime="TREND")
        strategy = _make_strategy(required_regime="TRENDING")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True

    def test_fail_open_when_insufficient_bars(self):
        """Fewer than 14 bars → fail-open (return True, don't block)."""
        orc = _make_orchestrator(detected_regime="RANGE")
        orc.dpm.fetch_ohlc.return_value = _make_ohlc_df(10).to_dict("records")
        strategy = _make_strategy(required_regime="TREND")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True

    def test_fail_open_when_no_data(self):
        """Empty data → fail-open."""
        orc = _make_orchestrator()
        orc.dpm.fetch_ohlc.return_value = []
        strategy = _make_strategy(required_regime="TREND")
        assert orc._passes_regime_prefilter(strategy, "EURUSD", "M15") is True


# ──────────────────────────────────────────────────────────────────────────────
# AC2: _write_regime_incompatible persiste el estado con timestamp
# ──────────────────────────────────────────────────────────────────────────────

class TestWriteRegimeIncompatible:
    """AC2: El par queda marcado REGIME_INCOMPATIBLE con timestamp."""

    def _make_in_memory_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE sys_strategies (
                class_id TEXT PRIMARY KEY,
                affinity_scores TEXT DEFAULT '{}'
            )
        """)
        conn.execute(
            "INSERT INTO sys_strategies (class_id, affinity_scores) VALUES (?, ?)",
            ("strat_regime_filter_test", "{}"),
        )
        conn.commit()
        return conn

    def test_regime_incompatible_status_written(self):
        """Status REGIME_INCOMPATIBLE is recorded for the symbol."""
        orc = _make_orchestrator()
        conn = self._make_in_memory_db()
        cursor = conn.cursor()
        strategy = _make_strategy(required_regime="TREND")

        orc._write_regime_incompatible(cursor, "strat_regime_filter_test", "EURUSD", strategy)
        conn.commit()

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat_regime_filter_test",)
        ).fetchone()
        data = json.loads(row[0])
        assert "EURUSD" in data
        assert data["EURUSD"]["status"] == "REGIME_INCOMPATIBLE"

    def test_regime_incompatible_includes_timestamp(self):
        """Entry must have a last_updated timestamp."""
        orc = _make_orchestrator()
        conn = self._make_in_memory_db()
        cursor = conn.cursor()
        strategy = _make_strategy(required_regime="TREND")

        orc._write_regime_incompatible(cursor, "strat_regime_filter_test", "EURUSD", strategy)
        conn.commit()

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat_regime_filter_test",)
        ).fetchone()
        data = json.loads(row[0])
        ts = data["EURUSD"].get("last_updated")
        assert ts is not None
        # Validate ISO 8601 format
        datetime.fromisoformat(ts)

    def test_regime_incompatible_preserves_historical_data(self):
        """Historical score/cycles data is NOT wiped when writing REGIME_INCOMPATIBLE."""
        orc = _make_orchestrator()
        conn = self._make_in_memory_db()
        existing = json.dumps({
            "EURUSD": {
                "score": 0.65,
                "n_trades": 42,
                "status": "QUALIFIED",
                "last_updated": "2026-01-01T00:00:00+00:00",
            }
        })
        conn.execute(
            "UPDATE sys_strategies SET affinity_scores = ? WHERE class_id = ?",
            (existing, "strat_regime_filter_test"),
        )
        conn.commit()

        cursor = conn.cursor()
        strategy = _make_strategy(required_regime="TREND")
        orc._write_regime_incompatible(cursor, "strat_regime_filter_test", "EURUSD", strategy)
        conn.commit()

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat_regime_filter_test",)
        ).fetchone()
        data = json.loads(row[0])
        entry = data["EURUSD"]
        # Status updated
        assert entry["status"] == "REGIME_INCOMPATIBLE"
        # Historical data preserved
        assert entry["score"] == 0.65
        assert entry["n_trades"] == 42

    def test_regime_incompatible_does_not_affect_other_symbols(self):
        """Only the incompatible symbol's entry is written; others untouched."""
        orc = _make_orchestrator()
        conn = self._make_in_memory_db()
        existing = json.dumps({
            "GBPUSD": {"score": 0.70, "status": "QUALIFIED"}
        })
        conn.execute(
            "UPDATE sys_strategies SET affinity_scores = ? WHERE class_id = ?",
            (existing, "strat_regime_filter_test"),
        )
        conn.commit()

        cursor = conn.cursor()
        strategy = _make_strategy(required_regime="TREND")
        orc._write_regime_incompatible(cursor, "strat_regime_filter_test", "EURUSD", strategy)
        conn.commit()

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat_regime_filter_test",)
        ).fetchone()
        data = json.loads(row[0])
        assert data["GBPUSD"]["score"] == 0.70
        assert data["GBPUSD"]["status"] == "QUALIFIED"
        assert data["EURUSD"]["status"] == "REGIME_INCOMPATIBLE"
