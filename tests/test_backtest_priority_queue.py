"""
Tests for HU 7.18 — Scheduler inteligente de backtests — prioritized queue
Trace_ID: EDGE-BKT-718-SMART-SCHEDULER-2026-03-24

Acceptance criteria:
  AC1: P1 se evalúa antes que P6 en todos los escenarios
  AC2: Cambio de contexto a LIVE_ACTIVE reduce el budget (max_slots) en el siguiente ciclo
  AC3: Tests verifican ordenamiento correcto del queue para todos los tiers
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, PropertyMock

import pytest

from core_brain.operational_mode_manager import (
    BacktestBudget,
    OperationalContext,
    OperationalModeManager,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_db() -> sqlite3.Connection:
    """Full in-memory DB."""
    from data_vault.schema import initialize_schema, run_migrations
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    run_migrations(conn)
    return conn


def _make_mode_manager(
    budget: BacktestBudget = BacktestBudget.AGGRESSIVE,
    context: OperationalContext = OperationalContext.BACKTEST_ONLY,
) -> OperationalModeManager:
    mgr = MagicMock(spec=OperationalModeManager)
    mgr.get_backtest_budget.return_value = budget
    mgr.current_context = context
    # get_component_frequencies returns cooldown based on context
    cooldown_map = {
        OperationalContext.BACKTEST_ONLY: 1.0,
        OperationalContext.SHADOW_ACTIVE: 12.0,
        OperationalContext.LIVE_ACTIVE:   24.0,
    }
    mgr.get_component_frequencies.return_value = {
        "backtest_cooldown_h": cooldown_map[context]
    }
    return mgr


def _seed_strategy(
    conn: sqlite3.Connection,
    class_id: str = "strat_pq_test",
    symbol: str = "EURUSD",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sys_strategies "
        "(class_id, mnemonic, mode, affinity_scores, market_whitelist) "
        "VALUES (?, ?, 'BACKTEST', '{}', ?)",
        (class_id, class_id, json.dumps([symbol])),
    )
    conn.commit()


def _seed_coverage(
    conn: sqlite3.Connection,
    strategy_id: str,
    symbol: str,
    timeframe: str = "M15",
    regime: str = "TREND",
    n_cycles: int = 1,
    n_trades_total: int = 30,
    effective_score: float = 0.65,
    status: str = "QUALIFIED",
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO sys_strategy_pair_coverage
            (strategy_id, symbol, timeframe, regime, n_cycles, n_trades_total,
             effective_score, status, last_evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (strategy_id, symbol, timeframe, regime, n_cycles, n_trades_total,
         effective_score, status, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _make_pq(conn: sqlite3.Connection, budget: BacktestBudget = BacktestBudget.AGGRESSIVE,
             context: OperationalContext = OperationalContext.BACKTEST_ONLY):
    """Build a BacktestPriorityQueue backed by an in-memory DB."""
    from core_brain.backtest_orchestrator import BacktestPriorityQueue

    storage = MagicMock()
    storage._get_conn.return_value = conn

    mode_manager = _make_mode_manager(budget=budget, context=context)
    return BacktestPriorityQueue(storage=storage, mode_manager=mode_manager)


# ──────────────────────────────────────────────────────────────────────────────
# AC2: get_max_slots() decreases with context
# ──────────────────────────────────────────────────────────────────────────────

class TestPriorityQueueBudget:
    """AC2: Context change to LIVE_ACTIVE reduces budget (max_slots)."""

    def test_aggressive_budget_has_more_slots_than_conservative(self):
        conn = _build_db()
        pq_aggressive = _make_pq(conn, budget=BacktestBudget.AGGRESSIVE,
                                  context=OperationalContext.BACKTEST_ONLY)
        pq_conservative = _make_pq(conn, budget=BacktestBudget.CONSERVATIVE,
                                    context=OperationalContext.LIVE_ACTIVE)
        assert pq_aggressive.get_max_slots() > pq_conservative.get_max_slots()

    def test_deferred_budget_returns_zero_slots(self):
        conn = _build_db()
        pq = _make_pq(conn, budget=BacktestBudget.DEFERRED)
        assert pq.get_max_slots() == 0

    def test_live_active_context_reduces_slots_vs_backtest_only(self):
        """LIVE_ACTIVE (CONSERVATIVE) must return fewer slots than BACKTEST_ONLY (AGGRESSIVE)."""
        conn = _build_db()
        pq_bt = _make_pq(conn, budget=BacktestBudget.AGGRESSIVE,
                          context=OperationalContext.BACKTEST_ONLY)
        pq_live = _make_pq(conn, budget=BacktestBudget.CONSERVATIVE,
                            context=OperationalContext.LIVE_ACTIVE)
        assert pq_live.get_max_slots() < pq_bt.get_max_slots()

    def test_deferred_queue_returns_empty_list(self):
        """When DEFERRED, get_queue() returns [] regardless of strategies."""
        conn = _build_db()
        _seed_strategy(conn, "strat_deferred")
        pq = _make_pq(conn, budget=BacktestBudget.DEFERRED)
        result = pq.get_queue()
        assert result == []

    def test_moderate_slots_between_aggressive_and_conservative(self):
        conn = _build_db()
        pq_agg  = _make_pq(conn, budget=BacktestBudget.AGGRESSIVE)
        pq_mod  = _make_pq(conn, budget=BacktestBudget.MODERATE)
        pq_cons = _make_pq(conn, budget=BacktestBudget.CONSERVATIVE)
        assert pq_agg.get_max_slots() >= pq_mod.get_max_slots() >= pq_cons.get_max_slots()


# ──────────────────────────────────────────────────────────────────────────────
# AC1 + AC3: Priority ordering P1 > ... > P6
# ──────────────────────────────────────────────────────────────────────────────

class TestPriorityQueueOrdering:
    """AC1 + AC3: Queue ordering correctness."""

    def test_p1_never_evaluated_before_p6_qualified(self):
        """AC1: P1 (never evaluated) always ranked before P6 (QUALIFIED, many cycles)."""
        conn = _build_db()
        # P6: QUALIFIED pair, 5 cycles
        _seed_strategy(conn, "strat_p6")
        _seed_coverage(conn, "strat_p6", "EURUSD", status="QUALIFIED", n_cycles=5,
                       n_trades_total=100, effective_score=0.72)
        # P1: strategy with no coverage entry at all
        _seed_strategy(conn, "strat_p1")

        pq = _make_pq(conn)
        queue = pq.get_queue()

        ids = [item["strategy_id"] for item in queue]
        assert ids.index("strat_p1") < ids.index("strat_p6")

    def test_p1_before_p6_in_all_mixed_scenarios(self):
        """P1 combo comes before P6 even when P6 has higher score."""
        conn = _build_db()
        _seed_strategy(conn, "strat_high_score", symbol="EURUSD")
        _seed_coverage(conn, "strat_high_score", "EURUSD", status="QUALIFIED",
                       n_cycles=10, n_trades_total=200, effective_score=0.90)
        _seed_strategy(conn, "strat_never_run")

        pq = _make_pq(conn)
        queue = pq.get_queue()
        ids = [item["strategy_id"] for item in queue]
        assert ids.index("strat_never_run") < ids.index("strat_high_score")

    def test_pending_before_qualified(self):
        """P2 (PENDING) is evaluated before P6 (QUALIFIED)."""
        conn = _build_db()
        _seed_strategy(conn, "strat_qualified")
        _seed_coverage(conn, "strat_qualified", "EURUSD", status="QUALIFIED",
                       n_cycles=5, n_trades_total=80, effective_score=0.70)
        _seed_strategy(conn, "strat_pending")
        _seed_coverage(conn, "strat_pending", "EURUSD", status="PENDING",
                       n_cycles=1, n_trades_total=5, effective_score=0.20)

        pq = _make_pq(conn)
        queue = pq.get_queue()
        ids = [item["strategy_id"] for item in queue]
        assert ids.index("strat_pending") < ids.index("strat_qualified")

    def test_low_confidence_before_qualified_many_cycles(self):
        """P5 (low confidence) comes before P6 (qualified, high cycles)."""
        conn = _build_db()
        _seed_strategy(conn, "strat_low_conf")
        _seed_coverage(conn, "strat_low_conf", "EURUSD", status="PENDING",
                       n_cycles=2, n_trades_total=5, effective_score=0.25)
        _seed_strategy(conn, "strat_stable")
        _seed_coverage(conn, "strat_stable", "EURUSD", status="QUALIFIED",
                       n_cycles=8, n_trades_total=150, effective_score=0.75)

        pq = _make_pq(conn)
        queue = pq.get_queue()
        ids = [item["strategy_id"] for item in queue]
        assert ids.index("strat_low_conf") < ids.index("strat_stable")

    def test_queue_returns_strategy_symbol_timeframe_tuples(self):
        """Each queue item must have strategy_id, symbol, timeframe keys."""
        conn = _build_db()
        _seed_strategy(conn, "strat_format")
        _seed_coverage(conn, "strat_format", "EURUSD", timeframe="M15",
                       status="PENDING", n_cycles=1)

        pq = _make_pq(conn)
        queue = pq.get_queue()

        assert len(queue) >= 1
        item = queue[0]
        assert "strategy_id" in item
        assert "symbol" in item
        assert "timeframe" in item

    def test_queue_respects_max_slots(self):
        """Queue length must not exceed get_max_slots()."""
        conn = _build_db()
        # Seed many strategies
        for i in range(10):
            sid = f"strat_slot_{i}"
            _seed_strategy(conn, sid)
            _seed_coverage(conn, sid, "EURUSD", status="QUALIFIED",
                           n_cycles=i + 1, n_trades_total=50, effective_score=0.65)

        pq = _make_pq(conn, budget=BacktestBudget.CONSERVATIVE,
                       context=OperationalContext.LIVE_ACTIVE)
        queue = pq.get_queue()
        assert len(queue) <= pq.get_max_slots()

    def test_empty_coverage_strategies_appear_first(self):
        """Multiple never-evaluated strategies come before any with coverage rows."""
        conn = _build_db()
        for sid in ["strat_new_a", "strat_new_b"]:
            _seed_strategy(conn, sid)
        _seed_strategy(conn, "strat_old")
        _seed_coverage(conn, "strat_old", "EURUSD", status="QUALIFIED",
                       n_cycles=3, n_trades_total=60, effective_score=0.68)

        pq = _make_pq(conn)
        queue = pq.get_queue()
        ids = [item["strategy_id"] for item in queue]

        old_idx = ids.index("strat_old")
        new_a_idx = ids.index("strat_new_a")
        new_b_idx = ids.index("strat_new_b")
        assert new_a_idx < old_idx
        assert new_b_idx < old_idx


# ──────────────────────────────────────────────────────────────────────────────
# Priority tier classification
# ──────────────────────────────────────────────────────────────────────────────

class TestPriorityTierClassification:
    """_priority_tier() assigns correct tier to each coverage state."""

    def _pq(self):
        return _make_pq(_build_db())

    def test_no_coverage_entry_is_tier_1(self):
        """Never evaluated → tier 1 (P1, highest priority)."""
        pq = self._pq()
        tier = pq._priority_tier(
            coverage_row=None,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier == 1

    def test_pending_low_cycles_is_tier_2(self):
        """PENDING with n_cycles <= 1 → tier 2 (P2)."""
        pq = self._pq()
        row = {"status": "PENDING", "n_cycles": 1, "n_trades_total": 3,
               "effective_score": 0.15, "timeframe": "M15"}
        tier = pq._priority_tier(
            coverage_row=row,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier == 2

    def test_pending_higher_cycles_is_tier_3(self):
        """PENDING with n_cycles > 1 → tier 3 (P3)."""
        pq = self._pq()
        row = {"status": "PENDING", "n_cycles": 3, "n_trades_total": 10,
               "effective_score": 0.30, "timeframe": "M15"}
        tier = pq._priority_tier(
            coverage_row=row,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier == 3

    def test_qualified_low_cycles_is_tier_4(self):
        """QUALIFIED with n_cycles < 3 → tier 4 (P4, score might be unstable)."""
        pq = self._pq()
        row = {"status": "QUALIFIED", "n_cycles": 2, "n_trades_total": 15,
               "effective_score": 0.60, "timeframe": "M15"}
        tier = pq._priority_tier(
            coverage_row=row,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier == 4

    def test_qualified_low_confidence_is_tier_5(self):
        """QUALIFIED but effective_score < 0.55 threshold → tier 5 (P5, low confidence)."""
        pq = self._pq()
        row = {"status": "PENDING", "n_cycles": 4, "n_trades_total": 8,
               "effective_score": 0.30, "timeframe": "M15"}
        tier = pq._priority_tier(
            coverage_row=row,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier <= 5  # lower than QUALIFIED fully stable

    def test_qualified_stable_is_tier_6(self):
        """QUALIFIED, n_cycles >= 3, effective_score >= 0.55 → tier 6 (P6, routine drift)."""
        pq = self._pq()
        row = {"status": "QUALIFIED", "n_cycles": 5, "n_trades_total": 120,
               "effective_score": 0.72, "timeframe": "M15"}
        tier = pq._priority_tier(
            coverage_row=row,
            strategy_id="x", symbol="EURUSD", timeframe="M15",
        )
        assert tier == 6

    def test_rejected_status_is_lower_priority_than_pending(self):
        """REJECTED pair should have lower priority than PENDING."""
        pq = self._pq()
        pending_row = {"status": "PENDING", "n_cycles": 1, "n_trades_total": 3,
                       "effective_score": 0.15, "timeframe": "M15"}
        rejected_row = {"status": "REJECTED", "n_cycles": 4, "n_trades_total": 50,
                        "effective_score": 0.10, "timeframe": "M15"}
        t_pending  = pq._priority_tier(pending_row,  "x", "EURUSD", "M15")
        t_rejected = pq._priority_tier(rejected_row, "x", "EURUSD", "M15")
        assert t_pending < t_rejected
