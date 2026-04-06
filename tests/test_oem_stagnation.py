"""
test_oem_stagnation.py — HU 10.9

Contract tests for OperationalEdgeMonitor._check_shadow_stagnation().
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from core_brain.operational_edge_monitor import OperationalEdgeMonitor, CheckStatus


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _instance(instance_id: str, *, strategy_id: str = "strat_01", symbol: str = "EURUSD") -> MagicMock:
    inst = MagicMock()
    inst.instance_id = instance_id
    inst.strategy_id = strategy_id
    inst.symbol = symbol
    return inst


@pytest.fixture
def oem_and_storage():
    storage = MagicMock()
    storage.get_sys_config.return_value = {}
    storage.get_sys_trades.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.log_audit_event.return_value = None

    shadow_storage = MagicMock()
    shadow_storage.list_active_instances.return_value = []

    oem = OperationalEdgeMonitor(storage=storage, shadow_storage=shadow_storage, interval_seconds=9999)
    return oem, storage, shadow_storage


class TestShadowStagnationCheck:
    def test_no_stagnation_when_recent_trades_exist(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-1")]
        storage.get_sys_trades.return_value = [{"close_time": _iso(2), "profit": 1.2, "instance_id": "I-1"}]

        result = oem._check_shadow_stagnation()

        assert result.status == CheckStatus.OK
        assert "sin estancamiento" in result.detail.lower()

    def test_warn_when_no_trades_in_window(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-2")]
        storage.get_sys_trades.return_value = []

        result = oem._check_shadow_stagnation()

        assert result.status == CheckStatus.WARN
        assert "SHADOW_STAGNATION_ALERT" in result.detail
        assert storage.log_audit_event.call_count == 1

    def test_idempotent_no_duplicate_alert_same_day(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-3")]
        storage.get_sys_trades.return_value = []

        first = oem._check_shadow_stagnation()
        second = oem._check_shadow_stagnation()

        assert first.status == CheckStatus.WARN
        assert second.status == CheckStatus.WARN
        assert storage.log_audit_event.call_count == 1

    def test_cause_outside_session_window_when_market_closed(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-4")]
        storage.get_sys_trades.return_value = []

        oem._any_session_active = MagicMock(return_value=False)
        result = oem._check_shadow_stagnation()

        assert result.status == CheckStatus.WARN
        assert "OUTSIDE_SESSION_WINDOW" in result.detail

    def test_cause_symbol_not_whitelisted(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-5", symbol="XAUUSD")]
        storage.get_sys_trades.return_value = []
        storage.get_sys_config.return_value = {"active_symbols": ["EURUSD", "USDJPY"]}

        result = oem._check_shadow_stagnation()

        assert result.status == CheckStatus.WARN
        assert "SYMBOL_NOT_WHITELISTED" in result.detail

    def test_uses_configurable_threshold_hours(self, oem_and_storage):
        oem, storage, shadow_storage = oem_and_storage
        shadow_storage.list_active_instances.return_value = [_instance("I-6")]
        storage.get_sys_config.return_value = {"shadow_stagnation_hours": 12}
        storage.get_sys_trades.return_value = [{"close_time": _iso(13), "profit": 0.3, "instance_id": "I-6"}]

        result = oem._check_shadow_stagnation()

        assert result.status == CheckStatus.WARN
        assert "12h" in result.detail
