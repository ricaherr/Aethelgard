"""
tests/test_incident_learning.py — TDD para IncidentLearningEngine (ETI E5-HU5.1)

Cubre:
  - Registro y persistencia de incidentes
  - Selección progresiva de rutas de recovery
  - Agotamiento de rutas y escalada a intervención manual
  - Resolución automática y marcado de incidente
  - Auto-reversión cuando el incidente desaparece
  - Registro de feedback de usuario
  - Estadísticas de éxito por ruta
  - Integración con AlertingService (notificación enriquecida)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call
import pytest

from core_brain.incident_learning_engine import (
    IncidentLearningEngine,
    IncidentRecord,
    IncidentStatus,
    RecoveryRoute,
    ROUTE_CATALOG,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_storage() -> MagicMock:
    storage = MagicMock()
    storage.save_edge_learning = MagicMock(return_value=None)
    storage.log_audit_event = MagicMock(return_value=None)
    return storage


def _make_alerting() -> MagicMock:
    alerting = MagicMock()
    alerting.send_incident_alert = MagicMock(return_value={"log_only": True})
    return alerting


def _make_engine(
    storage=None,
    alerting=None,
) -> IncidentLearningEngine:
    return IncidentLearningEngine(
        storage=storage or _make_storage(),
        alerting_service=alerting or _make_alerting(),
    )


# ── Test: Registro de Incidente ───────────────────────────────────────────────

def test_record_incident_devuelve_id_unico() -> None:
    """Dos incidentes del mismo tipo deben tener IDs distintos."""
    engine = _make_engine()
    id1 = engine.record_incident("connector_failure", "Timeout en MT5", trace_id="T-001")
    id2 = engine.record_incident("connector_failure", "Timeout en MT5", trace_id="T-002")
    assert id1 != id2


def test_record_incident_crea_registro_pendiente() -> None:
    """El incidente recién creado tiene estado OPEN."""
    engine = _make_engine()
    incident_id = engine.record_incident("connector_failure", "Auth error", trace_id="T-003")
    record = engine.get_incident(incident_id)
    assert record is not None
    assert record.status == IncidentStatus.OPEN
    assert record.incident_type == "connector_failure"
    assert record.cause == "Auth error"
    assert record.trace_id == "T-003"


def test_record_incident_persiste_en_storage() -> None:
    """El registro debe persistir en el StorageManager."""
    storage = _make_storage()
    engine = _make_engine(storage=storage)
    engine.record_incident("database_failure", "DB locked", trace_id="T-004")
    storage.save_edge_learning.assert_called_once()


# ── Test: Rutas de Recovery ───────────────────────────────────────────────────

def test_get_next_route_retorna_primera_ruta_para_tipo_conocido() -> None:
    """Para connector_failure sin rutas previas, retorna la primera del catálogo."""
    engine = _make_engine()
    route = engine.get_next_route("connector_failure", routes_tried=[])
    assert route is not None
    assert route in ROUTE_CATALOG["connector_failure"]


def test_get_next_route_omite_rutas_ya_probadas() -> None:
    """Si ya se intentó la primera ruta, retorna la siguiente en el catálogo."""
    engine = _make_engine()
    all_routes = ROUTE_CATALOG["connector_failure"]
    first_route = all_routes[0]
    route = engine.get_next_route("connector_failure", routes_tried=[first_route])
    assert route != first_route
    assert route in all_routes[1:]


def test_get_next_route_retorna_none_cuando_rutas_agotadas() -> None:
    """Si todas las rutas fueron intentadas, retorna None."""
    engine = _make_engine()
    all_routes = ROUTE_CATALOG["connector_failure"]
    route = engine.get_next_route("connector_failure", routes_tried=list(all_routes))
    assert route is None


def test_get_next_route_tipo_desconocido_retorna_ruta_generica() -> None:
    """Para un tipo de incidente desconocido, retorna ruta genérica."""
    engine = _make_engine()
    route = engine.get_next_route("unknown_exotic_failure", routes_tried=[])
    assert route is not None  # siempre hay al menos la ruta genérica


# ── Test: Registro de Intentos de Ruta ───────────────────────────────────────

def test_record_route_attempt_registra_intento_fallido() -> None:
    """El intento fallido se registra en el historial del incidente."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-010")
    engine.record_route_attempt(inc_id, "reconnect_provider", success=False)
    record = engine.get_incident(inc_id)
    assert "reconnect_provider" in record.routes_tried
    assert record.routes_results[0] is False


