"""
operational_edge_monitor.py — Verificación de Invariantes de Negocio

Componente standalone que ejecuta 9 checks contra la capa de almacenamiento
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
  orchestrator_heartbeat   — Loop principal sin bloqueos (heartbeat < 20 min)
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
    Daemon thread that audits 8 business invariants on every tick.

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
    MAX_HEARTBEAT_GAP_WARN_MINUTES = 10
    MAX_HEARTBEAT_GAP_FAIL_MINUTES = 20
    SILENCED_COMPONENT_GAP_SECONDS_DEFAULT = 120

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

    # ── Thread interface ──────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info(
            "[OPS-EDGE] Operational invariant monitor started (interval=%ds, checks=9)",
            self.interval_seconds,
        )
        while self.running:
            results = self.run_checks()
            self.last_results = results
            self.last_checked_at = datetime.now(timezone.utc).isoformat()

            failing = [k for k, r in results.items() if r.status == CheckStatus.FAIL]
            warnings = [k for k, r in results.items() if r.status == CheckStatus.WARN]

            # Persist snapshot to DB so the API (separate process) can read it
            try:
                orchestrator_down = "orchestrator_heartbeat" in failing
                if len(failing) >= 2 or orchestrator_down:
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
        """Ejecuta los 9 checks. Errores individuales no detienen el resto."""
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

        # CRITICAL si >= 2 checks fallan — heartbeat es siempre crítico solo
        orchestrator_down = "orchestrator_heartbeat" in failing
        if len(failing) >= 2 or orchestrator_down:
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

    def _write_repair_flags(self, failing: List[str], warnings: List[str]) -> None:
        """
        Escribe flags de reparación en sys_config para checks accionables.
        El MainOrchestrator los consume al inicio del siguiente ciclo.
        Checks no accionables (shadow_sync, signal_flow, rejection_rate,
        orchestrator_heartbeat) no generan flag — requieren diagnóstico humano.
        """
        flags: Dict[str, str] = {}
        requested_at = self.last_checked_at or datetime.now(timezone.utc).isoformat()

        for check in failing + warnings:
            flag_key = self._REPAIR_FLAG_MAP.get(check)
            if flag_key and flag_key not in flags:
                flags[flag_key] = requested_at
                logger.info(
                    "[OEM] Repair flag set: %s (triggered by check=%s)", flag_key, check
                )

        if flags:
            self.storage.update_sys_config(flags)

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

        instances = self.shadow_storage.list_active_instances()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        mature = [i for i in instances if (_parse_ts(getattr(i, "created_at", None)) or datetime.min.replace(tzinfo=timezone.utc)) < cutoff]

        if not mature:
            return CheckResult(CheckStatus.OK, "Sin instancias SHADOW maduras que evaluar")

        stuck = [i for i in mature if (getattr(i, "total_trades_executed", 0) or 0) == 0]
        if stuck:
            ids = [getattr(i, "instance_id", "?") for i in stuck[:5]]
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"{len(stuck)}/{len(mature)} instancias con 0 trades (mercado cerrado — esperado): {ids}",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"{len(stuck)}/{len(mature)} instancias con 0 trades: {ids}",
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

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.LIFECYCLE_STALE_HOURS)
        stale = [
            r.get("strategy_id", "?")
            for r in rankings
            if r.get("execution_mode") == "BACKTEST"
            and (_parse_ts(r.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)) < cutoff
        ]

        if stale:
            if not self._any_session_active():
                return CheckResult(
                    CheckStatus.WARN,
                    f"{len(stale)} estrategia(s) en BACKTEST sin actualizar >{self.LIFECYCLE_STALE_HOURS}h "
                    f"(mercado cerrado — actualización en pausa es esperado): {stale[:5]}",
                )
            return CheckResult(
                CheckStatus.FAIL,
                f"{len(stale)} estrategia(s) en BACKTEST sin actualizar >{self.LIFECYCLE_STALE_HOURS}h: {stale[:5]}",
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
        """El loop principal debe actualizar su heartbeat en menos de MAX_HEARTBEAT_GAP_FAIL_MINUTES."""
        heartbeats = self.storage.get_module_heartbeats()
        orchestrator_ts = heartbeats.get("orchestrator")
        source = "sys_config"

        if orchestrator_ts is None and hasattr(self.storage, "get_latest_module_heartbeat_audit"):
            orchestrator_ts = self.storage.get_latest_module_heartbeat_audit("orchestrator")
            source = "sys_audit_logs"

        if orchestrator_ts is None:
            return CheckResult(
                CheckStatus.WARN,
                "Sin heartbeat registrado en sys_config ni sys_audit_logs — orchestrator puede no haber iniciado aún",
            )

        last_beat = _parse_ts(orchestrator_ts)
        if last_beat is None:
            return CheckResult(
                CheckStatus.WARN,
                f"Heartbeat con formato inválido ({source}): {orchestrator_ts}",
            )

        gap_minutes = (datetime.now(timezone.utc) - last_beat).total_seconds() / 60
        gap_seconds = gap_minutes * 60

        silenced_threshold_raw = self.storage.get_sys_config().get(
            "oem_silenced_component_gap_seconds",
            self.MAX_HEARTBEAT_GAP_FAIL_MINUTES * 60,
        )
        try:
            silenced_threshold_seconds = max(60, int(silenced_threshold_raw))
        except (TypeError, ValueError):
            silenced_threshold_seconds = self.SILENCED_COMPONENT_GAP_SECONDS_DEFAULT

        if gap_seconds > silenced_threshold_seconds:
            return CheckResult(
                CheckStatus.FAIL,
                f"Componente Silenciado: sin HEARTBEAT hace {gap_seconds:.0f}s "
                f"(umbral: {silenced_threshold_seconds}s, source={source})",
            )

        if gap_minutes > self.MAX_HEARTBEAT_GAP_FAIL_MINUTES:
            return CheckResult(
                CheckStatus.FAIL,
                f"Loop principal sin heartbeat hace {gap_minutes:.1f} min "
                f"(umbral: {self.MAX_HEARTBEAT_GAP_FAIL_MINUTES} min, source={source}) — posible bloqueo",
            )
        if gap_minutes > self.MAX_HEARTBEAT_GAP_WARN_MINUTES:
            return CheckResult(
                CheckStatus.WARN,
                f"Heartbeat tardío: {gap_minutes:.1f} min (umbral warn: {self.MAX_HEARTBEAT_GAP_WARN_MINUTES} min, source={source})",
            )
        return CheckResult(
            CheckStatus.OK,
            f"Loop principal activo (heartbeat hace {gap_minutes:.1f} min, source={source})",
        )


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
