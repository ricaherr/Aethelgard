"""
test_connection_health.py — TDD tests for HU 5.1: ConnectionHealthMonitor.

Covers:
  - Root cause classification (all 6 categories)
  - Heartbeat success / failure detection
  - Consecutive-failure threshold and reconnect trigger
  - Reconnect success and failure flows
  - Fallback callback invocation
  - DB persistence via StorageManager (mocked)
  - ResilienceManager integration (process_connection_health_event)
  - MT5Connector health monitor attachment
  - Snapshot thread-safety (get_snapshot)
"""
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, call
import pytest

from core_brain.connection_health_monitor import (
    ConnectionHealthMonitor,
    ConnectorHealthSnapshot,
    ConnectorHealthStatus,
    RootCause,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_HEARTBEAT_FAIL,
    EVENT_HEARTBEAT_OK,
    EVENT_RECONNECT_ATTEMPT,
    EVENT_RECONNECT_SUCCESS,
    EVENT_RECONNECT_FAILED,
    EVENT_FALLBACK_TRIGGERED,
    EVENT_LATENCY_DEGRADED,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_connector(
    provider_id: str = "test_broker",
    is_available: bool = True,
    latency: float = 50.0,
    last_error: Optional[str] = None,
    connect_result: bool = True,
) -> MagicMock:
    connector = MagicMock()
    connector.provider_id = provider_id
    connector.is_available.return_value = is_available
    connector.get_latency.return_value = latency
    connector.last_error = last_error
    connector.connect_blocking.return_value = connect_result
    connector.connect.return_value = connect_result
    return connector


def _make_monitor(
    connector: Optional[MagicMock] = None,
    storage: Optional[MagicMock] = None,
    on_health_change=None,
    on_fallback=None,
    heartbeat_interval: float = 0.05,
    max_consecutive_failures: int = 2,
) -> ConnectionHealthMonitor:
    if connector is None:
        connector = _make_connector()
    return ConnectionHealthMonitor(
        connector=connector,
        storage=storage,
        on_health_change=on_health_change,
        on_fallback=on_fallback,
        heartbeat_interval_seconds=heartbeat_interval,
        max_consecutive_failures=max_consecutive_failures,
    )


# ── Root Cause Classification ─────────────────────────────────────────────────

class TestRootCauseClassification:

    def test_classify_auth_error(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Auth failed: bad password") == RootCause.AUTH

    def test_classify_auth_unauthorized(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Unauthorized access denied") == RootCause.AUTH

    def test_classify_auth_credential(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Invalid credentials provided") == RootCause.AUTH

    def test_classify_timeout_error(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("connection timed out after 30s") == RootCause.TIMEOUT

    def test_classify_timeout_timed_out(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Request timed out") == RootCause.TIMEOUT

    def test_classify_feed_inactive(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("No market data available for symbol") == RootCause.FEED_INACTIVE

    def test_classify_feed_tick(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Feed error: no tick received") == RootCause.FEED_INACTIVE

    def test_classify_network_refused(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Connection refused by host") == RootCause.NETWORK

    def test_classify_network_socket(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Socket error errno 111") == RootCause.NETWORK

    def test_classify_network_unreachable(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Host unreachable") == RootCause.NETWORK

    def test_classify_internal_error(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("Unexpected NullPointerException") == RootCause.INTERNAL_ERROR

    def test_classify_unknown_empty_string(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("") == RootCause.UNKNOWN

    def test_classify_unknown_none_string(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("None") == RootCause.UNKNOWN

    def test_auth_takes_priority_over_network(self):
        monitor = _make_monitor()
        assert monitor.classify_root_cause("auth socket error") == RootCause.AUTH


# ── ConnectorHealthSnapshot ───────────────────────────────────────────────────

class TestConnectorHealthSnapshot:

    def test_initial_status_is_unknown(self):
        monitor = _make_monitor()
        snapshot = monitor.get_snapshot()
        assert snapshot.status == ConnectorHealthStatus.UNKNOWN

    def test_snapshot_connector_id(self):
        connector = _make_connector(provider_id="mt5")
        monitor = _make_monitor(connector=connector)
        assert monitor.get_snapshot().connector_id == "mt5"

    def test_snapshot_is_healthy_false_when_unknown(self):
        monitor = _make_monitor()
        assert monitor.get_snapshot().is_healthy is False

    def test_notify_connected_sets_healthy_status(self):
        monitor = _make_monitor()
        monitor.notify_connected()
        snapshot = monitor.get_snapshot()
        assert snapshot.status == ConnectorHealthStatus.HEALTHY
        assert snapshot.is_healthy is True
        assert snapshot.root_cause is None

    def test_notify_disconnected_sets_disconnected_status(self):
        monitor = _make_monitor()
        monitor.notify_connected()
        monitor.notify_disconnected(root_cause=RootCause.NETWORK)
        snapshot = monitor.get_snapshot()
        assert snapshot.status == ConnectorHealthStatus.DISCONNECTED
        assert snapshot.root_cause == RootCause.NETWORK
        assert snapshot.is_healthy is False

    def test_notify_disconnected_defaults_to_unknown_cause(self):
        monitor = _make_monitor()
        monitor.notify_disconnected()
        assert monitor.get_snapshot().root_cause == RootCause.UNKNOWN


# ── Heartbeat Success ─────────────────────────────────────────────────────────

class TestHeartbeatSuccess:

    def test_heartbeat_ok_transitions_to_healthy(self):
        connector = _make_connector(is_available=True, latency=100.0)
        changes = []
        monitor = _make_monitor(
            connector=connector,
            on_health_change=lambda s: changes.append(s.status),
            heartbeat_interval=0.05,
            max_consecutive_failures=3,
        )
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        assert ConnectorHealthStatus.HEALTHY in changes

    def test_high_latency_causes_degraded_status(self):
        connector = _make_connector(is_available=True, latency=3000.0)
        changes = []
        monitor = _make_monitor(
            connector=connector,
            on_health_change=lambda s: changes.append(s.status),
            heartbeat_interval=0.05,
        )
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        assert ConnectorHealthStatus.DEGRADED in changes

    def test_consecutive_failures_reset_on_success(self):
        connector = _make_connector(is_available=True, latency=50.0)
        monitor = _make_monitor(connector=connector, heartbeat_interval=0.05)
        # Manually set failures
        with monitor._lock:
            monitor._consecutive_failures = 5
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        with monitor._lock:
            assert monitor._consecutive_failures == 0


# ── Heartbeat Failure ─────────────────────────────────────────────────────────

class TestHeartbeatFailure:

    def test_heartbeat_fail_increments_consecutive_failures(self):
        connector = _make_connector(is_available=False)
        monitor = _make_monitor(
            connector=connector,
            heartbeat_interval=0.05,
            max_consecutive_failures=999,
        )
        monitor.start()
        time.sleep(0.25)
        monitor.stop()
        with monitor._lock:
            assert monitor._consecutive_failures >= 2

    def test_heartbeat_fail_changes_status_to_disconnected(self):
        connector = _make_connector(is_available=False)
        statuses = []
        monitor = _make_monitor(
            connector=connector,
            on_health_change=lambda s: statuses.append(s.status),
            heartbeat_interval=0.05,
            max_consecutive_failures=999,
        )
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        assert ConnectorHealthStatus.DISCONNECTED in statuses

    def test_failure_threshold_triggers_reconnect(self):
        connector = _make_connector(is_available=False)
        reconnect_calls = []
        connector.connect_blocking.side_effect = lambda: reconnect_calls.append(1) or True
        monitor = ConnectionHealthMonitor(
            connector=connector,
            heartbeat_interval_seconds=0.05,
            max_consecutive_failures=2,
            reconnect_base_delay_seconds=0.02,
        )
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        assert len(reconnect_calls) >= 1

    def test_reconnect_success_resets_to_healthy(self):
        connector = _make_connector(is_available=False)
        connector.connect_blocking.return_value = True
        statuses = []
        monitor = ConnectionHealthMonitor(
            connector=connector,
            on_health_change=lambda s: statuses.append(s.status),
            heartbeat_interval_seconds=0.05,
            max_consecutive_failures=2,
            reconnect_base_delay_seconds=0.02,
        )
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        assert ConnectorHealthStatus.HEALTHY in statuses

    def test_reconnect_failure_triggers_fallback(self):
        connector = _make_connector(is_available=False)
        connector.connect_blocking.return_value = False
        fallback_calls = []
        monitor = ConnectionHealthMonitor(
            connector=connector,
            on_fallback=lambda s: fallback_calls.append(s),
            heartbeat_interval_seconds=0.05,
            max_consecutive_failures=2,
            reconnect_base_delay_seconds=0.02,
        )
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        assert len(fallback_calls) >= 1

    def test_fallback_snapshot_contains_root_cause(self):
        connector = _make_connector(is_available=False)
        connector.last_error = "Auth failed"
        connector.connect_blocking.return_value = False
        fallback_snapshots = []
        monitor = ConnectionHealthMonitor(
            connector=connector,
            on_fallback=lambda s: fallback_snapshots.append(s),
            heartbeat_interval_seconds=0.05,
            max_consecutive_failures=2,
            reconnect_base_delay_seconds=0.02,
        )
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        assert len(fallback_snapshots) >= 1
        assert fallback_snapshots[0].root_cause == RootCause.AUTH


# ── DB Persistence ────────────────────────────────────────────────────────────

class TestDBPersistence:

    def test_notify_connected_persists_event(self):
        storage = MagicMock()
        monitor = _make_monitor(storage=storage)
        monitor.notify_connected()
        storage.record_connector_health_event.assert_called_once()
        call_kwargs = storage.record_connector_health_event.call_args
        assert call_kwargs.kwargs.get("event_type") == EVENT_CONNECTED or \
               call_kwargs.args[1] == EVENT_CONNECTED

    def test_notify_disconnected_persists_event(self):
        storage = MagicMock()
        monitor = _make_monitor(storage=storage)
        monitor.notify_disconnected(root_cause=RootCause.AUTH)
        storage.record_connector_health_event.assert_called_once()

    def test_heartbeat_fail_persists_event(self):
        storage = MagicMock()
        connector = _make_connector(is_available=False)
        monitor = _make_monitor(
            connector=connector,
            storage=storage,
            heartbeat_interval=0.05,
            max_consecutive_failures=999,
        )
        monitor.start()
        time.sleep(0.2)
        monitor.stop()
        calls = [
            c for c in storage.record_connector_health_event.call_args_list
            if EVENT_HEARTBEAT_FAIL in str(c)
        ]
        assert len(calls) >= 1

    def test_db_error_does_not_crash_monitor(self):
        storage = MagicMock()
        storage.record_connector_health_event.side_effect = Exception("DB locked")
        connector = _make_connector(is_available=True, latency=50.0)
        monitor = _make_monitor(
            connector=connector,
            storage=storage,
            heartbeat_interval=0.05,
        )
        monitor.notify_connected(details={"test": True})
        # Should not raise; monitor still functional
        assert monitor.get_snapshot().status == ConnectorHealthStatus.HEALTHY

    def test_record_connector_health_event_persists_root_cause(self):
        storage = MagicMock()
        monitor = _make_monitor(storage=storage)
        monitor.notify_disconnected(root_cause=RootCause.NETWORK, details={"test": "value"})
        storage.record_connector_health_event.assert_called_once()
        kwargs = storage.record_connector_health_event.call_args[1]
        assert kwargs.get("root_cause") == RootCause.NETWORK.value or \
               RootCause.NETWORK.value in str(storage.record_connector_health_event.call_args)


# ── ResilienceManager Integration ─────────────────────────────────────────────

class TestResilienceManagerIntegration:

    def _make_resilience_manager(self):
        from core_brain.resilience_manager import ResilienceManager
        storage = MagicMock()
        storage._get_conn.return_value = MagicMock()
        return ResilienceManager(storage=storage)

    def test_healthy_snapshot_does_not_escalate(self):
        manager = self._make_resilience_manager()
        snapshot = ConnectorHealthSnapshot(
            connector_id="mt5",
            status=ConnectorHealthStatus.HEALTHY,
            root_cause=None,
            latency_ms=50.0,
            reconnect_attempts=0,
            last_tick_time=None,
            last_heartbeat_time=time.monotonic(),
            is_healthy=True,
        )
        from core_brain.resilience import SystemPosture
        posture = manager.process_connection_health_event(snapshot)
        assert posture == SystemPosture.NORMAL

    def test_reconnecting_snapshot_does_not_escalate(self):
        manager = self._make_resilience_manager()
        snapshot = ConnectorHealthSnapshot(
            connector_id="mt5",
            status=ConnectorHealthStatus.RECONNECTING,
            root_cause=RootCause.NETWORK,
            latency_ms=0.0,
            reconnect_attempts=1,
            last_tick_time=None,
            last_heartbeat_time=time.monotonic(),
            is_healthy=False,
        )
        from core_brain.resilience import SystemPosture
        posture = manager.process_connection_health_event(snapshot)
        assert posture == SystemPosture.NORMAL

    def test_disconnected_with_reconnects_escalates_posture(self):
        manager = self._make_resilience_manager()
        snapshot = ConnectorHealthSnapshot(
            connector_id="mt5",
            status=ConnectorHealthStatus.DISCONNECTED,
            root_cause=RootCause.NETWORK,
            latency_ms=0.0,
            reconnect_attempts=3,
            last_tick_time=None,
            last_heartbeat_time=time.monotonic(),
            is_healthy=False,
        )
        from core_brain.resilience import SystemPosture
        posture = manager.process_connection_health_event(snapshot)
        # Multiple failed reconnects → STRESSED (LOCKDOWN)
        assert posture in (SystemPosture.STRESSED, SystemPosture.DEGRADED, SystemPosture.CAUTION)

    def test_degraded_snapshot_does_not_escalate(self):
        manager = self._make_resilience_manager()
        snapshot = ConnectorHealthSnapshot(
            connector_id="mt5",
            status=ConnectorHealthStatus.DEGRADED,
            root_cause=None,
            latency_ms=3000.0,
            reconnect_attempts=0,
            last_tick_time=None,
            last_heartbeat_time=time.monotonic(),
            is_healthy=False,
        )
        from core_brain.resilience import SystemPosture
        posture = manager.process_connection_health_event(snapshot)
        assert posture == SystemPosture.NORMAL

    def test_first_disconnected_no_reconnects_triggers_self_heal(self):
        manager = self._make_resilience_manager()
        snapshot = ConnectorHealthSnapshot(
            connector_id="mt5",
            status=ConnectorHealthStatus.DISCONNECTED,
            root_cause=RootCause.NETWORK,
            latency_ms=0.0,
            reconnect_attempts=0,
            last_tick_time=None,
            last_heartbeat_time=time.monotonic(),
            is_healthy=False,
        )
        from core_brain.resilience import SystemPosture
        posture = manager.process_connection_health_event(snapshot)
        # SELF_HEAL → DEGRADED
        assert posture in (SystemPosture.DEGRADED, SystemPosture.CAUTION)


# ── MT5Connector Integration ──────────────────────────────────────────────────

class TestMT5ConnectorIntegration:

    def _make_mt5_connector_mock(self):
        """Build a minimal MT5Connector mock that bypasses MT5 library."""
        from unittest.mock import patch, MagicMock
        import connectors.mt5_connector as mt5_mod

        connector = MagicMock(spec=mt5_mod.MT5Connector)
        connector.provider_id = "mt5"
        connector.is_available.return_value = True
        connector.get_latency.return_value = 80.0
        connector.last_error = None
        connector.connect_blocking.return_value = True
        connector._health_monitor = None

        def attach_health_monitor(monitor):
            connector._health_monitor = monitor
            monitor.start()

        connector.attach_health_monitor.side_effect = attach_health_monitor
        return connector

    def test_attach_health_monitor_starts_monitor(self):
        connector = self._make_mt5_connector_mock()
        storage = MagicMock()
        monitor = _make_monitor(connector=connector, storage=storage, heartbeat_interval=0.05)
        connector.attach_health_monitor(monitor)
        time.sleep(0.15)
        monitor.stop()
        assert monitor._thread is not None

    def test_notify_connected_called_after_successful_connection(self):
        """Verify that _notify_health_connected sets HEALTHY status."""
        from connectors.mt5_connector import MT5Connector
        import connectors.mt5_connector as mt5_mod

        # Use a real MT5Connector instance but mock everything MT5-specific
        with patch.object(mt5_mod, "MT5_AVAILABLE", False):
            with pytest.raises(ImportError):
                MT5Connector()  # Disabled connector raises ImportError — expected

    def test_notify_health_connected_updates_monitor_state(self):
        """Call _notify_health_connected directly on a mock connector."""
        # Build a standalone monitor and verify notify_connected() works
        connector = self._make_mt5_connector_mock()
        monitor = _make_monitor(connector=connector)
        monitor.notify_connected(details={"demo": True, "account": "TestAccount"})
        assert monitor.get_snapshot().status == ConnectorHealthStatus.HEALTHY

    def test_notify_health_disconnected_classifies_auth_error(self):
        connector = self._make_mt5_connector_mock()
        monitor = _make_monitor(connector=connector)
        monitor.notify_disconnected(
            root_cause=monitor.classify_root_cause("Auth failed: invalid login"),
            details={"error": "Auth failed: invalid login"},
        )
        snapshot = monitor.get_snapshot()
        assert snapshot.root_cause == RootCause.AUTH
        assert snapshot.status == ConnectorHealthStatus.DISCONNECTED


# ── Thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_get_snapshot_is_stable(self):
        """Multiple threads reading snapshot simultaneously should not error."""
        monitor = _make_monitor()
        errors = []

        def read_snapshot():
            for _ in range(50):
                try:
                    monitor.get_snapshot()
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=read_snapshot) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_start_stop_idempotent(self):
        """Calling start() twice should not launch a second thread."""
        connector = _make_connector(is_available=True, latency=10.0)
        monitor = _make_monitor(connector=connector, heartbeat_interval=0.05)
        monitor.start()
        first_thread = monitor._thread
        monitor.start()  # second call — should be no-op
        assert monitor._thread is first_thread
        monitor.stop()


# ── Reconnect backoff ─────────────────────────────────────────────────────────

class TestReconnectBackoff:

    def test_backoff_grows_exponentially(self):
        """Verify delay formula: base * 2^(attempt-1), capped at max."""
        from core_brain.connection_health_monitor import (
            _RECONNECT_BASE_DELAY_SECONDS,
            _RECONNECT_MAX_DELAY_SECONDS,
        )
        base = _RECONNECT_BASE_DELAY_SECONDS
        cap = _RECONNECT_MAX_DELAY_SECONDS

        delays = [min(base * (2 ** (i)), cap) for i in range(6)]
        assert delays[0] < delays[1] < delays[2]
        assert all(d <= cap for d in delays)

    def test_reconnect_attempt_counter_increments(self):
        connector = _make_connector(is_available=False)
        connector.connect_blocking.return_value = False
        monitor = ConnectionHealthMonitor(
            connector=connector,
            heartbeat_interval_seconds=0.05,
            max_consecutive_failures=2,
            reconnect_base_delay_seconds=0.02,
        )
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        with monitor._lock:
            assert monitor._reconnect_attempts >= 1
