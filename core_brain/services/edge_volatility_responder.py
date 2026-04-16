"""
edge_volatility_responder.py — Respuesta Automática EDGE ante Volatilidad Extrema
==================================================================================

Gestiona la respuesta autónoma del sistema cuando el AnomalySentinel detecta
eventos de volatilidad extrema (LOCKDOWN) o elevada (WARNING).

Responsabilidades:
  - Mantener estado operativo: NORMAL / ELEVATED / LOCKDOWN
  - Reducir factor de riesgo (edge_volatility_risk_factor) en LOCKDOWN
  - Emitir alertas operacionales trazables por Trace_ID
  - Auto-revertir al estado NORMAL tras N lecturas NONE consecutivas
  - Persistir estado en sys_config para observabilidad cross-proceso

Uso típico::

    sentinel = AnomalySentinel(storage=storage)
    vrm = VolatilityResponseManager(storage=storage, alerting_service=alerting)
    sentinel.register_listener(vrm.on_volatility_event)

    # En el loop de monitoreo periódico:
    vrm.check_auto_reversal(sentinel)

ETI_ID: EDGE_Volatility_Response_2026-04-16
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from core_brain.services.anomaly_sentinel import DefenseProtocol, VolatilityEvent
from utils.alerting import Alert, AlertingService, AlertSeverity

logger = logging.getLogger(__name__)

# ── Configuración por defecto ─────────────────────────────────────────────────
_DEFAULT_RISK_REDUCTION_FACTOR: float = 0.5
_DEFAULT_AUTO_REVERT_CONSECUTIVE: int = 3

# ── Claves en sys_config ──────────────────────────────────────────────────────
_STATE_KEY = "edge_volatility_state"
_RISK_FACTOR_KEY = "edge_volatility_risk_factor"
_TRACE_KEY = "edge_volatility_last_trace_id"
_LOCKED_AT_KEY = "edge_volatility_locked_at"


class VolatilityResponseState(str, Enum):
    """Estado operativo del gestor de respuesta a volatilidad."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    LOCKDOWN = "LOCKDOWN"


