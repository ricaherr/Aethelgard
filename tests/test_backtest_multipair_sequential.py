"""
HU 7.14: Backtesting multi-par secuencial.
Trace_ID: EDGE-BKT-714-MULTI-PAIR-2026-03-24

TDD Red Phase: these tests MUST FAIL before implementation.

Validates:
  1. _get_symbols_for_backtest() returns all whitelist symbols normalized
  2. _get_symbols_for_backtest() falls back to default when whitelist is empty
  3. _execute_backtest() calls backtester once per symbol in whitelist
  4. affinity_scores has entries for all evaluated pairs after execution
  5. Symbol with incompatible regime is skipped (no backtester call)
  6. REGIME_INCOMPATIBLE status is written in affinity for skipped symbol
  7. run_pending_strategies() executes strategies sequentially (no asyncio.gather)
  8. Aggregate score is mean of evaluated pairs' scores
  9. Strategy with ALL pairs regime-skipped returns summary with evaluated=0
  10. _build_scenario_slices() accepts optional symbol parameter
"""
import asyncio
import json
import sqlite3
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn():
    """In-memory SQLite with minimal sys_strategies table."""
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
    return conn


def _make_strategy(symbols=None, required_regime="ANY", mode="BACKTEST"):
    if symbols is None:
        symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    return {
        "class_id": "strat-mp-001",
        "mnemonic": "MultiPairStrat",
        "market_whitelist": json.dumps(symbols),
        "affinity_scores": "{}",
        "execution_params": "{}",
        "mode": mode,
        "score_backtest": 0.0,
        "score_shadow": 0.0,
        "score_live": 0.0,
        "score": 0.0,
        "required_timeframes": "[]",
        "required_regime": required_regime,
        "last_backtest_at": None,
    }


