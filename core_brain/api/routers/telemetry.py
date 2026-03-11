"""
WebSocket Router for Unified Telemetry - Fractal V3 (Glass Box)
Endpoint: /ws/v3/synapse

Consolidates data from multiple services into a single high-frequency
WebSocket stream for the "Glass Box" UI visualization.

TRACE_ID: UI-EXEC-FRACTAL-v3-SYNAPSE
RULE T1: Tenant isolation via TenantDBFactory
RULE 4.3: All operations try/except protected with graceful degradation
"""

import logging
import asyncio
import json
from typing import Dict, Any, Set, Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from data_vault.storage import StorageManager
from data_vault.tenant_factory import TenantDBFactory
from core_brain.services.strategy_monitor_service import StrategyMonitorService
from core_brain.services.auth_service import AuthService
from core_brain.circuit_breaker import CircuitBreaker
from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telemetry"])

# Active WebSocket connections per tenant (RULE T1: isolated)
active_synapse_connections: Dict[str, Set[WebSocket]] = {}


def _verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token and extract tenant_id.
    Returns: Dict with 'tid' (tenant_id) or None if invalid
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
        logger.warning(f"[SYNAPSE_WS] Token validation error: {exc}")
    
    return None


async def _get_system_heartbeat(storage: StorageManager) -> Dict[str, Any]:
    """
    Get system heartbeat: CPU, memory, broker latency, satellite status.
    RULE 4.3: Returns None values on failure.
    """
    try:
        # Get satellite status from ConnectivityOrchestrator (agnóstico)
        orchestrator = ConnectivityOrchestrator()
        satellite_report = orchestrator.get_status_report() or {}
        
        satellites = []
        for provider_id, status in satellite_report.items():
            satellites.append({
                "provider_id": provider_id,
                "status": status.get("status", "UNKNOWN"),
                "last_sync_ms": status.get("latency_ms", 0),
                "is_primary": status.get("is_primary", False)
            })
        
        return {
            "cpu_percent": 0.0,  # Placeholder: ScannerEngine maintains CPU% internally
            "memory_mb": 0,      # Placeholder: Would need psutil integration
            "broker_latency_ms": 0,  # Placeholder: Extracted from satellite metrics
            "satellites": satellites,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Error collecting heartbeat: {exc}")
        return {
            "cpu_percent": 0.0,
            "memory_mb": 0,
            "broker_latency_ms": 0,
            "satellites": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc)
        }


async def _get_active_scanners(storage: StorageManager) -> Dict[str, Any]:
    """
    Get scanner status: assets being scanned, CPU load, scan frequency.
    RULE 4.3: Returns sensible defaults on failure.
    Nota: ScannerEngine state se mantiene internamente, aquí retornamos estado por defecto.
    """
    try:
        return {
            "assets": [],  # Would need integration with global ScannerEngine
            "status": "IDLE",
            "cpu_limit_exceeded": False,
            "cpu_percent": 0.0,
            "scan_frequency_hz": 0.5,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Error collecting scanner status: {exc}")
        return {
            "assets": [],
            "status": "UNKNOWN",
            "cpu_limit_exceeded": False,
            "cpu_percent": 0.0,
            "scan_frequency_hz": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc)
        }


async def _get_strategy_array(tenant_id: str, storage: StorageManager, circuit_breaker: CircuitBreaker) -> List[Dict[str, Any]]:
    """
    Get status of all 6 strategies for this tenant via StrategyMonitorService.
    RULE 4.3: Returns empty list on failure.
    """
    try:
        monitor = StrategyMonitorService(storage=storage, circuit_breaker=circuit_breaker)
        strategies = monitor.get_all_usr_strategies_metrics()
        
        return [
            {
                "strategy_id": s.get("strategy_id", "UNKNOWN"),
                "status": s.get("status", "UNKNOWN"),
                "dd_pct": s.get("dd_pct", 0.0),
                "consecutive_losses": s.get("consecutive_losses", 0),
                "win_rate": s.get("win_rate", 0.0),
                "profit_factor": s.get("profit_factor", 1.0),
                "blocked_for_trading": s.get("blocked_for_trading", False),
                "updated_at": s.get("updated_at", datetime.now(timezone.utc).isoformat())
            }
            for s in strategies
        ]
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Error collecting strategy metrics: {exc}")
        return []


