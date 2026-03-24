"""
operational_edge_monitor.py — Verificación de Invariantes de Negocio

Componente standalone que ejecuta 8 checks contra la capa de almacenamiento
y reporta el estado de salud operacional del sistema.

Checks:
  shadow_sync         — Instancias SHADOW maduras acumulando trades
  backtest_quality    — Al menos una estrategia con backtest_score > 0
  connector_exec      — Al menos un conector de ejecución habilitado
  signal_flow         — Señales generadas en las últimas 2h
  adx_sanity          — ADX no atascado en 0 en los market pulses
  lifecycle_coherence — Sin estrategias con rankings vencidos >48h
  rejection_rate      — Tasa de rechazo de señales < 95%
  score_stale         — Rankings actualizados en las últimas 72h
"""
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

    # ── Thread interface ──────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info(
            "[OPS-EDGE] Operational invariant monitor started (interval=%ds)",
            self.interval_seconds,
        )
        while self.running:
            results = self.run_checks()
            failing = [k for k, r in results.items() if r.status == CheckStatus.FAIL]
            if failing:
                logger.warning("[OPS-EDGE] Invariant violations: %s", ", ".join(failing))
                try:
                    self.storage.save_edge_learning(
                        detection=f"Invariant violations: {', '.join(failing)}",
                        action_taken="OPS-EDGE periodic audit",
                        learning=f"{len(failing)} checks FAIL",
                        details=str({k: results[k].detail for k in failing}),
                    )
                except Exception as exc:
                    logger.error("[OPS-EDGE] Could not persist violation record: %s", exc)
            time.sleep(self.interval_seconds)

    def stop(self) -> None:
        self.running = False
        logger.info("[OPS-EDGE] Operational invariant monitor stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Interfaz pública
    # ─────────────────────────────────────────────────────────────────────────

    def run_checks(self) -> Dict[str, CheckResult]:
        """Ejecuta los 8 checks. Errores individuales no detienen el resto."""
        checks = {
            "shadow_sync": self._check_shadow_sync,
            "backtest_quality": self._check_backtest_quality,
            "connector_exec": self._check_connector_exec,
            "signal_flow": self._check_signal_flow,
            "adx_sanity": self._check_adx_sanity,
            "lifecycle_coherence": self._check_lifecycle_coherence,
            "rejection_rate": self._check_rejection_rate,
            "score_stale": self._check_score_stale,
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

        if len(failing) >= 3:
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
    # Checks individuales
    # ─────────────────────────────────────────────────────────────────────────

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
            return CheckResult(
                CheckStatus.FAIL,
                f"{len(stuck)}/{len(mature)} instancias con 0 trades: {ids}",
            )
        return CheckResult(CheckStatus.OK, f"{len(mature)} instancias maduras con trades activos")

    def _check_backtest_quality(self) -> CheckResult:
        """Al menos una estrategia debe tener score_backtest > 0."""
        rankings = self.storage.get_all_signal_rankings()
        if not rankings:
            return CheckResult(CheckStatus.WARN, "Sin rankings de estrategias encontrados")

        with_score = [r for r in rankings if (r.get("score_backtest") or 0) > 0]
        if not with_score:
            return CheckResult(
                CheckStatus.FAIL,
                f"Todas las {len(rankings)} estrategias tienen score_backtest=0",
            )
        return CheckResult(CheckStatus.OK, f"{len(with_score)}/{len(rankings)} estrategias con backtest > 0")

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


# ─────────────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas (módulo-nivel)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(ts) -> Optional[datetime]:
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
        return float(data.get("adx", 0.0) or 0.0)
    return 0.0
