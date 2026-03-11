"""
Test para WebSocket /ws/v3/synapse (Telemetry Router)
Validación básica de estructura y autenticación.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_synapse_websocket_authentication_required():
    """Test que /ws/v3/synapse rechaza sin token."""
    # Este test requeriría un cliente WebSocket real
    # Por ahora usamos mock para demostrar la estructura
    from core_brain.api.routers.telemetry import _verify_token
    
    # Token inválido retorna None
    result = _verify_token("invalid_token")
    assert result is None


@pytest.mark.asyncio
async def test_synapse_consolidate_telemetry():
    """Test consolidación de telemetría."""
    from core_brain.api.routers.telemetry import _consolidate_telemetry
    from core_brain.circuit_breaker import CircuitBreaker
    
    # Mock storage
    mock_storage = MagicMock()
    mock_storage.get_sys_config.return_value = {
        "config_trading": {
            "total_units_r": 100,
            "available_units_r": 80,
            "exposure_pct": 0.2,
            "risk_mode": "NORMAL"
        }
    }
    mock_storage.get_signal_pipeline_history.return_value = []
    
    # Test consolidación
    tenant_id = "tenant-123"
    payload = await _consolidate_telemetry(tenant_id, mock_storage)
    
    # Validaciones
    assert "trace_id" in payload
    assert "timestamp" in payload
    assert payload["tenant_id"] == tenant_id
    assert "system_heartbeat" in payload
    assert "active_scanners" in payload
    assert "strategy_array" in payload
    assert "risk_buffer" in payload
    assert "anomalies" in payload


@pytest.mark.asyncio
async def test_synapse_error_resilience():
    """Test que los errores no cierran el WebSocket."""
    from core_brain.api.routers.telemetry import _consolidate_telemetry
    
    # Mock storage que lanza errores
    mock_storage = MagicMock()
    mock_storage.get_sys_config.side_effect = Exception("DB error")
    mock_storage.get_signal_pipeline_history.side_effect = Exception("DB error")
    
    # Debe retornar estructura graceful pesar de errores
    tenant_id = "tenant-123"
    payload = await _consolidate_telemetry(tenant_id, mock_storage)
    
    # Verificar que payload sigue siendo válido
    assert payload is not None
    assert "trace_id" in payload
    assert isinstance(payload, dict)


def test_is_within_minutes():
    """Test helper para chequeo de tiempo."""
    from core_brain.api.routers.telemetry import _is_within_minutes
    from datetime import datetime, timezone, timedelta
    
    # Timestamp reciente (ahora)
    now = datetime.now(timezone.utc).isoformat()
    assert _is_within_minutes(now, 5) is True
    
    # Timestamp antiguo (hace 10 min)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    assert _is_within_minutes(old, 5) is False
    
    # String inválido
    assert _is_within_minutes("invalid", 5) is False
    assert _is_within_minutes(None, 5) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