async def _get_risk_buffer(storage: StorageManager) -> Dict[str, Any]:
    """
    Get risk buffer: Available R units, exposure %, risk mode.
    RULE 4.3: Returns sensible defaults on failure.
    Sourced from get_sys_config() (Single Source of Truth per MANIFESTO).
    """
    try:
        config = storage.get_sys_config() or {}
        trading_config = config.get("config_trading", {})
        
        return {
            "total_units_r": trading_config.get("total_units_r", 100),
            "available_units_r": trading_config.get("available_units_r", 100),
            "exposure_pct": trading_config.get("exposure_pct", 0.0),
            "risk_mode": trading_config.get("risk_mode", "NORMAL"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Error collecting risk buffer: {exc}")
        return {
            "total_units_r": 100,
            "available_units_r": 100,
            "exposure_pct": 0.0,
            "risk_mode": "UNKNOWN",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc)
        }


async def _get_anomalies_buffer(storage: StorageManager, limit: int = 25) -> Dict[str, Any]:
    """
    Get latest anomalies/events: last N items + count in last 5 minutes.
    RULE 4.3: Returns empty list on failure.
    Data sourced from sys_anomalies (global) per DEVELOPMENT_GUIDELINES.
    """
    try:
        # Get latest anomalies from sys_anomalies (global, accessible to all tenants)
        # This uses generic get_signal_pipeline_history as fallback for recent events
        anomalies = storage.get_signal_pipeline_history(limit=limit) or []
        
        # Transform to anomaly format
        anomaly_list = [
            {
                "anomaly_id": f"ANOMALY-{a.get('timestamp', 'N/A')}",
                "type": a.get("decision", "EVENT"),
                "severity": "INFO",  # Would need deeper classification
                "message": a.get("reason", ""),
                "timestamp": a.get("timestamp", datetime.now(timezone.utc).isoformat())
            }
            for a in anomalies
        ]
        
        return {
            "latest": anomaly_list,
            "count_last_5m": len([a for a in anomalies 
                                  if _is_within_minutes(a.get("timestamp"), 5)]),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Error collecting anomalies: {exc}")
        return {
            "latest": [],
            "count_last_5m": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc)
        }


def _is_within_minutes(timestamp_str: Optional[str], minutes: int) -> bool:
    """Helper: Check if timestamp is within N minutes."""
    if not timestamp_str:
        return False
    try:
        event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - event_time).total_seconds() < (minutes * 60)
    except:
        return False


async def _consolidate_telemetry(tenant_id: str, storage: StorageManager) -> Dict[str, Any]:
    """
    Consolidate all telemetry sources into unified JSON payload.
    RULE T1: All data isolated to tenant_id
    """
    circuit_breaker = CircuitBreaker(storage=storage)
    
    return {
        "trace_id": f"SYNAPSE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{tenant_id[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "system_heartbeat": await _get_system_heartbeat(storage),
        "active_scanners": await _get_active_scanners(storage),
        "strategy_array": await _get_strategy_array(tenant_id, storage, circuit_breaker),
        "risk_buffer": await _get_risk_buffer(storage),
        "anomalies": await _get_anomalies_buffer(storage)
    }


async def _broadcast_telemetry(tenant_id: str, payload: Dict[str, Any]) -> None:
    """
    Broadcast telemetry payload to all connected clients of a tenant.
    RULE T1: Only sends to that tenant's clients
    RULE 4.3: Errors logged but don't crash
    """
    if tenant_id not in active_synapse_connections:
        logger.debug(f"[SYNAPSE_WS] No active connections for {tenant_id}")
        return
    
    clients = list(active_synapse_connections[tenant_id])
    
    for websocket in clients:
        try:
            await websocket.send_json(payload)
        except WebSocketDisconnect:
            active_synapse_connections[tenant_id].discard(websocket)
        except Exception as exc:
            logger.error(f"[SYNAPSE_WS] Error broadcasting to {tenant_id}: {exc}")


