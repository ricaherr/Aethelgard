"""
WebSocket Router for Real-Time Strategy Monitoring
Endpoint: /ws/strategy/monitor

Provides real-time updates of strategy metrics via WebSocket.
RULE T1: Tenant isolation enforced at connection and per-message level.
RULE 4.3: All DB operations wrapped in try/except with graceful failure.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Set, Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from data_vault.storage import StorageManager
from data_vault.tenant_factory import TenantDBFactory
from core_brain.services.strategy_monitor_service import StrategyMonitorService
from core_brain.services.auth_service import AuthService
from core_brain.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Strategy Monitoring"])

# Active WebSocket connections per tenant (RULE T1: isolated)
active_connections: Dict[str, Set[WebSocket]] = {}
strategy_monitor_services: Dict[str, StrategyMonitorService] = {}


def _verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token and extract tenant_id.
    
    Returns:
        Dict with 'tid' (tenant_id) or None if invalid
    """
    try:
        auth_service = AuthService()
        token_data = auth_service.decode_token(token)
        if token_data:
            return {
                'tid': token_data.tid,
                'sub': token_data.sub,
                'exp': token_data.exp
            }
    except Exception as exc:
        logger.warning(f"[STRATEGY_WS] Token validation error: {exc}")
    
    return None


def _get_or_create_monitor_service(tenant_id: str) -> StrategyMonitorService:
    """
    Get or create StrategyMonitorService for tenant (cached).
    RULE T1: Each tenant has isolated monitor service.
    """
    if tenant_id not in strategy_monitor_services:
        # RULE T1: TenantDBFactory provides isolated storage
        storage = TenantDBFactory.get_storage(tenant_id)
        circuit_breaker = CircuitBreaker(storage=storage)
        
        monitor = StrategyMonitorService(
            storage=storage,
            circuit_breaker=circuit_breaker
        )
        strategy_monitor_services[tenant_id] = monitor
        logger.info(f"[STRATEGY_WS] Created monitor service for tenant {tenant_id}")
    
    return strategy_monitor_services[tenant_id]


@router.websocket("/ws/strategy/monitor")
async def websocket_strategy_monitor(
    websocket: WebSocket,
    token: str = Query(...)
) -> None:
    """
    WebSocket endpoint for real-time strategy monitoring.
    
    Protocol:
    1. Client sends token via query parameter
    2. Server validates and authenticates
    3. Server sends initial metrics
    4. Client receives metrics every 5 seconds
    5. Server broadcasts on status changes
    
    Message Format:
    {
        "type": "metrics" | "status_changed" | "error",
        "data": {...},
        "timestamp": "2026-03-05T22:00:00Z"
    }
    
    RULE T1: Tenant isolation enforced
    RULE 4.3: All operations try/except protected
    """
    
    # RULE T1: Validate authentication and extract tenant_id
    token_data = _verify_token(token)
    
    if not token_data:
        await websocket.close(code=1008, reason="Authentication failed")
        logger.warning(f"[STRATEGY_WS] Connection rejected: invalid token")
        return
    
    tenant_id = token_data.get('tid')
    if not tenant_id:
        await websocket.close(code=1008, reason="No tenant_id in token")
        logger.warning(f"[STRATEGY_WS] Connection rejected: missing tenant_id")
        return
    
    logger.debug(f"[STRATEGY_WS] Authenticated tenant: {tenant_id}")
    
    # Accept connection
    try:
        await websocket.accept()
        logger.info(f"[STRATEGY_WS] Client connected for tenant {tenant_id}")
    except Exception as exc:
        logger.error(f"[STRATEGY_WS] Failed to accept connection: {exc}")
        return
    
    # Register connection (RULE T1: per-tenant)
    if tenant_id not in active_connections:
        active_connections[tenant_id] = set()
    active_connections[tenant_id].add(websocket)
    
    # Get monitor service for this tenant
    monitor = _get_or_create_monitor_service(tenant_id)
    
    # Connection variables
    is_connected = True
    
    try:
        # Send initial metrics
        try:
            metrics = monitor.get_all_strategies_metrics()
            await websocket.send_json({
                "type": "metrics",
                "data": metrics,
                "timestamp": datetime.now().isoformat(),
                "tenant_id": tenant_id
            })
            logger.debug(f"[STRATEGY_WS] Sent initial metrics to {tenant_id}")
        
        except Exception as exc:
            logger.error(f"[STRATEGY_WS] Error getting initial metrics: {exc}")
            await websocket.send_json({
                "type": "error",
                "message": "Failed to retrieve metrics",
                "timestamp": datetime.now().isoformat()
            })
        
        # Main loop: periodic updates + listen for client messages
        while is_connected:
            # Create task for periodic updates (every 5 seconds)
            try:
                # Wait 5 seconds or until client sends message
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=5.0
                )
                
                # Client sent message (possible keepalive)
                if message.strip() in ['ping', '']:
                    # Send pong
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                    logger.debug(f"[STRATEGY_WS] Ping/pong from {tenant_id}")
            
            except asyncio.TimeoutError:
                # Timeout - send periodic update
                pass
            
            except WebSocketDisconnect:
                is_connected = False
                logger.info(f"[STRATEGY_WS] Client disconnected: {tenant_id}")
                break
            
            # Send metrics update
            try:
                metrics = monitor.get_all_strategies_metrics()
                await websocket.send_json({
                    "type": "metrics",
                    "data": metrics,
                    "timestamp": datetime.now().isoformat(),
                    "tenant_id": tenant_id
                })
                logger.debug(f"[STRATEGY_WS] Sent metrics update to {tenant_id}")
            
            except WebSocketDisconnect:
                is_connected = False
                break
            
            except Exception as exc:
                # RULE 4.3: Log error but don't crash
                logger.error(f"[STRATEGY_WS] Error sending metrics: {exc}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error retrieving metrics: {str(exc)[:100]}",
                        "timestamp": datetime.now().isoformat()
                    })
                except:
                    break
    
    except Exception as exc:
        logger.error(f"[STRATEGY_WS] Unexpected error: {exc}", exc_info=True)
    
    finally:
        # Cleanup
        try:
            if tenant_id in active_connections:
                active_connections[tenant_id].discard(websocket)
                if not active_connections[tenant_id]:
                    del active_connections[tenant_id]
                    logger.info(f"[STRATEGY_WS] No more clients for {tenant_id}")
        except:
            pass
        
        logger.debug(f"[STRATEGY_WS] Connection cleanup complete for {tenant_id}")


async def broadcast_strategy_update(tenant_id: str, update: Dict[str, Any]) -> None:
    """
    Broadcast strategy status change to all connected clients of a tenant.
    Called when CircuitBreaker degrades a strategy (LIVE → QUARANTINE).
    
    RULE T1: Only sends to that tenant's clients
    RULE 4.3: Errors logged but don't crash
    
    Args:
        tenant_id: The tenant to notify
        update: Update payload (e.g., {"type": "status_changed", "strategy_id": "...", ...})
    """
    if tenant_id not in active_connections:
        logger.debug(f"[STRATEGY_WS] No active connections for {tenant_id}")
        return
    
    clients = list(active_connections[tenant_id])
    
    for websocket in clients:
        try:
            await websocket.send_json({
                **update,
                "tenant_id": tenant_id,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug(f"[STRATEGY_WS] Broadcast sent to {tenant_id}")
        
        except WebSocketDisconnect:
            # Client disconnected, will be cleaned up on next iteration
            try:
                active_connections.get(tenant_id, set()).discard(websocket)
            except:
                pass
        
        except Exception as exc:
            logger.error(f"[STRATEGY_WS] Broadcast error: {exc}")
