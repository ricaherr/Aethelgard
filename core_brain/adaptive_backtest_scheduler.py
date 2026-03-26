"""
AdaptiveBacktestScheduler — Cooldown dinámico y cola de prioridad
=================================================================

Determina qué estrategias en modo BACKTEST deben ejecutarse en el próximo
ciclo, ordenadas por prioridad y respetando un cooldown que varía según el
contexto operacional del sistema (OperationalModeManager).

Prioridad de la cola:
  P1 — Nunca ejecutadas (last_backtest_at IS NULL, score_backtest=0).
  P2 — Ejecutadas sin score (score_backtest=0, last_backtest_at set).
  P3 — Con score — más antigua primero (menor last_backtest_at).

Cooldown dinámico:
  AGGRESSIVE   (BACKTEST_ONLY)  →  1 h
  MODERATE     (SHADOW_ACTIVE)  → 12 h
  CONSERVATIVE (LIVE_ACTIVE)    → 24 h
  DEFERRED     (recursos altos) →  cola vacía (sistema sobrecargado)

Dependencias:
  - OperationalModeManager (HU 10.7) — presupuesto y frecuencias.
  - StorageManager (SSOT) — carga estrategias en modo BACKTEST.

Trace_ID: EDGE-BACKTEST-HU712-ADAPTIVE-SCHEDULER-2026-03-25
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from core_brain.operational_mode_manager import BacktestBudget, OperationalModeManager
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class AdaptiveBacktestScheduler:
    """
    Priority-queue scheduler for BacktestOrchestrator.

    Usage (MainOrchestrator / BacktestOrchestrator)::

        scheduler = AdaptiveBacktestScheduler(
            storage=storage_manager,
            mode_manager=operational_mode_manager,
        )

        if scheduler.is_deferred():
            return   # system overloaded — skip this cycle

        for strategy in scheduler.get_priority_queue():
            await backtest_orchestrator.run_single_strategy(
                strategy["class_id"], force=True
            )
    """

    def __init__(
        self,
        storage: StorageManager,
        mode_manager: OperationalModeManager,
    ) -> None:
        self.storage      = storage
        self.mode_manager = mode_manager

    # ── Public API ────────────────────────────────────────────────────────────

    def get_effective_cooldown_hours(self) -> float:
        """
        Return the cooldown (hours) for this cycle based on backtest budget.

        Delegates to OperationalModeManager.get_component_frequencies() so the
        value is always coherent with what MainOrchestrator applies globally.
        """
        ctx   = self.mode_manager.current_context
        freqs = self.mode_manager.get_component_frequencies(ctx)
        return float(freqs["backtest_cooldown_h"])

    def is_deferred(self) -> bool:
        """Return True when system resources are insufficient for backtesting."""
        return self.mode_manager.get_backtest_budget() == BacktestBudget.DEFERRED

    def get_priority_queue(self) -> List[Dict[str, Any]]:
        """
        Return ordered list of strategies ready for the next backtest cycle.

        Steps:
          1. Return [] immediately if budget is DEFERRED.
          2. Load all strategies with mode='BACKTEST'.
          3. Filter out strategies on cooldown.
          4. Sort by priority (P1 > P2 > P3).
        """
        if self.is_deferred():
            logger.info("[ADAPTIVE_SCHED] Budget DEFERRED — skipping backtest cycle.")
            return []

        strategies  = self._load_backtest_strategies()
        cooldown_h  = self.get_effective_cooldown_hours()
        now         = datetime.now(timezone.utc)

        eligible = [s for s in strategies if not self._is_on_cooldown(s, cooldown_h, now)]
        return self._sort_by_priority(eligible)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_on_cooldown(
        self, strategy: Dict, cooldown_h: float, now: datetime
    ) -> bool:
        """True if strategy was backtested less than cooldown_h hours ago."""
        if strategy.get("mode") != "BACKTEST":
            return True

        raw = strategy.get("last_backtest_at")
        if not raw:
            return False  # never run → eligible immediately

        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_h = (now - ts).total_seconds() / 3600
            return age_h < cooldown_h
        except Exception:
            return False

    def _sort_by_priority(self, strategies: List[Dict]) -> List[Dict]:
        """
        Sort by (priority_tier, last_backtest_at):
          tier 0 — score=0 AND never run  (P1)
          tier 1 — score=0, has been run  (P2)
          tier 2 — has score              (P3, oldest first)
        """
        def _key(s: Dict) -> Tuple[int, str]:
            score     = float(s.get("score_backtest") or 0.0)
            last_run  = s.get("last_backtest_at")
            never_run = last_run is None

            if score == 0.0 and never_run:
                tier = 0
            elif score == 0.0:
                tier = 1
            else:
                tier = 2

            # Within tier: oldest last_backtest_at first (smallest ISO string)
            sort_ts = last_run or "0000-00-00"
            return (tier, sort_ts)

        return sorted(strategies, key=_key)

    def _load_backtest_strategies(self) -> List[Dict]:
        """Load strategies with mode='BACKTEST' from sys_strategies."""
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT class_id, mode, score_backtest, last_backtest_at, updated_at
                FROM sys_strategies
                WHERE mode = 'BACKTEST'
                """,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("[ADAPTIVE_SCHED] Failed to load BACKTEST strategies: %s", exc)
            return []
