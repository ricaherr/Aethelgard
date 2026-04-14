import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_brain.orchestrators._cycle_scan import run_pre_phase, run_scan_phase


def _make_base_orchestrator() -> SimpleNamespace:
    stats = SimpleNamespace(cycles_completed=0, scans_total=0)
    stats.reset_if_new_day = MagicMock()

    storage = MagicMock()
    storage.get_dynamic_params.return_value = {}
    storage.update_module_heartbeat.return_value = None
    storage.log_audit_event.return_value = None
    storage.update_sys_config.return_value = None

    expiration_manager = MagicMock()
    expiration_manager.expire_old_sys_signals.return_value = {
        "total_checked": 0,
        "total_expired": 0,
        "by_timeframe": {},
    }

    resilience_manager = SimpleNamespace(current_posture=SimpleNamespace(value="NORMAL"))

    orch = SimpleNamespace(
        storage=storage,
        stats=stats,
        thought_callback=None,
        expiration_manager=expiration_manager,
        _check_and_run_weekly_dedup_learning=AsyncMock(),
        _check_and_run_weekly_shadow_evolution=AsyncMock(),
        _check_and_run_daily_backtest=AsyncMock(),
        _consume_oem_repair_flags=AsyncMock(),
        position_manager=None,
        resilience_manager=resilience_manager,
        _is_market_closed=MagicMock(return_value=False),
        modules_enabled_global={"scanner": True, "position_manager": False},
        scanner=SimpleNamespace(last_results={}),
        anomaly_sentinel=SimpleNamespace(push_ticks=MagicMock()),
        market_structure_analyzer=None,
        ui_mapping_service=None,
        _consecutive_empty_structure_cycles=0,
        _max_consecutive_empty_cycles=3,
        current_regime=None,
    )
    return orch


@pytest.mark.asyncio
async def test_backtest_timeout_is_audited_and_cycle_continues_fail_safe() -> None:
    orch = _make_base_orchestrator()
    orch.storage.get_global_modules_enabled.return_value = {
        "scanner": False,
        "position_manager": False,
    }
    orch.storage.get_sys_config.return_value = {"phase_timeout_backtest_s": 0.01}

    async def _slow_backtest() -> None:
        await asyncio.sleep(0.05)

    orch._check_and_run_daily_backtest = _slow_backtest

    with patch("core_brain.main_orchestrator.psutil.cpu_percent", return_value=10.0):
        result = await run_pre_phase(orch)

    assert result is False
    orch.storage.log_audit_event.assert_called()
    call_kwargs = orch.storage.log_audit_event.call_args.kwargs
    assert call_kwargs.get("action") == "PHASE_TIMEOUT"
    assert call_kwargs.get("resource_id") == "daily_backtest"


@pytest.mark.asyncio
async def test_position_monitor_timeout_is_audited() -> None:
    orch = _make_base_orchestrator()
    orch.storage.get_global_modules_enabled.return_value = {
        "scanner": False,
        "position_manager": True,
    }
    orch.storage.get_sys_config.return_value = {
        "phase_timeout_backtest_s": 1.0,
        "phase_timeout_positions_s": 0.01,
    }

    def _slow_monitor(**kwargs):
        del kwargs
        time.sleep(0.05)
        return {"monitored": 0, "actions": []}

    orch.position_manager = MagicMock()
    orch.position_manager.monitor_usr_positions.side_effect = _slow_monitor

    fake_conn = SimpleNamespace(is_connected=True)
    fake_orchestrator = MagicMock()
    fake_orchestrator.connectors = {"ACC1": fake_conn}
    fake_orchestrator.supports_info = {"ACC1": {"exec": True}}

    with patch("core_brain.main_orchestrator.psutil.cpu_percent", return_value=10.0), patch(
        "core_brain.connectivity_orchestrator.ConnectivityOrchestrator",
        return_value=fake_orchestrator,
    ):
        result = await run_pre_phase(orch)

    assert result is False
    timed_out_resources = [
        c.kwargs.get("resource_id")
        for c in orch.storage.log_audit_event.call_args_list
        if c.kwargs.get("action") == "PHASE_TIMEOUT"
    ]
    assert any(str(resource).startswith("position_monitor:") for resource in timed_out_resources)


