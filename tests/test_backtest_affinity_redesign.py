"""
HU 7.13: Rediseño semántico de affinity_scores.
Trace_ID: EDGE-BKT-713-AFFINITY-REDESIGN-2026-03-24

TDD Red Phase: these tests MUST FAIL before implementation.

Validates:
  1. _extract_parameter_overrides reads execution_params (NOT affinity_scores)
  2. _extract_parameter_overrides falls back to defaults when execution_params is empty
  3. _extract_parameter_overrides handles invalid JSON gracefully
  4. affinity_scores is NOT used as source for confidence_threshold / risk_reward
  5. _update_strategy_scores writes per-pair affinity structure to DB
  6. Per-pair entry contains all required semantic fields
  7. Status logic: QUALIFIED / REJECTED / PENDING
  8. cycles increments on repeated updates
  9. _load_backtest_strategies SELECT includes execution_params column
  10. Migration resets affinity_scores to {} for all strategies
"""
import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage_mock():
    """Minimal StorageManager mock that delegates _get_conn to an in-memory DB."""
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
    conn.execute("""
        INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, execution_params, affinity_scores)
        VALUES (
            'strat-001', 'TestStrat',
            '["EURUSD"]',
            '{"confidence_threshold": 0.65, "risk_reward": 2.0}',
            '{"EUR/USD": 0.92}'
        )
    """)
    conn.commit()
    mock_storage = MagicMock()
    mock_storage._get_conn.return_value = conn
    return mock_storage, conn


