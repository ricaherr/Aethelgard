"""
Dynamic Threshold Controller (DTC) — Motor de Exploración Activa en Simulación.
================================================================================
Trace_ID pattern: TRACE_DTC_{YYYYMMDD}_{HHMMSS}_{instance_id[:8].upper()}
Dominio: 07 (Adaptive Learning) — S-9 Dynamic Aggression Engine

Responsabilidad única:
  En modo SHADOW/BACKTEST, si una instancia no genera señales en `window_hours`
  horas, reduce el `dynamic_min_confidence` un `step_down` (piso: `floor_confidence`).
  Si el drawdown de la instancia supera `drawdown_alert_threshold`, recupera el
  umbral hacia el valor base (filosofía "Miedo Zero en Simulación").

Constraints de gobernanza:
  - Solo actúa sobre instancias con status INCUBATING o SHADOW_READY.
  - NUNCA actúa sobre PROMOTED_TO_REAL, DEAD o QUARANTINED.
  - El umbral dinámico se persiste en `parameter_overrides.dynamic_min_confidence`.
  - RULE DB-1: tablas con prefijo sys_.
  - RULE ID-1: Trace_IDs con patrón temporal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Estados SHADOW activos (no terminales)
_ACTIVE_SHADOW_STATUSES = ("INCUBATING", "SHADOW_READY")


class DynamicThresholdController:
    """
    Controlador de Umbral Dinámico para instancias SHADOW/BACKTEST.

    Protocolo "Miedo Zero en Simulación":
      1. Consulta sys_shadow_instances para verificar status e historial.
      2. Consulta sys_signals para detectar sequía de señales (window_hours).
      3. Si sequía detectada → reduce dynamic_min_confidence en step_down.
      4. Si drawdown supera drawdown_alert_threshold → recupera umbral base.
      5. Persiste el umbral en parameter_overrides.dynamic_min_confidence.

    Args:
        storage_conn:               Conexión SQLite inyectada (SSOT pattern).
        base_confidence:            Umbral base inicial (default 0.60).
        floor_confidence:           Piso mínimo absoluto (default 0.40).
        step_down:                  Reducción por ciclo de sequía (default 0.05).
        window_hours:               Ventana de detección de sequía en horas (default 24).
        drawdown_alert_threshold:   Drawdown que activa recuperación (default 0.10 = 10 %).
    """

    def __init__(
        self,
        storage_conn: sqlite3.Connection,
        base_confidence: float = 0.60,
        floor_confidence: float = 0.40,
        step_down: float = 0.05,
        window_hours: int = 24,
        drawdown_alert_threshold: float = 0.10,
    ) -> None:
        self._conn = storage_conn
        self._base_confidence = base_confidence
        self._floor = floor_confidence
        self._step = step_down
        self._window_hours = window_hours
        self._drawdown_alert = drawdown_alert_threshold

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate_and_adjust(self, instance_id: str) -> Dict[str, Any]:
        """
        Evaluar el estado de una instancia SHADOW y ajustar su umbral de confianza.

        Args:
            instance_id: UUID de la instancia en sys_shadow_instances.

        Returns:
            Dict con claves:
              ``instance_id``     — instance_id evaluado.
              ``adjusted``        — bool: True si se realizó un ajuste.
              ``old_threshold``   — umbral antes del ajuste.
              ``new_threshold``   — umbral después del ajuste (igual si no ajustó).
              ``reason``          — descripción textual del resultado.
              ``trace_id``        — Trace_ID de la operación.
        """
        trace_id = self._generate_trace_id(instance_id)
        instance = self._fetch_instance(instance_id)

        if not instance:
            return self._result(instance_id, False, None, None,
                                "instance_not_found", trace_id)

        status = instance.get("status", "")
        if status not in _ACTIVE_SHADOW_STATUSES:
            return self._result(instance_id, False, None, None,
                                f"status_not_applicable: {status}", trace_id)

        current_threshold = self._read_dynamic_threshold(instance)
        strategy_id = instance.get("strategy_id", "")

        # Verificar drawdown primero (mayor prioridad: seguridad)
        drawdown = float(instance.get("max_drawdown_pct") or 0.0)
        if drawdown > self._drawdown_alert:
            recovered = min(self._base_confidence, current_threshold + self._step)
            self._persist_threshold(instance_id, recovered, instance)
            logger.info(
                "[DTC] %s: drawdown %.2f%% > umbral — recuperando threshold %.2f→%.2f trace_id=%s",
                instance_id, drawdown * 100, current_threshold, recovered, trace_id,
            )
            return self._result(instance_id, True, current_threshold, recovered,
                                f"drawdown_recovery: drawdown={drawdown:.4f}", trace_id)

        # Verificar sequía de señales
        has_drought = self._check_signal_drought(strategy_id)
        if has_drought:
            reduced = max(self._floor, current_threshold - self._step)
            self._persist_threshold(instance_id, reduced, instance)
            logger.info(
                "[DTC] %s: sequía %dh detectada — threshold %.2f→%.2f trace_id=%s",
                instance_id, self._window_hours, current_threshold, reduced, trace_id,
            )
            return self._result(instance_id, True, current_threshold, reduced,
                                f"no_signals_{self._window_hours}h", trace_id)

        logger.debug("[DTC] %s: sin cambios (threshold=%.2f) trace_id=%s",
                     instance_id, current_threshold, trace_id)
        return self._result(instance_id, False, current_threshold, current_threshold,
                            "no_adjustment_needed", trace_id)

    def get_current_threshold(self, instance_id: str) -> float:
        """
        Obtener el umbral dinámico actual para una instancia.

        Args:
            instance_id: UUID de la instancia.

        Returns:
            Umbral vigente (base_confidence si no hay ajuste previo).
        """
        instance = self._fetch_instance(instance_id)
        if not instance:
            return self._base_confidence
        return self._read_dynamic_threshold(instance)

    def generate_trace_id(self, instance_id: str) -> str:
        """
        Generar Trace_ID para una operación DTC.

        Formato: ``TRACE_DTC_{YYYYMMDD}_{HHMMSS}_{instance_id[:8].upper()}``

        Args:
            instance_id: UUID de la instancia origen.

        Returns:
            Trace_ID con patrón temporal (RULE ID-1).
        """
        return self._generate_trace_id(instance_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Obtener datos de la instancia desde sys_shadow_instances."""
        try:
            cursor = self._conn.execute(
                """
                SELECT instance_id, strategy_id, status,
                       max_drawdown_pct, parameter_overrides
                FROM sys_shadow_instances
                WHERE instance_id = ?
                """,
                (instance_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            keys = ("instance_id", "strategy_id", "status",
                    "max_drawdown_pct", "parameter_overrides")
            return dict(zip(keys, row))
        except Exception as exc:
            logger.warning("[DTC] Error al leer instancia %s: %s", instance_id, exc)
            return None

    def _check_signal_drought(self, strategy_id: str) -> bool:
        """
        Verificar si no hubo señales para esta estrategia en la ventana temporal.

        Args:
            strategy_id: Estrategia origen de la instancia.

        Returns:
            True si no hay señales recientes (sequía detectada).
        """
        if not strategy_id:
            return True
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=self._window_hours)
            ).isoformat()
            cursor = self._conn.execute(
                """
                SELECT COUNT(*) FROM sys_signals
                WHERE strategy_id = ?
                  AND origin_mode IN ('SHADOW', 'BACKTEST')
                  AND created_at >= ?
                """,
                (strategy_id, cutoff),
            )
            count = int(cursor.fetchone()[0])
            return count == 0
        except Exception as exc:
            logger.warning("[DTC] Error al consultar sequía para %s: %s", strategy_id, exc)
            return False

    def _read_dynamic_threshold(self, instance: Dict[str, Any]) -> float:
        """
        Leer el umbral dinámico desde parameter_overrides de la instancia.

        Clave usada: ``dynamic_min_confidence``.
        Si no existe, retorna el umbral base.
        """
        raw = instance.get("parameter_overrides") or "{}"
        try:
            # parameter_overrides puede ser repr-dict o JSON
            if raw.startswith("{"):
                params = json.loads(raw)
            else:
                params = eval(raw)  # noqa: S307 — datos internos de DB, no input externo
            return float(params.get("dynamic_min_confidence", self._base_confidence))
        except Exception:
            return self._base_confidence

    def _persist_threshold(
        self,
        instance_id: str,
        new_threshold: float,
        instance: Dict[str, Any],
    ) -> None:
        """
        Persistir el nuevo umbral en sys_shadow_instances.parameter_overrides.

        Args:
            instance_id:    UUID de la instancia.
            new_threshold:  Nuevo valor a persistir.
            instance:       Dict con datos actuales de la instancia.
        """
        raw = instance.get("parameter_overrides") or "{}"
        try:
            if raw.startswith("{"):
                params = json.loads(raw)
            else:
                params = eval(raw)  # noqa: S307
        except Exception:
            params = {}

        params["dynamic_min_confidence"] = round(new_threshold, 6)
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            UPDATE sys_shadow_instances
            SET parameter_overrides = ?, updated_at = ?
            WHERE instance_id = ?
            """,
            (json.dumps(params), now, instance_id),
        )
        self._conn.commit()

    def _generate_trace_id(self, instance_id: str) -> str:
        """Generar Trace_ID con patrón temporal (RULE ID-1)."""
        now = datetime.now(timezone.utc)
        return (
            f"TRACE_DTC"
            f"_{now.strftime('%Y%m%d')}"
            f"_{now.strftime('%H%M%S')}"
            f"_{instance_id[:8].upper()}"
        )

    @staticmethod
    def _result(
        instance_id: str,
        adjusted: bool,
        old_threshold: Optional[float],
        new_threshold: Optional[float],
        reason: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        """Construir el dict de resultado estandarizado."""
        return {
            "instance_id": instance_id,
            "adjusted": adjusted,
            "old_threshold": old_threshold,
            "new_threshold": new_threshold,
            "reason": reason,
            "trace_id": trace_id,
        }
