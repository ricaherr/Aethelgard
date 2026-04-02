"""
shadow_db.py — Storage layer for SHADOW EVOLUTION v2.1 (sys_shadow_* tables).

Responsibility: CRUD operations for shadow instances, performance history, and promotion logs.
Uses dependency injection pattern (no self-instantiation of Storage whatsoever).
Follows RULE DB-1 (sys_ prefix) and RULE ID-1 (TRACE_ID patterns).

Trace_ID Patterns:
- TRACE_PROMOTION_REAL_{YYYYMMDD}_{HHMMSS}_{instance_id[:8]}
- TRACE_HEALTH_{YYYYMMDD}_{HHMMSS}_{instance_id[:8]}
- TRACE_KILL_{YYYYMMDD}_{HHMMSS}_{instance_id[:8]}
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Callable, Any
from uuid import uuid4

from models.shadow import (
    ShadowInstance,
    ShadowStatus,
    ShadowMetrics,
    ShadowPerformanceHistory,
    ShadowPromotionLog,
    HealthStatus,
    PillarStatus,
)

logger: logging.Logger = logging.getLogger(__name__)


class ShadowStorageManager:
    """
    Storage operations for SHADOW EVOLUTION protocol.
    Thread-safe wrapper around SQLite connection.
    Dependency Injection: storage_conn passed in, NOT created here.
    """

    def __init__(self, storage_conn: sqlite3.Connection) -> None:
        """
        Initialize with existing storage connection.
        No self-instantiation of databases.
        """
        self.conn: sqlite3.Connection = storage_conn
        self.conn.row_factory = sqlite3.Row

    def _execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        retries: int = 10,
        backoff: float = 0.5,
        **kwargs: Any
    ) -> Any:
        """
        Ejecuta una función con retry exponential si DB está locked.

        FIX-SHADOW-CONTENTION-001: Necesario porque concurrent writers
        en ShadowManager pueden saturar el WAL con 45+ commits/segundo.

        Args:
            func: Función a ejecutar (ej: una lambda que hace INSERT)
            retries: Número máximo de intentos (default 10)
            backoff: Multiplicador de espera exponencial (default 0.5s)
            *args, **kwargs: Argumentos para func

        Returns:
            Resultado de func()

        Raises:
            Last exception si todos los retries fallan
        """
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if 'locked' in str(e).lower():
                    last_exc = e
                    if attempt < retries - 1:
                        wait_time = backoff * (2 ** attempt)  # 0.5s, 1s, 2s, 4s, 8s, 16s...
                        logger.debug(
                            f"[SHADOW] DB locked, retrying ({attempt+1}/{retries}) "
                            f"waiting {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                raise
            except Exception:
                raise  # No-retry para otros tipos de error

        logger.error(
            f"[SHADOW] DB locked after {retries} retries, last error: {last_exc}"
        )
        raise last_exc if last_exc else RuntimeError("DB locked after retries")

    # ────────────────────────────────────────────────────────────────────────
    # sys_shadow_instances CRUD
    # ────────────────────────────────────────────────────────────────────────

    def create_shadow_instance(
        self,
        instance_id: str,
        strategy_id: str,
        account_id: str,
        account_type: str,
        parameter_overrides: Optional[Dict[str, Any]] = None,
        regime_filters: Optional[List[str]] = None,
    ) -> ShadowInstance:
        """
        Create a new SHADOW instance in the pool.
        
        Args:
            instance_id: UUID for this instance
            strategy_id: Strategy to execute (e.g., 'BRK_OPEN_0001')
            account_id: Account this instance belongs to
            account_type: 'DEMO' or 'REAL' (immutable)
            parameter_overrides: Dict of parameter adjustments
            regime_filters: List of allowed regimes
        
        Returns:
            ShadowInstance object
        
        Raises:
            ValueError: If account_type is invalid
        """
        if account_type not in ("DEMO", "REAL"):
            raise ValueError(f"account_type must be DEMO or REAL, got {account_type}")

        instance = ShadowInstance(
            instance_id=instance_id,
            strategy_id=strategy_id,
            account_id=account_id,
            account_type=account_type,
            parameter_overrides=parameter_overrides or {},
            regime_filters=regime_filters or [],
            birth_timestamp=datetime.now(timezone.utc),
        )

        cursor: sqlite3.Cursor = self.conn.cursor()
        db_dict = instance.to_db_dict()

        cursor.execute(
            """
            INSERT INTO sys_shadow_instances (
                instance_id, strategy_id, account_id, account_type,
                parameter_overrides, regime_filters, birth_timestamp, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                db_dict["instance_id"],
                db_dict["strategy_id"],
                db_dict["account_id"],
                db_dict["account_type"],
                db_dict["parameter_overrides"],
                db_dict["regime_filters"],
                db_dict["birth_timestamp"],
                db_dict["status"],
                db_dict["created_at"],
                db_dict["updated_at"],
            ),
        )
        self.conn.commit()
        logger.info(f"[SHADOW] Created instance {instance_id} ({strategy_id}) in {account_type}")
        return instance

    def get_shadow_instance(self, instance_id: str) -> Optional[ShadowInstance]:
        """Retrieve a SHADOW instance by ID."""
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sys_shadow_instances WHERE instance_id = ?", (instance_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ShadowInstance.from_db_dict(dict(row))

    def get_all_shadow_instances(self, account_id: str) -> List[ShadowInstance]:
        """Get all instances for an account."""
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM sys_shadow_instances WHERE account_id = ? ORDER BY created_at DESC",
            (account_id,),
        )
        return [ShadowInstance.from_db_dict(dict(row)) for row in cursor.fetchall()]

    def update_shadow_instance(self, instance: ShadowInstance) -> None:
        """Update an existing SHADOW instance."""
        def _do_update() -> None:
            cursor: sqlite3.Cursor = self.conn.cursor()
            db_dict = instance.to_db_dict()
            cursor.execute(
                """
                UPDATE sys_shadow_instances SET
                    strategy_id = ?, status = ?,
                    total_trades_executed = ?, profit_factor = ?, win_rate = ?,
                    max_drawdown_pct = ?, consecutive_losses_max = ?,
                    equity_curve_cv = ?,
                    promotion_trace_id = ?, backtest_trace_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE instance_id = ?
                """,
                (
                    db_dict["strategy_id"],
                    db_dict["status"],
                    db_dict["total_trades_executed"],
                    db_dict["profit_factor"],
                    db_dict["win_rate"],
                    db_dict["max_drawdown_pct"],
                    db_dict["consecutive_losses_max"],
                    db_dict["equity_curve_cv"],
                    db_dict["promotion_trace_id"],
                    db_dict["backtest_trace_id"],
                    db_dict["instance_id"],
                ),
            )
            self.conn.commit()
            logger.debug(f"[SHADOW] Updated instance {instance.instance_id}")

        # FIX-SHADOW-CONTENTION-001: Retry si DB está locked
        self._execute_with_retry(_do_update)

    def delete_shadow_instance(self, instance_id: str) -> None:
        """
        Mark a SHADOW instance as deleted (soft delete is safer).
        Note: Hard delete is discouraged (audit trail loss).
        """
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE sys_shadow_instances SET status = ? WHERE instance_id = ?",
            (ShadowStatus.DEAD.value, instance_id),
        )
        self.conn.commit()
        logger.info(f"[SHADOW] Marked instance {instance_id} as DEAD")

    # ────────────────────────────────────────────────────────────────────────
    # sys_shadow_performance_history CRUD
    # ────────────────────────────────────────────────────────────────────────

    def record_performance_snapshot(
        self,
        instance_id: str,
        pillar1_status: str,
        pillar2_status: str,
        pillar3_status: str,
        overall_health: str,
        event_trace_id: str,
    ) -> ShadowPerformanceHistory:
        """
        Record a weekly performance evaluation snapshot.

        Args:
            instance_id: Instance being evaluated
            pillar1_status: 'PASS' or 'FAIL'
            pillar2_status: 'PASS' or 'FAIL'
            pillar3_status: 'PASS' or 'FAIL'
            overall_health: HealthStatus value
            event_trace_id: TRACE_HEALTH_... identifier

        Returns:
            ShadowPerformanceHistory object created
        """
        history = ShadowPerformanceHistory(
            instance_id=instance_id,
            evaluation_date=datetime.now(timezone.utc),
            pillar1_status=PillarStatus(pillar1_status),
            pillar2_status=PillarStatus(pillar2_status),
            pillar3_status=PillarStatus(pillar3_status),
            overall_health=HealthStatus(overall_health),
            event_trace_id=event_trace_id,
        )

        def _do_insert() -> None:
            cursor: sqlite3.Cursor = self.conn.cursor()
            db_dict = history.to_db_dict()
            cursor.execute(
                """
                INSERT INTO sys_shadow_performance_history (
                    instance_id, evaluation_date, pillar1_status, pillar2_status,
                    pillar3_status, overall_health, event_trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    db_dict["instance_id"],
                    db_dict["evaluation_date"],
                    db_dict["pillar1_status"],
                    db_dict["pillar2_status"],
                    db_dict["pillar3_status"],
                    db_dict["overall_health"],
                    db_dict["event_trace_id"],
                ),
            )
            self.conn.commit()
            logger.debug(f"[SHADOW] Recorded performance snapshot for {instance_id}: {event_trace_id}")

        # FIX-SHADOW-CONTENTION-001: Retry si DB está locked
        self._execute_with_retry(_do_insert)
        return history

    def get_performance_history(
        self, instance_id: str, limit: int = 10
    ) -> List[ShadowPerformanceHistory]:
        """Get recent performance snapshots for an instance."""
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM sys_shadow_performance_history
            WHERE instance_id = ?
            ORDER BY evaluation_date DESC
            LIMIT ?
            """,
            (instance_id, limit),
        )
        return [ShadowPerformanceHistory.from_db_dict(dict(row)) for row in cursor.fetchall()]

    # ────────────────────────────────────────────────────────────────────────
    # sys_shadow_promotion_log CRUD (INSERT-ONLY, IMMUTABLE)
    # ────────────────────────────────────────────────────────────────────────

    def log_promotion_decision(
        self,
        instance_id: str,
        trace_id: str,
        promotion_status: str = "PENDING",
        pillar1_passed: bool = False,
        pillar2_passed: bool = False,
        pillar3_passed: bool = False,
        notes: str = "",
    ) -> ShadowPromotionLog:
        """
        Record a promotion decision (INSERT-ONLY, audit trail is immutable).

        Args:
            instance_id: Instance being promoted
            trace_id: Unique identifier (TRACE_PROMOTION_REAL_...)
            promotion_status: 'PENDING', 'APPROVED', 'REJECTED', 'EXECUTED'
            pillar1_passed: Profitability pilar PASS?
            pillar2_passed: Resiliencia pilar PASS?
            pillar3_passed: Consistencia pilar PASS?
            notes: Additional context

        Returns:
            ShadowPromotionLog object created
        """
        log = ShadowPromotionLog(
            instance_id=instance_id,
            trace_id=trace_id,
            promotion_status=promotion_status,
            pillar1_passed=pillar1_passed,
            pillar2_passed=pillar2_passed,
            pillar3_passed=pillar3_passed,
            approval_timestamp=datetime.now(timezone.utc),
            notes=notes,
        )

        def _do_insert() -> None:
            cursor: sqlite3.Cursor = self.conn.cursor()
            db_dict = log.to_db_dict()
            cursor.execute(
                """
                INSERT INTO sys_shadow_promotion_log (
                    instance_id, trace_id, promotion_status,
                    pillar1_passed, pillar2_passed, pillar3_passed,
                    approval_timestamp, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    db_dict["instance_id"],
                    db_dict["trace_id"],
                    db_dict["promotion_status"],
                    db_dict["pillar1_passed"],
                    db_dict["pillar2_passed"],
                    db_dict["pillar3_passed"],
                    db_dict["approval_timestamp"],
                    db_dict["notes"],
                ),
            )
            self.conn.commit()
            logger.info(f"[SHADOW] Logged promotion decision {trace_id} for {instance_id}: {promotion_status}")

        # FIX-SHADOW-CONTENTION-001: Retry si DB está locked
        self._execute_with_retry(_do_insert)
        return log

    def get_promotion_log(self, instance_id: str) -> List[ShadowPromotionLog]:
        """Get all promotion log entries for an instance."""
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM sys_shadow_promotion_log
            WHERE instance_id = ?
            ORDER BY created_at DESC
            """,
            (instance_id,),
        )
        return [ShadowPromotionLog.from_db_dict(dict(row)) for row in cursor.fetchall()]

    # ────────────────────────────────────────────────────────────────────────
    # Business Logic Helpers (Trace_ID Generation)
    # ────────────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_health_trace_id(instance_id: str) -> str:
        """Generate TRACE_ID for health evaluation."""
        now: datetime = datetime.now(timezone.utc)
        timestamp: str = now.strftime("%Y%m%d_%H%M%S")
        return f"TRACE_HEALTH_{timestamp}_{instance_id[:8]}"

    @staticmethod
    def generate_promotion_trace_id(instance_id: str) -> str:
        """Generate TRACE_ID for promotion to REAL."""
        now: datetime = datetime.now(timezone.utc)
        timestamp: str = now.strftime("%Y%m%d_%H%M%S")
        return f"TRACE_PROMOTION_REAL_{timestamp}_{instance_id[:8]}"

    @staticmethod
    def generate_kill_trace_id(instance_id: str) -> str:
        """Generate TRACE_ID for killing an instance."""
        now: datetime = datetime.now(timezone.utc)
        timestamp: str = now.strftime("%Y%m%d_%H%M%S")
        return f"TRACE_KILL_{timestamp}_{instance_id[:8]}"

    # ────────────────────────────────────────────────────────────────────────
    # Batch Query Methods (for evaluate_all_instances)
    # ────────────────────────────────────────────────────────────────────────

    def list_active_instances(self) -> List[ShadowInstance]:
        """
        Retrieve all SHADOW instances eligible for evaluation.

        Excludes DEAD and PROMOTED_TO_REAL instances (terminal states).
        Used by evaluate_all_instances() for batch processing.

        Returns:
            List of ShadowInstance ordered by creation date (oldest first).
        """
        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM sys_shadow_instances
            WHERE status NOT IN (?, ?)
            ORDER BY created_at ASC
            """,
            (ShadowStatus.DEAD.value, ShadowStatus.PROMOTED_TO_REAL.value),
        )
        rows: List[Any] = cursor.fetchall()
        return [ShadowInstance.from_db_dict(dict(row)) for row in rows]

    def calculate_instance_metrics_from_sys_trades(self, instance_id: str) -> ShadowMetrics:
        """Calculate 3 Pilares metrics for a SHADOW instance by reading sys_trades.

        This is the LIVE feedback loop: real DEMO trades → metrics → Darwinian selection.
        Called by ShadowManager.evaluate_all_instances() weekly.

        Args:
            instance_id: The SHADOW instance to evaluate.
        Returns:
            ShadowMetrics populated from sys_trades data.
        """
        import statistics as _stats

        cursor: sqlite3.Cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT profit, close_time FROM sys_trades
            WHERE instance_id = ? AND execution_mode = 'SHADOW'
            ORDER BY close_time ASC
            """,
            (instance_id,),
        )
        rows: List[Any] = cursor.fetchall()

        if not rows:
            return ShadowMetrics()

        profits: List[Any] = [r["profit"] for r in rows if r["profit"] is not None]
        if not profits:
            return ShadowMetrics()

        total: int = len(profits)
        wins: List[Any] = [p for p in profits if p > 0]
        losses: List[Any] = [abs(p) for p in profits if p < 0]

        win_rate: float = len(wins) / total if total > 0 else 0.0
        profit_factor: float = (
            sum(wins) / sum(losses) if losses else (1.5 if wins else 0.0)
        )

        # Equity curve CV (consistency metric)
        cumulative = []
        running = 0.0
        for p in profits:
            running += p
            cumulative.append(running)
        mean_equity = _stats.mean(cumulative) if cumulative else 0.0
        equity_cv = (
            (_stats.stdev(cumulative) / abs(mean_equity))
            if len(cumulative) > 1 and mean_equity != 0
            else 0.0
        )

        # Consecutive losses
        max_consec = 0
        current_consec = 0
        for p in profits:
            if p < 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0

        return ShadowMetrics(
            total_trades_executed=total,
            win_rate=win_rate,
            profit_factor=profit_factor,
            equity_curve_cv=equity_cv,
            consecutive_losses_max=max_consec,
        )

    def update_strategy_score_shadow(self, strategy_id: str, score_shadow: float) -> None:
        """
        Persist score_shadow to sys_strategies for the Darwinian scoring formula.

        FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30:
        score_shadow was never written after shadow evaluation, leaving it at 0.0
        and biasing the formula  score = live×0.50 + shadow×0.30 + backtest×0.20.

        Formula for score_shadow derived from ShadowMetrics:
            score_shadow = win_rate × min(profit_factor / 3.0, 1.0)
        Callers (ShadowManager) compute this value and pass it in.

        Args:
            strategy_id: sys_strategies.class_id to update.
            score_shadow: Normalized shadow score in [0.0, 1.0].
        """
        def _do_update() -> None:
            cursor: sqlite3.Cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE sys_strategies
                SET score_shadow = ?, updated_at = ?
                WHERE class_id = ?
                """,
                (round(score_shadow, 4), datetime.now(timezone.utc).isoformat(), strategy_id),
            )
            self.conn.commit()
            logger.debug(
                "[SHADOW] score_shadow updated: strategy=%s score_shadow=%.4f",
                strategy_id, score_shadow,
            )

        # FIX-SHADOW-CONTENTION-001: Retry si DB está locked
        self._execute_with_retry(_do_update)

    def update_parameter_overrides(self, instance_id: str, overrides: Dict[str, Any]) -> None:
        """
        Persist EdgeTuner-adjusted parameter overrides for a SHADOW instance.

        Called after each EdgeTuner feedback cycle to store per-instance
        calibrations that diverge from global strategy defaults.

        Args:
            instance_id: Target SHADOW instance UUID.
            overrides: Dict of parameter overrides (e.g. {"confidence_threshold": 0.77}).
        """
        def _do_update() -> None:
            cursor: sqlite3.Cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE sys_shadow_instances
                SET parameter_overrides = ?, updated_at = ?
                WHERE instance_id = ?
                """,
                (json.dumps(overrides), datetime.now(timezone.utc).isoformat(), instance_id),
            )
            self.conn.commit()
            logger.debug(f"[SHADOW] Updated parameter_overrides for {instance_id}: {overrides}")

        # FIX-SHADOW-CONTENTION-001: Retry si DB está locked
        self._execute_with_retry(_do_update)


# Convenience function for backwards compatibility
def create_shadow_manager(storage_conn: sqlite3.Connection) -> ShadowStorageManager:
    """Factory function to create ShadowStorageManager with DI."""
    return ShadowStorageManager(storage_conn)