def test_record_route_attempt_registra_intento_exitoso() -> None:
    """El intento exitoso se registra y no cambia el estado a RESOLVED automáticamente."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-011")
    engine.record_route_attempt(inc_id, "reconnect_provider", success=True)
    record = engine.get_incident(inc_id)
    assert record.routes_results[0] is True
    # mark_resolved es explícito, no automático en record_route_attempt
    assert record.status == IncidentStatus.OPEN


def test_record_route_attempt_con_id_inexistente_no_lanza() -> None:
    """Llamar con un ID de incidente inexistente no debe lanzar excepción."""
    engine = _make_engine()
    engine.record_route_attempt("non-existent-id", "reconnect_provider", success=False)


# ── Test: Resolución de Incidente ─────────────────────────────────────────────

def test_mark_resolved_cambia_estado_a_resolved() -> None:
    """Marcar como resuelto cambia el estado y registra la ruta de resolución."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-020")
    engine.mark_resolved(inc_id, resolution_route="reconnect_provider")
    record = engine.get_incident(inc_id)
    assert record.status == IncidentStatus.RESOLVED
    assert record.resolution_route == "reconnect_provider"


def test_mark_resolved_persiste_en_storage() -> None:
    """La resolución debe persistir en el StorageManager."""
    storage = _make_storage()
    engine = _make_engine(storage=storage)
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-021")
    storage.save_edge_learning.reset_mock()
    engine.mark_resolved(inc_id, resolution_route="reconnect_provider")
    storage.save_edge_learning.assert_called_once()


def test_mark_unresolved_cambia_estado_a_exhausted() -> None:
    """Tras agotamiento de rutas, el estado debe ser EXHAUSTED."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Auth error", trace_id="T-022")
    engine.mark_unresolved(inc_id)
    record = engine.get_incident(inc_id)
    assert record.status == IncidentStatus.EXHAUSTED


# ── Test: Auto-Reversión ──────────────────────────────────────────────────────

def test_check_auto_revert_resuelve_incidente_cuando_condicion_desaparece() -> None:
    """Si el check de condición retorna False (sin problema), marca el incidente resuelto."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-030")
    # condition_fn retorna False = problema ya no existe
    reverted = engine.check_auto_revert(inc_id, condition_fn=lambda: False)
    assert reverted is True
    assert engine.get_incident(inc_id).status == IncidentStatus.RESOLVED


