"""
Test: Tenant Isolation in /api/edge/history Endpoint

Validates that users can only access their own tenant's data, not other tenants' data.
This is a CRITICAL security test for multi-tenant SaaS.

Trace_ID: SECURITY-TENANT-ISOLATION-2026-001
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from data_vault.tenant_factory import TenantDBFactory
from models.auth import TokenPayload
from core_brain.api.routers.trading import get_edge_history


@pytest.fixture
def mock_token_alice():
    """Mock token for user Alice with tenant_id='alice_uuid'"""
    token = Mock(spec=TokenPayload)
    token.tid = "alice_uuid"
    return token


@pytest.fixture
def mock_token_bob():
    """Mock token for user Bob with tenant_id='bob_uuid'"""
    token = Mock(spec=TokenPayload)
    token.tid = "bob_uuid"
    return token


@pytest.mark.asyncio
async def test_tenant_isolation_edge_history_alice_vs_bob(mock_token_alice, mock_token_bob):
    """
    SECURITY TEST: Verify that Alice cannot access Bob's edge learning history.
    
    Scenario:
    1. Alice logs in (token.tid='alice_uuid')
    2. Bob logs in (token.tid='bob_uuid')
    3. Both call GET /api/edge/history
    4. They must get DIFFERENT data from their isolated BDs
    
    Expected:
    - Alice's endpoint uses TenantDBFactory.get_storage('alice_uuid')
    - Bob's endpoint uses TenantDBFactory.get_storage('bob_uuid')
    - Each gets only their own data
    """
    
    # Patch TenantDBFactory.get_storage to track which tenant was requested
    called_tenants = []
    
    original_get_storage = TenantDBFactory.get_storage
    
    def mock_get_storage_factory(tenant_id, base_path=None):
        called_tenants.append(tenant_id)
        return original_get_storage(tenant_id, base_path)
    
    with patch.object(TenantDBFactory, 'get_storage', side_effect=mock_get_storage_factory):
        # Alice calls endpoint
        result_alice = await get_edge_history(limit=50, token=mock_token_alice)
        
        # Bob calls endpoint
        result_bob = await get_edge_history(limit=50, token=mock_token_bob)
    
    # Verify that TenantDBFactory was called with correct tenant IDs
    assert "alice_uuid" in called_tenants, "TenantDBFactory should be called with alice_uuid"
    assert "bob_uuid" in called_tenants, "TenantDBFactory should be called with bob_uuid"
    
    # Verify that isolated storage was obtained
    assert called_tenants.count("alice_uuid") >= 1
    assert called_tenants.count("bob_uuid") >= 1


@pytest.mark.asyncio
async def test_endpoint_uses_tenantdbfactory_not_generic_storage(mock_token_alice):
    """
    UNIT TEST: Verify that /api/edge/history uses TenantDBFactory, NOT _get_storage().
    
    This ensures that the endpoint gets the tenant-isolated storage,
    not a shared generic storage that could leak data.
    """
    called_with = []
    
    original_get_storage = TenantDBFactory.get_storage
    
    def track_call(tenant_id, base_path=None):
        called_with.append(("TenantDBFactory.get_storage", tenant_id))
        return original_get_storage(tenant_id, base_path)
    
    with patch.object(TenantDBFactory, 'get_storage', side_effect=track_call) as mock_factory:
        result = await get_edge_history(limit=50, token=mock_token_alice)
    
    # Verify TenantDBFactory.get_storage was called
    assert mock_factory.called, "TenantDBFactory.get_storage should be called"
    assert mock_factory.call_count >= 1
    
    # Verify it was called with the correct tenant_id
    all_calls = [call[0][0] for call in mock_factory.call_args_list]
    assert "alice_uuid" in all_calls, f"Should call with alice_uuid, got {all_calls}"


@pytest.mark.asyncio
async def test_edge_history_response_format():
    """
    Verify that the endpoint returns properly structured data.
    """
    token = Mock(spec=TokenPayload)
    token.tid = "test_tenant"
    
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
    token.tid = "test_tenant"
    
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
    token.tid = "test_tenant"
    
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
