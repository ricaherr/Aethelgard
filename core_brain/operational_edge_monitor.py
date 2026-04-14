"""
operational_edge_monitor.py — Verificación de Invariantes de Negocio

Componente standalone que ejecuta 10 checks contra la capa de almacenamiento
y reporta el estado de salud operacional del sistema.

Checks:
    shadow_sync              — Instancias SHADOW maduras acumulando trades
    backtest_quality         — Al menos una estrategia con backtest_score > 0
    connector_exec           — Al menos un conector de ejecución habilitado
    signal_flow              — Señales generadas en las últimas 2h
    adx_sanity               — ADX no atascado en 0 en los market pulses
    lifecycle_coherence      — Sin estrategias con rankings vencidos >48h
    rejection_rate           — Tasa de rechazo de señales < 95%
    score_stale              — Rankings actualizados en las últimas 72h
    orchestrator_heartbeat   — Loop principal sin bloqueos (heartbeat < 120s)
    shadow_stagnation        — Instancias SHADOW activas sin trades recientes
"""
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class CheckStatus(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    status: CheckStatus
    detail: str


class OperationalEdgeMonitor(threading.Thread):
    """
    Daemon thread that audits business invariants on every tick.

    All checks are also callable synchronously via run_checks() and
    get_health_summary() for use in REST health endpoints or CLI scripts.

    Args:
        storage:          StorageManager principal del sistema.
        shadow_storage:   ShadowStorageManager opcional para check shadow_sync.
        interval_seconds: Frecuencia del loop (default 300 s / 5 min).
    """

    SIGNAL_FLOW_WINDOW_MINUTES = 120
    STALE_SCORE_HOURS = 72
    LIFECYCLE_STALE_HOURS = 48
    MAX_REJECTION_RATE = 0.95
    MIN_ADX_NONZERO_RATIO = 0.10
    HEARTBEAT_WARN_GAP_SECONDS_DEFAULT = 90
    HEARTBEAT_FAIL_GAP_SECONDS_DEFAULT = 120
    SILENCED_COMPONENT_GAP_SECONDS_DEFAULT = 120
    SHADOW_STAGNATION_WINDOW_HOURS_DEFAULT = 24
    SHADOW_STAGNATION_ALERTS_STATE_KEY = "oem_shadow_stagnation_alerts_daily"
    STARTUP_INVARIANT_GRACE_SECONDS_DEFAULT = 300
    STARTUP_GRACE_CHECKS = {"shadow_sync", "lifecycle_coherence"}
    SHADOW_INCUBATING_MAX_HOURS_DEFAULT = 24

    def __init__(
        self,
        storage: StorageManager,
        shadow_storage: Optional[Any] = None,
        interval_seconds: int = 300,
    ) -> None:
        super().__init__(daemon=True)
        self.storage = storage
        self.shadow_storage = shadow_storage
        self.interval_seconds = interval_seconds
        self.name = "OperationalEdgeMonitor"
        self.running = True
        self.last_results: Dict[str, CheckResult] = {}
        self.last_checked_at: Optional[str] = None
        self._stagnation_alert_cache: Dict[str, str] = {}
        self._started_at_utc = datetime.now(timezone.utc)

    # ── Thread interface ──────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info(
            "[OPS-EDGE] Operational invariant monitor started (interval=%ds, checks=10)",
            self.interval_seconds,
        )
        while self.running:
            results = self.run_checks()
            self.last_results = results
            self.last_checked_at = datetime.now(timezone.utc).isoformat()

            failing = [k for k, r in results.items() if r.status == CheckStatus.FAIL]
            warnings = [k for k, r in results.items() if r.status == CheckStatus.WARN]
            failing, warnings, _ = self._apply_startup_grace(failing, warnings)

            # Persist snapshot to DB so the API (separate process) can read it
            try:
                heartbeat_failed = any(name.endswith("_heartbeat") for name in failing)
                if len(failing) >= 2 or heartbeat_failed:
                    overall = "CRITICAL"
                elif failing:
                    overall = "DEGRADED"
                elif warnings:
                    overall = "DEGRADED"
                else:
                    overall = "OK"

                snapshot = {
                    "status": overall,
                    "checks": {n: {"status": r.status.value, "detail": r.detail} for n, r in results.items()},
                    "failing": failing,
                    "warnings": warnings,
                    "last_checked_at": self.last_checked_at,
                }
                self.storage.update_sys_config({"oem_health_snapshot": json.dumps(snapshot)})
                self._write_repair_flags(failing, warnings)
            except Exception as _exc:
                logger.warning("[OEM] Could not persist health snapshot: %s", _exc)

            if failing:
                logger.warning("[OPS-EDGE] Invariant violations: %s", ", ".join(failing))
                try:
                    self.storage.save_edge_learning(
                        detection=f"Invariant violations: {', '.join(failing)}",
                        action_taken="OPS-EDGE periodic audit",
                        learning=f"{len(failing)} checks FAIL, {len(warnings)} WARN",
                        details=str({k: results[k].detail for k in failing}),
                    )
                except Exception as exc:
                    logger.error("[OPS-EDGE] Could not persist violation record: %s", exc)
            else:
                logger.info(
                    "[OPS-EDGE] All checks passed (warnings=%d): %s",
                    len(warnings),
                    ", ".join(warnings) if warnings else "none",
                )
            time.sleep(self.interval_seconds)

    def stop(self) -> None:
        self.running = False
        logger.info("[OPS-EDGE] Operational invariant monitor stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Interfaz pública
    # ─────────────────────────────────────────────────────────────────────────

    def run_checks(self) -> Dict[str, CheckResult]:
        """Ejecuta los checks OEM. Errores individuales no detienen el resto."""
        checks = {
            "shadow_sync": self._check_shadow_sync,
            "backtest_quality": self._check_backtest_quality,
            "connector_exec": self._check_connector_exec,
            "signal_flow": self._check_signal_flow,
            "adx_sanity": self._check_adx_sanity,
            "lifecycle_coherence": self._check_lifecycle_coherence,
            "rejection_rate": self._check_rejection_rate,
            "score_stale": self._check_score_stale,
            "orchestrator_heartbeat": self._check_orchestrator_heartbeat,
            "shadow_stagnation": self._check_shadow_stagnation,
        }
        results = {}
        for name, fn in checks.items():
            try:
                results[name] = fn()
            except Exception as exc:
                logger.warning("[OEM] Check '%s' raised: %s", name, exc)
                results[name] = CheckResult(CheckStatus.WARN, f"Check error: {exc}")
        return results

    def get_health_summary(self) -> Dict:
        """
        Retorna resumen de salud del sistema.

        Returns:
            {
                "status": "OK" | "DEGRADED" | "CRITICAL",
                "checks": {name: {"status": str, "detail": str}},
                "failing": [list of failing check names],
                "warnings": [list of warning check names],
            }
        """
        results = self.run_checks()
        failing = [n for n, r in results.items() if r.status == CheckStatus.FAIL]
        warnings = [n for n, r in results.items() if r.status == CheckStatus.WARN]
        failing, warnings, _ = self._apply_startup_grace(failing, warnings)

        # CRITICAL si >= 2 checks fallan o cualquier heartbeat falla.
        heartbeat_failed = any(name.endswith("_heartbeat") for name in failing)
        if len(failing) >= 2 or heartbeat_failed:
            overall = "CRITICAL"
        elif failing:
            overall = "DEGRADED"
        elif warnings:
            overall = "DEGRADED"
        else:
            overall = "OK"

        return {
            "status": overall,
            "checks": {
                n: {"status": r.status.value, "detail": r.detail}
                for n, r in results.items()
            },
            "failing": failing,
            "warnings": warnings,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Repair flags — bus de comandos vía sys_config
    # ─────────────────────────────────────────────────────────────────────────

    # Mapa: check → flag de reparación automática segura
    _REPAIR_FLAG_MAP: Dict[str, str] = {
        "backtest_quality":    "oem_repair_force_backtest",
        "lifecycle_coherence": "oem_repair_force_backtest",
        "adx_sanity":          "oem_repair_force_ohlc_reload",
        "score_stale":         "oem_repair_force_ranking",
    }
    # Warnings are only auto-repairable for selected checks.
    _WARN_REPAIR_CHECKS = {"score_stale"}

    def _write_repair_flags(self, failing: List[str], warnings: List[str]) -> None:
        """
        Escribe flags de reparación en sys_config para checks accionables.
        El MainOrchestrator los consume al inicio del siguiente ciclo.
        Checks no accionables (shadow_sync, signal_flow, rejection_rate,
        orchestrator_heartbeat) no generan flag — requieren diagnóstico humano.
        """
        flags: Dict[str, str] = {}
        requested_at = self.last_checked_at or datetime.now(timezone.utc).isoformat()

        checks_to_repair = list(failing) + [w for w in warnings if w in self._WARN_REPAIR_CHECKS]

        for check in checks_to_repair:
            flag_key = self._REPAIR_FLAG_MAP.get(check)
            if flag_key and flag_key not in flags:
                flags[flag_key] = requested_at
                logger.info(
                    "[OEM] Repair flag set: %s (triggered by check=%s)", flag_key, check
                )

        if flags:
            self.storage.update_sys_config(flags)

    def _get_startup_invariant_grace_seconds(self) -> int:
        """Return startup grace period for non-actionable invariant checks."""
        try:
            raw = self.storage.get_sys_config().get(
                "oem_invariant_grace_seconds",
                self.STARTUP_INVARIANT_GRACE_SECONDS_DEFAULT,
            )
            return max(0, int(raw))
        except Exception:
            return self.STARTUP_INVARIANT_GRACE_SECONDS_DEFAULT

    def _get_shadow_incubating_max_hours(self) -> int:
        """Return the maximum acceptable incubating age before escalating."""
        try:
            raw = self.storage.get_sys_config().get(
                "oem_shadow_incubating_max_hours",
                self.SHADOW_INCUBATING_MAX_HOURS_DEFAULT,
            )
            return max(1, int(raw))
        except Exception:
            return self.SHADOW_INCUBATING_MAX_HOURS_DEFAULT

    def _get_sys_strategies_map(self) -> Dict[str, Dict[str, Any]]:
        """Build strategy lookup map by class_id for non-actionable checks."""
        try:
            strategies = self.storage.get_all_sys_strategies()
        except Exception:
            return {}

        mapped: Dict[str, Dict[str, Any]] = {}
        for strategy in strategies or []:
            class_id = strategy.get("class_id")
            if class_id:
                mapped[str(class_id)] = strategy
        return mapped

    @staticmethod
    def _is_strategy_non_actionable(strategy_meta: Optional[Dict[str, Any]]) -> bool:
        """Return True when strategy is intentionally blocked or disabled."""
        if not strategy_meta:
            return False

        readiness = str(strategy_meta.get("readiness", "")).upper()
        if readiness == "LOGIC_PENDING":
            return True

        enabled = strategy_meta.get("enabled")
        if enabled in (0, False, "0", "false", "False"):
            return True

        status = str(strategy_meta.get("status", "")).upper()
        return status in {"DISABLED", "INACTIVE", "ARCHIVED"}

    def _apply_startup_grace(self, failing: List[str], warnings: List[str]) -> tuple[List[str], List[str], List[str]]:
        """Downgrade selected FAIL checks to WARN during startup grace window."""
        if not failing:
            return failing, warnings, []

        grace_seconds = self._get_startup_invariant_grace_seconds()
        if grace_seconds <= 0:
            return failing, warnings, []

        elapsed = (datetime.now(timezone.utc) - self._started_at_utc).total_seconds()
        if elapsed >= grace_seconds:
            return failing, warnings, []

        graced = [check for check in failing if check in self.STARTUP_GRACE_CHECKS]
        if not graced:
            return failing, warnings, []

        adjusted_failing = [check for check in failing if check not in self.STARTUP_GRACE_CHECKS]
        adjusted_warnings = list(warnings)
        for check in graced:
            if check not in adjusted_warnings:
                adjusted_warnings.append(check)

        remaining = max(0, int(grace_seconds - elapsed))
        logger.info(
            "[OPS-EDGE] Startup grace active (%ss remaining) — non-actionable checks: %s",
            remaining,
            ", ".join(graced),
        )
        return adjusted_failing, adjusted_warnings, graced

    # ─────────────────────────────────────────────────────────────────────────
    # Checks individuales
    # ─────────────────────────────────────────────────────────────────────────

    def _any_session_active(self) -> bool:
        """
        Retorna True si al menos una sesión de mercado principal está activa ahora.
        Forex cerrado: sábado completo + domingo antes de las 22:00 UTC (apertura Sydney).
        """
        try:
            utc_now = datetime.now(timezone.utc)
            weekday = utc_now.weekday()  # 5=sábado, 6=domingo
            if weekday == 5:
                return False  # Sábado: mercado siempre cerrado
            if weekday == 6 and utc_now.hour < 22:
                return False  # Domingo antes de la apertura de Sydney (22:00 UTC)
            from core_brain.services.market_session_service import MarketSessionService
            svc = MarketSessionService(self.storage)
            return any(svc.is_session_active(s, utc_now) for s in ("sydney", "tokyo", "london", "ny"))
        except Exception as exc:
            logger.debug("[OEM] No se pudo verificar sesión de mercado: %s", exc)
            return True  # Asumir mercado abierto ante duda (fail-open para no suprimir checks)

    def _check_shadow_sync(self) -> CheckResult:
        """Instancias SHADOW con >2h de vida deben tener total_trades_executed > 0."""
        if self.shadow_storage is None:
            return CheckResult(CheckStatus.WARN, "shadow_storage no inyectado — check omitido")

        strategies_map = self._get_sys_strategies_map()
        incubating_max_hours = self._get_shadow_incubating_max_hours()
        now_utc = datetime.now(timezone.utc)
        instances = self.shadow_storage.list_active_instances()
        cutoff = now_utc - timedelta(hours=2)
        mature = [i for i in instances if (_parse_ts(getattr(i, "created_at", None)) or datetime.min.replace(tzinfo=timezone.utc)) < cutoff]

        if not mature:
            return CheckResult(CheckStatus.OK, "Sin instancias SHADOW maduras que evaluar")

        actionable_stuck_ids: List[str] = []
        non_actionable_ids: List[str] = []
        incubating_ok_ids: List[str] = []
        incubating_overdue_ids: List[str] = []

        for instance in mature:
            trades_executed = (getattr(instance, "total_trades_executed", 0) or 0)
            if trades_executed > 0:
                continue

            instance_id = str(getattr(instance, "instance_id", "?"))
            created_at = _parse_ts(getattr(instance, "created_at", None)) or datetime.min.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (now_utc - created_at).total_seconds() / 3600)

            raw_status = getattr(instance, "status", None)
            status_value = str(getattr(raw_status, "value", raw_status or "")).upper()
            strategy_id = str(getattr(instance, "strategy_id", ""))

            if status_value == "INCUBATING":
                if age_hours <= incubating_max_hours:
                    incubating_ok_ids.append(instance_id)
                else:
                    incubating_overdue_ids.append(instance_id)
                continue

            strategy_meta = strategies_map.get(strategy_id) if strategy_id else None
            if self._is_strategy_non_actionable(strategy_meta):
                non_actionable_ids.append(instance_id)
                continue

            actionable_stuck_ids.append(instance_id)

        if actionable_stuck_ids:
            ids = actionable_stuck_ids[:5]
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"{len(actionable_stuck_ids)}/{len(mature)} instancias con 0 trades (mercado cerrado — esperado): {ids}",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"{len(actionable_stuck_ids)}/{len(mature)} instancias con 0 trades accionables: {ids}",
            )

        if non_actionable_ids:
            return CheckResult(
                CheckStatus.WARN,
                f"{len(non_actionable_ids)}/{len(mature)} instancias con 0 trades no accionables (LOGIC_PENDING/disabled): {non_actionable_ids[:5]}",
            )

        if incubating_overdue_ids:
            return CheckResult(
                CheckStatus.WARN,
                f"{len(incubating_overdue_ids)}/{len(mature)} instancias siguen INCUBATING con 0 trades >{incubating_max_hours}h: {incubating_overdue_ids[:5]}",
            )

        if incubating_ok_ids:
            return CheckResult(
                CheckStatus.OK,
                f"{len(incubating_ok_ids)}/{len(mature)} instancias en incubación dentro de ventana ({incubating_max_hours}h)",
            )

        return CheckResult(CheckStatus.OK, f"{len(mature)} instancias maduras con trades activos")

    def _check_backtest_quality(self) -> CheckResult:
        """
        Estrategias en modo BACKTEST deben tener al menos una con score_backtest > 0.
        Fuente: sys_strategies (tiene score_backtest real del BacktestOrchestrator).
        sys_signal_ranking NO tiene este campo.
        """
        strategies = self.storage.get_all_sys_strategies()
        if not strategies:
            return CheckResult(CheckStatus.WARN, "Sin estrategias registradas en sys_strategies")

        backtest_strategies = [s for s in strategies if s.get("mode") == "BACKTEST"]
        if not backtest_strategies:
            return CheckResult(CheckStatus.WARN, "Sin estrategias en modo BACKTEST — check omitido")

        with_score = [s for s in backtest_strategies if (s.get("score_backtest") or 0) > 0]
        if not with_score:
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"Las {len(backtest_strategies)} estrategia(s) en BACKTEST tienen score_backtest=0 "
                    f"(mercado cerrado — backtest sin datos MT5 es esperado)",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"Las {len(backtest_strategies)} estrategia(s) en BACKTEST tienen score_backtest=0",
            )
        return CheckResult(
            CheckStatus.OK,
            f"{len(with_score)}/{len(backtest_strategies)} estrategias BACKTEST con score_backtest > 0",
        )

    def _check_connector_exec(self) -> CheckResult:
        """Al menos una cuenta de broker habilitada debe tener supports_exec=1."""
        accounts = self.storage.get_sys_broker_accounts(enabled_only=True)
        exec_capable = [a for a in accounts if a.get("supports_exec", 0)]
        if not exec_capable:
            return CheckResult(CheckStatus.FAIL, "Sin cuenta con supports_exec=1 habilitada")
        return CheckResult(CheckStatus.OK, f"{len(exec_capable)} cuenta(s) exec-capaz encontrada(s)")

    def _check_signal_flow(self) -> CheckResult:
        """Al menos una señal generada en las últimas 2h."""
        recent = self.storage.get_recent_sys_signals(minutes=self.SIGNAL_FLOW_WINDOW_MINUTES)
        if not recent:
            return CheckResult(
                CheckStatus.WARN,
                f"Sin señales en los últimos {self.SIGNAL_FLOW_WINDOW_MINUTES} min",
            )
        return CheckResult(CheckStatus.OK, f"{len(recent)} señal(es) en los últimos {self.SIGNAL_FLOW_WINDOW_MINUTES} min")

    def _check_adx_sanity(self) -> CheckResult:
        """Al menos el 10% de los market pulses deben tener ADX > 0."""
        pulses = self.storage.get_all_sys_market_pulses()
        if not pulses:
            return CheckResult(CheckStatus.WARN, "Sin datos de market pulse")

        total = len(pulses)
        nonzero = sum(1 for p in pulses.values() if _extract_adx(p) > 0)
        ratio = nonzero / total

        if ratio < self.MIN_ADX_NONZERO_RATIO:
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"ADX=0 en {total - nonzero}/{total} pulses (mercado cerrado — datos OHLC sin actualizar es esperado)",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"ADX=0 en {total - nonzero}/{total} pulses — scanner puede no estar llamando load_ohlc()",
            )
        return CheckResult(CheckStatus.OK, f"ADX no-cero en {nonzero}/{total} pulses ({ratio:.0%})")

    def _check_lifecycle_coherence(self) -> CheckResult:
        """Rankings en modo BACKTEST no deben permanecer sin actualizar >48h."""
        rankings = self.storage.get_all_signal_rankings()
        if not rankings:
            return CheckResult(CheckStatus.OK, "Sin rankings que evaluar")

        strategies_map = self._get_sys_strategies_map()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.LIFECYCLE_STALE_HOURS)
        actionable_stale: List[str] = []
        non_actionable_stale: List[str] = []

        for ranking in rankings:
            if ranking.get("execution_mode") != "BACKTEST":
                continue

            strategy_id = str(ranking.get("strategy_id", "?"))
            freshness_ts = _parse_ts(ranking.get("last_update_utc")) or _parse_ts(ranking.get("updated_at"))
            if (freshness_ts or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff:
                continue

            strategy_meta = strategies_map.get(strategy_id)
            zero_history_bootstrap = (
                ("total_usr_trades" in ranking or "completed_last_50" in ranking)
                and int(ranking.get("total_usr_trades") or 0) <= 0
                and int(ranking.get("completed_last_50") or 0) <= 0
            )

            if zero_history_bootstrap:
                non_actionable_stale.append(strategy_id)
                continue

            if self._is_strategy_non_actionable(strategy_meta):
                non_actionable_stale.append(strategy_id)
            else:
                actionable_stale.append(strategy_id)

        if actionable_stale:
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"{len(actionable_stale)} estrategia(s) en BACKTEST sin actualizar >{self.LIFECYCLE_STALE_HOURS}h "
                    f"(mercado cerrado — actualización en pausa es esperado): {actionable_stale[:5]}",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"{len(actionable_stale)} estrategia(s) en BACKTEST sin actualizar >{self.LIFECYCLE_STALE_HOURS}h: {actionable_stale[:5]}",
            )

        if non_actionable_stale:
            return CheckResult(
                CheckStatus.WARN,
                f"{len(non_actionable_stale)} estrategia(s) stale no accionables (LOGIC_PENDING/disabled): {non_actionable_stale[:5]}",
            )

        return CheckResult(CheckStatus.OK, "Sin estrategias atascadas en ciclo BACKTEST")

    def _check_rejection_rate(self) -> CheckResult:
        """Tasa de rechazo de señales debe ser < 95% en las últimas 4h."""
        signals = self.storage.get_recent_sys_signals(minutes=240, limit=200)
        if not signals:
            return CheckResult(CheckStatus.OK, "Sin señales para evaluar tasa de rechazo")

        rejected = sum(1 for s in signals if s.get("status") in ("REJECTED", "VETOED"))
        rate = rejected / len(signals)

        if rate >= self.MAX_REJECTION_RATE:
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"Tasa de rechazo {rate:.0%} ({rejected}/{len(signals)}) — mercado cerrado, rechazo total es esperado",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"Tasa de rechazo {rate:.0%} ({rejected}/{len(signals)}) — pipeline puede estar bloqueado",
            )
        return CheckResult(CheckStatus.OK, f"Tasa de rechazo {rate:.0%} ({rejected}/{len(signals)}) — aceptable")

    def _check_score_stale(self) -> CheckResult:
        """Todos los rankings deben haber sido actualizados en las últimas 72h."""
        rankings = self.storage.get_all_signal_rankings()
        if not rankings:
            return CheckResult(CheckStatus.WARN, "Sin rankings encontrados")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.STALE_SCORE_HOURS)
        stale = [
            r.get("strategy_id", "?")
            for r in rankings
            if (_parse_ts(r.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)) < cutoff
        ]

        if stale:
            return CheckResult(
                CheckStatus.WARN,
                f"{len(stale)} estrategia(s) sin puntaje en >{self.STALE_SCORE_HOURS}h: {stale[:5]}",
            )
        return CheckResult(CheckStatus.OK, f"Todos los {len(rankings)} rankings actualizados en <{self.STALE_SCORE_HOURS}h")

    def _check_orchestrator_heartbeat(self) -> CheckResult:
        """Heartbeat watchdog: mantiene contrato OEM legacy con validación multicomponente."""
        primary = self._check_component_heartbeat("orchestrator")
        if primary.status == CheckStatus.FAIL:
            return primary

        # Extra components are monitored only when they have heartbeat evidence.
        # This preserves OEM's 10-check contract while enforcing component SLA in production.
        monitored_components = ["scanner", "signal_factory", "executor", "risk_manager"]
        warnings: List[str] = []
        for component in monitored_components:
            if not self._has_heartbeat_evidence(component):
                continue
            result = self._check_component_heartbeat(component)
            if result.status == CheckStatus.FAIL:
                return CheckResult(CheckStatus.FAIL, f"{component}: {result.detail}")
            if result.status == CheckStatus.WARN:
                warnings.append(f"{component}: {result.detail}")

        if warnings:
            return CheckResult(CheckStatus.WARN, " | ".join(warnings))
        return primary

    def _has_heartbeat_evidence(self, component_name: str) -> bool:
        """Return True when there is heartbeat evidence in sys_config or canonical audit."""
        try:
            heartbeats = self.storage.get_module_heartbeats()
            if component_name in heartbeats and heartbeats.get(component_name) is not None:
                return True
        except Exception:
            pass

        if hasattr(self.storage, "get_latest_module_heartbeat_audit"):
            try:
                audit_raw = self.storage.get_latest_module_heartbeat_audit(component_name)
                return isinstance(audit_raw, (str, datetime)) and _parse_ts(audit_raw) is not None
            except Exception:
                return False
        return False

    def _check_component_heartbeat(self, component_name: str) -> CheckResult:
        """Evaluate heartbeat freshness for a component using strict SLA in seconds."""
        heartbeats = self.storage.get_module_heartbeats()
        config_ts_raw = heartbeats.get(component_name)
        config_ts = _parse_ts(config_ts_raw)

        audit_ts_raw: Optional[str] = None
        audit_ts: Optional[datetime] = None
        if hasattr(self.storage, "get_latest_module_heartbeat_audit"):
            raw = self.storage.get_latest_module_heartbeat_audit(component_name)
            if isinstance(raw, (str, datetime)):
                audit_ts_raw = raw.isoformat() if isinstance(raw, datetime) else raw
                audit_ts = _parse_ts(raw)

        sys_config = self.storage.get_sys_config()
        silenced_threshold_raw = sys_config.get(
            "oem_silenced_component_gap_seconds",
            self.HEARTBEAT_FAIL_GAP_SECONDS_DEFAULT,
        )
        warn_threshold_raw = sys_config.get(
            "oem_heartbeat_warn_gap_seconds",
            self.HEARTBEAT_WARN_GAP_SECONDS_DEFAULT,
        )
        fail_threshold_raw = sys_config.get(
            "oem_heartbeat_fail_gap_seconds",
            self.HEARTBEAT_FAIL_GAP_SECONDS_DEFAULT,
        )
        try:
            silenced_threshold_seconds = max(60, int(silenced_threshold_raw))
        except (TypeError, ValueError):
            silenced_threshold_seconds = self.SILENCED_COMPONENT_GAP_SECONDS_DEFAULT
        try:
            warn_threshold_seconds = max(30, int(warn_threshold_raw))
        except (TypeError, ValueError):
            warn_threshold_seconds = self.HEARTBEAT_WARN_GAP_SECONDS_DEFAULT
        try:
            fail_threshold_seconds = max(warn_threshold_seconds + 1, int(fail_threshold_raw))
        except (TypeError, ValueError):
            fail_threshold_seconds = self.HEARTBEAT_FAIL_GAP_SECONDS_DEFAULT

        source = "sys_config"
        chosen_ts = config_ts
        chosen_raw = config_ts_raw
        if audit_ts is not None:
            audit_age_seconds = (datetime.now(timezone.utc) - audit_ts).total_seconds()
            if (
                chosen_ts is None
                or audit_ts >= chosen_ts
                or audit_age_seconds <= silenced_threshold_seconds
            ):
                source = "sys_audit_logs"
                chosen_ts = audit_ts
                chosen_raw = audit_ts_raw

        if chosen_ts is None and config_ts_raw is None and audit_ts_raw is None:
            return CheckResult(
                CheckStatus.WARN,
                f"Sin heartbeat registrado en sys_config ni sys_audit_logs — {component_name} puede no haber iniciado aún",
            )

        if chosen_ts is None:
            return CheckResult(
                CheckStatus.WARN,
                f"Heartbeat con formato inválido ({component_name}, {source}): {chosen_raw}",
            )

        gap_seconds = (datetime.now(timezone.utc) - chosen_ts).total_seconds()

        if gap_seconds > silenced_threshold_seconds:
            return CheckResult(
                CheckStatus.FAIL,
                f"Componente Silenciado: {component_name} sin HEARTBEAT hace {gap_seconds:.0f}s "
                f"(umbral: {silenced_threshold_seconds}s, source={source})",
            )

        if gap_seconds > fail_threshold_seconds:
            return CheckResult(
                CheckStatus.FAIL,
                f"{component_name} sin heartbeat hace {gap_seconds:.0f}s "
                f"(umbral fail: {fail_threshold_seconds}s, source={source})",
            )
        if gap_seconds > warn_threshold_seconds:
            return CheckResult(
                CheckStatus.WARN,
                f"Heartbeat tardío: {component_name} {gap_seconds:.0f}s "
                f"(umbral warn: {warn_threshold_seconds}s, source={source})",
            )
        return CheckResult(
            CheckStatus.OK,
            f"{component_name} activo (heartbeat hace {gap_seconds:.0f}s, source={source})",
        )

    def _check_shadow_stagnation(self) -> CheckResult:
        """Detecta instancias SHADOW activas sin trades en la ventana operativa."""
        if self.shadow_storage is None:
            return CheckResult(CheckStatus.WARN, "shadow_storage no inyectado — check omitido")

        cfg = self.storage.get_sys_config() if hasattr(self.storage, "get_sys_config") else {}
        window_raw = cfg.get("shadow_stagnation_hours", self.SHADOW_STAGNATION_WINDOW_HOURS_DEFAULT)
        try:
            window_hours = max(1, int(window_raw))
        except (TypeError, ValueError):
            window_hours = self.SHADOW_STAGNATION_WINDOW_HOURS_DEFAULT

        instances = self.shadow_storage.list_active_instances()
        if not instances:
            return CheckResult(CheckStatus.OK, "Sin instancias SHADOW activas para evaluar")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        today_utc = datetime.now(timezone.utc).date().isoformat()
        stale_instances: List[str] = []
        causes: List[str] = []
        emitted = 0

        for instance in instances:
            instance_id = str(getattr(instance, "instance_id", ""))
            if not instance_id:
                continue

            recent_trades = self._count_recent_shadow_trades(instance_id, cutoff)
            if recent_trades > 0:
                continue

            stale_instances.append(instance_id)
            cause = self._classify_stagnation_cause(instance, cfg)
            causes.append(cause)

            if self._can_emit_stagnation_alert(instance_id, today_utc, cfg):
                self.storage.log_audit_event(
                    user_id="system",
                    action="SHADOW_STAGNATION_ALERT",
                    resource="shadow_instance",
                    resource_id=instance_id,
                    status="warning",
                    reason=(
                        f"Instance={instance_id} has 0 SHADOW trades in the last {window_hours}h; "
                        f"probable_cause={cause}"
                    ),
                )
                emitted += 1
                self._mark_stagnation_alert_emitted(instance_id, today_utc, cfg)

        if not stale_instances:
            return CheckResult(CheckStatus.OK, f"Sin estancamiento SHADOW en ventana de {window_hours}h")

        unique_causes = sorted(set(causes))
        return CheckResult(
            CheckStatus.WARN,
            (
                f"SHADOW_STAGNATION_ALERT: {len(stale_instances)} instancia(s) sin trades en {window_hours}h; "
                f"causas={unique_causes}; alerts_emitidas={emitted}"
            ),
        )

    def _count_recent_shadow_trades(self, instance_id: str, cutoff: datetime) -> int:
        """Cuenta trades SHADOW de una instancia con close_time >= cutoff."""
        if not hasattr(self.storage, "get_sys_trades"):
            return 0
        trades = self.storage.get_sys_trades(
            execution_mode="SHADOW",
            instance_id=instance_id,
            limit=1000,
        )
        recent = 0
        for trade in trades or []:
            ts_raw = trade.get("close_time") or trade.get("created_at")
            ts = _parse_ts(ts_raw)
            if ts and ts >= cutoff:
                recent += 1
        return recent

    def _classify_stagnation_cause(self, instance: Any, cfg: Dict[str, Any]) -> str:
        """Clasifica causa probable de estancamiento para diagnóstico OEM."""
        symbol = str(getattr(instance, "symbol", "") or "")
        active_symbols = cfg.get("active_symbols")
        if symbol and isinstance(active_symbols, list) and active_symbols and symbol not in active_symbols:
            return "SYMBOL_NOT_WHITELISTED"

        if not self._any_session_active():
            return "OUTSIDE_SESSION_WINDOW"

        target_regime = str(getattr(instance, "target_regime", "") or "").upper()
        if target_regime and target_regime != "ANY":
            pulses = self.storage.get_all_sys_market_pulses() if hasattr(self.storage, "get_all_sys_market_pulses") else {}
            observed_regimes = {
                str((p.get("data") or p).get("regime", "")).upper()
                for p in (pulses or {}).values()
                if isinstance((p.get("data") or p), dict)
            }
            observed_regimes.discard("")
            if observed_regimes and target_regime not in observed_regimes:
                return "REGIME_MISMATCH"

        return "UNKNOWN"

    def _can_emit_stagnation_alert(self, instance_id: str, day_key: str, cfg: Dict[str, Any]) -> bool:
        """Idempotencia diaria por instancia para SHADOW_STAGNATION_ALERT."""
        if self._stagnation_alert_cache.get(instance_id) == day_key:
            return False
        state = cfg.get(self.SHADOW_STAGNATION_ALERTS_STATE_KEY, {})
        if not isinstance(state, dict):
            return True
        return state.get(instance_id) != day_key

    def _mark_stagnation_alert_emitted(self, instance_id: str, day_key: str, cfg: Dict[str, Any]) -> None:
        """Persist idempotencia diaria del alert de estancamiento en sys_config."""
        self._stagnation_alert_cache[instance_id] = day_key
        state = cfg.get(self.SHADOW_STAGNATION_ALERTS_STATE_KEY, {})
        if not isinstance(state, dict):
            state = {}
        state[instance_id] = day_key
        self.storage.update_sys_config({self.SHADOW_STAGNATION_ALERTS_STATE_KEY: state})


# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas (módulo-nivel)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(ts: "str | datetime | None") -> Optional[datetime]:
    """Convierte string ISO o datetime a datetime timezone-aware. Retorna None si falla."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(ts))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_adx(pulse_entry: Dict) -> float:
    """Extrae el valor ADX de una entrada de market pulse (soporta estructura anidada)."""
    if not pulse_entry:
        return 0.0
    data = pulse_entry.get("data") or pulse_entry
    if isinstance(data, dict):
        adx = data.get("adx") or data.get("metrics", {}).get("adx", 0.0)
        return float(adx or 0.0)
    return 0.0
