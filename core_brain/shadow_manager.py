"""
ShadowManager: Orchestration logic for SHADOW EVOLUTION v2.1

Responsibility:
  - Evaluate health of all SHADOW instances (3 Pilares logic)
  - Determine promotability to REAL account
  - Generate Trace_IDs for all decisions
  - Orchestrate batch evaluations

Trace_ID: SHADOW-MANAGER-2026-001

Dependency Injection:
  - storage_manager: ShadowStorageManager (passed in, NOT self-instantiated)
  - promotion_validator: PromotionValidator (created internally)

Rules:
  - RULE DB-1: All governance tables use sys_ prefix
  - RULE ID-1: All decisions generate TRACE_ID_{YYYYMMDD}_{HHMMSS}_{instance_id[:8]}
  - RULE DI-1: Storage passed via dependency injection
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from models.shadow import (
    ShadowInstance,
    ShadowMetrics,
    ShadowStatus,
    HealthStatus,
)
from data_vault.shadow_db import ShadowStorageManager

logger = logging.getLogger(__name__)


class PromotionValidator:
    """
    Validates SHADOW instances against 3 Pilares before promotion to REAL.
    
    Pilares:
      1. PROFITABILIDAD: PF >= 1.5 AND WR >= 0.60
      2. RESILIENCIA: DD <= 0.12 AND CL <= 3
      3. CONSISTENCIA: trades >= 15 AND CV <= 0.40
    """

    # Thresholds (configurable from DB in production)
    PILAR1_MIN_PF = 1.5
    PILAR1_MIN_WR = 0.60
    PILAR2_MAX_DD = 0.12
    PILAR2_MAX_CL = 3
    PILAR3_MIN_TRADES = 15
    PILAR3_MAX_CV = 0.40

    def validate_pilar1_profitability(
        self, metrics: ShadowMetrics
    ) -> Tuple[bool, str]:
        """
        PILAR 1: PROFITABILIDAD (¿Gana dinero?)
        
        Requires:
          - profit_factor >= 1.5
          - win_rate >= 0.60
        
        Returns:
          (passed: bool, reason: str)
        """
        pf_pass = metrics.profit_factor >= self.PILAR1_MIN_PF
        wr_pass = metrics.win_rate >= self.PILAR1_MIN_WR

        if pf_pass and wr_pass:
            return True, f"Pilar 1 PASS: PF={metrics.profit_factor:.2f} (>= {self.PILAR1_MIN_PF}), WR={metrics.win_rate:.1%} (>= {self.PILAR1_MIN_WR:.0%})"
        else:
            failed = []
            if not pf_pass:
                failed.append(f"Profit Factor {metrics.profit_factor:.2f} < {self.PILAR1_MIN_PF}")
            if not wr_pass:
                failed.append(f"Win Rate {metrics.win_rate:.1%} < {self.PILAR1_MIN_WR:.0%}")
            return False, f"Pilar 1 FAILED: {' | '.join(failed)}"

    def validate_pilar2_resiliencia(
        self, metrics: ShadowMetrics
    ) -> Tuple[bool, str]:
        """
        PILAR 2: RESILIENCIA (¿Sobrevive stress?)
        
        Requires:
          - max_drawdown_pct <= 0.12
          - consecutive_losses_max <= 3
        
        Returns:
          (passed: bool, reason: str)
        """
        dd_pass = metrics.max_drawdown_pct <= self.PILAR2_MAX_DD
        cl_pass = metrics.consecutive_losses_max <= self.PILAR2_MAX_CL

        if dd_pass and cl_pass:
            return True, f"Pilar 2 PASS: DD={metrics.max_drawdown_pct:.1%} (<= {self.PILAR2_MAX_DD:.0%}), CL={metrics.consecutive_losses_max} (<= {self.PILAR2_MAX_CL})"
        else:
            failed = []
            if not dd_pass:
                failed.append(
                    f"Max Drawdown {metrics.max_drawdown_pct:.1%} > {self.PILAR2_MAX_DD:.0%}"
                )
            if not cl_pass:
                failed.append(
                    f"Consecutive Losses {metrics.consecutive_losses_max} > {self.PILAR2_MAX_CL}"
                )
            return False, f"Pilar 2 FAILED: {' | '.join(failed)}"

    def validate_pilar3_consistency(
        self, metrics: ShadowMetrics
    ) -> Tuple[bool, str]:
        """
        PILAR 3: CONSISTENCIA (¿Es predecible?)
        
        Requires:
          - total_trades_executed >= 15
          - equity_curve_cv <= 0.40
        
        Returns:
          (passed: bool, reason: str)
        """
        trades_pass = metrics.total_trades_executed >= self.PILAR3_MIN_TRADES
        cv_pass = metrics.equity_curve_cv <= self.PILAR3_MAX_CV

        if trades_pass and cv_pass:
            return True, f"Pilar 3 PASS: Trades={metrics.total_trades_executed} (>= {self.PILAR3_MIN_TRADES}), CV={metrics.equity_curve_cv:.2f} (<= {self.PILAR3_MAX_CV})"
        else:
            failed = []
            if not trades_pass:
                failed.append(
                    f"Trades Executed {metrics.total_trades_executed} < {self.PILAR3_MIN_TRADES}"
                )
            if not cv_pass:
                failed.append(
                    f"Equity Curve CV {metrics.equity_curve_cv:.2f} > {self.PILAR3_MAX_CV}"
                )
            return False, f"Pilar 3 FAILED: {' | '.join(failed)}"

    def validate_all_pillars(
        self, metrics: ShadowMetrics
    ) -> Tuple[bool, str]:
        """
        Validate all 3 Pilares simultaneously.
        
        Returns:
          (all_pass: bool, summary: str)
        """
        p1, p1_reason = self.validate_pilar1_profitability(metrics)
        p2, p2_reason = self.validate_pilar2_resiliencia(metrics)
        p3, p3_reason = self.validate_pilar3_consistency(metrics)

        if p1 and p2 and p3:
            summary = f"✅ 3 Pilares HEALTHY: {p1_reason} | {p2_reason} | {p3_reason}"
            return True, summary
        else:
            failed_pillars = []
            if not p1:
                failed_pillars.append(p1_reason)
            if not p2:
                failed_pillars.append(p2_reason)
            if not p3:
                failed_pillars.append(p3_reason)
            summary = f"❌ Pilares FAILED: {' | '.join(failed_pillars)}"
            return False, summary


class ShadowManager:
    """
    Orchestrates health evaluation and promotion decisions for SHADOW instances.
    
    Responsibilities:
      1. Evaluate single instance health (3 Pilares)
      2. Batch evaluate all instances
      3. Classify instances (HEALTHY | MONITOR | QUARANTINED | DEAD)
      4. Determine promotability to REAL account
      5. Generate Trace_IDs for all decisions
    
    Dependency Injection:
      - storage: ShadowStorageManager (NOT self-instantiated)
    """

    def __init__(self, storage: ShadowStorageManager):
        """
        Initialize ShadowManager with injected dependencies.
        
        Args:
            storage: ShadowStorageManager instance (injected, NOT self-created)
        """
        self.storage = storage
        self.promotion_validator = PromotionValidator()
        self.logger = logging.getLogger(__name__)

    def generate_trace_id(
        self, instance_id: str, event_type: str = "HEALTH"
    ) -> str:
        """
        Generate Trace_ID for decision tracking (RULE ID-1).
        
        Pattern: TRACE_{EVENT}_{YYYYMMDD}_{HHMMSS}_{instance_id[:8]}
        
        Args:
            instance_id: SHADOW instance UUID
            event_type: HEALTH | PROMOTION_REAL | KILL | QUARANTINE (default: HEALTH)
        
        Returns:
            Trace_ID string
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        short_id = instance_id[:8] if len(instance_id) >= 8 else instance_id
        
        return f"TRACE_{event_type}_{timestamp}_{short_id}"

    def evaluate_single_instance(
        self, instance: ShadowInstance, return_trace: bool = False
    ) -> Tuple[HealthStatus, Optional[str]]:
        """
        Evaluate health of single SHADOW instance against 3 Pilares.
        
        Decision Tree:
          1. If Pilar 1 FAILS → DEAD
          2. Else if Pilar 2 FAILS → QUARANTINED
          3. Else if Pilar 3 WEAK → MONITOR
          4. Else → HEALTHY
        
        Args:
            instance: ShadowInstance to evaluate
            return_trace: If True, also return Trace_ID
        
        Returns:
            HealthStatus or (HealthStatus, trace_id) if return_trace=True
        """
        metrics = instance.metrics
        trace_id = self.generate_trace_id(instance.instance_id, "HEALTH")

        # PILAR 1: PROFITABILIDAD (death condition)
        p1_pass, p1_reason = self.promotion_validator.validate_pilar1_profitability(
            metrics
        )
        if not p1_pass and metrics.total_trades_executed >= 15:  # Only kill if enough sample
            self.logger.warning(
                f"[SHADOW] {trace_id}: MUERTE - Pilar 1 FALLIDO | {p1_reason}"
            )
            if return_trace:
                return HealthStatus.DEAD, trace_id
            return HealthStatus.DEAD

        # PILAR 2: RESILIENCIA (quarantine condition)
        p2_pass, p2_reason = self.promotion_validator.validate_pilar2_resiliencia(
            metrics
        )
        if not p2_pass:
            self.logger.warning(
                f"[SHADOW] {trace_id}: CUARENTENA - Pilar 2 FALLIDO | {p2_reason}"
            )
            if return_trace:
                return HealthStatus.QUARANTINED, trace_id
            return HealthStatus.QUARANTINED

        # PILAR 3: CONSISTENCIA (monitor condition)
        p3_pass, p3_reason = self.promotion_validator.validate_pilar3_consistency(
            metrics
        )
        if not p3_pass:
            self.logger.info(
                f"[SHADOW] {trace_id}: MONITOR - Pilar 3 DÉBIL | {p3_reason}"
            )
            if return_trace:
                return HealthStatus.MONITOR, trace_id
            return HealthStatus.MONITOR

        # All 3 Pilares PASS
        self.logger.info(f"[SHADOW] {trace_id}: ✅ HEALTHY - 3 Pilares validados")
        if return_trace:
            return HealthStatus.HEALTHY, trace_id
        return HealthStatus.HEALTHY

    def is_promotable_to_real(
        self, instance: ShadowInstance
    ) -> Tuple[bool, str]:
        """
        Determine if SHADOW instance is promotable to REAL account.
        
        Requirements:
          1. Status must be INCUBATING (not already promoted)
          2. Health must be HEALTHY (all 3 Pilares PASS)
          3. Minimum metrics met
        
        Args:
            instance: ShadowInstance to check
        
        Returns:
            (can_promote: bool, reason: str)
        """
        # Check current status
        if instance.status == ShadowStatus.PROMOTED_TO_REAL:
            return False, "Already promoted to REAL"
        
        if instance.status == ShadowStatus.DEAD:
            return False, "Instance marked DEAD - cannot promote"
        
        if instance.status == ShadowStatus.QUARANTINED:
            return False, "Instance QUARANTINED - cannot promote until retest passes"

        # Evaluate health
        health, trace_id = self.evaluate_single_instance(instance, return_trace=True)
        
        # Get detailed pillar information
        metrics = instance.metrics
        p1_pass, p1_reason = self.promotion_validator.validate_pilar1_profitability(metrics)
        p2_pass, p2_reason = self.promotion_validator.validate_pilar2_resiliencia(metrics)
        p3_pass, p3_reason = self.promotion_validator.validate_pilar3_consistency(metrics)

        if health != HealthStatus.HEALTHY:
            if not p1_pass:
                return False, f"Cannot promote: {p1_reason} (Trace: {trace_id})"
            elif not p2_pass:
                return False, f"Cannot promote: {p2_reason} (Trace: {trace_id})"
            elif not p3_pass:
                return False, f"Cannot promote: {p3_reason} (Trace: {trace_id})"
            else:
                return (
                    False,
                    f"Health is {health.value}, not HEALTHY (Trace: {trace_id})",
                )

        # Validate all 3 Pilares explicitly
        approved, pillar_reason = self.promotion_validator.validate_all_pillars(
            instance.metrics
        )
        if not approved:
            return False, f"Pilares validation failed: {pillar_reason}"

        return True, f"✅ Promotable to REAL - 3 Pilares confirmed (Trace: {trace_id})"

    def evaluate_all_instances(self) -> Dict[str, List[Dict]]:
        """
        Batch evaluate all SHADOW instances and classify by health/action.
        
        Returns:
            Dict with keys:
              - promotions: List of (instance_id, trace_id) ready for REAL account
              - kills: List of (instance_id, trace_id) marked DEAD
              - quarantines: List of (instance_id, trace_id) marked QUARANTINED
              - monitors: List of (instance_id, trace_id) marked MONITOR
        """
        # In Week 2, assume we're reading from storage
        # For now, return empty structure (storage not yet implemented)
        result = {
            "promotions": [],
            "kills": [],
            "quarantines": [],
            "monitors": [],
        }

        # TODO: When storage.list_shadow_instances() is implemented:
        # instances = self.storage.list_shadow_instances(status=ShadowStatus.INCUBATING)
        # for instance in instances:
        #     health = self.evaluate_single_instance(instance)
        #     ...append to result

        return result
