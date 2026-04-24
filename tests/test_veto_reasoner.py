"""Contract tests for HU 10.17b (Veto Reasoner presentation layer).

Validates resilience status serialization and graceful unavailable behavior.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from core_brain.resilience import SystemPosture
from core_brain.server import create_app, set_resilience_manager


def test_resilience_status_endpoint_returns_unavailable_payload_when_manager_not_ready() -> None:
    """When manager is not initialized, GET /status returns 200 + posture=UNAVAILABLE.

    HTTP 503 would cause browser console spam on every polling cycle.  A 200 with
    a structured UNAVAILABLE payload lets the UI render a graceful state without
    flooding DevTools with errors.  HTTP 503 is still used by POST /command.
    """
    set_resilience_manager(None)
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v3/resilience/status")

    assert response.status_code == 200
    data = response.json()
    assert data["posture"] == "UNAVAILABLE"
    assert data["is_healing"] is False


def test_resilience_status_endpoint_serializes_posture_narrative_and_recovery_context() -> None:
    """Endpoint must serialize posture+narrative+healing context for UI consumption."""
    manager = SimpleNamespace(
        current_posture=SystemPosture.DEGRADED,
        is_healing=True,
        _l0_failure_counts={"XAUUSD": 1},
        _l1_provider_map={"MT5": ["STRAT_01"]},
        _cooldowns={"XAUUSD": 0.0},
        _healing_attempts={"data_coherence:XAUUSD": 1},
        get_current_status_narrative=lambda: "Sistema en DEGRADED — recovery_plan=retry_feed",
        is_in_cooldown=lambda _scope: True,
    )

    set_resilience_manager(manager)
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v3/resilience/status")

    assert response.status_code == 200
    data = response.json()
    assert data["posture"] == "DEGRADED"
    assert data["is_healing"] is True
    assert "recovery_plan" in data["narrative"]
    assert "XAUUSD" in data["exclusions"]["muted"]
    assert "STRAT_01" in data["exclusions"]["quarantined"]

    set_resilience_manager(None)
