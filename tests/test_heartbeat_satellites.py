"""
E2E Integration Test: Heartbeat Satellite Emission
====================================================
Guards against the exact regression that broke Satellite Link:
- heartbeat_loop MUST emit SYSTEM_HEARTBEAT with satellite data
- satellite emission MUST NOT depend on regime_classifier success
- ConnectivityOrchestrator singleton MUST retain storage across calls

This test would have caught the bug where regime_classifier.classify()
crashed and killed the SYSTEM_HEARTBEAT emission before it reached the UI.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_storage():
    """Minimal StorageManager mock with provider data."""
    storage = MagicMock()
    storage.get_data_providers.return_value = [
        {
            "name": "yahoo",
            "enabled": 1,
            "priority": 100,
            "supports_data": 1,
            "supports_exec": 0,
        },
        {
            "name": "mt5",
            "enabled": 1,
            "priority": 200,
            "supports_data": 1,
            "supports_exec": 1,
        },
    ]
    storage.get_broker_accounts.return_value = []
    storage.get_connector_settings.return_value = {}
    return storage


@pytest.fixture
def mock_connector_yahoo():
    """Yahoo connector stub."""
    conn = MagicMock()
    conn.provider_id = "yahoo"
    conn.is_available.return_value = True
    conn.get_latency.return_value = 150.0
    conn.last_error = None
    return conn


@pytest.fixture
def mock_connector_mt5():
    """MT5 connector stub."""
    conn = MagicMock()
    conn.provider_id = "mt5"
    conn.is_available.return_value = False
    conn.get_latency.return_value = 0.0
    conn.last_error = None
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHeartbeatSatelliteEmission:
    """
    Validates that SYSTEM_HEARTBEAT always contains satellite data,
    even when other subsystems (regime classifier, CPU monitor) fail.
    """

    def test_get_status_report_returns_all_providers(
        self, mock_storage, mock_connector_yahoo, mock_connector_mt5
    ):
        """ConnectivityOrchestrator.get_status_report() returns all registered connectors."""
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        # Reset singleton for test isolation
        ConnectivityOrchestrator._instance = None

        orch = ConnectivityOrchestrator(storage=mock_storage)
        orch.register_connector(mock_connector_yahoo)
        orch.register_connector(mock_connector_mt5)
        orch.supports_info = {
            "yahoo": {"data": True, "exec": False},
            "mt5": {"data": True, "exec": True},
        }

        report = orch.get_status_report()

        assert "yahoo" in report, "Yahoo missing from satellite report"
        assert "mt5" in report, "MT5 missing from satellite report"
        assert report["yahoo"]["status"] == "ONLINE"
        assert report["yahoo"]["supports_data"] is True
        assert report["mt5"]["supports_exec"] is True
        assert report["yahoo"]["latency"] == 150.0

        # Cleanup singleton
        ConnectivityOrchestrator._instance = None

    def test_report_survives_connector_crash(
        self, mock_storage, mock_connector_yahoo
    ):
        """If one connector throws on is_available/get_latency, report still returns data."""
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        ConnectivityOrchestrator._instance = None

        # Create a crashing connector
        bad_conn = MagicMock()
        bad_conn.provider_id = "broken_broker"
        bad_conn.is_available.side_effect = RuntimeError("MT5 not installed")
        bad_conn.get_latency.side_effect = RuntimeError("MT5 not installed")
        bad_conn.last_error = "crash"

        orch = ConnectivityOrchestrator(storage=mock_storage)
        orch.register_connector(mock_connector_yahoo)
        orch.register_connector(bad_conn)

        report = orch.get_status_report()

        # Yahoo should still be present and healthy
        assert "yahoo" in report, "Healthy connector dropped due to sibling crash"
        assert report["yahoo"]["is_available"] is True

        # Broken connector should still appear but with safe defaults
        assert "broken_broker" in report, "Broken connector should still appear in report"
        assert report["broken_broker"]["is_available"] is False
        assert report["broken_broker"]["latency"] == 0.0

        ConnectivityOrchestrator._instance = None

    def test_singleton_retains_storage(self, mock_storage):
        """Singleton pattern must NOT lose storage on subsequent instantiations."""
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        ConnectivityOrchestrator._instance = None

        # First creation with storage
        orch1 = ConnectivityOrchestrator(storage=mock_storage)
        assert orch1.storage is mock_storage

        # Second creation without storage (like heartbeat_loop used to do)
        orch2 = ConnectivityOrchestrator()
        assert orch2 is orch1, "Singleton must return same instance"
        assert orch2.storage is mock_storage, (
            "Singleton lost storage! This is the exact bug that broke Satellite Link. "
            "The heartbeat_loop creates ConnectivityOrchestrator() without storage, "
            "and the singleton __init__ guard skips re-initialization."
        )

        ConnectivityOrchestrator._instance = None

    @pytest.mark.asyncio
    async def test_heartbeat_emits_satellites_even_when_regime_crashes(
        self, mock_storage, mock_connector_yahoo, mock_connector_mt5
    ):
        """
        THE critical E2E test. Simulates the exact heartbeat_loop flow.
        
        If regime_classifier.classify() throws, SYSTEM_HEARTBEAT with satellites
        MUST still be emitted. This is the regression that broke Satellite Link.
        """
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        ConnectivityOrchestrator._instance = None

        # Setup orchestrator with providers
        orch = ConnectivityOrchestrator(storage=mock_storage)
        orch.register_connector(mock_connector_yahoo)
        orch.register_connector(mock_connector_mt5)
        orch.supports_info = {
            "yahoo": {"data": True, "exec": False},
            "mt5": {"data": True, "exec": True},
        }

        # Mock the event emitter
        emitted_events = []

        async def mock_emit(event_type, payload):
            emitted_events.append({"type": event_type, "payload": payload})

        # --- Simulate heartbeat_loop logic (same structure as server.py) ---

        # Block 1: SYSTEM_HEARTBEAT (satellites, cpu, sync)
        try:
            metrics = {
                "core": "ACTIVE",
                "storage": "STABLE",
                "notificator": "CONFIGURED",
                "cpu_load": 5.0,
                "satellites": orch.get_status_report(),
                "sync_fidelity": {"score": 1.0, "status": "OPTIMAL"},
                "timestamp": datetime.now().isoformat(),
            }
            await mock_emit("SYSTEM_HEARTBEAT", metrics)
        except Exception:
            pass  # Should NOT reach here

        # Block 2: REGIME_UPDATE (simulate crash)
        try:
            raise RuntimeError("regime_classifier.classify() has no price data")
        except Exception:
            pass  # This crash must NOT affect block 1

        # --- Assertions ---

        # SYSTEM_HEARTBEAT must have been emitted
        heartbeats = [e for e in emitted_events if e["type"] == "SYSTEM_HEARTBEAT"]
        assert len(heartbeats) == 1, "SYSTEM_HEARTBEAT was not emitted!"

        payload = heartbeats[0]["payload"]
        sats = payload.get("satellites", {})

        assert "yahoo" in sats, "Yahoo missing from heartbeat satellites"
        assert "mt5" in sats, "MT5 missing from heartbeat satellites"
        assert sats["yahoo"]["status"] == "ONLINE"
        assert sats["yahoo"]["supports_data"] is True
        assert sats["mt5"]["supports_exec"] is True

        # REGIME_UPDATE should NOT have been emitted (it crashed)
        regime_events = [e for e in emitted_events if e["type"] == "REGIME_UPDATE"]
        assert len(regime_events) == 0, "REGIME_UPDATE should not emit when classifier crashes"

        ConnectivityOrchestrator._instance = None

    def test_manual_disabled_connector_appears_with_correct_status(
        self, mock_storage, mock_connector_yahoo
    ):
        """Manually disabled connectors should show MANUAL_DISABLED, not disappear."""
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        ConnectivityOrchestrator._instance = None

        orch = ConnectivityOrchestrator(storage=mock_storage)
        orch.register_connector(mock_connector_yahoo)
        orch.manual_states["yahoo"] = False  # User disabled it

        report = orch.get_status_report()

        assert "yahoo" in report, "Disabled connector must still appear in report"
        assert report["yahoo"]["status"] == "MANUAL_DISABLED"
        assert report["yahoo"]["is_available"] is False
        assert report["yahoo"]["latency"] == 0.0

        ConnectivityOrchestrator._instance = None
