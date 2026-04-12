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
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Optional, Union
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
    PILAR3_MAX_CV = 0.40

    def __init__(self, min_trades: int = 15) -> None:
        """Initialize with configurable Pilar 3 threshold.

        Args:
            min_trades: Minimum shadow trades required for Pilar 3. Default 15.
                        Set lower (e.g. 5) for low-frequency strategies.
                        HU 3.13 — Trace_ID: ADAPTIVE-PILAR3-2026-03-25
        """
        self.PILAR3_MIN_TRADES = min_trades

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
            summary = f"[OK] 3 Pilares HEALTHY: {p1_reason} | {p2_reason} | {p3_reason}"
            return True, summary
        else:
            failed_pillars = []
            if not p1:
                failed_pillars.append(p1_reason)
            if not p2:
                failed_pillars.append(p2_reason)
            if not p3:
                failed_pillars.append(p3_reason)
            summary = f"[FAIL] Pilares FAILED: {' | '.join(failed_pillars)}"
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

    def __init__(
        self,
        storage: Union[ShadowStorageManager, 'StorageManager'],
        regime_classifier: Optional[Any] = None,
        edge_tuner: Optional[Any] = None,
        pilar3_min_trades: int = 15,
    ):
        """
        Initialize ShadowManager with injected dependencies.

        Args:
            storage: Either ShadowStorageManager instance OR generic StorageManager.
                     If StorageManager, extracts .conn to create ShadowStorageManager.
            regime_classifier: Optional RegimeClassifier for threshold context-adjustment.
                               When provided, TREND/RANGE/CRASH regimes modulate thresholds.
            edge_tuner: Optional EdgeTuner for per-instance confidence calibration.
                        When provided, updates parameter_overrides after each evaluation.
            pilar3_min_trades: Pilar 3 minimum trades threshold. Reads from
                               dynamic_params.pilar3_min_trades at startup (default 5).
                               HU 3.13 — Trace_ID: ADAPTIVE-PILAR3-2026-03-25
        """
        # Handle both ShadowStorageManager and generic StorageManager
        if isinstance(storage, ShadowStorageManager):
            self.storage = storage
        else:
            try:
                if hasattr(storage, 'conn'):
                    conn = storage.conn
                elif hasattr(storage, 'connection'):
                    conn = storage.connection
                elif hasattr(storage, 'get_conn'):
                    conn = storage.get_conn()
                elif hasattr(storage, '_get_conn'):
                    conn = storage._get_conn()
                elif hasattr(storage, 'get_connection'):
                    conn = storage.get_connection()
                else:
                    raise AttributeError(
                        f"Cannot extract SQLite connection from {type(storage).__name__}. "
                        f"Expected .conn/.connection or one of get_conn(), _get_conn(), get_connection()."
                    )
                self.storage = ShadowStorageManager(conn)
            except (AttributeError, TypeError) as e:
                logger.error(f"Failed to create ShadowStorageManager: {e}")
                raise

        self.promotion_validator = PromotionValidator(min_trades=pilar3_min_trades)
        self.regime_classifier = regime_classifier
        self.edge_tuner = edge_tuner
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
        self.logger.info(f"[SHADOW] {trace_id}: [OK] HEALTHY - 3 Pilares validados")
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

        return True, f"[OK] Promotable to REAL - 3 Pilares confirmed (Trace: {trace_id})"

    def _get_current_regime(self) -> str:
        """
        Query RegimeClassifier for the current market regime.

        Returns:
            Regime string: 'TREND' | 'RANGE' | 'CRASH' | 'NORMAL'.
            Falls back to 'NORMAL' if classifier is unavailable.
        """
        if self.regime_classifier is None:
            return "NORMAL"
        try:
            regime = self.regime_classifier.classify()
            return regime.value if hasattr(regime, "value") else str(regime)
        except Exception as e:
            self.logger.warning(f"[SHADOW] RegimeClassifier error, using NORMAL: {e}")
            return "NORMAL"

    def _build_regime_adjusted_validator(self, regime: str) -> PromotionValidator:
        """
        Build a PromotionValidator with thresholds tuned to the current regime.

        Regime adjustments:
          TREND  → WR floor drops to 0.55 (trends reward momentum, not mean-reversion).
                   DD ceiling tightens to 0.10 (trending losses are more dangerous).
          RANGE  → Standard thresholds (WR 0.60, DD 0.12).
          CRASH  → Defensive: WR floor rises to 0.65, DD ceiling tightens to 0.08.
          NORMAL → Standard thresholds.

        Args:
            regime: Current market regime string.

        Returns:
            PromotionValidator configured for the given regime.
        """
        validator = PromotionValidator(
            min_trades=self.promotion_validator.PILAR3_MIN_TRADES
        )

        if regime == "TREND":
            validator.PILAR1_MIN_WR = 0.55
            validator.PILAR2_MAX_DD = 0.10
        elif regime == "CRASH":
            validator.PILAR1_MIN_WR = 0.65
            validator.PILAR2_MAX_DD = 0.08

        return validator

    def _apply_edge_tuner_overrides(
        self,
        instance: 'ShadowInstance',
        health: HealthStatus,
        p1_pass: bool,
    ) -> None:
        """
        Use EdgeTuner feedback to adjust per-instance parameter_overrides.

        Logic:
          HEALTHY  → Increase confidence_threshold override by 0.01 (exploit edge).
          MONITOR  → Decrease confidence_threshold override by 0.01 (be more selective).
          QUARANTINED → Decrease by 0.02 and raise min_signal_score by 5 pts.
          DEAD     → No update (terminal state).

        Persists via storage.update_parameter_overrides().

        Args:
            instance: ShadowInstance being evaluated.
            health: Health classification result.
            p1_pass: Whether Pilar 1 (Profitability) passed.
        """
        if self.edge_tuner is None:
            return

        try:
            current_overrides = dict(instance.parameter_overrides)

            current_ct = float(current_overrides.get("confidence_threshold", 0.75))
            current_ms = int(current_overrides.get("min_signal_score", 60))

            if health == HealthStatus.HEALTHY:
                new_ct = min(0.95, current_ct + 0.01)
                current_overrides["confidence_threshold"] = round(new_ct, 3)

            elif health == HealthStatus.MONITOR:
                new_ct = max(0.50, current_ct - 0.01)
                current_overrides["confidence_threshold"] = round(new_ct, 3)

            elif health == HealthStatus.QUARANTINED:
                new_ct = max(0.50, current_ct - 0.02)
                current_overrides["confidence_threshold"] = round(new_ct, 3)
                current_overrides["min_signal_score"] = min(80, current_ms + 5)

            else:
                return  # DEAD or INCUBATING — no update

            self.storage.update_parameter_overrides(instance.instance_id, current_overrides)
            self.logger.info(
                f"[SHADOW-EDGE] EdgeTuner overrides updated for {instance.instance_id[:8]}: "
                f"confidence_threshold={current_overrides.get('confidence_threshold')} "
                f"[health={health.value}]"
            )

        except Exception as e:
            self.logger.warning(
                f"[SHADOW-EDGE] Could not apply EdgeTuner overrides for "
                f"{instance.instance_id[:8]}: {e}"
            )

    def evaluate_all_instances(self) -> Dict[str, List[Dict]]:
        """
        Batch evaluate all active SHADOW instances against the 3 Pilares.

        Execution Flow:
          1. Load all non-terminal instances from sys_shadow_instances (DB).
          2. Resolve current market regime via RegimeClassifier (if injected).
          3. Build a regime-adjusted PromotionValidator.
          4. For each instance:
             a. Evaluate health (HEALTHY | MONITOR | QUARANTINED | DEAD).
             b. Persist snapshot to sys_shadow_performance_history.
             c. Update instance status in sys_shadow_instances.
             d. Log promotion decision for HEALTHY instances.
             e. Apply EdgeTuner parameter overrides (if EdgeTuner injected).
          5. Return classification report.

        Returns:
            Dict with four classified lists, each entry a Dict containing:
              - instance_id: UUID of the SHADOW instance.
              - trace_id: TRACE_HEALTH_... audit identifier.
              - reason: Human-readable classification reason (kills only).
              - strategy_id: Associated strategy.
        """
        result: Dict[str, List[Dict]] = {
            "promotions": [],
            "kills": [],
            "quarantines": [],
            "monitors": [],
        }

        # 1. Load active instances from DB
        try:
            instances = self.storage.list_active_instances()
        except Exception as e:
            self.logger.error(f"[SHADOW] Failed to load active instances: {e}")
            return result

        if not instances:
            self.logger.info("[SHADOW] evaluate_all_instances: no active instances found.")
            return result

        # 2. Resolve regime and build adjusted validator
        regime = self._get_current_regime()
        validator = self._build_regime_adjusted_validator(regime)
        self.logger.info(
            f"[SHADOW] Evaluating {len(instances)} instances | "
            f"Regime={regime} | "
            f"Thresholds: WR>={validator.PILAR1_MIN_WR:.0%}, "
            f"DD<={validator.PILAR2_MAX_DD:.0%}"
        )

        # 3. Evaluate each instance
        for instance in instances:
            try:
                # ETI-02/GAP-02: Fuente de métricas con fallback a shadow sintético.
                # Primaria: sys_trades (ejecución real DEMO con execution_mode='SHADOW').
                # Fallback: calculate_instance_metrics_from_shadow_history() que lee
                # los trades sintéticos escritos por ShadowPenaltyInjector cuando
                # la instancia aún no tiene ejecución real pero sí señales simuladas.
                metrics = self.storage.calculate_instance_metrics_from_sys_trades(
                    instance.instance_id
                )
                if metrics.total_trades_executed == 0:
                    metrics = self.storage.calculate_instance_metrics_from_shadow_history(
                        instance.instance_id
                    )
                instance.metrics = metrics
                trace_id = self.generate_trace_id(instance.instance_id, "HEALTH")

                # --- Run 3 Pilares with regime-adjusted thresholds ---
                p1_pass, p1_reason = validator.validate_pilar1_profitability(metrics)
                p2_pass, p2_reason = validator.validate_pilar2_resiliencia(metrics)
                p3_pass, p3_reason = validator.validate_pilar3_consistency(metrics)

                # --- Classify health (mirrors evaluate_single_instance logic) ---
                if not p1_pass and metrics.total_trades_executed >= validator.PILAR3_MIN_TRADES:
                    health = HealthStatus.DEAD
                elif not p2_pass:
                    health = HealthStatus.QUARANTINED
                elif not p3_pass:
                    health = HealthStatus.MONITOR
                else:
                    health = HealthStatus.HEALTHY

                # --- Persist performance snapshot ---
                try:
                    self.storage.record_performance_snapshot(
                        instance_id=instance.instance_id,
                        pillar1_status="PASS" if p1_pass else "FAIL",
                        pillar2_status="PASS" if p2_pass else "FAIL",
                        pillar3_status="PASS" if p3_pass else "FAIL",
                        overall_health=health.value,
                        event_trace_id=trace_id,
                    )
                except Exception as e:
                    self.logger.error(
                        f"[SHADOW] Failed to record snapshot for {instance.instance_id[:8]}: {e}"
                    )

                # --- Update instance status in DB ---
                try:
                    new_status = {
                        HealthStatus.HEALTHY: ShadowStatus.SHADOW_READY,
                        HealthStatus.DEAD: ShadowStatus.DEAD,
                        HealthStatus.QUARANTINED: ShadowStatus.QUARANTINED,
                        HealthStatus.MONITOR: ShadowStatus.INCUBATING,
                    }.get(health, ShadowStatus.INCUBATING)

                    instance.status = new_status
                    self.storage.update_shadow_instance(instance)
                except Exception as e:
                    self.logger.error(
                        f"[SHADOW] Failed to update status for {instance.instance_id[:8]}: {e}"
                    )

                # --- Persist promotion decision log for HEALTHY instances ---
                if health == HealthStatus.HEALTHY:
                    try:
                        promo_trace = self.generate_trace_id(
                            instance.instance_id, "PROMOTION_REAL"
                        )
                        self.storage.log_promotion_decision(
                            instance_id=instance.instance_id,
                            trace_id=promo_trace,
                            promotion_status="APPROVED",
                            pillar1_passed=p1_pass,
                            pillar2_passed=p2_pass,
                            pillar3_passed=p3_pass,
                            notes=(
                                f"Regime={regime} | "
                                f"PF={metrics.profit_factor:.2f} WR={metrics.win_rate:.1%} "
                                f"DD={metrics.max_drawdown_pct:.1%} "
                                f"Trades={metrics.total_trades_executed}"
                            ),
                        )
                    except Exception as e:
                        self.logger.error(
                            f"[SHADOW] Failed to log promotion for {instance.instance_id[:8]}: {e}"
                        )

                # --- Update score_shadow in sys_strategies ---
                # FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30:
                # score_shadow was never written, leaving it at 0 permanently.
                # Formula: win_rate × min(profit_factor / 3.0, 1.0) → [0.0, 1.0]
                try:
                    score_shadow = self._compute_score_shadow(metrics)
                    self.storage.update_strategy_score_shadow(
                        instance.strategy_id, score_shadow
                    )
                except Exception as e:
                    self.logger.error(
                        f"[SHADOW] Failed to update score_shadow for "
                        f"strategy={instance.strategy_id}: {e}"
                    )

                # --- Apply EdgeTuner per-instance overrides ---
                self._apply_edge_tuner_overrides(instance, health, p1_pass)

                # --- Route to result bucket ---
                entry: Dict = {
                    "instance_id": instance.instance_id,
                    "strategy_id": instance.strategy_id,
                    "trace_id": trace_id,
                    "regime": regime,
                    "metrics": {
                        "profit_factor": metrics.profit_factor,
                        "win_rate": metrics.win_rate,
                        "max_drawdown_pct": metrics.max_drawdown_pct,
                        "consecutive_losses_max": metrics.consecutive_losses_max,
                        "trade_count": metrics.total_trades_executed,
                    },
                }

                if health == HealthStatus.HEALTHY:
                    result["promotions"].append(entry)
                    self.logger.info(
                        f"[SHADOW] [OK] PROMOTE → REAL: {instance.instance_id[:8]} "
                        f"({instance.strategy_id}) | {p1_reason} | {p2_reason} | {p3_reason}"
                    )
                elif health == HealthStatus.DEAD:
                    entry["reason"] = p1_reason
                    result["kills"].append(entry)
                    self.logger.warning(
                        f"[SHADOW] [FAIL] DEAD: {instance.instance_id[:8]} ({instance.strategy_id}) "
                        f"| {p1_reason}"
                    )
                elif health == HealthStatus.QUARANTINED:
                    entry["reason"] = p2_reason
                    result["quarantines"].append(entry)
                    self.logger.warning(
                        f"[SHADOW] [WARNING] QUARANTINE: {instance.instance_id[:8]} "
                        f"({instance.strategy_id}) | {p2_reason}"
                    )
                else:  # MONITOR
                    entry["reason"] = p3_reason
                    result["monitors"].append(entry)
                    self.logger.info(
                        f"[SHADOW] [MONITOR] MONITOR: {instance.instance_id[:8]} "
                        f"({instance.strategy_id}) | {p3_reason}"
                    )

            except Exception as e:
                self.logger.error(
                    f"[SHADOW] Unexpected error evaluating {instance.instance_id[:8]}: {e}",
                    exc_info=True,
                )

        total = sum(len(v) for v in result.values())
        self.logger.info(
            f"[SHADOW] evaluate_all_instances complete: "
            f"{len(result['promotions'])} promotions, "
            f"{len(result['kills'])} kills, "
            f"{len(result['quarantines'])} quarantines, "
            f"{len(result['monitors'])} monitors "
            f"({total}/{len(instances)} processed) | Regime={regime}"
        )
        return result

    # ────────────────────────────────────────────────────────────────────────
    # Score helpers (FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30)
    # ────────────────────────────────────────────────────────────────────────

    def _compute_score_shadow(self, metrics: ShadowMetrics) -> float:
        """Derive score_shadow from live shadow metrics. Range [0.0, 1.0].

        Formula: win_rate × min(profit_factor / 3.0, 1.0)
        Returns 0.0 when no trades are available (avoids false signal).

        Args:
            metrics: Fresh ShadowMetrics from calculate_instance_metrics_from_sys_trades().

        Returns:
            Normalized shadow score in [0.0, 1.0].
        """
        if metrics.total_trades_executed == 0:
            return 0.0
        pf_normalized = min(metrics.profit_factor / 3.0, 1.0)
        return round(metrics.win_rate * pf_normalized, 4)

    def recalculate_all_shadow_scores(self) -> Dict:
        """Manual trigger to recalculate shadow metrics and score_shadow for all instances.

        FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30:
        Exposes a recalculation mechanism that can be called without waiting for
        the hourly evaluate_all_instances() cycle. Useful after:
          - Database migration that populates historical instance_id in sys_trades.
          - Manual intervention to reset scores after a data fix.
          - On-demand revalidation via API endpoint or admin script.

        Workflow per active instance:
          1. Compute fresh ShadowMetrics from sys_trades.
          2. Update sys_shadow_instances metrics columns.
          3. Update sys_strategies.score_shadow.

        Returns:
            Dict with 'recalculated' (int count) and 'skipped' (int, instances with 0 trades).
        """
        summary: Dict = {"recalculated": 0, "skipped": 0}

        try:
            instances = self.storage.list_active_instances()
        except Exception as e:
            self.logger.error(f"[SHADOW] recalculate_all_shadow_scores: failed to load instances: {e}")
            return summary

        for instance in instances:
            try:
                metrics = self.storage.calculate_instance_metrics_from_sys_trades(
                    instance.instance_id
                )
                if metrics.total_trades_executed == 0:
                    summary["skipped"] += 1
                    self.logger.debug(
                        "[SHADOW] recalculate: skipped %s — 0 trades in sys_trades",
                        instance.instance_id[:8],
                    )
                    continue

                instance.metrics = metrics
                self.storage.update_shadow_instance(instance)

                score_shadow = self._compute_score_shadow(metrics)
                self.storage.update_strategy_score_shadow(instance.strategy_id, score_shadow)

                summary["recalculated"] += 1
                self.logger.info(
                    "[SHADOW] recalculate: %s strategy=%s trades=%d "
                    "wr=%.1%% pf=%.2f score_shadow=%.4f",
                    instance.instance_id[:8],
                    instance.strategy_id,
                    metrics.total_trades_executed,
                    metrics.win_rate,
                    metrics.profit_factor,
                    score_shadow,
                )
            except Exception as e:
                self.logger.error(
                    f"[SHADOW] recalculate: unexpected error for {instance.instance_id[:8]}: {e}",
                    exc_info=True,
                )

        self.logger.info(
            "[SHADOW] recalculate_all_shadow_scores complete: "
            "recalculated=%d skipped=%d",
            summary["recalculated"], summary["skipped"],
        )
        return summary
