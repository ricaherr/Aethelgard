"""
IntegrityGuard — Servicio de Autodiagnóstico en Runtime (EDGE)
==============================================================

Realiza "Chequeos Vivos" (Lightweight Health Checks) sobre datos en ejecución:
  - Check_Database:      Conectividad a DB + legibilidad de sys_config.
  - Check_Data_Coherence: Detección de congelamiento de ticks de mercado.
  - Check_Veto_Logic:    Indicadores críticos (ADX) nulos o cero persistentes.

Restricciones técnicas:
  - Sin análisis estático (AST), sin pytest/mypy, sin escaneo de archivos.
  - Tiempo de CPU por ciclo completo <= 200 ms.
  - Cada log de salud lleva Trace_ID obligatorio.

TRACE_ID: EDGE-IGNITION-PHASE-1-INTEGRITY-GUARD-2026-03-30
"""
import json
import logging
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# -- Constantes --------------------------------------------------------------
_TICK_STALENESS_SECONDS = 300   # 5 minutos
_ADX_ZERO_COUNT_THRESHOLD = 3  # Cuantos ceros seguidos disparan CRITICAL


class HealthStatus(Enum):
    """Estado de salud retornado por cada chequeo y por check_health()."""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class CheckResult:
    """Resultado atomico de un chequeo individual."""
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
    Servicio de autodiagnostico en runtime para el orquestador principal.

    Uso:
        guard = IntegrityGuard(storage=storage_manager)
        report = guard.check_health()
        if report.overall == HealthStatus.CRITICAL:
            # detener ciclo de trading
    """

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage
        self._adx_zero_streak: int = 0  # Contador de ciclos con ADX == 0

    # -- API publica ---------------------------------------------------------

    def check_health(self) -> HealthReport:
        """
        Ejecuta los tres chequeos en secuencia y retorna un HealthReport.

        Performance: <= 200 ms total de CPU.
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

    # -- Chequeos individuales ----------------------------------------------

    def _check_database(self, parent_trace_id: str) -> CheckResult:
        """Check_Database: Valida conexion funcional a DB y lectura de sys_config."""
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:db"
        try:
            config = self._storage.get_sys_config()
            if not isinstance(config, dict):
                raise ValueError("sys_config no retorno un dict")
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
        Check_Data_Coherence: Detecta congelamiento si el ultimo tick de mercado
        en sys_config tiene mas de _TICK_STALENESS_SECONDS de antiguedad.
        """
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:coherence"
        try:
            config = self._storage.get_sys_config()
            last_tick_raw: Optional[str] = config.get("last_market_tick_ts")
            repair_armed = bool(config.get("oem_repair_force_ohlc_reload"))

            if last_tick_raw is None:
                elapsed = (time.monotonic() - t0) * 1000
                return CheckResult(
                    name="Check_Data_Coherence",
                    status=HealthStatus.WARNING,
                    message=(
                        "last_market_tick_ts no encontrado en sys_config. Sin datos de tick. "
                        f"repair_armed={repair_armed}"
                    ),
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
                        f"Datos desactualizados: ultimo tick hace "
                        f"{int(age_seconds)}s (umbral {_TICK_STALENESS_SECONDS}s). "
                        f"Broker sin conexion activa - sistema en modo analisis. "
                        f"repair_armed={repair_armed}"
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            return CheckResult(
                name="Check_Data_Coherence",
                status=HealthStatus.OK,
                message=f"Tick fresco: {int(age_seconds)}s de antiguedad.",
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
        Check_Veto_Logic: Si el ADX (o indicadores criticos) en sys_config
        presentan valor nulo o 0 de forma persistente (_ADX_ZERO_COUNT_THRESHOLD
        ciclos consecutivos), retorna HEALTH_CRITICAL.
        """
        t0 = time.monotonic()
        trace_id = f"{parent_trace_id}:veto"
        try:
            config = self._storage.get_sys_config()
            dynamic_params: Dict = config.get("dynamic_params", {})
            if isinstance(dynamic_params, str):
                dynamic_params = json.loads(dynamic_params)

            adx_value = _normalize_adx(dynamic_params.get("adx", dynamic_params.get("ADX")))
            if adx_value is None:
                adx_value = self._get_fallback_adx_from_market_pulse()

            market_probably_closed = self._is_market_probably_closed(config)
            repair_armed = bool(config.get("oem_repair_force_ohlc_reload"))
            tick_age_s = self._get_tick_age_seconds(config)

            if repair_armed and adx_value is None:
                # Allow one recovery cycle while OEM refreshes OHLC snapshots.
                self._adx_zero_streak = 0
                elapsed = (time.monotonic() - t0) * 1000
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.WARNING,
                    message=(
                        "ADX invalido/nulo/cero durante reparacion OEM activa "
                        f"(tick_age={tick_age_s if tick_age_s is not None else 'unknown'}s). "
                        "Se mantiene en WARNING hasta completar recarga."
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )

            if market_probably_closed and adx_value is None:
                # Prevent false-positive CRITICAL during inactive sessions.
                self._adx_zero_streak = 0
                elapsed = (time.monotonic() - t0) * 1000
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.WARNING,
                    message=(
                        "ADX invalido/nulo/cero con mercado inactivo (tick stale). "
                        f"No se eleva a CRITICAL fuera de sesion. tick_age={tick_age_s if tick_age_s is not None else 'unknown'}s"
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )

            if adx_value is None:
                self._adx_zero_streak += 1
            else:
                self._adx_zero_streak = 0

            elapsed = (time.monotonic() - t0) * 1000
            if self._adx_zero_streak >= _ADX_ZERO_COUNT_THRESHOLD:
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.CRITICAL,
                    message=(
                        f"ADX invalido/nulo/cero durante {self._adx_zero_streak} ciclos "
                        f"consecutivos (umbral {_ADX_ZERO_COUNT_THRESHOLD}). "
                        f"Indicadores criticos comprometidos. tick_age={tick_age_s if tick_age_s is not None else 'unknown'}s"
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            if self._adx_zero_streak > 0:
                return CheckResult(
                    name="Check_Veto_Logic",
                    status=HealthStatus.WARNING,
                    message=(
                        f"ADX invalido/nulo/cero en {self._adx_zero_streak} ciclo(s). "
                        f"Monitoreo activo (umbral {_ADX_ZERO_COUNT_THRESHOLD}). "
                        f"tick_age={tick_age_s if tick_age_s is not None else 'unknown'}s"
                    ),
                    trace_id=trace_id,
                    elapsed_ms=round(elapsed, 2),
                )
            return CheckResult(
                name="Check_Veto_Logic",
                status=HealthStatus.OK,
                message=f"ADX valido: {adx_value}.",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )
        except (ValueError, TypeError, OSError) as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return CheckResult(
                name="Check_Veto_Logic",
                status=HealthStatus.CRITICAL,
                message=f"Error al leer indicadores criticos: {exc}",
                trace_id=trace_id,
                elapsed_ms=round(elapsed, 2),
            )

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _aggregate_status(results: List[CheckResult]) -> HealthStatus:
        statuses = {r.status for r in results}
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK

    @staticmethod
    def _is_market_probably_closed(config: Dict) -> bool:
        """
        Heuristic to avoid ADX false positives when the market is inactive.

        Requires a stale last_market_tick_ts to consider closure; otherwise
        keeps fail-open behavior to avoid masking real runtime failures.
        """
        try:
            last_tick_raw = config.get("last_market_tick_ts")
            if not last_tick_raw:
                return False

            last_tick_dt = datetime.fromisoformat(str(last_tick_raw))
            if last_tick_dt.tzinfo is None:
                last_tick_dt = last_tick_dt.replace(tzinfo=timezone.utc)

            utc_now = datetime.now(timezone.utc)
            tick_age = (utc_now - last_tick_dt).total_seconds()
            if tick_age <= _TICK_STALENESS_SECONDS:
                return False

            # Fast path for canonical forex weekend closure.
            weekday = utc_now.weekday()
            if weekday == 5 or (weekday == 6 and utc_now.hour < 22):
                return True

            return False
        except Exception:
            return False

    @staticmethod
    def _get_tick_age_seconds(config: Dict) -> Optional[int]:
        """Return tick age in seconds for observability messages, if available."""
        try:
            last_tick_raw = config.get("last_market_tick_ts")
            if not last_tick_raw:
                return None

            last_tick_dt = datetime.fromisoformat(str(last_tick_raw))
            if last_tick_dt.tzinfo is None:
                last_tick_dt = last_tick_dt.replace(tzinfo=timezone.utc)

            age_seconds = int((datetime.now(timezone.utc) - last_tick_dt).total_seconds())
            return max(age_seconds, 0)
        except Exception:
            return None

    def _get_fallback_adx_from_market_pulse(self) -> Optional[float]:
        """
        Fallback ADX source from latest sys_market_pulse entries.

        Uses the maximum non-zero ADX found across latest symbol pulses.
        Returns None when pulse data is unavailable or all values are invalid.
        """
        try:
            if not hasattr(self._storage, "get_all_sys_market_pulses"):
                return None

            pulses = self._storage.get_all_sys_market_pulses() or {}
            if not isinstance(pulses, dict) or not pulses:
                return None

            best: Optional[float] = None
            for pulse_entry in pulses.values():
                adx = _extract_adx_from_pulse_entry(pulse_entry)
                if adx is None:
                    continue
                if best is None or adx > best:
                    best = adx
            return best
        except Exception:
            return None

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


def _normalize_adx(adx_raw: object) -> Optional[float]:
    """Return normalized ADX or None when value is invalid/non-finite/<= 0."""
    try:
        adx = float(adx_raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(adx) or adx <= 0.0:
        return None
    return adx


def _extract_adx_from_pulse_entry(pulse_entry: object) -> Optional[float]:
    """Extract ADX from a pulse entry with tolerant nested-shape parsing."""
    if not isinstance(pulse_entry, dict):
        return None

    data = pulse_entry.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = None

    metrics = None
    if isinstance(data, dict):
        metrics = data.get("metrics")
        if not isinstance(metrics, dict):
            metrics = data

    if not isinstance(metrics, dict):
        return None

    return _normalize_adx(metrics.get("adx", metrics.get("ADX")))
