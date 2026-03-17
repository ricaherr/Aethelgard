"""
TDD Tests – HU 5.3 Infrastructure Feedback Loop "The Pulse"
============================================================

TRACE_ID: INFRA-PULSE-HU53-2026-001

Tests verify:
1. _get_system_heartbeat() returns real CPU% from psutil (not 0.0 placeholder)
2. _get_system_heartbeat() returns real memory from psutil (not 0 placeholder)
3. Veto skips run_single_cycle() when CPU exceeds threshold
4. Veto allows run_single_cycle() when CPU is within limits
5. Veto logs to usr_notifications with category SYSTEM_STRESS
6. Veto threshold is read from dynamic_params (not hardcoded)
7. PositionManager is NOT affected by CPU veto (open trades keep running)
"""
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from data_vault.storage import StorageManager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_storage():
    """Minimal StorageManager mock for orchestrator tests."""
    storage = MagicMock(spec=StorageManager)
    storage.get_dynamic_params.return_value = {}
    storage.get_global_modules_enabled.return_value = {"scanner": True, "position_manager": True}
    storage.update_module_heartbeat.return_value = None
    storage.save_notification.return_value = True
    return storage


def _build_orchestrator(mock_storage):
    """
    Build a MainOrchestrator with all heavy dependencies mocked.
    Returns orchestrator instance ready for run_single_cycle() calls.
    """
    from core_brain.main_orchestrator import MainOrchestrator

    orc = MainOrchestrator.__new__(MainOrchestrator)
    orc.storage = mock_storage
    orc.thought_callback = None
    orc.modules_enabled_global = {"scanner": True, "position_manager": True}

    # Session stats mock (minimal)
    orc.stats = MagicMock()
    orc.stats.cycles_completed = 0
    orc.stats.reset_if_new_day = MagicMock()

    # Dependency mocks
    orc.expiration_manager = MagicMock()
    orc.expiration_manager.expire_old_sys_signals.return_value = {
        "total_checked": 0, "total_expired": 0, "by_timeframe": {}
    }
    orc.position_manager = MagicMock()
    orc.position_manager.monitor_usr_positions.return_value = {"monitored": 0, "actions": []}

    orc.scanner = MagicMock()
    orc.scanner.last_results = {}
    orc.signal_factory = MagicMock()
    orc.risk_manager = MagicMock()
    orc.executor = MagicMock()
    orc.regime_classifier = MagicMock()
    orc.edge_tuner = MagicMock()
    orc.strategy_ranker = MagicMock()
    orc.signal_selector = MagicMock()
    orc.cooldown_manager = MagicMock()
    orc.dedup_learner = MagicMock()
    orc.coherence_monitor = MagicMock()
    orc.threshold_optimizer = MagicMock()
    orc.closure_listener = MagicMock()

    # Internal state
    orc._last_dedup_learning_date = None
    orc._last_shadow_evolution_date = None
    orc._last_ranking_cycle = None

    return orc


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: _get_system_heartbeat() – psutil integration
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemHeartbeatPsutil:
    """Verify _get_system_heartbeat() uses real psutil instead of placeholders."""

    @pytest.mark.asyncio
    async def test_heartbeat_returns_real_cpu(self, mock_storage):
        """cpu_percent must reflect psutil value, not the 0.0 placeholder."""
        from core_brain.api.routers.telemetry import _get_system_heartbeat

        with patch("core_brain.api.routers.telemetry.psutil") as mock_psutil, \
             patch("core_brain.api.routers.telemetry.ConnectivityOrchestrator") as mock_orch_cls:

            mock_psutil.cpu_percent.return_value = 45.5
            mock_psutil.virtual_memory.return_value = MagicMock(used=512 * 1024 * 1024)
            mock_orch_cls.return_value.get_status_report.return_value = {}

            result = await _get_system_heartbeat(mock_storage)

        assert result["cpu_percent"] == 45.5, (
            f"Expected cpu_percent=45.5 from psutil, got {result['cpu_percent']}. "
            "The 0.0 placeholder must be replaced with psutil.cpu_percent()"
        )

    @pytest.mark.asyncio
    async def test_heartbeat_returns_real_memory(self, mock_storage):
        """memory_mb must reflect psutil virtual_memory.used, not 0 placeholder."""
        from core_brain.api.routers.telemetry import _get_system_heartbeat

        with patch("core_brain.api.routers.telemetry.psutil") as mock_psutil, \
             patch("core_brain.api.routers.telemetry.ConnectivityOrchestrator") as mock_orch_cls:

            mock_psutil.cpu_percent.return_value = 30.0
            mock_psutil.virtual_memory.return_value = MagicMock(used=768 * 1024 * 1024)
            mock_orch_cls.return_value.get_status_report.return_value = {}

            result = await _get_system_heartbeat(mock_storage)

        assert result["memory_mb"] == 768, (
            f"Expected memory_mb=768 from psutil, got {result['memory_mb']}. "
            "The 0 placeholder must be replaced with psutil.virtual_memory().used // (1024*1024)"
        )

    @pytest.mark.asyncio
    async def test_heartbeat_broker_latency_from_satellites(self, mock_storage):
        """broker_latency_ms must be computed from satellite last_sync_ms data."""
        from core_brain.api.routers.telemetry import _get_system_heartbeat

        satellite_status = {
            "MT5": {"status": "OK", "latency_ms": 120, "is_primary": True},
            "Yahoo": {"status": "OK", "latency_ms": 80, "is_primary": False},
        }

        with patch("core_brain.api.routers.telemetry.psutil") as mock_psutil, \
             patch("core_brain.api.routers.telemetry.ConnectivityOrchestrator") as mock_orch_cls:

            mock_psutil.cpu_percent.return_value = 20.0
            mock_psutil.virtual_memory.return_value = MagicMock(used=256 * 1024 * 1024)
            mock_orch_cls.return_value.get_status_report.return_value = satellite_status

            result = await _get_system_heartbeat(mock_storage)

        assert result["broker_latency_ms"] == 100, (
            f"Expected average latency 100ms ((120+80)/2), got {result['broker_latency_ms']}. "
            "broker_latency_ms must be the mean of satellite last_sync_ms values"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: CPU Veto – run_single_cycle() behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestCpuVetoBlock:
    """Verify infrastructure veto skips new cycle trades when CPU is critical."""

    @pytest.mark.asyncio
    async def test_veto_skips_cycle_when_cpu_critical(self, mock_storage):
        """When CPU > threshold, run_single_cycle() must return early without scanning."""
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 90}
        orc = _build_orchestrator(mock_storage)

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 95.0  # Above threshold
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        # Scanner must NOT have been called
        orc.scanner.scan_assets.assert_not_called()

    @pytest.mark.asyncio
    async def test_veto_allows_cycle_when_cpu_normal(self, mock_storage):
        """When CPU <= threshold, run_single_cycle() must NOT return early."""
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 90}
        orc = _build_orchestrator(mock_storage)

        # Make scanner return empty result so cycle completes normally
        orc._get_scan_schedule = MagicMock(return_value=[])
        orc._get_assets_due_for_scan = MagicMock(return_value=[])

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 50.0  # Below threshold
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        # Cycle must have proceeded past the heartbeat step
        orc.storage.update_module_heartbeat.assert_any_call("orchestrator")

    @pytest.mark.asyncio
    async def test_veto_uses_default_threshold_when_no_dynamic_params(self, mock_storage):
        """Veto default threshold is 90% when dynamic_params is empty or missing key."""
        mock_storage.get_dynamic_params.return_value = {}  # No cpu_veto_threshold key
        orc = _build_orchestrator(mock_storage)

        # CPU at 95% — must veto (default threshold 90)
        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 95.0
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        orc.scanner.scan_assets.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: Veto Notification – usr_notifications logging
# ─────────────────────────────────────────────────────────────────────────────

