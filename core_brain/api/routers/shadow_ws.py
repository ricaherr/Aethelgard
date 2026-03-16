"""
WebSocket Router for SHADOW Pool Evolution
Endpoint: /ws/shadow

Responsibilities:
  - Accept WebSocket connections from frontend clients
  - Validate authentication via JWT token
  - Register connections per tenant (isolation)
  - Handle disconnections gracefully
  - Listen for client keepalive messages

RULE T1: Tenant isolation per token subject (sub)
RULE 4.3: All operations try/except protected with graceful degradation

Pattern: Replicated from telemetry.py (working correctly)
Trace_ID: SHADOW-WS-INTEGRATION-2026-001
"""

import logging
import asyncio
from typing import Dict, Optional, Set, Any
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from data_vault.tenant_factory import TenantDBFactory
from core_brain.api.dependencies.auth import get_ws_user
from models.auth import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SHADOW WebSocket"])

# Global registry of active SHADOW WebSocket connections per tenant
# Structure: { tenant_id: {websocket1, websocket2, ...} }
active_shadow_connections: Dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/shadow")
async def websocket_shadow(
    websocket: WebSocket,
    token_data: TokenPayload = Depends(get_ws_user),
) -> None:
    """
    WebSocket endpoint for SHADOW pool real-time status updates.

    Authentication: via get_ws_user dependency (cookie → header → query param).
    Rejects with WebSocketException(1008) if token is missing or invalid.

    RULE T1: Tenant isolation per token subject (sub)
    RULE 4.3: All operations try/except protected with graceful degradation
    Trace_ID: SHADOW-WS-INTEGRATION-2026-001
    """
    tenant_id = token_data.sub
    logger.info(f"[SHADOW_WS] Authenticated tenant: {tenant_id}")

    try:
        await websocket.accept()
        logger.info(f"[SHADOW_WS] ✓ WebSocket accepted for tenant: {tenant_id}")
    except Exception as exc:
        logger.error(f"[SHADOW_WS] Failed to accept WebSocket handshake: {exc}", exc_info=True)
        return

    # RULE T1: Register connection per tenant
    if tenant_id not in active_shadow_connections:
        active_shadow_connections[tenant_id] = set()
    active_shadow_connections[tenant_id].add(websocket)
    logger.debug(f"[SHADOW_WS] Registered connection for {tenant_id}. Count: {len(active_shadow_connections[tenant_id])}")

    try:
        storage = TenantDBFactory.get_storage(tenant_id)
    except Exception as storage_error:
        logger.error(f"[SHADOW_WS] Storage error: {storage_error}", exc_info=True)
        storage = None

    try:
        await websocket.send_json({
            "event_type": "SHADOW_CONNECTION_ESTABLISHED",
            "message": "Connected to SHADOW WebSocket",
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"[SHADOW_WS] Welcome message sent to {tenant_id}")

        # RULE 4.3: Main loop — listen for keepalive with timeout
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                logger.debug(f"[SHADOW_WS] Keepalive from {tenant_id}: {message[:50]}")

            except asyncio.TimeoutError:
                # Connection still open, awaiting broadcasts from MainOrchestrator
                logger.debug(f"[SHADOW_WS] No keepalive from {tenant_id} (timeout OK, continuing)")
                continue

            except WebSocketDisconnect:
                logger.info(f"[SHADOW_WS] Client disconnected: {tenant_id}")
                break

            except Exception as exc:
                logger.error(f"[SHADOW_WS] Error in message loop: {exc}", exc_info=True)
                break

    finally:
        try:
            if tenant_id in active_shadow_connections:
                active_shadow_connections[tenant_id].discard(websocket)
                if not active_shadow_connections[tenant_id]:
                    del active_shadow_connections[tenant_id]
                    logger.info(f"[SHADOW_WS] All connections closed for tenant: {tenant_id}")
        except Exception as exc:
            logger.error(f"[SHADOW_WS] Cleanup error: {exc}")


def get_active_shadow_connections() -> Dict[str, Set[WebSocket]]:
    """
    Retrieve the active SHADOW WebSocket connections registry.
    Used by MainOrchestrator to broadcast events.
    """
    return active_shadow_connections


async def broadcast_shadow_update(tenant_id: str, update: Dict[str, Any]) -> None:
    """
    Broadcast SHADOW status update to all connected clients of a tenant.
    Called by MainOrchestrator when SHADOW evaluation completes.
    
    RULE T1: Only sends to that tenant's clients
    RULE 4.3: Errors logged but don't crash
    
    Args:
        tenant_id: The tenant to notify
        update: Update payload (e.g., {"event_type": "SHADOW_STATUS_UPDATE", ...})
    """
    if tenant_id not in active_shadow_connections:
        logger.debug(f"[SHADOW_WS] No active connections for tenant {tenant_id}")
        return
    
    # Get snapshot of connections to avoid "dict changed during iteration" errors
    clients = list(active_shadow_connections[tenant_id])
    
    for websocket in clients:
        try:
            await websocket.send_json({
                **update,
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.debug(f"[SHADOW_WS] Broadcast sent to {tenant_id}")
        
        except WebSocketDisconnect:
            # Client disconnected, will be cleaned up on next iteration
            try:
                active_shadow_connections.get(tenant_id, set()).discard(websocket)
            except:
                pass
        
        except Exception as exc:
            logger.error(f"[SHADOW_WS] Error in broadcast to {tenant_id}: {exc}")
            try:
                active_shadow_connections.get(tenant_id, set()).discard(websocket)
            except:
                pass
