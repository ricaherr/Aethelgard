"""
resilience.py — API Router for Resilience Control (HU 10.17b).

Exposes two endpoints for the ResilienceConsole UI:

  GET  /api/v3/resilience/status
      Returns current SystemPosture, healing-budget remaining, and the
      lists of quarantined/muted scopes.

  POST /api/v3/resilience/command
      Accepts operator interventions: RETRY_HEALING, OVERRIDE_POSTURE,
      RELEASE_SCOPE.  Each action delegates to the live ResilienceManager
      instance — the human always has the last word over system posture.

Design notes:
  - Reads/writes the ResilienceManager singleton registered in server.py.
  - Returns HTTP 503 when the manager is not yet initialised (engine
    is still booting); the UI shows a graceful "unavailable" state.
  - All mutations are fire-and-forget from the API perspective — the
    ResilienceManager is authoritative; the endpoint only triggers it.

Trace_ID: EDGE-IGNITION-PHASE-6-RESILIENCE-UI
Source of truth: docs/10_INFRA_RESILIENCY.md §E14
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/resilience", tags=["Resilience"])

# ── Accepted command actions ──────────────────────────────────────────────────
_VALID_COMMANDS = {"RETRY_HEALING", "OVERRIDE_POSTURE", "RELEASE_SCOPE"}


class ResilienceCommandRequest(BaseModel):
    """Body for POST /api/v3/resilience/command."""

    action: str = Field(
        ...,
        description="One of: RETRY_HEALING | OVERRIDE_POSTURE | RELEASE_SCOPE",
    )
    scope: str | None = Field(
        None,
        description="Asset or strategy identifier (required for RELEASE_SCOPE).",
    )
    posture: str | None = Field(
        None,
        description="Target posture string (required for OVERRIDE_POSTURE).",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_UNAVAILABLE_STATUS: Dict[str, Any] = {
    "posture": "UNAVAILABLE",
    "narrative": "ResilienceManager no inicializado — el motor puede estar arrancando.",
    "is_healing": False,
    "heal_budget_remaining": 0,
    "exclusions": {"muted": [], "quarantined": [], "in_cooldown": []},
}


def _get_manager_or_none() -> Any:
    """Return the live ResilienceManager, or None if not yet initialised."""
    from core_brain.server import get_resilience_manager
    return get_resilience_manager()


def _require_manager() -> Any:
    """Return the live ResilienceManager or raise HTTP 503 (for write operations)."""
    manager = _get_manager_or_none()
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="ResilienceManager no inicializado — el motor puede estar arrancando.",
        )
    return manager


def _build_status_payload(manager: Any) -> Dict[str, Any]:
    """Serialize current ResilienceManager state into the API response body."""
    from core_brain.resilience import SystemPosture, EdgeAction

    posture = manager.current_posture
    narrative = manager.get_current_status_narrative()

    # Derive quarantined/muted scopes from internal counters
    muted: List[str] = [
        scope
        for scope, count in manager._l0_failure_counts.items()
        if count > 0
    ]
    quarantined: List[str] = [
        scope
        for provider_scopes in manager._l1_provider_map.values()
        for scope in provider_scopes
    ]
    in_cooldown: List[str] = [
        scope for scope in manager._cooldowns if manager.is_in_cooldown(scope)
    ]

    # Healing budget: how many retries remain across all active heal keys
    from core_brain.resilience_manager import _MAX_HEAL_RETRIES
    used_retries = sum(manager._healing_attempts.values())
    total_budget = _MAX_HEAL_RETRIES * max(len(manager._healing_attempts), 1)
    heal_budget_remaining = max(0, total_budget - used_retries)

    return {
        "posture": posture.value,
        "narrative": narrative,
        "is_healing": manager.is_healing,
        "heal_budget_remaining": heal_budget_remaining,
        "exclusions": {
            "muted": muted,
            "quarantined": quarantined,
            "in_cooldown": in_cooldown,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_resilience_status() -> Dict[str, Any]:
    """
    Returns the current SystemPosture, healing budget, and exclusion lists.

    When ResilienceManager is not yet initialised (engine still booting), returns
    HTTP 200 with posture="UNAVAILABLE" — the server CAN respond, the subsystem
    is simply not ready.  HTTP 503 is reserved for POST /command which requires an
    active manager to mutate state.

    Response schema::

        {
          "posture": "DEGRADED",
          "narrative": "Sistema en DEGRADED — afectado: ...",
          "is_healing": false,
          "heal_budget_remaining": 2,
          "exclusions": {
            "muted": ["XAUUSD"],
            "quarantined": ["STRAT_01"],
            "in_cooldown": []
          }
        }
    """
    manager = _get_manager_or_none()
    if manager is None:
        logger.debug("[ResilienceAPI] GET /status — manager not ready, returning UNAVAILABLE.")
        return _UNAVAILABLE_STATUS
    return _build_status_payload(manager)


@router.post("/command")
async def send_resilience_command(body: ResilienceCommandRequest) -> Dict[str, Any]:
    """
    Send an operator intervention command to the ResilienceManager.

    Supported actions:

    ``RETRY_HEALING``
        Resets the healing-attempts counter so the next incoming report
        triggers a fresh self-healing cycle.  Useful after a manual fix.

    ``OVERRIDE_POSTURE``
        Forces the posture to the specified value (``body.posture``).
        The human operator takes precedence over algorithmic decisions.
        Valid values: NORMAL | CAUTION | DEGRADED | STRESSED.

    ``RELEASE_SCOPE``
        Removes ``body.scope`` from the mute-window, provider-map, and
        cooldown registry so the asset/strategy can resume normal operation.
    """
    if body.action not in _VALID_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Acción no reconocida: '{body.action}'. "
                   f"Valores válidos: {sorted(_VALID_COMMANDS)}",
        )

    manager = _require_manager()

    if body.action == "RETRY_HEALING":
        manager._healing_attempts.clear()
        logger.info(
            "[ResilienceAPI] RETRY_HEALING — healing counters reset by operator."
        )
        return {"success": True, "action": "RETRY_HEALING", "detail": "Contadores de sanación reiniciados."}

    if body.action == "OVERRIDE_POSTURE":
        from core_brain.resilience import SystemPosture
        if not body.posture:
            raise HTTPException(status_code=400, detail="'posture' requerido para OVERRIDE_POSTURE.")
        try:
            new_posture = SystemPosture(body.posture.upper())
        except ValueError:
            valid = [p.value for p in SystemPosture]
            raise HTTPException(
                status_code=400,
                detail=f"Postura inválida: '{body.posture}'. Valores: {valid}",
            )
        old_posture = manager._current_posture.value
        manager._current_posture = new_posture
        logger.warning(
            "[ResilienceAPI] OVERRIDE_POSTURE: %s → %s (operador manual).",
            old_posture,
            new_posture.value,
        )
        return {
            "success": True,
            "action": "OVERRIDE_POSTURE",
            "detail": f"Postura actualizada: {old_posture} → {new_posture.value}",
        }

    # RELEASE_SCOPE
    if not body.scope:
        raise HTTPException(status_code=400, detail="'scope' requerido para RELEASE_SCOPE.")
    scope = body.scope

    manager._l0_failure_counts.pop(scope, None)
    manager._cooldowns.pop(scope, None)
    manager._l0_mute_window = [
        (ts, sc) for ts, sc in manager._l0_mute_window if sc != scope
    ]
    for provider in list(manager._l1_provider_map):
        try:
            manager._l1_provider_map[provider].remove(scope)
        except ValueError:
            pass
    for key in [k for k in manager._healing_attempts if scope in k]:
        del manager._healing_attempts[key]

    logger.info(
        "[ResilienceAPI] RELEASE_SCOPE '%s' — all exclusion entries cleared by operator.",
        scope,
    )
    return {
        "success": True,
        "action": "RELEASE_SCOPE",
        "detail": f"Scope '{scope}' liberado de todas las exclusiones.",
    }
