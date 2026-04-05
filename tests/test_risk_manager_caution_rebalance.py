import pytest

from core_brain.risk_manager import RiskManager


@pytest.mark.asyncio
async def test_rebalance_after_caution_restores_multiplier(storage):
    """RiskManager must restore risk multiplier to 1.0 after CAUTION ends."""
    risk_manager = RiskManager(storage=storage)

    result = await risk_manager.rebalance_after_caution(
        symbol="EURUSD",
        trace_id="TRACE-REB-001",
    )

    state = storage.get_sys_config()
    assert result["status"] == "ok"
    assert state.get("econ_risk_multiplier_EURUSD") == 1.0
    assert state.get("econ_rebalance_last_symbol") == "EURUSD"


@pytest.mark.asyncio
async def test_rebalance_after_caution_clamps_invalid_multiplier(storage):
    """Invalid multipliers should be clamped to safe default (1.0)."""
    risk_manager = RiskManager(storage=storage)

    result = await risk_manager.rebalance_after_caution(
        symbol="GBPUSD",
        trace_id="TRACE-REB-002",
        target_risk_multiplier=1.5,
    )

    state = storage.get_sys_config()
    assert result["status"] == "ok"
    assert state.get("econ_risk_multiplier_GBPUSD") == 1.0