class TestVetoNotification:
    """Verify a SYSTEM_STRESS notification is saved when veto triggers."""

    @pytest.mark.asyncio
    async def test_veto_logs_notification_on_trigger(self, mock_storage):
        """When veto fires, storage.save_notification must be called with SYSTEM_STRESS category."""
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 90}
        orc = _build_orchestrator(mock_storage)

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 97.3
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        mock_storage.save_notification.assert_called_once()
        args, _ = mock_storage.save_notification.call_args
        notification = args[0]
        assert notification.get("category") == "SYSTEM_STRESS", (
            f"Expected category='SYSTEM_STRESS', got '{notification.get('category')}'"
        )

    @pytest.mark.asyncio
    async def test_veto_does_not_log_notification_when_cpu_normal(self, mock_storage):
        """When CPU is below threshold, no SYSTEM_STRESS notification is saved."""
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 90}
        orc = _build_orchestrator(mock_storage)

        orc._get_scan_schedule = MagicMock(return_value=[])
        orc._get_assets_due_for_scan = MagicMock(return_value=[])

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 40.0
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        # Search for any SYSTEM_STRESS notification call
        system_stress_calls = [
            c for c in mock_storage.save_notification.call_args_list
            if c.args and c.args[0].get("category") == "SYSTEM_STRESS"
        ]
        assert len(system_stress_calls) == 0, "No SYSTEM_STRESS notification expected when CPU is normal"


