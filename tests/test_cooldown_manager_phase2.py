"""
test_cooldown_manager_phase2.py — Integration tests for Cooldown Manager (PHASE 2)

Coverage:
  - Cooldown application with escalation
  - Volatility-based adjustments
  - Failure reason classification
  - Persistence to storage
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add path for imports
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from core_brain.cooldown_manager import CooldownManager, ExecutionFailureReason


class TestCooldownManagerPhase2:
    """PHASE 2: Cooldown Manager integration tests."""

    @pytest.fixture
    def mock_storage(self):
        """Mock StorageManager with required methods."""
        storage = AsyncMock()
        storage.get_active_cooldown = AsyncMock(return_value=None)
        storage.register_cooldown = MagicMock()  # sync method (no await)
        storage.log_cooldown_event = AsyncMock()
        return storage

    @pytest.fixture
    def manager(self, mock_storage):
        """Create CooldownManager instance."""
        return CooldownManager(storage_manager=mock_storage)


    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Basic Cooldown Application
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_apply_cooldown_liquidity_failure(self, manager, mock_storage):
        """Test: LIQUIDITY failure triggers cooldown."""
        market_context = {"volatility_zscore": 0.5, "regime": "TRENDING"}
        
        result = await manager.apply_cooldown(
            signal_id="SIG-001",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=market_context
        )
        
        assert result["cooldown_minutes"] > 0
        assert result["cooldown_expires"] is not None
        assert result["retry_count"] == 1
        assert mock_storage.register_cooldown.called

    @pytest.mark.asyncio
    async def test_apply_cooldown_timeout_failure(self, manager, mock_storage):
        """Test: TIMEOUT failure triggers cooldown."""
        market_context = {"volatility_zscore": 0.3, "regime": "TRENDING"}
        
        result = await manager.apply_cooldown(
            signal_id="SIG-002",
            symbol="GBPUSD",
            strategy="Strategy2",
            failure_reason="TIMEOUT",
            market_context=market_context
        )
        
        assert result["cooldown_minutes"] > 0
        assert mock_storage.register_cooldown.called

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Escalation
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_escalation_on_retry(self, manager, mock_storage):
        """Test: Second failure escalates cooldown."""
        # First failure
        mock_storage.get_active_cooldown.return_value = None
        market_context = {"volatility_zscore": 0.5, "regime": "TRENDING"}
        
        result1 = await manager.apply_cooldown(
            signal_id="SIG-003",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=market_context
        )
        
        cooldown_1 = result1["cooldown_minutes"]
        
        # Simulate retry counter
        mock_storage.get_active_cooldown.return_value = {
            "retry_count": 1,
            "failure_reason": "LIQUIDITY_INSUFFICIENT"
        }
        
        result2 = await manager.apply_cooldown(
            signal_id="SIG-003",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=market_context
        )
        
        cooldown_2 = result2["cooldown_minutes"]
        
        # Second failure should escalate (longer cooldown)
        assert result2["retry_count"] == 2
        assert cooldown_2 > cooldown_1

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Volatility Adjustment
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_volatility_adjustment_calm(self, manager, mock_storage):
        """Test: Calm market reduces cooldown."""
        mock_storage.get_active_cooldown.return_value = None
        
        # Calm market
        calm_context = {"volatility_zscore": 0.3, "regime": "TRENDING"}
        result_calm = await manager.apply_cooldown(
            signal_id="SIG-004",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=calm_context
        )
        
        calm_cooldown = result_calm["cooldown_minutes"]
        
        # Volatile market
        volatile_context = {"volatility_zscore": 2.5, "regime": "VOLATILE"}
        result_volatile = await manager.apply_cooldown(
            signal_id="SIG-005",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=volatile_context
        )
        
        volatile_cooldown = result_volatile["cooldown_minutes"]
        
        # Volatile should have longer cooldown
        assert volatile_cooldown > calm_cooldown

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Failure Reason Mapping
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_different_failure_reasons_different_cooldowns(self,  manager, mock_storage):
        """Test: Different failures have different base cooldowns."""
        mock_storage.get_active_cooldown.return_value = None
        market_context = {"volatility_zscore": 0.5, "regime": "TRENDING"}
        
        # LIQUIDITY failure (short cooldown)
        result_liq = await manager.apply_cooldown(
            signal_id="SIG-006",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            market_context=market_context
        )
        
        # CONNECTION failure (longer cooldown)
        result_conn = await manager.apply_cooldown(
            signal_id="SIG-007",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="BROKER_CONNECTION_ERROR",
            market_context=market_context
        )
        
        # Different failures should have different cooldowns
        assert result_liq["cooldown_minutes"] != result_conn["cooldown_minutes"]
        # CONNECTION errors should be longer
        assert result_conn["cooldown_minutes"] > result_liq["cooldown_minutes"]

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Persistence
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cooldown_persists_to_storage(self, manager, mock_storage):
        """Test: Cooldown is registered in storage."""
        mock_storage.get_active_cooldown.return_value = None
        market_context = {"volatility_zscore": 0.5, "regime": "TRENDING"}
        
        await manager.apply_cooldown(
            signal_id="SIG-008",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="SLIPPAGE_EXCEEDED",
            market_context=market_context
        )
        
        # Verify storage.register_cooldown was called
        assert mock_storage.register_cooldown.called
        call_args = mock_storage.register_cooldown.call_args
        
        assert call_args[1]["signal_id"] == "SIG-008"
        assert call_args[1]["symbol"] == "EURUSD"
        assert call_args[1]["failure_reason"] == "SLIPPAGE_EXCEEDED"
        assert call_args[1]["cooldown_minutes"] > 0
        assert call_args[1]["cooldown_expires"] is not None

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Max Cooldown Caps
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cooldown_respects_max_limit(self, manager, mock_storage):
        """Test: Cooldown capped at maximum for reason."""
        # Simulate retry with extreme volatility  
        mock_storage.get_active_cooldown.return_value = {
            "retry_count": 3,
            "failure_reason": "INSUFFICIENT_BALANCE"
        }
        
        extreme_context = {"volatility_zscore": 3.5, "regime": "FLASH_MOVE"}
        result = await manager.apply_cooldown(
            signal_id="SIG-009",
            symbol="EURUSD",
            strategy="Strategy1",
            failure_reason="INSUFFICIENT_BALANCE",
            market_context=extreme_context
        )
        
        # Should be capped at max for this reason
        assert result["cooldown_minutes"] > 0
        assert result.get("cooldown_capped", False) or result["cooldown_minutes"] <= 120


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