class VolatilityResponseManager:
    """
    Gestor de respuesta automática EDGE ante eventos de volatilidad extrema.

    Suscribe callbacks al AnomalySentinel. Ante LOCKDOWN reduce el factor de
    riesgo y emite alerta CRITICAL. Ante WARNING emite alerta WARNING. La
    auto-reversión ocurre tras ``auto_revert_consecutive`` llamadas consecutivas
    a ``check_auto_reversal`` con protocolo NONE.

    Args:
        storage:                 StorageManager para persistencia de estado.
        alerting_service:        AlertingService para notificaciones operacionales.
        risk_reduction_factor:   Factor de riesgo aplicado en LOCKDOWN (default 0.5).
        auto_revert_consecutive: N lecturas NONE consecutivas para revertir a NORMAL.
    """

    def __init__(
        self,
        storage: Any,
        alerting_service: Optional[AlertingService] = None,
        risk_reduction_factor: float = _DEFAULT_RISK_REDUCTION_FACTOR,
        auto_revert_consecutive: int = _DEFAULT_AUTO_REVERT_CONSECUTIVE,
    ) -> None:
        self._storage = storage
        self._alerting = alerting_service or AlertingService()
        self._risk_reduction_factor = risk_reduction_factor
        self._auto_revert_consecutive = auto_revert_consecutive
        self._state = VolatilityResponseState.NORMAL
        self._none_consecutive = 0
        logger.info(
            "[VRM] Initialized. risk_factor=%.2f, revert_after=%d NONE consecutivos",
            risk_reduction_factor,
            auto_revert_consecutive,
        )

    # ── API pública ───────────────────────────────────────────────────────────

    def on_volatility_event(self, event: VolatilityEvent) -> None:
        """
        Callback para AnomalySentinel. Actúa sobre el evento recibido.

        Args:
            event: VolatilityEvent con protocolo LOCKDOWN o WARNING.
        """
        self._none_consecutive = 0
        if event.protocol == DefenseProtocol.LOCKDOWN:
            self._handle_lockdown(event)
        elif event.protocol == DefenseProtocol.WARNING:
            self._handle_elevated(event)

    def check_auto_reversal(self, sentinel: Any) -> None:
        """
        Verifica si la volatilidad regresó a rango normal.
        Debe llamarse periódicamente desde el loop de monitoreo.

        Args:
            sentinel: AnomalySentinel con método get_defense_protocol().
        """
        if self._state == VolatilityResponseState.NORMAL:
            return
        protocol = sentinel.get_defense_protocol()
        if protocol == DefenseProtocol.NONE:
            self._none_consecutive += 1
        else:
            self._none_consecutive = 0
        if self._none_consecutive >= self._auto_revert_consecutive:
            self._revert_to_normal(sentinel.last_trace_id)

    def get_state(self) -> VolatilityResponseState:
        """Retorna el estado operativo actual."""
        return self._state

    # ── Handlers internos ─────────────────────────────────────────────────────

    def _handle_lockdown(self, event: VolatilityEvent) -> None:
        """Aplica respuesta de LOCKDOWN: reduce riesgo y alerta CRITICAL."""
        prev_state = self._state
        self._state = VolatilityResponseState.LOCKDOWN
        self._persist_state(event.trace_id)
        self._reduce_risk_factor(event.trace_id)
        self._log_audit(event, action="LOCKDOWN_RESPONSE")
        if prev_state != VolatilityResponseState.LOCKDOWN:
            self._send_alert(event, AlertSeverity.CRITICAL)
            logger.critical(
                "[VRM] LOCKDOWN activado. Z-Score=%.2f, Trace_ID=%s",
                event.z_score or 0.0,
                event.trace_id,
            )

    def _handle_elevated(self, event: VolatilityEvent) -> None:
        """Registra volatilidad elevada y alerta WARNING."""
        prev_state = self._state
        if self._state != VolatilityResponseState.LOCKDOWN:
            self._state = VolatilityResponseState.ELEVATED
        self._persist_state(event.trace_id)
        self._log_audit(event, action="ELEVATED_RESPONSE")
        if prev_state == VolatilityResponseState.NORMAL:
            self._send_alert(event, AlertSeverity.WARNING)
            logger.warning(
                "[VRM] Volatilidad elevada. Z-Score=%.2f, Trace_ID=%s",
                event.z_score or 0.0,
                event.trace_id,
            )

    def _revert_to_normal(self, trace_id: str) -> None:
        """Restaura el estado NORMAL y el factor de riesgo completo."""
        self._state = VolatilityResponseState.NORMAL
        self._none_consecutive = 0
        self._restore_risk_factor(trace_id)
        self._persist_state(trace_id)
        logger.info("[VRM] Auto-reversión a NORMAL completada. Trace_ID=%s", trace_id)

    # ── Persistencia y side-effects ────────────────────────────────────────────

    def _persist_state(self, trace_id: str) -> None:
        """Persiste estado y trace_id en sys_config para observabilidad."""
        try:
            self._storage.update_sys_config({
                _STATE_KEY: self._state.value,
                _TRACE_KEY: trace_id,
                _LOCKED_AT_KEY: datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.warning("[VRM] No se pudo persistir estado: %s", exc)

    def _reduce_risk_factor(self, trace_id: str) -> None:
        """Escribe factor de riesgo reducido en sys_config."""
        try:
            self._storage.update_sys_config(
                {_RISK_FACTOR_KEY: str(self._risk_reduction_factor)}
            )
            logger.info(
                "[VRM] Factor de riesgo → %.2f. Trace_ID=%s",
                self._risk_reduction_factor,
                trace_id,
            )
        except Exception as exc:
            logger.warning("[VRM] No se pudo reducir riesgo: %s", exc)

    def _restore_risk_factor(self, trace_id: str) -> None:
        """Restaura factor de riesgo a 1.0 (operación normal)."""
        try:
            self._storage.update_sys_config({_RISK_FACTOR_KEY: "1.0"})
            logger.info("[VRM] Factor de riesgo → 1.0 (restaurado). Trace_ID=%s", trace_id)
        except Exception as exc:
            logger.warning("[VRM] No se pudo restaurar riesgo: %s", exc)

    def _log_audit(self, event: VolatilityEvent, action: str) -> None:
        """Registra la acción en sys_audit_logs con Trace_ID para trazabilidad."""
        try:
            self._storage.log_audit_event(
                user_id="system",
                action=action,
                resource="anomaly_sentinel",
                resource_id=event.trace_id,
                status=self._audit_status(event),
                reason=self._audit_reason(event),
            )
        except Exception as exc:
            logger.warning("[VRM] No se pudo loguear audit: %s", exc)

    def _audit_status(self, event: VolatilityEvent) -> str:
        return "warning" if event.protocol == DefenseProtocol.WARNING else "critical"

    def _audit_reason(self, event: VolatilityEvent) -> str:
        z = event.z_score or 0.0
        return (
            f"protocol={event.protocol.value} "
            f"z_score={z:.3f} trace_id={event.trace_id}"
        )

    def _send_alert(self, event: VolatilityEvent, severity: AlertSeverity) -> None:
        """Despacha alerta operacional vía AlertingService."""
        z = event.z_score or 0.0
        r = event.spread_ratio or 0.0
        self._alerting.send_alert(Alert(
            severity=severity,
            key=f"volatility:{event.trace_id[:8]}",
            title=f"Volatilidad {event.protocol.value} — Respuesta EDGE activada",
            message=(
                f"Protocolo: {event.protocol.value}\n"
                f"Z-Score: {z:.3f}\n"
                f"Spread Ratio: {r:.3f}\n"
                f"Trace_ID: {event.trace_id}\n"
                f"Estado EDGE: {self._state.value}"
            ),
            component="VolatilityResponseManager",
        ))
