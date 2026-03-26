"""
HU 7.15: Score con confianza estadística n/(n+k).
Trace_ID: EDGE-BKT-715-CONFIDENCE-SCORING-2026-03-24

TDD Red Phase: these tests MUST FAIL before implementation.

Validates:
  1. confidence(0, k)   = 0.0
  2. confidence(k, k)   = 0.5
  3. confidence(200, 20) ≈ 0.909
  4. Parametric: n=0,5,10,20,30,50,100 values monotonically increase
  5. effective_score = raw_score × confidence(n_trades, k)
  6. Strategy with 5 trades receives PENDING, not QUALIFIED (low confidence)
  7. k is read from execution_params (not hardcoded)
  8. k defaults to 20 when absent from execution_params
  9. Status REJECTED requires both effective_score < 0.20 AND confidence >= 0.50
 10. Status PENDING when effective_score < 0.20 but confidence < 0.50 (few trades)
 11. confidence field in affinity entry is no longer 1.0 placeholder
 12. effective_score differs from raw_score when n_trades is small
"""
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_with_strategy(execution_params=None):
    ep = execution_params or {}
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE sys_strategies (
            class_id TEXT PRIMARY KEY,
            mnemonic TEXT,
            market_whitelist TEXT DEFAULT '[]',
            affinity_scores TEXT DEFAULT '{}',
            execution_params TEXT DEFAULT '{}',
            mode TEXT DEFAULT 'BACKTEST',
            score_backtest REAL DEFAULT 0.0,
            score_shadow REAL DEFAULT 0.0,
            score_live REAL DEFAULT 0.0,
            score REAL DEFAULT 0.0,
            updated_at TEXT,
            last_backtest_at TEXT,
            required_timeframes TEXT DEFAULT '[]',
            required_regime TEXT DEFAULT 'ANY'
        )
    """)
    conn.execute(
        "INSERT INTO sys_strategies (class_id, mnemonic, execution_params) VALUES (?,?,?)",
        ("s1", "Strat", json.dumps(ep)),
    )
    conn.commit()
    return conn


def _make_orchestrator(conn):
    from core_brain.backtest_orchestrator import BacktestOrchestrator
    mock_storage = MagicMock()
    mock_storage._get_conn.return_value = conn
    mock_storage.get_sys_config.return_value = {}
    mock_dpm = MagicMock()
    mock_bt = MagicMock()
    mock_bt.MIN_REGIME_SCORE = 0.75
    orch = BacktestOrchestrator(
        storage=mock_storage,
        data_provider_manager=mock_dpm,
        scenario_backtester=mock_bt,
    )
    return orch


def _make_matrix(n_trades=20, raw_score=0.80):
    from core_brain.scenario_backtester import AptitudeMatrix, RegimeResult, StressCluster
    result = RegimeResult(
        stress_cluster=StressCluster.INSTITUTIONAL_TREND,
        detected_regime="TREND",
        profit_factor=2.5,
        max_drawdown_pct=0.08,
        total_trades=n_trades,
        win_rate=0.65,
        regime_score=raw_score,
    )
    return AptitudeMatrix(
        strategy_id="s1",
        parameter_overrides={},
        overall_score=raw_score,
        passes_threshold=False,
        results_by_regime=[result],
        trace_id="T",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _strategy_row(execution_params=None):
    ep = execution_params or {}
    return {
        "class_id": "s1",
        "mnemonic": "Strat",
        "market_whitelist": '["EURUSD"]',
        "affinity_scores": "{}",
        "execution_params": json.dumps(ep),
        "required_timeframes": "[]",
        "required_regime": "ANY",
    }


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestConfidenceFormula(unittest.TestCase):
    """Unit tests for the confidence(n, k) = n/(n+k) formula."""

    def _confidence(self, n, k=20):
        from core_brain.backtest_orchestrator import compute_confidence
        return compute_confidence(n, k)

    def test_confidence_zero_trades_is_zero(self):
        """confidence(0, k) must be 0.0 — no data, no confidence."""
        self.assertEqual(self._confidence(0, 20), 0.0)

    def test_confidence_n_equals_k_is_half(self):
        """confidence(k, k) must be 0.5."""
        self.assertAlmostEqual(self._confidence(20, 20), 0.5, places=6)

    def test_confidence_200_trades_k20(self):
        """confidence(200, 20) must be ≈ 0.909 (200/220)."""
        self.assertAlmostEqual(self._confidence(200, 20), 200 / 220, places=6)

    def test_confidence_monotonically_increases_with_n(self):
        """More trades → higher confidence."""
        ns = [0, 5, 10, 20, 30, 50, 100]
        values = [self._confidence(n, 20) for n in ns]
        for i in range(len(values) - 1):
            self.assertLess(values[i], values[i + 1],
                            f"confidence({ns[i]}) must be < confidence({ns[i+1]})")

    def test_confidence_with_custom_k(self):
        """k=10: confidence(10, 10) = 0.5."""
        self.assertAlmostEqual(self._confidence(10, 10), 0.5, places=6)

    def test_confidence_returns_float(self):
        """compute_confidence must return a float."""
        self.assertIsInstance(self._confidence(50, 20), float)


class TestEffectiveScore(unittest.TestCase):
    """Tests that effective_score = raw_score × confidence is applied correctly."""

    def _write_and_read(self, n_trades, raw_score, k=20, execution_params=None):
        ep = dict(execution_params or {})
        if k != 20:
            ep["confidence_k"] = k
        conn = _make_conn_with_strategy(ep)
        orch = _make_orchestrator(conn)
        strategy = _strategy_row(ep)
        matrix = _make_matrix(n_trades=n_trades, raw_score=raw_score)

        cursor = conn.cursor()
        orch._write_pair_affinity(cursor, "s1", "EURUSD", raw_score, matrix, strategy)
        conn.commit()

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id='s1'"
        ).fetchone()
        return json.loads(row[0]).get("EURUSD", {})

    def test_effective_score_equals_raw_times_confidence(self):
        """effective_score must be raw_score × confidence(n_trades, k)."""
        entry = self._write_and_read(n_trades=20, raw_score=0.80, k=20)
        expected_conf     = 20 / (20 + 20)   # 0.5
        expected_effective = round(0.80 * expected_conf, 4)
        self.assertAlmostEqual(entry["effective_score"], expected_effective, places=4)

    def test_confidence_field_is_not_one(self):
        """confidence field must no longer be the 1.0 placeholder."""
        entry = self._write_and_read(n_trades=20, raw_score=0.80)
        self.assertNotEqual(entry["confidence"], 1.0,
                            "confidence must be n/(n+k), not the 1.0 placeholder")

    def test_confidence_field_correct_value(self):
        """confidence field must equal n/(n+k)."""
        entry = self._write_and_read(n_trades=20, raw_score=0.80, k=20)
        self.assertAlmostEqual(entry["confidence"], 0.5, places=4)

    def test_effective_differs_from_raw_with_few_trades(self):
        """With few trades, effective_score must be noticeably lower than raw_score."""
        entry = self._write_and_read(n_trades=5, raw_score=0.90, k=20)
        self.assertLess(entry["effective_score"], entry["raw_score"],
                        "effective_score must be < raw_score when n_trades is small")

    def test_k_read_from_execution_params(self):
        """k=10 in execution_params must produce confidence(20,10)=20/30≈0.667."""
        entry = self._write_and_read(n_trades=20, raw_score=1.0, k=10)
        self.assertAlmostEqual(entry["confidence"], round(20 / 30, 4), places=4)

    def test_k_defaults_to_20_when_absent(self):
        """When execution_params has no confidence_k, default k=20 must be used."""
        entry = self._write_and_read(n_trades=20, raw_score=1.0)
        self.assertAlmostEqual(entry["confidence"], 0.5, places=4)


class TestStatusRulesWithConfidence(unittest.TestCase):
    """Tests for the updated status logic incorporating confidence guard."""

    def _status(self, n_trades, raw_score, k=20):
        return TestEffectiveScore()._write_and_read(n_trades, raw_score, k).get("status")

    def test_status_qualified_high_trades_high_score(self):
        """High n_trades + high raw_score → QUALIFIED."""
        # confidence(100,20)=100/120≈0.833; effective=0.80×0.833≈0.667 ≥ 0.55
        self.assertEqual(self._status(n_trades=100, raw_score=0.80), "QUALIFIED")

    def test_five_trades_high_score_is_pending_not_qualified(self):
        """5 trades with high raw_score must be PENDING — confidence too low."""
        # confidence(5,20)=5/25=0.20; effective=0.90×0.20=0.18 < 0.55
        status = self._status(n_trades=5, raw_score=0.90)
        self.assertNotEqual(status, "QUALIFIED",
                            "5 trades must not produce QUALIFIED regardless of score")
        self.assertEqual(status, "PENDING")

    def test_rejected_requires_confidence_at_least_half(self):
        """
        REJECTED requires effective_score < 0.20 AND confidence >= 0.50.
        n=5, k=20 → confidence=0.20 < 0.50 → cannot be REJECTED.
        """
        status = self._status(n_trades=5, raw_score=0.10)
        self.assertNotEqual(status, "REJECTED",
                            "Low confidence (n=5) must prevent REJECTED status")
        self.assertEqual(status, "PENDING")

    def test_rejected_when_confidence_sufficient_and_score_low(self):
        """effective_score < 0.20 AND confidence >= 0.50 → REJECTED."""
        # n=20, k=20: confidence=0.50; raw=0.30; effective=0.30×0.50=0.15 < 0.20
        self.assertEqual(self._status(n_trades=20, raw_score=0.30), "REJECTED")

    def test_pending_when_score_in_middle_range(self):
        """0.20 ≤ effective_score < 0.55 → PENDING."""
        # n=50, k=20: confidence≈0.714; raw=0.40; effective≈0.286 → PENDING
        self.assertEqual(self._status(n_trades=50, raw_score=0.40), "PENDING")


if __name__ == "__main__":
    unittest.main()