# ─────────────────────────────────────────────────────────────────────────────
# Group 4: Threshold from dynamic_params (SSOT)
# ─────────────────────────────────────────────────────────────────────────────

class TestVetoThresholdFromDynamicParams:
    """Verify veto threshold is always read from dynamic_params (SSOT), never hardcoded."""

    @pytest.mark.asyncio
    async def test_custom_threshold_respected(self, mock_storage):
        """A custom cpu_veto_threshold=70 from DB is used instead of the 90 default."""
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 70}
        orc = _build_orchestrator(mock_storage)

        # CPU at 75% — above custom threshold 70, below default 90
        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 75.0
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        # Must veto — custom threshold 70 was exceeded
        orc.scanner.scan_assets.assert_not_called()

    @pytest.mark.asyncio
    async def test_dynamic_params_queried_every_cycle(self, mock_storage):
        """get_dynamic_params() must be called during run_single_cycle() to read veto threshold."""
        mock_storage.get_dynamic_params.return_value = {}
        orc = _build_orchestrator(mock_storage)

        orc._get_scan_schedule = MagicMock(return_value=[])
        orc._get_assets_due_for_scan = MagicMock(return_value=[])

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0  # Well below threshold
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        mock_storage.get_dynamic_params.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# Group 5: Position Manager isolation from veto
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionManagerUnaffectedByVeto:
    """Verify open position management continues even when CPU veto fires."""

    @pytest.mark.asyncio
    async def test_position_manager_runs_before_veto_check(self, mock_storage):
        """
        PositionManager must run regardless of CPU state.
        (It manages existing open trades — must not be skipped.)
        """
        mock_storage.get_dynamic_params.return_value = {"cpu_veto_threshold": 90}
        orc = _build_orchestrator(mock_storage)
        orc.position_manager.monitor_usr_positions.return_value = {
            "monitored": 2, "actions": []
        }

        with patch("core_brain.main_orchestrator.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 99.0  # Max CPU — veto fires
            with patch.object(orc, "_check_and_run_weekly_dedup_learning", new=AsyncMock()), \
                 patch.object(orc, "_check_and_run_weekly_shadow_evolution", new=AsyncMock()):
                await orc.run_single_cycle()

        # PositionManager must still have been called
        orc.position_manager.monitor_usr_positions.assert_called_once()
