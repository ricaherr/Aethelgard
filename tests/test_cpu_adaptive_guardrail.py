from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_brain.orchestrators._cycle_scan import (
    CpuPressureState,
    _evaluate_cpu_pressure,
    run_pre_phase,
)



def _make_base_orchestrator(dynamic_params: dict | None = None) -> SimpleNamespace:
    stats = SimpleNamespace(cycles_completed=0, scans_total=0)
    stats.reset_if_new_day = MagicMock()

    storage = MagicMock()
    storage.get_dynamic_params.return_value = dynamic_params or {}
    storage.get_global_modules_enabled.return_value = {"scanner": True, "position_manager": False}
    storage.update_module_heartbeat.return_value = None
    storage.save_notification.return_value = True
    storage.get_sys_config.return_value = {}

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
        signal_review_manager=None,
    )
    return orch


@patch("core_brain.main_orchestrator.psutil")
def test_normal_state_when_avg_below_throttle(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.side_effect = [50.0, 50.0, 50.0, 50.0, 50.0]
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})

    state = CpuPressureState.NORMAL
    for _ in range(5):
        state = _evaluate_cpu_pressure(orch, orch.storage.get_dynamic_params())

    assert state == CpuPressureState.NORMAL


@pytest.mark.asyncio
@patch("core_brain.main_orchestrator.psutil")
async def test_throttled_state_skips_every_other_cycle(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.return_value = 80.0
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})

    outcomes = []
    for _ in range(6):
        outcomes.append(await run_pre_phase(orch))

    assert outcomes == [False, True, False, True, False, True]


@pytest.mark.asyncio
@patch("core_brain.main_orchestrator.psutil")
async def test_veto_state_triggers_notification(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.return_value = 95.0
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_veto_threshold": 90})

    result = await run_pre_phase(orch)

    assert result is False
    orch.storage.save_notification.assert_called_once()


@patch("core_brain.main_orchestrator.psutil")
def test_window_size_from_dynamic_params(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.side_effect = [10.0, 20.0, 30.0, 40.0, 50.0]
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 3, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})

    for _ in range(5):
        _evaluate_cpu_pressure(orch, orch.storage.get_dynamic_params())

    assert isinstance(orch._cpu_pressure_window, deque)
    assert orch._cpu_pressure_window.maxlen == 3
    assert list(orch._cpu_pressure_window) == [30.0, 40.0, 50.0]


@patch("core_brain.main_orchestrator.psutil")
def test_throttle_threshold_from_dynamic_params(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.side_effect = [65.0, 65.0, 65.0, 65.0, 65.0]
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_throttle_threshold": 60, "cpu_veto_threshold": 90})

    state = CpuPressureState.NORMAL
    for _ in range(5):
        state = _evaluate_cpu_pressure(orch, orch.storage.get_dynamic_params())

    assert state == CpuPressureState.THROTTLED


@patch("core_brain.main_orchestrator.psutil")
def test_single_sample_no_error(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.return_value = 82.0
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})

    state = _evaluate_cpu_pressure(orch, orch.storage.get_dynamic_params())

    assert state in {CpuPressureState.NORMAL, CpuPressureState.THROTTLED, CpuPressureState.VETO}


@pytest.mark.asyncio
@patch("core_brain.main_orchestrator.psutil")
async def test_transition_veto_to_normal_resets_counter(mock_psutil: MagicMock) -> None:
    mock_psutil.side_effect = None
    mock_psutil.cpu_percent.side_effect = [95.0, 95.0, 95.0, 10.0]

    orch = _make_base_orchestrator({"cpu_pressure_window_size": 1, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})
    orch._cpu_throttle_skip_counter = 7

    await run_pre_phase(orch)
    await run_pre_phase(orch)
    await run_pre_phase(orch)
    result = await run_pre_phase(orch)

    assert result is True
    assert orch._cpu_throttle_skip_counter == 0


@pytest.mark.asyncio
@patch("core_brain.main_orchestrator.psutil")
async def test_existing_infrastructure_pulse_unaffected(mock_psutil: MagicMock) -> None:
    mock_psutil.cpu_percent.return_value = 55.0
    orch = _make_base_orchestrator({"cpu_pressure_window_size": 5, "cpu_throttle_threshold": 75, "cpu_veto_threshold": 90})

    result = await run_pre_phase(orch)

    assert result is True
    mock_psutil.cpu_percent.assert_called()
