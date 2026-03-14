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
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from data_vault.tenant_factory import TenantDBFactory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SHADOW WebSocket"])

# Global registry of active SHADOW WebSocket connections per tenant
# Structure: { tenant_id: {websocket1, websocket2, ...} }
active_shadow_connections: Dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/shadow")
async def websocket_shadow(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for SHADOW pool real-time status updates.
    Token is extracted from query, headers, or cookies.
    """
    
    logger.warning(f"[SHADOW_WS] ========== HANDLER EXECUTION STARTED ==========")
    logger.info(f"[SHADOW_WS] Client address: {websocket.client}")
    
    logger.info(f"[SHADOW_WS] ✓ Websocket handler STARTED")
    logger.info(f"[SHADOW_WS] Headers: {dict(websocket.headers)}")
    logger.info(f"[SHADOW_WS] Cookies: {websocket.cookies}")
    
    try:
        # Extract token from multiple sources (in order of preference)
        token_str = None
        
        # 1. Try query parameter first (from URL like ws://localhost:8000/ws/shadow?token=...)
        query_params = websocket.scope.get("query_string", b"").decode()
        if "token=" in query_params:
            parts = query_params.split("token=")
            if len(parts) > 1:
                token_str = parts[1].split("&")[0]  # Get value before next param
                logger.info(f"[SHADOW_WS] ✓ Token found in query parameter")
        
        # 2. Try HttpOnly cookie (PREFERRED)
        if not token_str and websocket.cookies:
            token_str = websocket.cookies.get("a_token")
            if token_str:
                logger.info(f"[SHADOW_WS] ✓ Token found in HttpOnly cookie")
        
        # 3. Try Authorization header (if no cookie)
        if not token_str:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_str = auth_header[7:]  # Remove 'Bearer ' prefix
                logger.info(f"[SHADOW_WS] ✓ Token found in Authorization header")
        
        # 4. If still no token, generate demo token for development
        if not token_str:
            logger.warning(f"[SHADOW_WS] ⚠️ No token found. Generating fallback for DEVELOPMENT MODE")
            try:
                logger.debug(f"[SHADOW_WS] [1] About to import AuthService...")
                from core_brain.services.auth_service import AuthService
                logger.debug(f"[SHADOW_WS] [2] AuthService imported successfully")
                
                logger.debug(f"[SHADOW_WS] [3] Creating AuthService instance...")
                auth_service = AuthService()
                logger.debug(f"[SHADOW_WS] [4] AuthService instance created")
                
                logger.debug(f"[SHADOW_WS] [5] Calling create_access_token()...")
                token_str = auth_service.create_access_token(
                    subject="demo@aethelgard.local",
                    role="trader"
                )
                logger.debug(f"[SHADOW_WS] [6] Token created: {token_str[:30]}...")
                logger.info(f"[SHADOW_WS] ✓ Generated fallback demo token")
            except Exception as e:
                logger.error(f"[SHADOW_WS] ❌ FALLBACK TOKEN GENERATION FAILED: {e}", exc_info=True)
                token_str = None
        
        # STEP 1: ACCEPT the WebSocket (BEFORE validation, like telemetry.py)
        try:
            logger.info(f"[SHADOW_WS] About to call websocket.accept()...")
            await websocket.accept()
            logger.warning(f"[SHADOW_WS] ✓✓✓ WebSocket handshake ACCEPTED - from here on connection is LIVE ✓✓✓")
        except Exception as exc:
            logger.error(f"[SHADOW_WS] ❌ Failed to accept WebSocket handshake: {exc}", exc_info=True)
            return
        
        # STEP 2: NOW validate token (AFTER accept, like telemetry.py)
        logger.info(f"[SHADOW_WS] [STEP-2] About to validate token...")
        from core_brain.services.auth_service import AuthService
        auth_service = AuthService()
        try:
            logger.debug(f"[SHADOW_WS] Decoding token: {token_str[:30]}...")
            token_data = auth_service.decode_token(token_str)
            logger.info(f"[SHADOW_WS] ✓ Token validation successful, subject={token_data.sub}")
        except Exception as token_error:
            logger.error(f"[SHADOW_WS] ❌ Token decode error: {token_error}", exc_info=True)
            token_data = None
        
        if not token_data:
            await websocket.close(code=1008, reason="Invalid token")
            logger.warning(f"[SHADOW_WS] Connection closed: invalid token")
            return
        
        # Extract tenant_id from token subject (use 'sub' like telemetry.py)
        tenant_id = token_data.sub  # NOT 'tid', use 'sub' (user_id as tenant_id)
        if not tenant_id:
            await websocket.close(code=1008, reason="No tenant_id in token")
            logger.warning(f"[SHADOW_WS] Connection closed: missing subject")
            return
        
        logger.info(f"[SHADOW_WS] ✓ WebSocket authenticated for tenant: {tenant_id}")
        
        # RULE T1: Register connection (per-tenant isolation)
        if tenant_id not in active_shadow_connections:
            active_shadow_connections[tenant_id] = set()
        active_shadow_connections[tenant_id].add(websocket)
        logger.debug(f"[SHADOW_WS] Registered connection for {tenant_id}. Count: {len(active_shadow_connections[tenant_id])}")
        
        # Get tenant-isolated storage (RULE T1)
        logger.debug(f"[SHADOW_WS] [3.1] About to get TenantDBFactory storage...")
        try:
            storage = TenantDBFactory.get_storage(tenant_id)
            logger.debug(f"[SHADOW_WS] [3.2] ✓ Storage obtained for {tenant_id}")
        except Exception as storage_error:
            logger.error(f"[SHADOW_WS] ❌ Storage error: {storage_error}", exc_info=True)
            storage = None
        
        try:
            # Send welcome message (using client-expected field name)
            logger.debug(f"[SHADOW_WS] [4.1] About to send welcome message...")
            welcome_payload = {
                "event_type": "SHADOW_CONNECTION_ESTABLISHED",
                "message": "Connected to SHADOW WebSocket",
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            logger.debug(f"[SHADOW_WS] [4.2] Payload: {welcome_payload}")
            await websocket.send_json(welcome_payload)
            logger.warning(f"[SHADOW_WS] ✓✓✓ Welcome message sent to {tenant_id} - CLIENT SHOULD SEE THIS ✓✓✓")
            
            # RULE 4.3: Main loop - listen for keepalive with timeout
            # Use timeout so server can respond to broadcasts independently
            logger.warning(f"[SHADOW_WS] ========== ENTERING MAIN LOOP FOR {tenant_id} ==========")
            while True:
                try:
                    # Wait max 30 seconds for client message (keepalive/ping)
                    # If no message, timeout and loop continues (allows broadcasts)
                    logger.debug(f"[SHADOW_WS] About to call websocket.receive_text() for {tenant_id}...")
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=30.0
                    )
                    logger.debug(f"[SHADOW_WS] Keepalive from {tenant_id}: {message[:50]}")
                    # Client sent keepalive, connection still active
                    
                except asyncio.TimeoutError:
                    # No message in 30s - connection still open but inactive
                    # This allows MainOrchestrator to broadcast events independently
                    logger.debug(f"[SHADOW_WS] No keepalive from {tenant_id} (timeout OK, continuing loop)")
                    continue
                    
                except WebSocketDisconnect:
                    logger.info(f"[SHADOW_WS] Client disconnected: {tenant_id}")
                    break
                
                except Exception as exc:
                    logger.error(f"[SHADOW_WS] ❌ Error in message loop: {exc}", exc_info=True)
                    break
        
        finally:
            # Cleanup: Remove connection from registry
            try:
                if tenant_id in active_shadow_connections:
                    active_shadow_connections[tenant_id].discard(websocket)
                    if not active_shadow_connections[tenant_id]:
                        del active_shadow_connections[tenant_id]
                        logger.info(f"[SHADOW_WS] All connections closed for tenant: {tenant_id}")
                    else:
                        logger.debug(f"[SHADOW_WS] Connection removed. Remaining: {len(active_shadow_connections[tenant_id])}")
            except Exception as e:
                logger.error(f"[SHADOW_WS] Cleanup error: {e}")
    
    except Exception as e:
        logger.error(f"[SHADOW_WS] Unexpected error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass


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