def _make_orchestrator(storage=None, conn=None):
    """Build BacktestOrchestrator with minimal mocks."""
    from core_brain.backtest_orchestrator import BacktestOrchestrator

    if storage is None:
        storage, conn = _make_storage_mock()

    mock_dpm = MagicMock()
    mock_backtester = MagicMock()
    mock_backtester._detect_regime.return_value = "RANGE"

    # sys_config returns needed keys
    mock_storage_cfg = MagicMock()
    mock_storage_cfg.get_sys_config.return_value = {
        "cooldown_hours": 24,
        "bars_per_window": 100,
        "bars_fetch_initial": 500,
        "bars_fetch_max": 1000,
        "bars_fetch_retry": 250,
        "min_trades_per_cluster": 15,
        "default_symbol": "EURUSD",
        "default_timeframe": "H1",
        "min_score_for_promotion": 0.75,
        "score_weights": {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
    }
    storage.get_sys_config = mock_storage_cfg.get_sys_config

    orch = BacktestOrchestrator(
        storage=storage,
        data_provider_manager=mock_dpm,
        scenario_backtester=mock_backtester,
    )
    return orch, storage, conn


def _make_strategy(
    execution_params=None,
    affinity_scores=None,
    market_whitelist=None,
):
    """Build a minimal strategy dict."""
    ep = execution_params if execution_params is not None else {"confidence_threshold": 0.65, "risk_reward": 2.0}
    af = affinity_scores if affinity_scores is not None else {"EUR/USD": 0.92}
    wl = market_whitelist if market_whitelist is not None else ["EURUSD"]
    return {
        "class_id": "strat-001",
        "mnemonic": "TestStrat",
        "market_whitelist": json.dumps(wl),
        "affinity_scores": json.dumps(af),
        "execution_params": json.dumps(ep),
        "mode": "BACKTEST",
        "score_backtest": 0.0,
        "score_shadow": 0.0,
        "score_live": 0.0,
        "score": 0.0,
        "required_timeframes": "[]",
        "required_regime": "ANY",
        "last_backtest_at": None,
    }


def _make_matrix(overall_score=0.70):
    """Build a minimal AptitudeMatrix mock."""
    from core_brain.scenario_backtester import AptitudeMatrix, RegimeResult, StressCluster
    result = RegimeResult(
        stress_cluster=StressCluster.INSTITUTIONAL_TREND,
        detected_regime="TREND",
        profit_factor=1.74,
        max_drawdown_pct=0.11,
        total_trades=52,
        win_rate=0.62,
        regime_score=overall_score,
    )
    return AptitudeMatrix(
        strategy_id="strat-001",
        parameter_overrides={"confidence_threshold": 0.65},
        overall_score=overall_score,
        passes_threshold=overall_score >= 0.75,
        results_by_regime=[result],
        trace_id="TRACE_TEST",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestAffinityRedesign(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1-4: _extract_parameter_overrides reads execution_params
    # ------------------------------------------------------------------

    def test_reads_confidence_threshold_from_execution_params(self):
        """confidence_threshold must come from execution_params, not affinity_scores."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(
            execution_params={"confidence_threshold": 0.65, "risk_reward": 2.0},
            affinity_scores={"confidence_threshold": 0.99, "risk_reward": 9.9},
        )
        params = orch._extract_parameter_overrides(strategy)
        self.assertEqual(params["confidence_threshold"], 0.65)

    def test_reads_risk_reward_from_execution_params(self):
        """risk_reward must come from execution_params, not affinity_scores."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(
            execution_params={"confidence_threshold": 0.65, "risk_reward": 2.5},
            affinity_scores={"confidence_threshold": 0.99, "risk_reward": 9.9},
        )
        params = orch._extract_parameter_overrides(strategy)
        self.assertEqual(params["risk_reward"], 2.5)

    def test_falls_back_to_defaults_when_execution_params_empty(self):
        """Empty execution_params must return defaults: threshold=0.75, rr=1.5."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(execution_params={}, affinity_scores={"EUR/USD": 0.92})
        params = orch._extract_parameter_overrides(strategy)
        self.assertEqual(params["confidence_threshold"], 0.75)
        self.assertEqual(params["risk_reward"], 1.5)

    def test_handles_invalid_json_in_execution_params(self):
        """Corrupt execution_params JSON must not raise — fall back to defaults."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy()
        strategy["execution_params"] = "NOT_VALID_JSON"
        params = orch._extract_parameter_overrides(strategy)
        self.assertEqual(params["confidence_threshold"], 0.75)
        self.assertEqual(params["risk_reward"], 1.5)

    def test_affinity_scores_values_are_ignored(self):
        """Even when affinity_scores has confidence_threshold, execution_params wins."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(
            execution_params={"confidence_threshold": 0.60},
            affinity_scores={"confidence_threshold": 0.99},
        )
        params = orch._extract_parameter_overrides(strategy)
        self.assertNotEqual(params["confidence_threshold"], 0.99,
                            "affinity_scores.confidence_threshold must NOT be used")
        self.assertEqual(params["confidence_threshold"], 0.60)

    # ------------------------------------------------------------------
    # 5: SELECT includes execution_params
    # ------------------------------------------------------------------

    def test_load_backtest_strategies_includes_execution_params(self):
        """_load_backtest_strategies must return execution_params key in each row."""
        orch, storage, conn = _make_orchestrator()
        rows = orch._load_backtest_strategies()
        if rows:
            self.assertIn("execution_params", rows[0],
                          "_load_backtest_strategies must SELECT execution_params")

    def test_load_strategy_includes_execution_params(self):
        """_load_strategy must return execution_params in the result dict."""
        orch, storage, conn = _make_orchestrator()
        row = orch._load_strategy("strat-001")
        if row is not None:
            self.assertIn("execution_params", row,
                          "_load_strategy must SELECT execution_params")

    # ------------------------------------------------------------------
    # 6-8: _update_strategy_scores writes per-pair affinity
    # ------------------------------------------------------------------

    def test_update_strategy_scores_writes_affinity_per_pair(self):
        """After update, affinity_scores must contain an entry keyed by symbol."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.70)
        orch._update_strategy_scores("strat-001", 0.70, strategy, symbol="EURUSD", matrix=matrix)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        affinity = json.loads(row[0])
        self.assertIn("EURUSD", affinity,
                      "affinity_scores must have a key per evaluated symbol")

    def test_per_pair_entry_has_all_required_fields(self):
        """Per-pair affinity entry must include all semantic fields from HU 7.13 spec."""
        required_fields = {
            "effective_score", "raw_score", "confidence",
            "n_trades", "profit_factor", "max_drawdown",
            "win_rate", "optimal_timeframe", "regime_evaluated",
            "status", "cycles", "last_updated",
        }
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.70)
        orch._update_strategy_scores("strat-001", 0.70, strategy, symbol="EURUSD", matrix=matrix)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        entry = json.loads(row[0])["EURUSD"]
        missing = required_fields - set(entry.keys())
        self.assertFalse(missing, f"Missing fields in per-pair affinity: {missing}")

    def test_status_qualified_when_score_above_threshold(self):
        """effective_score >= 0.55 → status = QUALIFIED."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.80)
        orch._update_strategy_scores("strat-001", 0.80, strategy, symbol="EURUSD", matrix=matrix)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        entry = json.loads(row[0])["EURUSD"]
        self.assertEqual(entry["status"], "QUALIFIED")

    def test_status_rejected_when_score_below_floor(self):
        """effective_score < 0.20 → status = REJECTED."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.10)
        orch._update_strategy_scores("strat-001", 0.10, strategy, symbol="EURUSD", matrix=matrix)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        entry = json.loads(row[0])["EURUSD"]
        self.assertEqual(entry["status"], "REJECTED")

    def test_status_pending_when_score_in_middle(self):
        """0.20 <= effective_score < 0.55 → status = PENDING."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.40)
        orch._update_strategy_scores("strat-001", 0.40, strategy, symbol="EURUSD", matrix=matrix)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        entry = json.loads(row[0])["EURUSD"]
        self.assertEqual(entry["status"], "PENDING")

    def test_cycles_increments_on_repeated_updates(self):
        """cycles must increment from 0 → 1 → 2 on repeated updates."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        matrix = _make_matrix(overall_score=0.70)

        orch._update_strategy_scores("strat-001", 0.70, strategy, symbol="EURUSD", matrix=matrix)
        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        cycles_1 = json.loads(row[0])["EURUSD"]["cycles"]

        orch._update_strategy_scores("strat-001", 0.70, strategy, symbol="EURUSD", matrix=matrix)
        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("strat-001",)
        ).fetchone()
        cycles_2 = json.loads(row[0])["EURUSD"]["cycles"]

        self.assertEqual(cycles_2, cycles_1 + 1,
                         "cycles must increment by 1 on each update")

    def test_update_without_matrix_does_not_crash(self):
        """Calling _update_strategy_scores with matrix=None must not raise."""
        orch, storage, conn = _make_orchestrator()
        strategy = _make_strategy()
        try:
            orch._update_strategy_scores("strat-001", 0.70, strategy)
        except Exception as exc:
            self.fail(f"_update_strategy_scores crashed with matrix=None: {exc}")

    # ------------------------------------------------------------------
    # 10: Migration resets affinity_scores
    # ------------------------------------------------------------------

    def test_migration_resets_affinity_scores_to_empty_dict(self):
        """Migration must reset affinity_scores = '{}' for strategies with legacy content."""
        from data_vault.schema import initialize_schema, run_migrations

        conn = sqlite3.connect(":memory:")
        # Bootstrap the full schema so run_migrations has all tables it expects
        initialize_schema(conn)

        # Insert strategy with legacy developer-opinion affinity scores
        conn.execute(
            "UPDATE sys_strategies SET affinity_scores = ? WHERE class_id = (SELECT class_id FROM sys_strategies LIMIT 1)",
            ('{"EUR/USD": 0.92, "GBP/USD": 0.85}',),
        )
        # If no strategy exists yet, insert one directly
        conn.execute(
            """
            INSERT OR IGNORE INTO sys_strategies (class_id, mnemonic, affinity_scores)
            VALUES ('s1-migrate', 'MigrateStrat', '{"EUR/USD": 0.92, "GBP/USD": 0.85}')
            """
        )
        conn.commit()
        run_migrations(conn)

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?", ("s1-migrate",)
        ).fetchone()
        self.assertIsNotNone(row)
        value = json.loads(row[0])
        self.assertEqual(value, {},
                         "Migration must reset affinity_scores to {} for legacy entries")


if __name__ == "__main__":
    unittest.main()
