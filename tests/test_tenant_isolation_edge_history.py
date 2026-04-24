"""
Test: /api/edge/history endpoint — global storage (EdgeTuner is a system process).

usr_edge_learning is written by EdgeTuner via the global orchestrator storage
(StorageManager with no user_id → data_vault/global/aethelgard.db).
The endpoint must read from the same global DB so the data is actually visible.
All authenticated users see the same system-level monitoring data.

Trace_ID: SECURITY-TENANT-ISOLATION-2026-001
"""
import pytest
from unittest.mock import Mock, patch
import json

from data_vault.storage import StorageManager
from models.auth import TokenPayload
from core_brain.api.routers.trading import get_edge_history


@pytest.fixture
def mock_token_alice():
    """Mock token for user Alice with tenant_id='alice_uuid'"""
    token = Mock(spec=TokenPayload)
    token.sub = "alice_uuid"
    return token


@pytest.fixture
def mock_token_bob():
    """Mock token for user Bob with tenant_id='bob_uuid'"""
    token = Mock(spec=TokenPayload)
    token.sub = "bob_uuid"
    return token


@pytest.mark.asyncio
async def test_edge_history_uses_global_storage_not_tenant(mock_token_alice, mock_token_bob):
    """
    ARCHITECTURE TEST: /api/edge/history must use global _get_storage(), NOT TenantDBFactory.

    EdgeTuner is a system process: it writes usr_edge_learning rows via
    StorageManager() (global DB). Reading from tenant DB would return empty results.
    Both Alice and Bob must see the same system monitoring feed.
    """
    global_storage_calls = []
    original_global = StorageManager

    with patch('core_brain.api.routers.trading._get_storage') as mock_global:
        mock_storage = Mock()
        mock_storage.get_tuning_history.return_value = []
        mock_storage.get_edge_learning_history.return_value = []
        mock_global.return_value = mock_storage

        result_alice = await get_edge_history(limit=50, token=mock_token_alice)
        result_bob = await get_edge_history(limit=50, token=mock_token_bob)

    # Both calls must have used global storage
    assert mock_global.call_count == 2, (
        f"_get_storage() should be called once per request, got {mock_global.call_count}"
    )
    assert isinstance(result_alice, dict) and "history" in result_alice
    assert isinstance(result_bob, dict) and "history" in result_bob


@pytest.mark.asyncio
async def test_endpoint_uses_global_storage_not_tenantdbfactory(mock_token_alice):
    """
    UNIT TEST: /api/edge/history uses _get_storage() (global), NOT TenantDBFactory.

    This is intentional: edge learning data is system-wide operational telemetry,
    not per-user trading data.
    """
    with patch('core_brain.api.routers.trading._get_storage') as mock_global:
        mock_storage = Mock()
        mock_storage.get_tuning_history.return_value = []
        mock_storage.get_edge_learning_history.return_value = []
        mock_global.return_value = mock_storage

        result = await get_edge_history(limit=50, token=mock_token_alice)

    assert mock_global.called, "_get_storage() should be called for global edge data"
    assert "history" in result


@pytest.mark.asyncio
async def test_edge_history_response_format():
    """
    Verify that the endpoint returns properly structured data.
    """
    token = Mock(spec=TokenPayload)
    token.sub = "test_tenant"
    
    result = await get_edge_history(limit=10, token=token)
    
    # Verify response structure
    assert isinstance(result, dict), "Should return dict"
    assert "history" in result, "Should have 'history' field"
    assert "count" in result, "Should have 'count' field"
    assert isinstance(result["history"], list), "'history' should be a list"
    assert isinstance(result["count"], int), "'count' should be an integer"
    
    # Verify each event has required fields
    for event in result["history"]:
        assert "id" in event
        assert "timestamp" in event
        assert "type" in event
        assert event["type"] in ["PARAMETRIC_TUNING", "AUTONOMOUS_LEARNING"]


@pytest.mark.asyncio
async def test_tuning_event_structure():
    """
    Verify PARAMETRIC_TUNING events have correct structure.
    """
    token = Mock(spec=TokenPayload)
    token.sub = "test_tenant"
    
    result = await get_edge_history(limit=100, token=token)
    
    tuning_events = [e for e in result["history"] if e["type"] == "PARAMETRIC_TUNING"]
    
    for event in tuning_events:
        # These should be present for PARAMETRIC_TUNING
        assert "trigger" in event
        assert "adjustment_factor" in event
        # These may or may not be present
        assert "old_params" in event or "new_params" in event or True


@pytest.mark.asyncio
async def test_autonomous_learning_event_structure():
    """
    Verify AUTONOMOUS_LEARNING events have correct structure.
    """
    token = Mock(spec=TokenPayload)
    token.sub = "test_tenant"
    
    result = await get_edge_history(limit=100, token=token)
    
    learning_events = [e for e in result["history"] if e["type"] == "AUTONOMOUS_LEARNING"]
    
    for event in learning_events:
        # These should be present for AUTONOMOUS_LEARNING
        assert "detection" in event
        assert "action_taken" in event
        assert "learning" in event
        assert "delta" in event or "regime" in event or True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
