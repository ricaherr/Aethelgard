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

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
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

logger = logging.getLogger(__name__)


class ShadowStorageManager:
    """
    Storage operations for SHADOW EVOLUTION protocol.
    Thread-safe wrapper around SQLite connection.
    Dependency Injection: storage_conn passed in, NOT created here.
    """

    def __init__(self, storage_conn: sqlite3.Connection):
        """
        Initialize with existing storage connection.
        No self-instantiation of databases.
        """
        self.conn = storage_conn
        self.conn.row_factory = sqlite3.Row

    # ────────────────────────────────────────────────────────────────────────
    # sys_shadow_instances CRUD
    # ────────────────────────────────────────────────────────────────────────

    def create_shadow_instance(
        self,
        instance_id: str,
        strategy_id: str,
        account_id: str,
        account_type: str,
        parameter_overrides: Dict = None,
        regime_filters: List[str] = None,
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

        cursor = self.conn.cursor()
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
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sys_shadow_instances WHERE instance_id = ?", (instance_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ShadowInstance.from_db_dict(dict(row))

    def get_all_shadow_instances(self, account_id: str) -> List[ShadowInstance]:
        """Get all instances for an account."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM sys_shadow_instances WHERE account_id = ? ORDER BY created_at DESC",
            (account_id,),
        )
        return [ShadowInstance.from_db_dict(dict(row)) for row in cursor.fetchall()]

    def update_shadow_instance(self, instance: ShadowInstance) -> None:
        """Update an existing SHADOW instance."""
        cursor = self.conn.cursor()
        db_dict = instance.to_db_dict()

        cursor.execute(
            """
            UPDATE sys_shadow_instances SET
                strategy_id = ?, status = ?,
                total_trades_executed = ?, profit_factor = ?, win_rate = ?,
                max_drawdown_pct = ?, consecutive_losses_max = ?,
                equity_curve_cv = ?,
                promotion_trace_id = ?, backtest_trace_id = ?,
                updated_at = ?
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
                db_dict["updated_at"],
                db_dict["instance_id"],
            ),
        )
        self.conn.commit()
        logger.debug(f"[SHADOW] Updated instance {instance.instance_id}")

    def delete_shadow_instance(self, instance_id: str) -> None:
        """
        Mark a SHADOW instance as deleted (soft delete is safer).
        Note: Hard delete is discouraged (audit trail loss).
        """
        cursor = self.conn.cursor()
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

        cursor = self.conn.cursor()
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
        return history

    def get_performance_history(
        self, instance_id: str, limit: int = 10
    ) -> List[ShadowPerformanceHistory]:
        """Get recent performance snapshots for an instance."""
        cursor = self.conn.cursor()
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

        cursor = self.conn.cursor()
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
        return log

    def get_promotion_log(self, instance_id: str) -> List[ShadowPromotionLog]:
        """Get all promotion log entries for an instance."""
        cursor = self.conn.cursor()
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
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        return f"TRACE_HEALTH_{timestamp}_{instance_id[:8]}"

    @staticmethod
    def generate_promotion_trace_id(instance_id: str) -> str:
        """Generate TRACE_ID for promotion to REAL."""
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        return f"TRACE_PROMOTION_REAL_{timestamp}_{instance_id[:8]}"

    @staticmethod
    def generate_kill_trace_id(instance_id: str) -> str:
        """Generate TRACE_ID for killing an instance."""
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
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
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM sys_shadow_instances
            WHERE status NOT IN (?, ?)
            ORDER BY created_at ASC
            """,
            (ShadowStatus.DEAD.value, ShadowStatus.PROMOTED_TO_REAL.value),
        )
        rows = cursor.fetchall()
        return [ShadowInstance.from_db_dict(dict(row)) for row in rows]

    def update_parameter_overrides(self, instance_id: str, overrides: Dict) -> None:
        """
        Persist EdgeTuner-adjusted parameter overrides for a SHADOW instance.

        Called after each EdgeTuner feedback cycle to store per-instance
        calibrations that diverge from global strategy defaults.

        Args:
            instance_id: Target SHADOW instance UUID.
            overrides: Dict of parameter overrides (e.g. {"confidence_threshold": 0.77}).
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE sys_shadow_instances
            SET parameter_overrides = ?, updated_at = ?
            WHERE instance_id = ?
            """,
            (str(overrides), datetime.now(timezone.utc).isoformat(), instance_id),
        )
        self.conn.commit()
        logger.debug(f"[SHADOW] Updated parameter_overrides for {instance_id}: {overrides}")


# Convenience function for backwards compatibility
def create_shadow_manager(storage_conn: sqlite3.Connection) -> ShadowStorageManager:
    """Factory function to create ShadowStorageManager with DI."""
    return ShadowStorageManager(storage_conn)