@pytest.mark.asyncio
async def test_scan_timeout_falls_back_to_cached_results() -> None:
    orch = _make_base_orchestrator()
    orch.storage.get_sys_config.return_value = {"phase_timeout_scan_s": 0.01}
    orch._get_scan_schedule = MagicMock(return_value={"EURUSD|M5": 10.0})
    orch._should_scan_now = MagicMock(return_value=[("EURUSD", "M5")])

    async def _slow_request_scan(_assets):
        await asyncio.sleep(0.05)
        return {}

    orch._request_scan = _slow_request_scan
    orch._update_regime_from_scan = MagicMock()
    orch._persist_scan_telemetry = MagicMock()
    orch.scanner.last_results = {
        "EURUSD|M5": {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "regime": "RANGE",
            "provider_source": "cache",
            "metrics": {"adx": 20},
            "df": None,
        }
    }

    bundle = await run_scan_phase(orch)

    assert bundle is not None
    assert "EURUSD|M5" in bundle.scan_results_with_data
    timed_out_resources = [
        c.kwargs.get("resource_id")
        for c in orch.storage.log_audit_event.call_args_list
        if c.kwargs.get("action") == "PHASE_TIMEOUT"
    ]
    assert "scan_request" in timed_out_resources


@pytest.mark.asyncio
async def test_scan_backpressure_pauses_request_when_db_latency_is_high() -> None:
    orch = _make_base_orchestrator()
    orch.storage.get_sys_config.return_value = {
        "phase_timeout_scan_s": 1.0,
        "scan_backpressure_latency_ms": 200,
    }
    orch.storage.get_db_transaction_metrics.return_value = {
        "global": {"avg_ms": 250.0, "last_ms": 260.0, "count": 12}
    }
    orch._get_scan_schedule = MagicMock(return_value={"EURUSD|M5": 10.0})
    orch._should_scan_now = MagicMock(return_value=[("EURUSD", "M5")])
    orch._request_scan = AsyncMock(return_value={})
    orch._update_regime_from_scan = MagicMock()
    orch._persist_scan_telemetry = MagicMock()
    orch.scanner.last_results = {
        "EURUSD|M5": {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "regime": "RANGE",
            "provider_source": "cache",
            "metrics": {"adx": 20},
            "df": None,
        }
    }

    bundle = await run_scan_phase(orch)

    assert bundle is not None
    orch._request_scan.assert_not_called()
    backpressure_events = [
        c.kwargs for c in orch.storage.log_audit_event.call_args_list
        if c.kwargs.get("action") == "SCAN_BACKPRESSURE"
    ]
    assert backpressure_events


@pytest.mark.asyncio
async def test_scan_backpressure_allows_request_when_latency_is_healthy() -> None:
    orch = _make_base_orchestrator()
    orch.storage.get_sys_config.return_value = {
        "phase_timeout_scan_s": 1.0,
        "scan_backpressure_latency_ms": 200,
    }
    orch.storage.get_db_transaction_metrics.return_value = {
        "global": {"avg_ms": 80.0, "last_ms": 75.0, "count": 12}
    }
    orch._get_scan_schedule = MagicMock(return_value={"EURUSD|M5": 10.0})
    orch._should_scan_now = MagicMock(return_value=[("EURUSD", "M5")])
    orch._request_scan = AsyncMock(return_value={})
    orch._update_regime_from_scan = MagicMock()
    orch._persist_scan_telemetry = MagicMock()
    orch.scanner.last_results = {
        "EURUSD|M5": {
            "symbol": "EURUSD",
            "timeframe": "M5",
            "regime": "RANGE",
            "provider_source": "cache",
            "metrics": {"adx": 20},
            "df": None,
        }
    }

    await run_scan_phase(orch)

    orch._request_scan.assert_called_once()