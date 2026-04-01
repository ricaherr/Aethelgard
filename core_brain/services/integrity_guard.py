"""
IntegrityGuard — Servicio de Autodiagnóstico en Runtime (EDGE)
==============================================================

Realiza "Chequeos Vivos" (Lightweight Health Checks) sobre datos en ejecución:
  - Check_Database:      Conectividad a DB + legibilidad de sys_config.
  - Check_Data_Coherence: Detección de congelamiento de ticks de mercado.
  - Check_Veto_Logic:    Indicadores críticos (ADX) nulos o cero persistentes.

Restricciones técnicas:
  - Sin análisis estático (AST), sin pytest/mypy, sin escaneo de archivos.
  - Tiempo de CPU por ciclo completo ≤ 200 ms.
  - Cada log de salud lleva Trace_ID obligatorio.

TRACE_ID: EDGE-IGNITION-PHASE-1-INTEGRITY-GUARD-2026-03-30
"""
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────
_TICK_STALENESS_SECONDS = 300   # 5 minutos
_ADX_ZERO_COUNT_THRESHOLD = 3  # Cuántos ceros seguidos disparan CRITICAL


class HealthStatus(Enum):
    """Estado de salud retornado por cada chequeo y por check_health()."""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class CheckResult:
    """Resultado atómico de un chequeo individual."""
    name: str
    status: HealthStatus
    message: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    elapsed_ms: float = 0.0


@dataclass
class HealthReport:
    """Reporte agregado de todos los chequeos."""
    overall: HealthStatus
    checks: List[CheckResult]
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class IntegrityGuard:
    """
    Servicio de autodiagnóstico en runtime para el orquestador principal.

    Uso:
        guard = IntegrityGuard(storage=storage_manager)
        report = guard.check_health()
        if report.overall == HealthStatus.CRITICAL:
            # detener ciclo de trading
    """

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage
        self._adx_zero_streak: int = 0  # Contador de ciclos con ADX == 0

    # ── API pública ──────────────────────────────────────────────────────────

    def check_health(self) -> HealthReport:
        """
        Ejecuta los tres chequeos en secuencia y retorna un HealthReport.

        Performance: ≤ 200 ms total de CPU.
        """
        trace_id = str(uuid.uuid4())
        results: List[CheckResult] = [
            self._check_database(trace_id),
            self._check_data_coherence(trace_id),
            self._check_veto_logic(trace_id),
        ]

        overall = self._aggregate_status(results)
        report = HealthReport(
            overall=overall,
            checks=results,
            trace_id=trace_id,
        )
        self._emit_health_log(report)
        return report

    # ── Chequeos individuales ─────────────────────────────────────────────────

    def _check_database(self, parent_trace_id: str) -> CheckResult:
        """
        Check_Database: Valida conexión funcional a DB y lectura de sys_config.
        """
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:db"
        try:
            config = self._storage.get_sys_config()
            if not isinstance(config, dict):
                raise ValueError("sys_config no retornó un dict")
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="Check_Database",
                status=HealthStatus.OK,
                message=f"DB conectada. sys_config tiene {len(config)} claves.",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="Check_Database",
                status=HealthStatus.CRITICAL,
                message=f"Fallo de conectividad DB: {exc}",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )

    def _check_data_coherence(self, parent_trace_id: str) -> CheckResult:
        """
        Check_Data_Coherence: Detecta congelamiento si el último tick de mercado
        en sys_config tiene más de _TICK_STALENESS_SECONDS de antigüedad.
        """
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:coherence"
        try:
            config = self._storage.get_sys_config()
            last_tick_raw: Optional[str] = config.get("last_market_tick_ts")

            if last_tick_raw is None:
                elapsed = (time.monotonic() - t0) * 1000
                return CheckResult(
                    name="Check_Data_Coherence",
                    status=HealthStatus.WARNING,
                    message="last_market_tick_ts no encontrado en sys_config. Sin datos de tick.",
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )

            last_tick_dt = datetime.fromisoformat(str(last_tick_raw))
            if last_tick_dt.tzinfo is None:
                last_tick_dt = last_tick_dt.replace(tzinfo=timezone.utc)

            age_seconds = (
                datetime.now(timezone.utc) - last_tick_dt
            ).total_seconds()

            elapsed = (time.monotonic() - t0) * 1000
            if age_seconds > _TICK_STALENESS_SECONDS:
                return CheckResult(
                    name="Check_Data_Coherence",
                    status=HealthStatus.WARNING,
                    message=(
                        f"Datos desactualizados: último tick hace "
                        f"{int(age_seconds)}s (umbral {_TICK_STALENESS_SECONDS}s). "
                        f"Broker sin conexión activa — sistema en modo análisis."
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            return CheckResult(
                name="Check_Data_Coherence",
                status=HealthStatus.OK,
                message=f"Tick fresco: {int(age_seconds)}s de antigüedad.",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )
        except (ValueError, TypeError, OSError) as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="Check_Data_Coherence",
                status=HealthStatus.CRITICAL,
                message=f"Error al leer timestamp de tick: {exc}",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )

    def _check_veto_logic(self, parent_trace_id: str) -> CheckResult:
        """
        Check_Veto_Logic: Si el ADX (o indicadores críticos) en sys_config
        presentan valor nulo o 0 de forma persistente (_ADX_ZERO_COUNT_THRESHOLD
        ciclos consecutivos), retorna HEALTH_CRITICAL.
        """
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:veto"
        try:
            config = self._storage.get_sys_config()
            dynamic_params: Dict = config.get("dynamic_params", {})
            if isinstance(dynamic_params, str):
                import json
                dynamic_params = json.loads(dynamic_params)

            adx_value = dynamic_params.get("adx", dynamic_params.get("ADX"))

            if adx_value is None or adx_value == 0:
                self._adx_zero_streak += 1
            else:
                self._adx_zero_streak = 0

            elapsed = (time.monotonic() - t0) * 1000
            if self._adx_zero_streak >= _ADX_ZERO_COUNT_THRESHOLD:
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.CRITICAL,
                    message=(
                        f"ADX nulo/cero durante {self._adx_zero_streak} ciclos "
                        f"consecutivos (umbral {_ADX_ZERO_COUNT_THRESHOLD}). "
                        "Indicadores críticos comprometidos."
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            if self._adx_zero_streak > 0:
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.WARNING,
                    message=(
                        f"ADX nulo/cero en {self._adx_zero_streak} ciclo(s). "
                        f"Monitoreo activo (umbral {_ADX_ZERO_COUNT_THRESHOLD})."
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            return CheckResult(
                name="Check_Veto_Logic",
                status=HealthStatus.OK,
                message=f"ADX válido: {adx_value}.",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )
        except (ValueError, TypeError, OSError) as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="Check_Veto_Logic",
                status=HealthStatus.CRITICAL,
                message=f"Error al leer indicadores críticos: {exc}",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_status(results: List[CheckResult]) -> HealthStatus:
        statuses = {r.status for r in results}
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK

    @staticmethod
    def _emit_health_log(report: HealthReport) -> None:
        log_fn = logger.info
        if report.overall == HealthStatus.CRITICAL:
            log_fn = logger.critical
        elif report.overall == HealthStatus.WARNING:
            log_fn = logger.warning

        failed = [c for c in report.checks if c.status != HealthStatus.OK]
        details = "; ".join(f"[{c.name}] {c.message}" for c in failed) or "Todos OK"
        log_fn(
            "[IntegrityGuard] trace_id=%s overall=%s | %s",
            report.trace_id,
            report.overall.value,
            details,
        )
