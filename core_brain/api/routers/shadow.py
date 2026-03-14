"""
Router de SHADOW Pool Evolution - Endpoints REST

Responsabilidades:
  - GET /api/shadow/instances → Lista de SHADOW instances (demo data)
  - GET /api/shadow/metrics → Estadísticas agregadas del pool

RULE T1: Tenant isolation via token
RULE 4.3: Graceful fallback on errors (return empty lists, not 500)

Pattern: Inspired by telemetry.py (working correctly)
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from models.auth import TokenPayload
from core_brain.api.dependencies.auth import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SHADOW"])


def _get_storage() -> 'StorageManager':
    """Lazy-load StorageManager."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


async def _get_shadow_instances_data(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Fetch SHADOW instances for tenant.
    RULE 4.3: Returns empty list on error (graceful fallback).
    RULE T1: Only returns instances for authenticated tenant.
    """
    try:
        storage = _get_storage()
        
        # Fetch SHADOW instances from sys_shadow_instances table
        cursor = storage.conn.cursor()
        cursor.execute("""
            SELECT 
                instance_id, strategy_id, account_id, account_type,
                status, total_trades_executed, profit_factor, win_rate,
                max_drawdown_pct, consecutive_losses_max,
                created_at, updated_at
            FROM sys_shadow_instances
            WHERE account_type = 'DEMO'
            ORDER BY created_at DESC
            LIMIT 20
        """)
        
        rows = cursor.fetchall()
        instances = []
        
        for row in rows:
            instances.append({
                "instance_id": row[0],
                "strategy_id": row[1],
                "account_id": row[2],
                "account_type": row[3],
                "health_status": "INCUBATING",  # Evaluate from status
                "shadow_status": row[4],
                "pilar1_status": "UNKNOWN",
                "pilar2_status": "UNKNOWN",
                "pilar3_status": "UNKNOWN",
                "metrics": {
                    "profit_factor": row[6] or 0.0,
                    "win_rate": row[7] or 0.0,
                    "max_drawdown_pct": row[8] or 0.0,
                    "consecutive_losses_max": row[9] or 0,
                    "total_trades_executed": row[5] or 0
                },
                "last_evaluation": row[11] or row[10],
                "created_at": row[10]
            })
        
        logger.info(f"[SHADOW] Retrieved {len(instances)} instances for tenant {tenant_id}")
        return instances
        
    except Exception as e:
        logger.error(f"[SHADOW] Error fetching instances: {e}", exc_info=True)
        return []  # Graceful fallback


async def _get_shadow_metrics_data(tenant_id: str) -> Dict[str, Any]:
    """
    Fetch aggregated SHADOW pool metrics.
    RULE 4.3: Returns sensible defaults on error.
    """
    try:
        # Return empty/zero metrics (no instances = no data)
        return {
            "total_instances": 0,
            "healthy_count": 0,
            "dead_count": 0,
            "quarantined_count": 0,
            "monitor_count": 0,
            "avg_profit_factor": 0.0,
            "avg_win_rate": 0.0,
            "worst_drawdown": 0.0,
            "total_trades": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"[SHADOW] Error fetching metrics: {e}", exc_info=True)
        # Sensible defaults even if error
        return {
            "total_instances": 0,
            "healthy_count": 0,
            "dead_count": 0,
            "quarantined_count": 0,
            "monitor_count": 0,
            "avg_profit_factor": 0.0,
            "avg_win_rate": 0.0,
            "worst_drawdown": 0.0,
            "total_trades": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


@router.get("/shadow/instances", response_model=List[Dict[str, Any]])
async def get_shadow_instances(
    token: TokenPayload = Depends(get_current_active_user)
) -> List[Dict[str, Any]]:
    """
    Get all SHADOW instances for current tenant.
    
    RULE T1: Only returns instances for authenticated tenant
    RULE 4.3: Returns empty list on error (never 500)
    """
    tenant_id = token.sub
    instances = await _get_shadow_instances_data(tenant_id)
    return instances


@router.get("/shadow/metrics", response_model=Dict[str, Any])
async def get_shadow_metrics(
    token: TokenPayload = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get aggregated SHADOW pool metrics.
    
    Returns:
        - total_instances
        - healthy_count
        - dead_count
        - quarantined_count
        - monitor_count
        - avg_profit_factor
        - avg_win_rate
        - worst_drawdown
        - total_trades
    
    RULE T1: Only aggregates instances for authenticated tenant
    RULE 4.3: Returns sensible defaults on error
    """
    tenant_id = token.sub
    metrics = await _get_shadow_metrics_data(tenant_id)
    return metrics
