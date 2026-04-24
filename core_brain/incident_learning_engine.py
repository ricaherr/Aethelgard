"""
core_brain/incident_learning_engine.py — Motor de Aprendizaje de Incidentes (ETI E5-HU5.1)

Registra, analiza y propone rutas de auto-reparación progresiva ante incidentes críticos.

Ciclo de vida de un incidente:
  OPEN → (intentos de recovery) → RESOLVED | EXHAUSTED

Catálogo de rutas (ROUTE_CATALOG):
  Cada tipo de incidente tiene rutas ordenadas por prioridad (menos invasiva primero).
  El motor aprende qué rutas tienen mayor tasa de éxito histórico.

Integración:
  ResilienceManager.process_report() → ILE.record_incident() + ILE.record_route_attempt()
  OperationalEdgeMonitor.run() → ILE.check_auto_revert()
  AlertingService → send_incident_alert() para notificación enriquecida

Trace_ID: ETI-ILE-E5HU51-2026-04-24
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Catálogo de rutas de recovery por tipo de incidente ───────────────────────
# Orden: menos invasiva → más invasiva → fallback
ROUTE_CATALOG: Dict[str, List[str]] = {
    "connector_failure": [
        "reconnect_provider",
        "fallback_broker",
        "demo_mode",
    ],
    "database_failure": [
        "clear_db_cache",
        "reconnect_db",
        "restart_scanner",
    ],
    "data_coherence": [
        "reconnect_provider",
        "alternative_feed",
        "pause_trading",
    ],
    "cascade_lockdown": [
        "gradual_restore",
        "partial_restore",
        "manual_intervention",
    ],
    "volatility_lockdown": [
        "reduce_risk_factor",
        "pause_new_entries",
        "close_only_mode",
    ],
    "_generic": [
        "reconnect_provider",
        "restart_scanner",
        "pause_trading",
    ],
}

# Sugerencias de acción para cada tipo de incidente (para notificaciones)
_SUGGESTIONS: Dict[str, str] = {
    "connector_failure": "Verificar credenciales del broker y estado de red.",
    "database_failure": "Revisar locks de SQLite. Reiniciar si persiste.",
    "data_coherence": "Validar feed de datos y conexión al proveedor.",
    "cascade_lockdown": "Revisar estado general del sistema. Posible intervención manual.",
    "volatility_lockdown": "Volatilidad extrema detectada. Revisar exposición de posiciones.",
    "_generic": "Revisar logs del sistema para identificar la causa raíz.",
}


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class IncidentRecord:
    """Registro completo de un incidente y su proceso de recovery."""

    incident_id: str
    incident_type: str
    cause: str
    trace_id: str
    timestamp: float
    status: IncidentStatus = IncidentStatus.OPEN
    routes_tried: List[str] = field(default_factory=list)
    routes_results: List[bool] = field(default_factory=list)
    resolution_route: str = ""
    user_feedback: str = ""
    resolved_at: Optional[float] = None


# Alias para uso externo tipado
RecoveryRoute = str


class IncidentLearningEngine:
    """
    Motor de aprendizaje adaptativo de incidentes.

    Registra cada incidente, ofrece rutas de recovery ordenadas por
    efectividad histórica y aprende de los resultados para mejorar
    la selección futura.

    Args:
        storage: StorageManager para persistencia de aprendizaje.
        alerting_service: AlertingService para notificaciones enriquecidas.
    """

    def __init__(
        self,
        storage: Any,
        alerting_service: Optional[Any] = None,
    ) -> None:
        self._storage = storage
        self._alerting = alerting_service
        # incident_id → IncidentRecord
        self._incidents: Dict[str, IncidentRecord] = {}
        # route_name → (successes, total_attempts)
        self._route_stats: Dict[str, List[int]] = {}

    # ── API pública ───────────────────────────────────────────────────────────

    def record_incident(
        self,
        incident_type: str,
        cause: str,
        trace_id: str = "",
        notify: bool = True,
    ) -> str:
        """
        Registra un nuevo incidente y retorna su ID único.

        Args:
            incident_type: Categoría del incidente (clave en ROUTE_CATALOG).
            cause: Descripción de la causa detectada.
            trace_id: ID de trazabilidad del evento origen.
            notify: Si True, envía notificación enriquecida via alerting_service.

        Returns:
            incident_id único (UUID).
        """
        incident_id = str(uuid.uuid4())
        record = IncidentRecord(
            incident_id=incident_id,
            incident_type=incident_type,
            cause=cause,
            trace_id=trace_id,
            timestamp=time.monotonic(),
        )
        self._incidents[incident_id] = record

        logger.warning(
            "[ILE] Incidente registrado id=%s type=%s cause=%s trace_id=%s",
            incident_id, incident_type, cause, trace_id,
        )

        try:
            suggestion = _SUGGESTIONS.get(incident_type, _SUGGESTIONS["_generic"])
            first_route = self.get_next_route(incident_type, routes_tried=[])
            self._storage.save_edge_learning(
                detection=f"Incidente: {incident_type} — {cause}",
                action_taken=f"Ruta inicial propuesta: {first_route}",
                learning=f"trace_id={trace_id}",
                details=f"incident_id={incident_id} | suggestion={suggestion}",
            )
        except Exception as exc:
            logger.warning("[ILE] No se pudo persistir incidente: %s", exc)

        if notify and self._alerting is not None:
            self._notify_incident_created(record)

        return incident_id

    def record_route_attempt(
        self, incident_id: str, route_name: str, success: bool
    ) -> None:
        """
        Registra el resultado de un intento de recovery.

        Args:
            incident_id: ID del incidente activo.
            route_name: Nombre de la ruta ejecutada.
            success: True si la ruta resolvió el problema.
        """
        record = self._incidents.get(incident_id)
        if record is None:
            logger.debug("[ILE] record_route_attempt: incident_id=%s no encontrado", incident_id)
            return

        record.routes_tried.append(route_name)
        record.routes_results.append(success)

        if route_name not in self._route_stats:
            self._route_stats[route_name] = [0, 0]
        self._route_stats[route_name][1] += 1
        if success:
            self._route_stats[route_name][0] += 1

        logger.info(
            "[ILE] Ruta '%s' resultado=%s para incidente %s",
            route_name, "ÉXITO" if success else "FALLO", incident_id,
        )

    def get_next_route(
        self, incident_type: str, routes_tried: List[str]
    ) -> Optional[RecoveryRoute]:
        """
        Retorna la siguiente ruta de recovery a intentar.

        Ordena las rutas disponibles por tasa de éxito histórico (mayor primero),
        manteniendo el orden del catálogo como desempate.

        Args:
            incident_type: Tipo de incidente.
            routes_tried: Rutas ya intentadas para este incidente.

        Returns:
            Nombre de la siguiente ruta, o None si todas fueron intentadas.
        """
        catalog_routes = ROUTE_CATALOG.get(incident_type, ROUTE_CATALOG["_generic"])
        remaining = [r for r in catalog_routes if r not in routes_tried]
        if not remaining:
            return None
        # Ordenar por tasa de éxito (mayor primero), preservar orden catálogo como desempate
        remaining.sort(
            key=lambda r: self.get_success_rate(r),
            reverse=True,
        )
        return remaining[0]

    def mark_resolved(self, incident_id: str, resolution_route: str) -> None:
        """
        Marca un incidente como RESOLVED tras una ruta exitosa.

        Args:
            incident_id: ID del incidente.
            resolution_route: Ruta que resolvió el problema.
        """
        record = self._incidents.get(incident_id)
        if record is None:
            return
        record.status = IncidentStatus.RESOLVED
        record.resolution_route = resolution_route
        record.resolved_at = time.monotonic()

        logger.info(
            "[ILE] Incidente %s RESUELTO via '%s' tras %d intentos",
            incident_id, resolution_route, len(record.routes_tried),
        )

        try:
            self._storage.save_edge_learning(
                detection=f"Incidente resuelto: {record.incident_type}",
                action_taken=f"Ruta exitosa: {resolution_route}",
                learning=f"Intentos totales: {len(record.routes_tried)}",
                details=f"incident_id={incident_id} | routes={record.routes_tried}",
            )
        except Exception as exc:
            logger.warning("[ILE] No se pudo persistir resolución: %s", exc)

    def mark_unresolved(self, incident_id: str) -> None:
        """
        Marca un incidente como EXHAUSTED tras agotar todas las rutas.

        Args:
            incident_id: ID del incidente.
        """
        record = self._incidents.get(incident_id)
        if record is None:
            return
        record.status = IncidentStatus.EXHAUSTED

        logger.error(
            "[ILE] Incidente %s AGOTADO — %d rutas fallidas. Intervención manual requerida.",
            incident_id, len(record.routes_tried),
        )

        if self._alerting is not None:
            try:
                self._alerting.send_incident_alert(
                    incident_id=incident_id,
                    incident_type=record.incident_type,
                    cause=record.cause,
                    status="EXHAUSTED",
                    routes_tried=record.routes_tried,
                    suggestion="⚠️ Todas las rutas automáticas fallaron. Se requiere intervención manual.",
                    trace_id=record.trace_id,
                )
            except Exception as exc:
                logger.warning("[ILE] Fallo al notificar agotamiento: %s", exc)

    def check_auto_revert(
        self,
        incident_id: str,
        condition_fn: Callable[[], bool],
    ) -> bool:
        """
        Verifica si el incidente se resolvió automáticamente (condición desapareció).

        Args:
            incident_id: ID del incidente a verificar.
            condition_fn: Callable que retorna True si el problema PERSISTE,
                          False si el problema ya no existe.

        Returns:
            True si el incidente fue auto-revertido, False si persiste.
        """
        record = self._incidents.get(incident_id)
        if record is None or record.status != IncidentStatus.OPEN:
            return False

        problem_persists = condition_fn()
        if problem_persists:
            return False

        self.mark_resolved(incident_id, resolution_route="auto_revert")

        if self._alerting is not None:
            try:
                self._alerting.send_incident_alert(
                    incident_id=incident_id,
                    incident_type=record.incident_type,
                    cause=record.cause,
                    status="AUTO_RESOLVED",
                    routes_tried=record.routes_tried,
                    suggestion="El sistema se auto-recuperó. Monitoreo activo.",
                    trace_id=record.trace_id,
                )
            except Exception as exc:
                logger.warning("[ILE] Fallo al notificar auto-reversión: %s", exc)

        return True

    def record_user_feedback(self, incident_id: str, feedback: str) -> None:
        """
        Registra feedback manual del usuario para enriquecer el aprendizaje.

        Args:
            incident_id: ID del incidente.
            feedback: Texto libre del usuario describiendo la resolución.
        """
        record = self._incidents.get(incident_id)
        if record is None:
            return
        record.user_feedback = feedback

        logger.info("[ILE] Feedback registrado para incidente %s: %s", incident_id, feedback)

        try:
            self._storage.save_edge_learning(
                detection=f"Feedback de usuario: {record.incident_type}",
                action_taken="Registro de feedback manual",
                learning=feedback,
                details=f"incident_id={incident_id}",
            )
        except Exception as exc:
            logger.warning("[ILE] No se pudo persistir feedback: %s", exc)

    def get_success_rate(self, route_name: str) -> float:
        """
        Retorna la tasa de éxito histórica de una ruta (0.0 a 1.0).

        Args:
            route_name: Nombre de la ruta de recovery.

        Returns:
            Proporción de éxitos sobre total de intentos. 0.0 si sin historial.
        """
        stats = self._route_stats.get(route_name)
        if stats is None or stats[1] == 0:
            return 0.0
        return stats[0] / stats[1]

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        """Retorna el registro de un incidente por su ID, o None si no existe."""
        return self._incidents.get(incident_id)

    def get_history(self, limit: int = 50) -> List[IncidentRecord]:
        """
        Retorna el historial de incidentes ordenado del más reciente al más antiguo.

        Args:
            limit: Número máximo de incidentes a retornar.

        Returns:
            Lista de IncidentRecord ordenados por timestamp descendente.
        """
        sorted_records = sorted(
            self._incidents.values(),
            key=lambda r: r.timestamp,
            reverse=True,
        )
        return sorted_records[:limit]

    # ── Privados ──────────────────────────────────────────────────────────────

    def _notify_incident_created(self, record: IncidentRecord) -> None:
        """Envía notificación enriquecida al crear un incidente."""
        suggestion = _SUGGESTIONS.get(record.incident_type, _SUGGESTIONS["_generic"])
        first_route = self.get_next_route(record.incident_type, routes_tried=[])
        try:
            self._alerting.send_incident_alert(
                incident_id=record.incident_id,
                incident_type=record.incident_type,
                cause=record.cause,
                status="OPEN",
                routes_tried=[],
                suggestion=suggestion,
                trace_id=record.trace_id,
                next_route=first_route,
            )
        except Exception as exc:
            logger.warning("[ILE] Fallo al notificar creación de incidente: %s", exc)