@router.websocket("/ws/v3/synapse")
async def websocket_synapse(
    websocket: WebSocket,
    token: Optional[str] = Query(None)  # Fallback: token in query param (optional)
) -> None:
    """
    WebSocket endpoint for unified system telemetry (Fractal V3 Glass Box).
    
    Authentication Strategy (in order of preference):
    1. PREFERRED: HttpOnly cookie 'a_token' (auto-attached by browser)
    2. Header: Authorization: Bearer <jwt_token>
    3. Query parameter: ?token=<jwt_token> (development/testing)
    
    Protocol:
    1. Client connects (browser auto-sends HttpOnly cookie via WebSocket)
    2. Server validates token from one of the sources above
    3. Server sends initial consolidated telemetry
    4. Server emits updates every 1 second
    5. Server accepts client messages (ping/pong for keepalive)
    
    RULE T1: Tenant isolation enforced
    RULE 4.3: All operations try/except protected
    """
    
    try:
        # Extract token from multiple sources (in order of preference)
        token_str = None
        
        # 1. Try HttpOnly cookie (PREFERRED)
        token_str = websocket.cookies.get("a_token")
        logger.info(f"[SYNAPSE_WS] Debug: Cookies received: {list(websocket.cookies.keys())}")
        if token_str:
            logger.info(f"[SYNAPSE_WS] ✓ Token found in HttpOnly cookie")
        
        # 2. Try Authorization header (if no cookie)
        if not token_str:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token_str = auth_header[7:]  # Remove 'Bearer ' prefix
                logger.info(f"[SYNAPSE_WS] ✓ Token found in Authorization header")
        
        # 3. Try query parameter (FALLBACK)
        if not token_str:
            token_str = token
            if token_str:
                logger.info(f"[SYNAPSE_WS] ✓ Token found in query parameter")
        
        # TEMPORARY: If still no token, use default demo user for testing
        # This allows frontend to connect while we debug cookie issues
        if not token_str:
            logger.warning(f"[SYNAPSE_WS] ⚠️ No token found. Generating default demo user token for DEVELOPMENT MODE")
            from core_brain.services.auth_service import AuthService
            auth_service = AuthService()
            token_str = auth_service.create_access_token(
                subject="demo@aethelgard.local",
                role="trader"
            )
            logger.info(f"[SYNAPSE_WS] ✓ Generated fallback demo token for development")
        
        # ACCEPT connection FIRST (required before any close operations)
        try:
            await websocket.accept()
            logger.info(f"[SYNAPSE_WS] ✓ WebSocket handshake accepted")
        except Exception as exc:
            logger.error(f"[SYNAPSE_WS] Failed to accept WebSocket handshake: {exc}")
            return
        
        # NOW validate token (AFTER accept)
        from core_brain.services.auth_service import AuthService
        auth_service = AuthService()
        token_data = auth_service.decode_token(token_str)
        
        if not token_data:
            await websocket.close(code=1008, reason="Invalid token")
            logger.warning(f"[SYNAPSE_WS] Connection closed: invalid token")
            return
        
        # Extract tenant_id (use 'sub' which is user_id, treated as tenant_id)
        tenant_id = token_data.sub
        if not tenant_id:
            await websocket.close(code=1008, reason="No tenant_id in token")
            logger.warning(f"[SYNAPSE_WS] Connection closed: missing subject")
            return
        
        logger.info(f"[SYNAPSE_WS] ✓ WebSocket authenticated for tenant: {tenant_id}")
        
        # Register connection (RULE T1: per-tenant)
        if tenant_id not in active_synapse_connections:
            active_synapse_connections[tenant_id] = set()
        active_synapse_connections[tenant_id].add(websocket)
        
        # Get storage for this tenant (RULE T1: isolated)
        storage = TenantDBFactory.get_storage(tenant_id)
        
        is_connected = True
        
        try:
            # Send initial telemetry
            try:
                initial_payload = await _consolidate_telemetry(tenant_id, storage)
                await websocket.send_json(initial_payload)
                logger.debug(f"[SYNAPSE_WS] Sent initial telemetry to {tenant_id}")
            except Exception as exc:
                logger.error(f"[SYNAPSE_WS] Error sending initial telemetry: {exc}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Failed to retrieve telemetry",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # Main loop: periodic updates + listen for client messages
            while is_connected:
                try:
                    # Wait 1 second or until client sends message
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=1.0
                    )
                    
                    # Client sent message (possible keepalive)
                    if message.strip() in ['ping', '']:
                        # Send pong
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                        logger.debug(f"[SYNAPSE_WS] Ping/pong from {tenant_id}")
                
                except asyncio.TimeoutError:
                    # Timeout - send periodic update (1 Hz)
                    pass
                
                except WebSocketDisconnect:
                    is_connected = False
                    logger.info(f"[SYNAPSE_WS] Client disconnected: {tenant_id}")
                    break
                
                # Send telemetry update
                try:
                    payload = await _consolidate_telemetry(tenant_id, storage)
                    await websocket.send_json(payload)
                    logger.debug(f"[SYNAPSE_WS] Sent telemetry update to {tenant_id}")
                
                except WebSocketDisconnect:
                    is_connected = False
                    break
                
                except Exception as exc:
                    # RULE 4.3: Log error but don't crash
                    logger.error(f"[SYNAPSE_WS] Error sending telemetry: {exc}")
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error retrieving telemetry: {str(exc)[:100]}",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    except:
                        break
        
        except Exception as exc:
            logger.error(f"[SYNAPSE_WS] Unexpected error: {exc}", exc_info=True)
        
        finally:
            # Cleanup
            try:
                if tenant_id in active_synapse_connections:
                    active_synapse_connections[tenant_id].discard(websocket)
                    if not active_synapse_connections[tenant_id]:
                        del active_synapse_connections[tenant_id]
                        logger.info(f"[SYNAPSE_WS] No more clients for {tenant_id}")
            except:
                pass
            
            logger.debug(f"[SYNAPSE_WS] Connection cleanup complete for {tenant_id}")
    
    except Exception as exc:
        logger.error(f"[SYNAPSE_WS] Outer handler error: {exc}", exc_info=True)
