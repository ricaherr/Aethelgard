"""
strategy_pending.py — API Router for LOGIC_PENDING Strategy Management (HU 3.2).

Endpoints:
  GET  /api/v3/strategy-pending
      Lista todas las estrategias LOGIC_PENDING con su diagnóstico actual.

  POST /api/v3/strategy-pending/{class_id}/retry
      Re-ejecuta el diagnóstico y autocorrección para una estrategia específica.

  POST /api/v3/strategy-pending/{class_id}/discard
      Marca la estrategia como DISCARDED (archivada, no se ejecutará).

  POST /api/v3/strategy-pending/{class_id}/promote
      Promueve forzosamente la estrategia a READY_FOR_ENGINE (override manual).

Auth: page-level protection via AuthGuard on the frontend.  Backend auth is not
applied here — consistent with the MonitorPage endpoint pattern (see resilience.py).

Trace_ID: ETI-E3-HU3.1
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from data_vault.storage import StorageManager
    from core_brain.strategy_pending_diagnostics import StrategyPendingDiagnosticsService

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/strategy-pending", tags=["Strategy Pending"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_storage() -> "StorageManager":
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


def _get_diagnostics_service() -> "StrategyPendingDiagnosticsService":
    from core_brain.strategy_pending_diagnostics import StrategyPendingDiagnosticsService
    return StrategyPendingDiagnosticsService(_get_storage())


def _parse_readiness_notes(notes_raw: Optional[str]) -> Dict[str, Any]:
    """Parse readiness_notes as JSON diagnosis payload, or return raw text."""
    if not notes_raw:
        return {}
    try:
        parsed = json.loads(notes_raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return {"cause_detail": notes_raw}


# ── Schemas ───────────────────────────────────────────────────────────────────

class PendingStrategyResponse(BaseModel):
    """Representación de una estrategia LOGIC_PENDING con su diagnóstico."""
    class_id: str
    mnemonic: str
    strategy_type: str
    readiness: str
    cause: Optional[str] = None
    cause_detail: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fixed: Optional[bool] = None
    last_checked: Optional[str] = None
    description: Optional[str] = None


class ActionRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Motivo opcional de la acción manual.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[PendingStrategyResponse])
async def list_pending_strategies() -> List[PendingStrategyResponse]:
    """Lista todas las estrategias LOGIC_PENDING con diagnóstico persistido."""
    storage = _get_storage()
    try:
        strategies = storage.get_pending_strategies()
    except Exception as e:
        logger.error("[STRATEGY_PENDING] Error fetching pending strategies: %s", e)
        raise HTTPException(status_code=503, detail="Error al consultar estrategias pendientes.")

    result: List[PendingStrategyResponse] = []
    for s in strategies:
        diagnosis = _parse_readiness_notes(s.get("readiness_notes"))
        result.append(PendingStrategyResponse(
            class_id=s["class_id"],
            mnemonic=s.get("mnemonic", s["class_id"]),
            strategy_type=s.get("type", "UNKNOWN"),
            readiness=s.get("readiness", "LOGIC_PENDING"),
            cause=diagnosis.get("cause"),
            cause_detail=diagnosis.get("cause_detail"),
            suggestion=diagnosis.get("suggestion"),
            auto_fixed=diagnosis.get("auto_fixed"),
            last_checked=diagnosis.get("last_checked"),
            description=s.get("description"),
        ))
    return result


@router.post("/{class_id}/retry")
async def retry_diagnosis(
    class_id: str,
    body: ActionRequest = ActionRequest(),
) -> Dict[str, Any]:
    """Re-ejecuta diagnóstico y autocorrección para una estrategia."""
    service = _get_diagnostics_service()
    diagnosis = service.diagnose_one(class_id)
    if diagnosis is None:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{class_id}' no encontrada o no está en LOGIC_PENDING.",
        )
    return {
        "ok": True,
        "result": diagnosis.to_dict(),
    }


@router.post("/{class_id}/discard")
async def discard_strategy(
    class_id: str,
    body: ActionRequest = ActionRequest(),
) -> Dict[str, Any]:
    """Archiva (descarta) una estrategia LOGIC_PENDING marcándola como DISCARDED."""
    storage = _get_storage()
    strategy = storage.get_strategy(class_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Estrategia '{class_id}' no encontrada.")

    notes = json.dumps({
        "cause": strategy.get("readiness_notes", ""),
        "action": "DISCARDED_BY_USER",
        "reason": body.reason or "Archivada manualmente por el operador.",
    })
    storage.update_strategy_readiness(class_id=class_id, readiness="DISCARDED", readiness_notes=notes)
    logger.info("[STRATEGY_PENDING] %s discarded by operator", class_id)
    return {"ok": True, "class_id": class_id, "new_readiness": "DISCARDED"}


@router.post("/{class_id}/promote")
async def promote_strategy(
    class_id: str,
    body: ActionRequest = ActionRequest(),
) -> Dict[str, Any]:
    """Promueve forzosamente una estrategia a READY_FOR_ENGINE (override manual)."""
    storage = _get_storage()
    strategy = storage.get_strategy(class_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Estrategia '{class_id}' no encontrada.")

    notes = json.dumps({
        "action": "PROMOTED_BY_USER",
        "reason": body.reason or "Promovida manualmente por el operador.",
    })
    storage.update_strategy_readiness(class_id=class_id, readiness="READY_FOR_ENGINE", readiness_notes=notes)
    logger.warning("[STRATEGY_PENDING] %s force-promoted to READY_FOR_ENGINE by operator", class_id)
    return {"ok": True, "class_id": class_id, "new_readiness": "READY_FOR_ENGINE"}
