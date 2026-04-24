"""
resilience_manager.py — Aethelgard Immune System Brain (ResilienceManager).

Receives EdgeEventReports from diagnostic components (IntegrityGuard,
AnomalySentinel, CoherenceService, and any ResilienceInterface implementor)
and manages the global SystemPosture.  The ResilienceManager is the SOLE
authority over posture transitions and EdgeAction enforcement.

Design rules:
  - Never raises — storage failures are logged and swallowed.
  - Posture only escalates (NORMAL → CAUTION → DEGRADED → STRESSED).
  - De-escalation is NOT implemented here; it belongs to a future HU.

Escalation matrix:
  EdgeAction.MUTE (L0)       → tracks per-asset count.
                                >= 3  → CAUTION
                                >= 6  → DEGRADED
  EdgeAction.QUARANTINE (L1) → CAUTION
  EdgeAction.SELF_HEAL (L2)  → DEGRADED
  EdgeAction.LOCKDOWN (L3)   → STRESSED

Correlation Engine (HU 10.16):
  >= 3 distinct assets MUTE within 60s → auto-escalate to L3/STRESSED.
  >= 2 L1/QUARANTINE failures sharing the same DataProvider → re-classify as L2/SERVICE.

Self-Healing Playbook (HU 10.16):
  Check_Data_Coherence → reconnect_provider(), max 3 retries → STRESSED on exhaustion.
  Check_Database       → clear_db_cache() + reconnect, max 3 retries → STRESSED on exhaustion.
  Spread_Anomaly       → 5-minute cooldown before re-evaluating the asset.

Trace_ID: ARCH-RESILIENCE-ENGINE-V1-C
Source of truth: docs/10_INFRA_RESILIENCY.md §E14
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Callable, Optional

from core_brain.resilience import (
    EdgeAction,
    EdgeEventReport,
    ResilienceLevel,
    SystemPosture,
)
from core_brain.close_only_guard import CloseOnlyGuard
from core_brain.resilience_autotune import ResilienceAutoTuner
from core_brain.incident_learning_engine import IncidentLearningEngine

logger = logging.getLogger(__name__)

# ── Escalation thresholds ─────────────────────────────────────────────────────
_L0_CAUTION_THRESHOLD = 3
_L0_DEGRADED_THRESHOLD = 6

# ── Correlation Engine constants ──────────────────────────────────────────────
_CORRELATION_WINDOW_SECONDS: float = 60.0
_CORRELATION_L0_THRESHOLD: int = 3   # distinct assets muted within window → L3

# ── Self-Healing Playbook constants ───────────────────────────────────────────
_MAX_HEAL_RETRIES: int = 3
_SPREAD_COOLDOWN_SECONDS: float = 300.0  # 5 minutes

# Issue type keys carried in report.metadata["issue_type"]
ISSUE_DATA_COHERENCE = "Check_Data_Coherence"
ISSUE_DATABASE = "Check_Database"
ISSUE_SPREAD_ANOMALY = "Spread_Anomaly"

# Ordered posture severity (index = severity level).
_POSTURE_ORDER = [
    SystemPosture.NORMAL,
    SystemPosture.CAUTION,
    SystemPosture.DEGRADED,
    SystemPosture.STRESSED,
]

# Modules degraded automatically on LOCKDOWN — non-critical, can be paused.
_LOCKDOWN_DEGRADED_MODULES: frozenset[str] = frozenset({
    "SignalFactory",
    "Scanner",
    "Backtest",
    "StrategyEngine",
})

# Modules NEVER degraded — critical for position management.
_PROTECTED_MODULES: frozenset[str] = frozenset({
    "PositionManager",
    "RiskManager",
    "Executor",
})


class ResilienceManager:
    """
    Central arbiter of the engine's operational SystemPosture.

    Includes three sub-systems beyond the base escalation matrix:

    CorrelationEngine
        Detects temporal cascades of L0 MUTE events. If ≥3 distinct assets
        emit MUTE within a 60-second window, a synthetic L3/LOCKDOWN is
        injected and the system transitions to STRESSED immediately.

    RootCauseDiagnosis
        Monitors L1/QUARANTINE reports. If two or more strategies quarantine
        due to failures on the same DataProvider (report.metadata["data_provider"]),
        the incident is re-classified as L2/SERVICE and escalated to DEGRADED.

    SelfHealingPlaybook
        Bounded retry loops for known issue types (identified via
        report.metadata["issue_type"]).  Healing callables are injected at
        construction time (dependency inversion).  Once retries are exhausted,
        the system escalates to STRESSED.

    Usage::

        manager = ResilienceManager(
            storage=storage_manager,
            reconnect_provider_fn=my_reconnect,
            clear_db_cache_fn=my_clear_cache,
        )
        posture = manager.process_report(report)

    Args:
        storage: StorageManager instance used to persist audit events.
        reconnect_provider_fn: Callable[[], bool] — attempts reconnection;
            returns True on success. Defaults to a no-op returning False.
        clear_db_cache_fn: Callable[[], None] — clears the DB connection cache.
            Defaults to a no-op.
    """

    def __init__(
        self,
        storage: Any,
        reconnect_provider_fn: Optional[Callable[[], bool]] = None,
        clear_db_cache_fn: Optional[Callable[[], None]] = None,
        close_only_guard: Optional[CloseOnlyGuard] = None,
        auto_tuner: Optional[ResilienceAutoTuner] = None,
        incident_learning_engine: Optional[IncidentLearningEngine] = None,
    ) -> None:
        self._storage = storage
        self._current_posture: SystemPosture = SystemPosture.NORMAL
        self._l0_failure_counts: dict[str, int] = defaultdict(int)
        self._last_report: Optional[EdgeEventReport] = None
        self._last_cause: str = ""
        self._last_recovery_plan: str = ""

        # ── Correlation Engine state ──────────────────────────────────────────
        # Each entry: (monotonic_timestamp, asset_scope)
        self._l0_mute_window: list[tuple[float, str]] = []
        # Maps data_provider → list of strategy scopes that quarantined
        self._l1_provider_map: dict[str, list[str]] = defaultdict(list)

        # ── Self-Healing Playbook state ───────────────────────────────────────
        self._healing_attempts: dict[str, int] = defaultdict(int)
        self._cooldowns: dict[str, float] = {}   # scope → cooldown end (monotonic)
        self._is_healing: bool = False

        # Injectable healing callbacks
        self._reconnect_provider_fn: Callable[[], bool] = (
            reconnect_provider_fn or (lambda: False)
        )
        self._clear_db_cache_fn: Callable[[], None] = (
            clear_db_cache_fn or (lambda: None)
        )

        # ── Granular Degradation state ────────────────────────────────────────
        # Set of module names currently in degraded state.
        self._degraded_modules: set[str] = set()
        self._close_only_guard: Optional[CloseOnlyGuard] = close_only_guard

        # ── AutoTune — HU 4.1 ────────────────────────────────────────────────
        self._auto_tuner: Optional[ResilienceAutoTuner] = auto_tuner
        # Nº de veces que try_auto_revert() fue invocado desde la entrada a STRESSED.
        self._revert_attempt_count: int = 0

        # ── Incident Learning Engine — ETI E5-HU5.1 ──────────────────────────
        self._ile: Optional[IncidentLearningEngine] = incident_learning_engine
        # Maps heal key (e.g. "data_coherence:XAUUSD") → incident_id activo
        self._active_incidents: dict[str, str] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def current_posture(self) -> SystemPosture:
        """Read-only view of the current system posture."""
        return self._current_posture

    @property
    def is_healing(self) -> bool:
        """True while a healing action is executing (self-heal in flight)."""
        return self._is_healing

    def process_report(self, report: EdgeEventReport) -> SystemPosture:
        """
        Evaluate an incoming EdgeEventReport and update SystemPosture.

        Processing order:
          1. CorrelationEngine  — may inject a synthetic L3 cascade.
          2. RootCauseDiagnosis — may upgrade L1 → L2/SERVICE.
          3. SelfHealingPlaybook — bounded retries for known issue types.
          4. Standard escalation matrix.

        Escalation is one-directional: posture never decreases here.
        The method persists the event in sys_audit_logs regardless of
        whether a posture transition occurs.

        Args:
            report: EdgeEventReport from a diagnostic component.

        Returns:
            Updated SystemPosture after processing the report.
        """
        self._run_correlation_engine(report)
        report = self._run_root_cause_diagnosis(report)
        self._last_report = report
        self._last_recovery_plan = self._build_recovery_plan(report)
        self._last_cause = f"{report.level.value}_{report.action.value}"
        self._run_healing_playbook(report)

        target_posture = self._resolve_target_posture(report)
        if self._is_escalation(target_posture):
            logger.warning(
                "[ResilienceManager] %s → %s | scope=%s | reason=%s | trace_id=%s",
                self._current_posture.value,
                target_posture.value,
                report.scope,
                report.reason,
                report.trace_id,
            )
            self._current_posture = target_posture
            if target_posture == SystemPosture.STRESSED:
                self._revert_attempt_count = 0
                self.activate_close_only_protocol()

        self._persist_audit(report)
        return self._current_posture

    def get_current_status_narrative(self) -> str:
        """
        Return a human-readable string describing the current posture.

        Designed for the UI's SystemHealthPanel. Returns an empty string
        when the posture is NORMAL and no report has been processed yet.

        Returns:
            Actionable narrative string, e.g.:
            "Sistema en DEGRADED — afectado: IntegrityGuard (L2_SELF_HEAL).
             Componente IntegrityGuard: auto-recuperación en curso."
        """
        if self._current_posture == SystemPosture.NORMAL and not self._last_report:
            return ""

        posture_label = self._current_posture.value
        scope = self._last_report.scope if self._last_report else "UNKNOWN"
        cause = self._last_cause or "UNKNOWN"

        base = f"Sistema en {posture_label} — afectado: {scope} ({cause})"
        if self._last_recovery_plan:
            return f"{base}. {self._last_recovery_plan}"
        return base

    def is_in_cooldown(self, scope: str) -> bool:
        """
        Return True if the asset is within an active Spread_Anomaly cooldown.

        Args:
            scope: Asset identifier (e.g. "XAUUSD").
        """
        end_time = self._cooldowns.get(scope)
        if end_time is None:
            return False
        return time.monotonic() < end_time

    # ── Granular Degradation public API ──────────────────────────────────────

    @property
    def close_only_mode(self) -> bool:
        """True when close-only mode is active (no new positions allowed)."""
        if self._close_only_guard is None:
            return False
        return self._close_only_guard.is_active

    def degrade_module(self, module_name: str) -> None:
        """
        Mark a module as degraded.

        Protected modules (PositionManager, RiskManager, Executor) are silently
        ignored — they must never be degraded.

        Args:
            module_name: Logical name of the module (e.g. "SignalFactory").
        """
        if module_name in _PROTECTED_MODULES:
            logger.warning(
                "[ResilienceManager] Intento de degradar módulo protegido '%s' — ignorado.",
                module_name,
            )
            return
        if module_name not in self._degraded_modules:
            self._degraded_modules.add(module_name)
            logger.warning(
                "[ResilienceManager][Degradation] Módulo '%s' marcado como DEGRADADO.",
                module_name,
            )

    def restore_module(self, module_name: str) -> None:
        """
        Remove a module from the degraded registry.

        Args:
            module_name: Logical name of the module to restore.
        """
        if module_name in self._degraded_modules:
            self._degraded_modules.discard(module_name)
            logger.info(
                "[ResilienceManager][Degradation] Módulo '%s' RESTAURADO.",
                module_name,
            )

    def is_module_degraded(self, module_name: str) -> bool:
        """Return True if the module is currently in the degraded registry."""
        return module_name in self._degraded_modules

    def activate_close_only_protocol(self) -> None:
        """
        Activate close-only mode and degrade all non-critical modules.

        Called automatically when a LOCKDOWN event is processed.
        Protected modules (PositionManager, RiskManager, Executor) are preserved.
        """
        if self._close_only_guard is not None:
            self._close_only_guard.activate()
        for module in _LOCKDOWN_DEGRADED_MODULES:
            self.degrade_module(module)
        logger.warning(
            "[ResilienceManager] Protocolo close-only activado. "
            "Módulos degradados: %s. Protegidos: %s.",
            sorted(_LOCKDOWN_DEGRADED_MODULES),
            sorted(_PROTECTED_MODULES),
        )

    def try_auto_revert(self, edge_eroded: bool = False) -> bool:
        """
        Attempt to auto-revert close-only mode and restore degraded modules.

        Respects the dynamic min_stability_cycles threshold: if fewer cycles
        have elapsed since STRESSED was entered, reversion is blocked.
        On successful revert, notifies the AutoTuner for incremental calibration.

        Args:
            edge_eroded: True if execution quality degraded post-recovery.
                         Passed to the AutoTuner to decide whether to harden params.

        Returns:
            True if reversion occurred, False otherwise.
        """
        if self._close_only_guard is None:
            return False

        self._revert_attempt_count += 1

        min_cycles = (
            int(self._auto_tuner.get_param("min_stability_cycles"))
            if self._auto_tuner is not None
            else 0
        )
        if self._revert_attempt_count < min_cycles:
            logger.info(
                "[ResilienceManager] Reversión bloqueada por AutoTune "
                "(cycles=%d/%d mínimos requeridos).",
                self._revert_attempt_count,
                min_cycles,
            )
            return False

        reverted = self._close_only_guard.check_auto_revert()
        if reverted:
            for module in list(self._degraded_modules):
                self.restore_module(module)
            logger.info(
                "[ResilienceManager] Auto-reversión completa — todos los módulos restaurados."
            )
            if self._auto_tuner is not None:
                trace_id = (
                    self._last_report.trace_id if self._last_report else ""
                )
                self._auto_tuner.record_recovery(
                    stability_cycles=self._revert_attempt_count,
                    edge_eroded=edge_eroded,
                    trace_id=trace_id,
                )
        return reverted

    # ── Correlation Engine ────────────────────────────────────────────────────

    def _run_correlation_engine(self, report: EdgeEventReport) -> None:
        """
        Track temporal clusters of L0 MUTE events across distinct assets.
        Triggers a synthetic LOCKDOWN if ≥correlation_l0_threshold distinct
        assets mute within correlation_window_seconds.
        Uses dynamic thresholds from AutoTuner when available.
        """
        if report.action != EdgeAction.MUTE:
            return

        window_secs = (
            float(self._auto_tuner.get_param("correlation_window_seconds"))
            if self._auto_tuner is not None
            else _CORRELATION_WINDOW_SECONDS
        )
        corr_threshold = (
            int(self._auto_tuner.get_param("correlation_l0_threshold"))
            if self._auto_tuner is not None
            else _CORRELATION_L0_THRESHOLD
        )

        now = time.monotonic()
        cutoff = now - window_secs
        self._l0_mute_window = [
            (ts, sc) for ts, sc in self._l0_mute_window if ts >= cutoff
        ]
        self._l0_mute_window.append((now, report.scope))
        distinct = {sc for _, sc in self._l0_mute_window}
        if len(distinct) >= corr_threshold:
            self._trigger_correlation_cascade(distinct)

    def _trigger_correlation_cascade(self, distinct_assets: set[str]) -> None:
        """Inject a synthetic L3/LOCKDOWN and escalate posture to STRESSED."""
        logger.warning(
            "[ResilienceManager][CorrelationEngine] %d distinct assets muted "
            "within %ss window → L3/STRESSED. Assets: %s",
            len(distinct_assets),
            _CORRELATION_WINDOW_SECONDS,
            ", ".join(sorted(distinct_assets)),
        )
        synthetic = EdgeEventReport(
            level=ResilienceLevel.GLOBAL,
            scope="CORRELATION_CASCADE",
            action=EdgeAction.LOCKDOWN,
            reason=(
                f"Temporal correlation: {len(distinct_assets)} assets muted "
                f"in {_CORRELATION_WINDOW_SECONDS}s — systemic failure suspected."
            ),
        )
        self._persist_audit(synthetic)
        if self._is_escalation(SystemPosture.STRESSED):
            self._current_posture = SystemPosture.STRESSED
        self._l0_mute_window.clear()

    # ── Root Cause Diagnosis ──────────────────────────────────────────────────

    def _run_root_cause_diagnosis(
        self, report: EdgeEventReport
    ) -> EdgeEventReport:
        """
        Promote multiple L1/QUARANTINE failures on the same DataProvider
        to an L2/SERVICE failure.  DataProvider is read from
        report.metadata["data_provider"].
        """
        if report.action != EdgeAction.QUARANTINE:
            return report
        provider = report.metadata.get("data_provider")
        if not provider:
            return report
        self._l1_provider_map[provider].append(report.scope)
        if len(self._l1_provider_map[provider]) >= 2:
            return self._build_l2_upgrade(provider)
        return report

    def _build_l2_upgrade(self, provider: str) -> EdgeEventReport:
        """Build a synthetic L2/SERVICE report from a shared-provider root cause."""
        strategies = ", ".join(self._l1_provider_map[provider])
        logger.warning(
            "[ResilienceManager][RootCause] Multiple L1 failures share "
            "DataProvider '%s' (strategies: %s) → re-classifying as L2/SERVICE.",
            provider,
            strategies,
        )
        return EdgeEventReport(
            level=ResilienceLevel.SERVICE,
            scope=provider,
            action=EdgeAction.SELF_HEAL,
            reason=(
                f"Root cause: shared DataProvider '{provider}' failing "
                f"(strategies: {strategies})."
            ),
            metadata={"root_cause_provider": provider},
        )

    # ── Self-Healing Playbook ─────────────────────────────────────────────────

    def _run_healing_playbook(self, report: EdgeEventReport) -> None:
        """
        Dispatch healing actions based on report.metadata["issue_type"].
        No-op when issue_type is absent or unknown.
        """
        issue_type = report.metadata.get("issue_type")
        if not issue_type:
            return
        if issue_type == ISSUE_SPREAD_ANOMALY:
            self._apply_spread_cooldown(report.scope)
        elif issue_type == ISSUE_DATA_COHERENCE:
            self._heal_data_coherence(report.scope)
        elif issue_type == ISSUE_DATABASE:
            self._heal_database(report.scope)

    def _apply_spread_cooldown(self, scope: str) -> None:
        """Register a cooldown on the asset after a spread anomaly.
        Duration is dynamic (spread_cooldown_seconds from AutoTuner)."""
        cooldown_secs = (
            float(self._auto_tuner.get_param("spread_cooldown_seconds"))
            if self._auto_tuner is not None
            else _SPREAD_COOLDOWN_SECONDS
        )
        end_time = time.monotonic() + cooldown_secs
        self._cooldowns[scope] = end_time
        logger.info(
            "[AUTO-HEAL] Spread_Anomaly cooldown registered for %s — "
            "re-evaluation blocked for %ss.",
            scope,
            cooldown_secs,
        )

    def _heal_data_coherence(self, scope: str) -> None:
        """
        Attempt reconnect_provider() for frozen-tick (Check_Data_Coherence) issues.
        Escalates to STRESSED after _MAX_HEAL_RETRIES failed attempts.
        Registra cada intento en IncidentLearningEngine cuando está disponible.
        """
        key = f"data_coherence:{scope}"
        attempt = self._healing_attempts[key] + 1
        self._healing_attempts[key] = attempt
        logger.info(
            "[AUTO-HEAL] [Attempt %d/%d] Executing reconnect_provider for %s",
            attempt,
            _MAX_HEAL_RETRIES,
            scope,
        )
        # ILE: abrir incidente en el primer intento
        if self._ile is not None and attempt == 1:
            trace_id = self._last_report.trace_id if self._last_report else ""
            inc_id = self._ile.record_incident(
                "data_coherence", f"Frozen tick detected for {scope}", trace_id=trace_id
            )
            self._active_incidents[key] = inc_id

        success = self._try_reconnect()
        if self._ile is not None and key in self._active_incidents:
            self._ile.record_route_attempt(
                self._active_incidents[key], "reconnect_provider", success=success
            )

        if success:
            logger.info("[AUTO-HEAL] reconnect_provider succeeded for %s", scope)
            self._healing_attempts[key] = 0
            if self._ile is not None and key in self._active_incidents:
                self._ile.mark_resolved(self._active_incidents.pop(key), "reconnect_provider")
            return
        max_retries = (
            int(self._auto_tuner.get_param("max_heal_retries"))
            if self._auto_tuner is not None
            else _MAX_HEAL_RETRIES
        )
        if attempt >= max_retries:
            self._escalate_after_exhaustion(scope, "reconnect_provider")

    def _heal_database(self, scope: str) -> None:
        """
        Attempt clear_db_cache() + reconnect for Check_Database issues.
        Escalates to STRESSED after _MAX_HEAL_RETRIES failed attempts.
        Registra cada intento en IncidentLearningEngine cuando está disponible.
        """
        key = f"database:{scope}"
        attempt = self._healing_attempts[key] + 1
        self._healing_attempts[key] = attempt
        logger.info(
            "[AUTO-HEAL] [Attempt %d/%d] Executing clear_db_cache for %s",
            attempt,
            _MAX_HEAL_RETRIES,
            scope,
        )
        # ILE: abrir incidente en el primer intento
        if self._ile is not None and attempt == 1:
            trace_id = self._last_report.trace_id if self._last_report else ""
            inc_id = self._ile.record_incident(
                "database_failure", f"DB issue detected for {scope}", trace_id=trace_id
            )
            self._active_incidents[key] = inc_id

        success = self._try_db_heal()
        if self._ile is not None and key in self._active_incidents:
            self._ile.record_route_attempt(
                self._active_incidents[key], "clear_db_cache", success=success
            )

        if success:
            logger.info("[AUTO-HEAL] DB heal succeeded for %s", scope)
            self._healing_attempts[key] = 0
            if self._ile is not None and key in self._active_incidents:
                self._ile.mark_resolved(self._active_incidents.pop(key), "clear_db_cache")
            return
        max_retries = (
            int(self._auto_tuner.get_param("max_heal_retries"))
            if self._auto_tuner is not None
            else _MAX_HEAL_RETRIES
        )
        if attempt >= max_retries:
            self._escalate_after_exhaustion(scope, "clear_db_cache")

    def _try_reconnect(self) -> bool:
        """Execute the injected reconnect callback; returns False on exception."""
        self._is_healing = True
        try:
            return bool(self._reconnect_provider_fn())
        except Exception as exc:
            logger.warning("[AUTO-HEAL] reconnect_provider raised: %s", exc)
            return False
        finally:
            self._is_healing = False

    def _try_db_heal(self) -> bool:
        """Execute clear_db_cache then reconnect; returns False on exception."""
        self._is_healing = True
        try:
            self._clear_db_cache_fn()
            return bool(self._reconnect_provider_fn())
        except Exception as exc:
            logger.warning("[AUTO-HEAL] DB heal raised: %s", exc)
            return False
        finally:
            self._is_healing = False

    def _escalate_after_exhaustion(self, scope: str, action: str) -> None:
        """Log retry exhaustion, notify ILE, and escalate posture to STRESSED."""
        logger.error(
            "[AUTO-HEAL] Exhausted %d retries for '%s' on %s — escalating to STRESSED.",
            _MAX_HEAL_RETRIES,
            action,
            scope,
        )
        # ILE: marcar incidente como agotado si existe uno activo para este scope
        if self._ile is not None:
            for key, inc_id in list(self._active_incidents.items()):
                if scope in key:
                    self._ile.mark_unresolved(inc_id)
                    self._active_incidents.pop(key, None)

        if self._is_escalation(SystemPosture.STRESSED):
            self._current_posture = SystemPosture.STRESSED

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_target_posture(self, report: EdgeEventReport) -> SystemPosture:
        """Map an EdgeEventReport to the target SystemPosture."""
        if report.action == EdgeAction.LOCKDOWN:
            return SystemPosture.STRESSED
        if report.action == EdgeAction.SELF_HEAL:
            return SystemPosture.DEGRADED
        if report.action == EdgeAction.QUARANTINE:
            return SystemPosture.CAUTION
        if report.action == EdgeAction.MUTE:
            return self._evaluate_mute_escalation(report.scope)
        return self._current_posture

    def _evaluate_mute_escalation(self, asset_scope: str) -> SystemPosture:
        """
        Track per-asset MUTE counts and escalate posture when thresholds
        are reached.  Uses dynamic thresholds from AutoTuner when available.

        Thresholds (cumulative per asset):
          >= l0_degraded_threshold → DEGRADED
          >= l0_caution_threshold  → CAUTION
          < l0_caution_threshold   → no change
        """
        self._l0_failure_counts[asset_scope] += 1
        count = self._l0_failure_counts[asset_scope]
        degraded_thr = (
            int(self._auto_tuner.get_param("l0_degraded_threshold"))
            if self._auto_tuner is not None
            else _L0_DEGRADED_THRESHOLD
        )
        caution_thr = (
            int(self._auto_tuner.get_param("l0_caution_threshold"))
            if self._auto_tuner is not None
            else _L0_CAUTION_THRESHOLD
        )
        if count >= degraded_thr:
            return SystemPosture.DEGRADED
        if count >= caution_thr:
            return SystemPosture.CAUTION
        return self._current_posture

    def _is_escalation(self, target: SystemPosture) -> bool:
        """Return True only if target is strictly more severe than current."""
        return _POSTURE_ORDER.index(target) > _POSTURE_ORDER.index(self._current_posture)

    def _build_recovery_plan(self, report: EdgeEventReport) -> str:
        """Generate a short actionable recovery plan text for the audit log and UI."""
        plans: dict[EdgeAction, str] = {
            EdgeAction.MUTE: (
                f"Instrumento {report.scope} silenciado. "
                "Monitoreo activo. Sin nuevas entradas en este activo."
            ),
            EdgeAction.QUARANTINE: (
                f"Estrategia {report.scope} en cuarentena. "
                "Posiciones existentes gestionadas. Sin nuevas entradas."
            ),
            EdgeAction.SELF_HEAL: (
                f"Componente {report.scope}: auto-recuperación en curso. "
                "Nuevas señales bloqueadas hasta resolución."
            ),
            EdgeAction.LOCKDOWN: (
                "Sistema en STRESSED. Cancelar órdenes pendientes. "
                "SL → Breakeven. Intervención manual recomendada."
            ),
        }
        return plans.get(report.action, "")

    # ── Connection Health integration (HU 5.1) ───────────────────────────────

    def process_connection_health_event(
        self,
        snapshot: Any,  # ConnectorHealthSnapshot — avoid circular import
    ) -> SystemPosture:
        """
        Convert a ConnectorHealthSnapshot into an EdgeEventReport and process it.

        Mapping:
          HEALTHY / DEGRADED (latency)  → no escalation (logged only)
          DISCONNECTED (root=AUTH)      → L2 SELF_HEAL (service-level failure)
          DISCONNECTED (root=NETWORK)   → L2 SELF_HEAL
          RECONNECTING                  → no escalation (in-flight recovery)
          FALLBACK_TRIGGERED            → L3 LOCKDOWN  (unrecoverable connector)

        Returns:
            Current SystemPosture after processing.
        """
        from core_brain.connection_health_monitor import ConnectorHealthStatus, RootCause

        status = snapshot.status
        root_cause = snapshot.root_cause
        connector_id = snapshot.connector_id

        # Healthy or degraded by latency — no posture escalation needed
        if status in (ConnectorHealthStatus.HEALTHY, ConnectorHealthStatus.RECONNECTING):
            logger.debug(
                "[ResilienceManager] Connector %s status=%s — no escalation",
                connector_id, status.value,
            )
            return self._current_posture

        if status == ConnectorHealthStatus.DEGRADED:
            logger.warning(
                "[ResilienceManager] Connector %s DEGRADED latency=%.0fms",
                connector_id, snapshot.latency_ms,
            )
            return self._current_posture

        # Disconnected — escalate to SERVICE level
        reason = (
            f"Connector {connector_id} DISCONNECTED: root_cause={root_cause.value if root_cause else 'UNKNOWN'} "
            f"reconnect_attempts={snapshot.reconnect_attempts}"
        )

        # Fallback triggered = L3 (unrecoverable without manual intervention)
        if snapshot.reconnect_attempts > 0 and status == ConnectorHealthStatus.DISCONNECTED:
            action = EdgeAction.LOCKDOWN
            level = ResilienceLevel.GLOBAL
        else:
            action = EdgeAction.SELF_HEAL
            level = ResilienceLevel.SERVICE

        report = EdgeEventReport(
            level=level,
            scope=f"connector:{connector_id}",
            action=action,
            reason=reason,
            metadata={
                "connector_id": connector_id,
                "root_cause": root_cause.value if root_cause else None,
                "latency_ms": snapshot.latency_ms,
                "reconnect_attempts": snapshot.reconnect_attempts,
                "issue_type": f"connector_{connector_id}_failure",
            },
        )
        return self.process_report(report)

    def _persist_audit(self, report: EdgeEventReport) -> None:
        """
        Persist the resilience event to sys_audit_logs.

        Fire-and-forget: storage errors are logged at WARNING level
        and never propagate to the caller.
        """
        details = f"{report.reason} | recovery_plan={self._last_recovery_plan}"
        try:
            conn = self._storage._get_conn()
            conn.execute(
                """
                INSERT INTO sys_audit_logs
                    (user_id, action, resource, resource_id, status, reason, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "system",
                    "RESILIENCE_EVENT",
                    report.scope,
                    report.level.value,
                    report.action.value,
                    details[:1000],
                    report.trace_id,
                ),
            )
            conn.commit()
        except Exception as exc:
            logger.warning(
                "[ResilienceManager] Could not persist audit log: %s", exc
            )