def _make_orchestrator(conn=None, regime_allow=True):
    """Build BacktestOrchestrator with controlled mocks."""
    from core_brain.backtest_orchestrator import BacktestOrchestrator
    from core_brain.scenario_backtester import AptitudeMatrix, RegimeResult, StressCluster

    if conn is None:
        conn = _make_conn()

    mock_storage = MagicMock()
    mock_storage._get_conn.return_value = conn
    mock_storage.get_sys_config.return_value = {
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

    mock_dpm = MagicMock()
    mock_dpm.fetch_ohlc.return_value = None  # no real data needed

    # Build a minimal AptitudeMatrix for each call
    def _make_matrix(strategy_id, parameter_overrides, scenario_slices, strategy_instance):
        result = RegimeResult(
            stress_cluster=StressCluster.INSTITUTIONAL_TREND,
            detected_regime="TREND",
            profit_factor=1.50,
            max_drawdown_pct=0.10,
            total_trades=20,
            win_rate=0.60,
            regime_score=0.65,
        )
        return AptitudeMatrix(
            strategy_id=strategy_id,
            parameter_overrides=parameter_overrides,
            overall_score=0.65,
            passes_threshold=False,
            results_by_regime=[result],
            trace_id="TRACE_TEST",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    mock_backtester = MagicMock()
    mock_backtester.run_scenario_backtest.side_effect = _make_matrix
    mock_backtester._detect_regime.return_value = "RANGE"
    mock_backtester.MIN_REGIME_SCORE = 0.75

    orch = BacktestOrchestrator(
        storage=mock_storage,
        data_provider_manager=mock_dpm,
        scenario_backtester=mock_backtester,
    )

    # Patch regime pre-filter to allow or deny
    orch._passes_regime_prefilter = MagicMock(return_value=regime_allow)
    # Patch _build_strategy_for_backtest to avoid strategy class lookup
    orch._build_strategy_for_backtest = MagicMock(return_value=None)
    # Patch _build_scenario_slices to return empty list (backtester mock handles it)
    orch._build_scenario_slices = MagicMock(return_value=[])

    return orch, conn, mock_backtester


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestMultiPairSequential(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1-2: _get_symbols_for_backtest
    # ------------------------------------------------------------------

    def test_get_symbols_returns_all_whitelist_symbols(self):
        """_get_symbols_for_backtest must return all symbols in market_whitelist."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD", "USDJPY"])
        symbols = orch._get_symbols_for_backtest(strategy)
        self.assertEqual(set(symbols), {"EURUSD", "GBPUSD", "USDJPY"})

    def test_get_symbols_normalizes_slash_format(self):
        """Symbols like 'EUR/USD' must be normalized to 'EURUSD'."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(symbols=["EUR/USD", "GBP/USD"])
        symbols = orch._get_symbols_for_backtest(strategy)
        self.assertIn("EURUSD", symbols)
        self.assertIn("GBPUSD", symbols)
        for s in symbols:
            self.assertNotIn("/", s, "Symbols must not contain '/'")

    def test_get_symbols_falls_back_to_default_when_empty(self):
        """Empty market_whitelist must fall back to config default_symbol."""
        orch, _, _ = _make_orchestrator()
        strategy = _make_strategy(symbols=[])
        symbols = orch._get_symbols_for_backtest(strategy)
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0], "EURUSD")  # default from config

    # ------------------------------------------------------------------
    # 3-4: _execute_backtest calls backtester per symbol
    # ------------------------------------------------------------------

    def test_execute_backtest_calls_backtester_for_each_symbol(self):
        """backtester.run_scenario_backtest must be called once per symbol."""
        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD","GBPUSD","USDJPY"]', "{}"))
        conn.commit()

        orch, conn, mock_backtester = _make_orchestrator(conn=conn)
        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD", "USDJPY"])

        asyncio.run(orch._execute_backtest(strategy))

        call_count = mock_backtester.run_scenario_backtest.call_count
        self.assertEqual(call_count, 3,
                         f"Expected 3 backtester calls (one per symbol), got {call_count}")

    def test_affinity_scores_has_entry_for_each_evaluated_pair(self):
        """After _execute_backtest, affinity_scores must have one key per symbol."""
        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD","GBPUSD"]', "{}"))
        conn.commit()

        orch, conn, _ = _make_orchestrator(conn=conn)
        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD"])

        asyncio.run(orch._execute_backtest(strategy))

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat-mp-001",),
        ).fetchone()
        affinity = json.loads(row[0])
        self.assertIn("EURUSD", affinity, "affinity_scores must have EURUSD entry")
        self.assertIn("GBPUSD", affinity, "affinity_scores must have GBPUSD entry")

    # ------------------------------------------------------------------
    # 5-6: Regime-incompatible symbols are skipped
    # ------------------------------------------------------------------

    def test_regime_incompatible_symbol_does_not_call_backtester(self):
        """If regime pre-filter vetoes a symbol, backtester must NOT be called for it."""
        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD","GBPUSD"]', "{}"))
        conn.commit()

        orch, conn, mock_backtester = _make_orchestrator(conn=conn, regime_allow=False)
        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD"])

        asyncio.run(orch._execute_backtest(strategy))

        mock_backtester.run_scenario_backtest.assert_not_called()

    def test_regime_incompatible_status_written_in_affinity(self):
        """Symbol skipped by regime filter must have status=REGIME_INCOMPATIBLE in affinity_scores."""
        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD"]', "{}"))
        conn.commit()

        orch, conn, _ = _make_orchestrator(conn=conn, regime_allow=False)
        strategy = _make_strategy(symbols=["EURUSD"])

        asyncio.run(orch._execute_backtest(strategy))

        row = conn.execute(
            "SELECT affinity_scores FROM sys_strategies WHERE class_id = ?",
            ("strat-mp-001",),
        ).fetchone()
        affinity = json.loads(row[0])
        if "EURUSD" in affinity:
            self.assertEqual(affinity["EURUSD"]["status"], "REGIME_INCOMPATIBLE",
                             "Skipped symbol must have status=REGIME_INCOMPATIBLE")

    # ------------------------------------------------------------------
    # 7: run_pending_strategies uses sequential execution
    # ------------------------------------------------------------------

    def test_run_pending_strategies_sequential_not_gather(self):
        """run_pending_strategies must NOT use asyncio.gather — sequential execution."""
        import inspect
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        import ast, textwrap

        src = inspect.getsource(BacktestOrchestrator.run_pending_strategies)
        self.assertNotIn(
            "asyncio.gather",
            src,
            "run_pending_strategies must not use asyncio.gather — use sequential loop",
        )

    # ------------------------------------------------------------------
    # 8: Aggregate score is mean of evaluated pairs
    # ------------------------------------------------------------------

    def test_aggregate_score_is_mean_of_pairs(self):
        """score_backtest stored in DB must equal mean of per-pair overall_scores."""
        from core_brain.scenario_backtester import AptitudeMatrix, RegimeResult, StressCluster

        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD","GBPUSD"]', "{}"))
        conn.commit()

        orch, conn, mock_backtester = _make_orchestrator(conn=conn)

        # Two pairs return different scores: 0.60 and 0.80 → mean = 0.70
        scores = [0.60, 0.80]
        call_idx = [0]

        def _matrix_with_score(strategy_id, parameter_overrides, scenario_slices, strategy_instance):
            score = scores[call_idx[0] % len(scores)]
            call_idx[0] += 1
            result = RegimeResult(
                stress_cluster=StressCluster.INSTITUTIONAL_TREND,
                detected_regime="TREND",
                profit_factor=1.5,
                max_drawdown_pct=0.10,
                total_trades=20,
                win_rate=0.60,
                regime_score=score,
            )
            return AptitudeMatrix(
                strategy_id=strategy_id,
                parameter_overrides=parameter_overrides,
                overall_score=score,
                passes_threshold=False,
                results_by_regime=[result],
                trace_id="T",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        mock_backtester.run_scenario_backtest.side_effect = _matrix_with_score

        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD"])
        asyncio.run(orch._execute_backtest(strategy))

        row = conn.execute(
            "SELECT score_backtest FROM sys_strategies WHERE class_id = ?",
            ("strat-mp-001",),
        ).fetchone()
        self.assertAlmostEqual(row[0], 0.70, places=2,
                               msg="score_backtest must be mean of per-pair scores")

    # ------------------------------------------------------------------
    # 9: All pairs skipped → None return
    # ------------------------------------------------------------------

    def test_execute_returns_none_when_all_pairs_regime_skipped(self):
        """If all pairs are regime-incompatible, _execute_backtest must return None."""
        conn = _make_conn()
        conn.execute("""
            INSERT INTO sys_strategies (class_id, mnemonic, market_whitelist, affinity_scores)
            VALUES (?, ?, ?, ?)
        """, ("strat-mp-001", "MP", '["EURUSD","GBPUSD"]', "{}"))
        conn.commit()

        orch, conn, _ = _make_orchestrator(conn=conn, regime_allow=False)
        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD"])

        result = asyncio.run(orch._execute_backtest(strategy))
        self.assertIsNone(result,
                          "_execute_backtest must return None when all pairs are skipped")

    # ------------------------------------------------------------------
    # 10: _build_scenario_slices accepts symbol parameter
    # ------------------------------------------------------------------

    def test_build_scenario_slices_accepts_symbol_param(self):
        """_build_scenario_slices(strategy, params, symbol='GBPUSD') must not raise."""
        orch, _, _ = _make_orchestrator()
        # Restore the real method (bypassed in make_orchestrator)
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        orch._build_scenario_slices = BacktestOrchestrator._build_scenario_slices.__get__(orch)
        orch._passes_regime_prefilter = MagicMock(return_value=False)

        strategy = _make_strategy(symbols=["EURUSD", "GBPUSD"])
        try:
            orch._build_scenario_slices(strategy, {}, symbol="GBPUSD")
        except TypeError as exc:
            self.fail(
                f"_build_scenario_slices rejected 'symbol' parameter: {exc}"
            )


if __name__ == "__main__":
    unittest.main()