def test_check_auto_revert_no_resuelve_si_condicion_persiste() -> None:
    """Si la condición aún existe, el incidente queda OPEN."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-031")
    reverted = engine.check_auto_revert(inc_id, condition_fn=lambda: True)
    assert reverted is False
    assert engine.get_incident(inc_id).status == IncidentStatus.OPEN


def test_check_auto_revert_envia_notificacion_en_resolucion() -> None:
    """Al auto-revertir, debe notificarse via alerting."""
    alerting = _make_alerting()
    engine = _make_engine(alerting=alerting)
    # notify=False para aislar solo la llamada del auto-revert
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-032", notify=False)
    alerting.send_incident_alert.reset_mock()
    engine.check_auto_revert(inc_id, condition_fn=lambda: False)
    alerting.send_incident_alert.assert_called_once()


# ── Test: Feedback de Usuario ─────────────────────────────────────────────────

def test_record_user_feedback_almacena_en_registro() -> None:
    """El feedback de usuario se guarda en el registro del incidente."""
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-040")
    engine.record_user_feedback(inc_id, feedback="Reconexión manual exitosa")
    record = engine.get_incident(inc_id)
    assert record.user_feedback == "Reconexión manual exitosa"


def test_record_user_feedback_persiste_en_storage() -> None:
    """El feedback persiste en el StorageManager."""
    storage = _make_storage()
    engine = _make_engine(storage=storage)
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-041")
    storage.save_edge_learning.reset_mock()
    engine.record_user_feedback(inc_id, feedback="Resuelto manualmente")
    storage.save_edge_learning.assert_called_once()


# ── Test: Estadísticas de Éxito ───────────────────────────────────────────────

def test_get_success_rate_retorna_0_sin_historial() -> None:
    """Sin historial, la tasa de éxito de cualquier ruta es 0."""
    engine = _make_engine()
    rate = engine.get_success_rate("reconnect_provider")
    assert rate == 0.0


def test_get_success_rate_calcula_correctamente() -> None:
    """Después de 2 éxitos y 1 fallo, la tasa debe ser 2/3 ≈ 0.667."""
    engine = _make_engine()
    for i in range(2):
        inc_id = engine.record_incident("connector_failure", "Timeout", trace_id=f"T-05{i}")
        engine.record_route_attempt(inc_id, "reconnect_provider", success=True)
    inc_id = engine.record_incident("connector_failure", "Timeout", trace_id="T-052")
    engine.record_route_attempt(inc_id, "reconnect_provider", success=False)
    rate = engine.get_success_rate("reconnect_provider")
    assert abs(rate - 2 / 3) < 0.01


# ── Test: Historial de Incidentes ─────────────────────────────────────────────

def test_get_history_retorna_lista_vacia_sin_incidentes() -> None:
    """Sin incidentes registrados, el historial es vacío."""
    engine = _make_engine()
    assert engine.get_history() == []


def test_get_history_retorna_incidentes_en_orden_reciente_primero() -> None:
    """El historial debe ordenarse del más reciente al más antiguo."""
    engine = _make_engine()
    id1 = engine.record_incident("connector_failure", "Timeout", trace_id="T-060")
    id2 = engine.record_incident("database_failure", "Locked", trace_id="T-061")
    history = engine.get_history()
    assert history[0].incident_id == id2
    assert history[1].incident_id == id1


def test_get_history_respeta_limite() -> None:
    """El parámetro limit controla cuántos incidentes se retornan."""
    engine = _make_engine()
    for i in range(5):
        engine.record_incident("connector_failure", f"cause_{i}", trace_id=f"T-07{i}")
    history = engine.get_history(limit=3)
    assert len(history) == 3


# ── Test: Notificación enriquecida ────────────────────────────────────────────

def test_notificacion_enviada_al_crear_incidente_critico() -> None:
    """Al registrar un incidente CRITICAL, se envía notificación via alerting."""
    alerting = _make_alerting()
    engine = _make_engine(alerting=alerting)
    engine.record_incident(
        "connector_failure", "Auth error", trace_id="T-080", notify=True
    )
    alerting.send_incident_alert.assert_called_once()


def test_notificacion_contiene_sugerencia_de_accion() -> None:
    """La notificación de incidente debe incluir sugerencia de acción."""
    alerting = _make_alerting()
    engine = _make_engine(alerting=alerting)
    engine.record_incident(
        "connector_failure", "Auth error", trace_id="T-081", notify=True
    )
    call_kwargs = alerting.send_incident_alert.call_args
    # Verificar que se pasó suggestion
    assert "suggestion" in call_kwargs.kwargs or len(call_kwargs.args) >= 4


def test_no_notificacion_cuando_notify_false() -> None:
    """Con notify=False, no debe enviarse notificación al crear el incidente."""
    alerting = _make_alerting()
    engine = _make_engine(alerting=alerting)
    engine.record_incident(
        "connector_failure", "Auth error", trace_id="T-082", notify=False
    )
    alerting.send_incident_alert.assert_not_called()


# ── Test: Integración — múltiples rutas antes de escalar ─────────────────────

def test_ciclo_completo_dos_rutas_antes_de_escalar() -> None:
    """
    El sistema debe probar al menos 2 rutas antes de marcar EXHAUSTED.
    Simula: ruta1 falla → ruta2 falla → EXHAUSTED.
    """
    engine = _make_engine()
    inc_id = engine.record_incident("connector_failure", "Broker down", trace_id="T-090")

    route1 = engine.get_next_route("connector_failure", routes_tried=[])
    assert route1 is not None
    engine.record_route_attempt(inc_id, route1, success=False)

    route2 = engine.get_next_route("connector_failure", routes_tried=[route1])
    assert route2 is not None
    assert route2 != route1
    engine.record_route_attempt(inc_id, route2, success=False)

    # Simular que no hay más rutas → EXHAUSTED
    all_routes = ROUTE_CATALOG["connector_failure"]
    remaining = engine.get_next_route("connector_failure", routes_tried=list(all_routes))
    if remaining is None:
        engine.mark_unresolved(inc_id)
        assert engine.get_incident(inc_id).status == IncidentStatus.EXHAUSTED


def test_ciclo_completo_resolucion_en_segunda_ruta() -> None:
    """
    Ruta1 falla → Ruta2 éxito → incidente RESOLVED.
    """
    engine = _make_engine()
    inc_id = engine.record_incident("database_failure", "Lock timeout", trace_id="T-091")

    route1 = engine.get_next_route("database_failure", routes_tried=[])
    engine.record_route_attempt(inc_id, route1, success=False)

    route2 = engine.get_next_route("database_failure", routes_tried=[route1])
    engine.record_route_attempt(inc_id, route2, success=True)
    engine.mark_resolved(inc_id, resolution_route=route2)

    record = engine.get_incident(inc_id)
    assert record.status == IncidentStatus.RESOLVED
    assert record.resolution_route == route2
    assert len(record.routes_tried) == 2
