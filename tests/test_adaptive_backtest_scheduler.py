"""
Tests: AdaptiveBacktestScheduler — cooldown dinámico y cola de prioridad
========================================================================
Verifica AdaptiveBacktestScheduler:
1. get_effective_cooldown_hours() retorna el cooldown según el presupuesto
   operacional: 1h (AGGRESSIVE), 12h (MODERATE), 24h (CONSERVATIVE).
2. is_deferred() retorna True cuando el presupuesto es DEFERRED.
3. get_priority_queue() excluye estrategias en cooldown.
4. get_priority_queue() ordena por prioridad:
   - P1: nunca ejecutadas (last_backtest_at IS NULL, score_backtest=0)
   - P2: ejecutadas pero sin score (score_backtest=0)
   - P3: con score — más antigua primero
5. get_priority_queue() retorna lista vacía si todas están en cooldown.
6. Estrategias con mode != 'BACKTEST' se excluyen siempre.
7. is_deferred() con DEFERRED budget impide retornar cola (retorna []).
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core_brain.adaptive_backtest_scheduler import AdaptiveBacktestScheduler
from core_brain.operational_mode_manager import (
    BacktestBudget,
    OperationalContext,
    OperationalModeManager,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts(hours_ago: float) -> str:
    """ISO timestamp for N hours in the past."""
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.isoformat()


def _make_strategy(
    class_id: str,
    score_backtest: float = 0.0,
    last_backtest_at=None,
    mode: str = "BACKTEST",
) -> dict:
    return {
        "class_id": class_id,
        "mode": mode,
        "score_backtest": score_backtest,
        "last_backtest_at": last_backtest_at,
        "updated_at": last_backtest_at or "2020-01-01T00:00:00",
    }


def _make_scheduler(
    strategies: list,
    budget: BacktestBudget = BacktestBudget.AGGRESSIVE,
    context: OperationalContext = OperationalContext.BACKTEST_ONLY,
) -> AdaptiveBacktestScheduler:
    storage = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    storage._get_conn.return_value = conn

    rows = [tuple(s.values()) for s in strategies]
    cols = list(strategies[0].keys()) if strategies else []
    cursor.description = [(c,) for c in cols]
    cursor.fetchall.return_value = rows

    mode_mgr = MagicMock(spec=OperationalModeManager)
    mode_mgr.get_backtest_budget.return_value = budget
    mode_mgr.current_context = context
    mode_mgr.get_component_frequencies.return_value = {
        BacktestBudget.AGGRESSIVE:   {"backtest_cooldown_h": 1},
        BacktestBudget.MODERATE:     {"backtest_cooldown_h": 12},
        BacktestBudget.CONSERVATIVE: {"backtest_cooldown_h": 24},
        BacktestBudget.DEFERRED:     {"backtest_cooldown_h": 24},
    }[budget]

    return AdaptiveBacktestScheduler(storage=storage, mode_manager=mode_mgr)


# ── Tests: cooldown dinámico ──────────────────────────────────────────────────

class TestEffectiveCooldown:

    def test_aggressive_budget_gives_1h_cooldown(self):
        sched = _make_scheduler(
            [_make_strategy("S1")],
            budget=BacktestBudget.AGGRESSIVE,
            context=OperationalContext.BACKTEST_ONLY,
        )
        assert sched.get_effective_cooldown_hours() == 1

    def test_moderate_budget_gives_12h_cooldown(self):
        sched = _make_scheduler(
            [_make_strategy("S1")],
            budget=BacktestBudget.MODERATE,
            context=OperationalContext.SHADOW_ACTIVE,
        )
        assert sched.get_effective_cooldown_hours() == 12

    def test_conservative_budget_gives_24h_cooldown(self):
        sched = _make_scheduler(
            [_make_strategy("S1")],
            budget=BacktestBudget.CONSERVATIVE,
            context=OperationalContext.LIVE_ACTIVE,
        )
        assert sched.get_effective_cooldown_hours() == 24


# ── Tests: is_deferred ────────────────────────────────────────────────────────

class TestIsDeferred:

    def test_deferred_budget_returns_true(self):
        sched = _make_scheduler([_make_strategy("S1")], budget=BacktestBudget.DEFERRED)
        assert sched.is_deferred() is True

    def test_aggressive_budget_returns_false(self):
        sched = _make_scheduler([_make_strategy("S1")], budget=BacktestBudget.AGGRESSIVE)
        assert sched.is_deferred() is False

    def test_get_priority_queue_returns_empty_when_deferred(self):
        """Si el presupuesto es DEFERRED, get_priority_queue() devuelve []."""
        sched = _make_scheduler([_make_strategy("S1")], budget=BacktestBudget.DEFERRED)
        assert sched.get_priority_queue() == []


# ── Tests: filtrado por cooldown ──────────────────────────────────────────────

class TestCooldownFiltering:

    def test_never_run_strategy_is_eligible(self):
        """Estrategia nunca ejecutada (last_backtest_at=None) siempre es elegible."""
        sched = _make_scheduler(
            [_make_strategy("S1", last_backtest_at=None)],
            budget=BacktestBudget.AGGRESSIVE,
        )
        queue = sched.get_priority_queue()
        assert len(queue) == 1
        assert queue[0]["class_id"] == "S1"

    def test_recently_run_strategy_is_excluded(self):
        """Estrategia ejecutada hace 0.5h con cooldown 1h debe quedar fuera."""
        sched = _make_scheduler(
            [_make_strategy("S1", last_backtest_at=_ts(0.5))],
            budget=BacktestBudget.AGGRESSIVE,  # cooldown = 1h
        )
        assert sched.get_priority_queue() == []

    def test_old_enough_strategy_is_included(self):
        """Estrategia ejecutada hace 2h con cooldown 1h debe incluirse."""
        sched = _make_scheduler(
            [_make_strategy("S1", score_backtest=0.5, last_backtest_at=_ts(2))],
            budget=BacktestBudget.AGGRESSIVE,  # cooldown = 1h
        )
        queue = sched.get_priority_queue()
        assert len(queue) == 1

    def test_non_backtest_mode_excluded(self):
        """Estrategias con mode != 'BACKTEST' no se incluyen."""
        sched = _make_scheduler(
            [_make_strategy("S1", mode="SHADOW")],
            budget=BacktestBudget.AGGRESSIVE,
        )
        assert sched.get_priority_queue() == []


# ── Tests: orden de prioridad ─────────────────────────────────────────────────

class TestPriorityOrder:

    def test_never_run_before_score_zero_before_scored(self):
        """P1 (nunca run) > P2 (score=0, run antes) > P3 (con score)."""
        strategies = [
            _make_strategy("SCORED",    score_backtest=0.8,  last_backtest_at=_ts(48)),
            _make_strategy("ZERO_OLD",  score_backtest=0.0,  last_backtest_at=_ts(24)),
            _make_strategy("NEVER_RUN", score_backtest=0.0,  last_backtest_at=None),
        ]
        sched = _make_scheduler(strategies, budget=BacktestBudget.AGGRESSIVE)
        queue = sched.get_priority_queue()
        ids = [s["class_id"] for s in queue]
        assert ids[0] == "NEVER_RUN"
        assert ids[1] == "ZERO_OLD"
        assert ids[2] == "SCORED"

    def test_oldest_last_backtest_first_within_same_priority(self):
        """Dentro de P3, la más antigua (last_backtest_at más vieja) va primero."""
        strategies = [
            _make_strategy("RECENT",  score_backtest=0.5, last_backtest_at=_ts(10)),
            _make_strategy("OLDEST",  score_backtest=0.5, last_backtest_at=_ts(48)),
            _make_strategy("MIDDLE",  score_backtest=0.5, last_backtest_at=_ts(25)),
        ]
        sched = _make_scheduler(strategies, budget=BacktestBudget.AGGRESSIVE)
        queue = sched.get_priority_queue()
        ids = [s["class_id"] for s in queue]
        assert ids[0] == "OLDEST"
        assert ids[1] == "MIDDLE"
        assert ids[2] == "RECENT"

    def test_empty_queue_when_all_on_cooldown(self):
        strategies = [
            _make_strategy("S1", last_backtest_at=_ts(0.1)),
            _make_strategy("S2", last_backtest_at=_ts(0.2)),
        ]
        sched = _make_scheduler(strategies, budget=BacktestBudget.AGGRESSIVE)  # cooldown=1h
        assert sched.get_priority_queue() == []

    def test_mixed_cooldown_returns_only_eligible(self):
        """Solo las estrategias fuera de cooldown aparecen en la cola."""
        strategies = [
            _make_strategy("HOT",  last_backtest_at=_ts(0.5)),   # en cooldown (1h)
            _make_strategy("COLD", last_backtest_at=_ts(2.0)),   # fuera de cooldown
        ]
        sched = _make_scheduler(strategies, budget=BacktestBudget.AGGRESSIVE)
        queue = sched.get_priority_queue()
        assert len(queue) == 1
        assert queue[0]["class_id"] == "COLD"
