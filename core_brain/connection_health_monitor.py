"""
connection_health_monitor.py — HU 5.1: Monitoreo activo de conexión broker/feed.

Runs a background daemon thread that:
  - Pings the connector on every heartbeat interval
  - Classifies failure root causes (NETWORK, AUTH, FEED_INACTIVE, TIMEOUT, INTERNAL_ERROR)
  - Attempts automatic reconnection with exponential backoff
  - Persists every health event to sys_connector_health via StorageManager
  - Invokes optional callbacks for ResilienceManager and fallback logic

Design rules:
  - Never raises — all exceptions are logged and swallowed.
  - Thread-safe snapshot via internal lock.
  - Connector's DLL/API calls are NOT invoked directly; only is_available() and get_latency().

Trace_ID: EDGE-CONN-HEALTH-HU5.1-2026-04-22
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from connectors.base_connector import BaseConnector
    from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_HEARTBEAT_INTERVAL_SECONDS: float = 10.0
_MAX_CONSECUTIVE_FAILURES: int = 3
_RECONNECT_BASE_DELAY_SECONDS: float = 5.0
_RECONNECT_MAX_DELAY_SECONDS: float = 120.0
_LATENCY_DEGRADED_THRESHOLD_MS: float = 2000.0

# ── Event type constants (stored in sys_connector_health.event_type) ──────────

EVENT_CONNECTED = "CONNECTED"
EVENT_DISCONNECTED = "DISCONNECTED"
EVENT_HEARTBEAT_FAIL = "HEARTBEAT_FAIL"
EVENT_HEARTBEAT_OK = "HEARTBEAT_OK"
EVENT_RECONNECT_ATTEMPT = "RECONNECT_ATTEMPT"
EVENT_RECONNECT_SUCCESS = "RECONNECT_SUCCESS"
EVENT_RECONNECT_FAILED = "RECONNECT_FAILED"
EVENT_FALLBACK_TRIGGERED = "FALLBACK_TRIGGERED"
EVENT_LATENCY_DEGRADED = "LATENCY_DEGRADED"


# ── Enums ─────────────────────────────────────────────────────────────────────

class ConnectorHealthStatus(str, Enum):
    """Operational health status of a connector."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    UNKNOWN = "UNKNOWN"


class RootCause(str, Enum):
    """Classified root cause of a connector failure."""
    NETWORK = "NETWORK"
    AUTH = "AUTH"
    FEED_INACTIVE = "FEED_INACTIVE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


# ── Value Object ──────────────────────────────────────────────────────────────

@dataclass
class ConnectorHealthSnapshot:
    """Point-in-time health state of a connector (immutable view)."""
    connector_id: str
    status: ConnectorHealthStatus
    root_cause: Optional[RootCause]
    latency_ms: float
    reconnect_attempts: int
    last_tick_time: Optional[float]
    last_heartbeat_time: float
    is_healthy: bool
    details: Dict[str, Any] = field(default_factory=dict)


# ── Main class ────────────────────────────────────────────────────────────────

class ConnectionHealthMonitor:
    """
    Active health monitor for broker/feed connectors.

    Instantiate once per connector, call start() after the connector is
    initialized.  The monitor never forces reconnections from inside the DLL
    thread — it calls connect_blocking() or connect() via a normal Python
    thread, which the connector itself routes safely.

    Args:
        connector: Any object implementing BaseConnector (is_available,
                   get_latency, provider_id).
        storage: StorageManager used to persist events. Pass None to skip DB.
        on_health_change: Callback fired on every status transition.
        on_fallback: Callback fired when reconnect exhausts without success.
        heartbeat_interval_seconds: Seconds between health checks.
        max_consecutive_failures: Failures before a reconnect is triggered.
    """

    def __init__(
        self,
        connector: "BaseConnector",
        storage: Optional["StorageManager"] = None,
        on_health_change: Optional[Callable[[ConnectorHealthSnapshot], None]] = None,
        on_fallback: Optional[Callable[[ConnectorHealthSnapshot], None]] = None,
        heartbeat_interval_seconds: float = _HEARTBEAT_INTERVAL_SECONDS,
        max_consecutive_failures: int = _MAX_CONSECUTIVE_FAILURES,
        reconnect_base_delay_seconds: float = _RECONNECT_BASE_DELAY_SECONDS,
    ) -> None:
        self._connector = connector
        self._storage = storage
        self._on_health_change = on_health_change
        self._on_fallback = on_fallback
        self._heartbeat_interval = heartbeat_interval_seconds
        self._max_failures = max_consecutive_failures
        self._reconnect_base_delay = reconnect_base_delay_seconds

        # Mutable state — always accessed under self._lock
        self._status: ConnectorHealthStatus = ConnectorHealthStatus.UNKNOWN
        self._root_cause: Optional[RootCause] = None
        self._latency_ms: float = 0.0
        self._reconnect_attempts: int = 0
        self._consecutive_failures: int = 0
        self._last_heartbeat_time: float = time.monotonic()
        self._last_tick_time: Optional[float] = None
        self._lock = threading.Lock()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def connector_id(self) -> str:
        """Unique identifier taken from the connector's provider_id."""
        return self._connector.provider_id

    def start(self) -> None:
        """Start the background heartbeat daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.debug("[HealthMonitor:%s] Already running", self.connector_id)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"HealthMonitor-{self.connector_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[HealthMonitor:%s] Started (interval=%.0fs)", self.connector_id, self._heartbeat_interval)

    def stop(self) -> None:
        """Stop the heartbeat monitor (blocks up to 5 s for clean shutdown)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("[HealthMonitor:%s] Stopped", self.connector_id)

    def get_snapshot(self) -> ConnectorHealthSnapshot:
        """Return a thread-safe point-in-time snapshot of current health."""
        with self._lock:
            return ConnectorHealthSnapshot(
                connector_id=self.connector_id,
                status=self._status,
                root_cause=self._root_cause,
                latency_ms=self._latency_ms,
                reconnect_attempts=self._reconnect_attempts,
                last_tick_time=self._last_tick_time,
                last_heartbeat_time=self._last_heartbeat_time,
                is_healthy=self._status == ConnectorHealthStatus.HEALTHY,
                details={"consecutive_failures": self._consecutive_failures},
            )

    def notify_connected(self, details: Optional[Dict[str, Any]] = None) -> None:
        """Notify the monitor that the connector successfully established a connection."""
        with self._lock:
            self._status = ConnectorHealthStatus.HEALTHY
            self._root_cause = None
            self._consecutive_failures = 0
        self._persist_event(EVENT_CONNECTED, None, details or {})
        self._emit_health_change()

    def notify_disconnected(
        self,
        root_cause: Optional[RootCause] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Notify the monitor that the connector lost its connection."""
        rc = root_cause or RootCause.UNKNOWN
        with self._lock:
            self._status = ConnectorHealthStatus.DISCONNECTED
            self._root_cause = rc
        self._persist_event(EVENT_DISCONNECTED, rc, details or {})
        self._emit_health_change()

    def classify_root_cause(self, error_message: str) -> RootCause:
        """
        Public helper: classify a free-text error into a RootCause.

        Priority order:
          AUTH    — auth / login / password / unauthorized / credential
          TIMEOUT — timeout / timed out / connection timed
          FEED    — feed / tick / market data / no data
          NETWORK — network / connection refused / socket / errno / unreachable
          INTERNAL— any other non-empty string
          UNKNOWN — empty / None
        """
        return self._classify_root_cause(error_message)

    # ── Private — heartbeat loop ──────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_heartbeat()
            except Exception as exc:
                logger.error("[HealthMonitor:%s] Unexpected error: %s", self.connector_id, exc)
            self._stop_event.wait(timeout=self._heartbeat_interval)

    def _run_heartbeat(self) -> None:
        try:
            is_up = self._connector.is_available()
            latency = self._connector.get_latency() if is_up else 0.0
        except Exception as exc:
            is_up = False
            latency = 0.0
            logger.warning("[HealthMonitor:%s] Exception during heartbeat probe: %s", self.connector_id, exc)

        with self._lock:
            self._latency_ms = latency
            self._last_heartbeat_time = time.monotonic()

        if is_up:
            self._handle_heartbeat_success(latency)
        else:
            self._handle_heartbeat_failure()

    def _handle_heartbeat_success(self, latency_ms: float) -> None:
        with self._lock:
            prev_status = self._status
            self._consecutive_failures = 0
            if latency_ms > _LATENCY_DEGRADED_THRESHOLD_MS:
                self._status = ConnectorHealthStatus.DEGRADED
            else:
                self._status = ConnectorHealthStatus.HEALTHY
                self._root_cause = None

        if prev_status != self._status:
            event = (
                EVENT_LATENCY_DEGRADED
                if self._status == ConnectorHealthStatus.DEGRADED
                else EVENT_HEARTBEAT_OK
            )
            self._persist_event(event, None, {"latency_ms": latency_ms})
            self._emit_health_change()

    def _handle_heartbeat_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            failures = self._consecutive_failures

        root_cause = self._classify_root_cause_from_connector()
        self._persist_event(
            EVENT_HEARTBEAT_FAIL,
            root_cause,
            {"consecutive_failures": failures},
        )

        with self._lock:
            prev_status = self._status
            self._status = ConnectorHealthStatus.DISCONNECTED
            self._root_cause = root_cause

        if prev_status != ConnectorHealthStatus.DISCONNECTED:
            self._emit_health_change()

        if failures >= self._max_failures:
            self._attempt_reconnect(root_cause)

    # ── Private — reconnect & fallback ───────────────────────────────────────

    def _attempt_reconnect(self, root_cause: RootCause) -> None:
        with self._lock:
            self._reconnect_attempts += 1
            attempt = self._reconnect_attempts
            self._status = ConnectorHealthStatus.RECONNECTING

        delay = min(
            self._reconnect_base_delay * (2 ** (attempt - 1)),
            _RECONNECT_MAX_DELAY_SECONDS,
        )
        self._persist_event(
            EVENT_RECONNECT_ATTEMPT,
            root_cause,
            {"attempt": attempt, "backoff_seconds": delay},
        )
        self._emit_health_change()

        logger.info(
            "[HealthMonitor:%s] Reconnect #%d in %.0fs (root_cause=%s)",
            self.connector_id, attempt, delay, root_cause.value,
        )

        if self._stop_event.wait(timeout=delay):
            return  # Monitor stopped during backoff

        success = self._invoke_reconnect()

        if success:
            with self._lock:
                self._status = ConnectorHealthStatus.HEALTHY
                self._root_cause = None
                self._consecutive_failures = 0
            self._persist_event(EVENT_RECONNECT_SUCCESS, None, {"attempt": attempt})
            self._emit_health_change()
            logger.info("[HealthMonitor:%s] Reconnect #%d succeeded", self.connector_id, attempt)
        else:
            with self._lock:
                self._status = ConnectorHealthStatus.DISCONNECTED
            self._persist_event(EVENT_RECONNECT_FAILED, root_cause, {"attempt": attempt})
            self._emit_health_change()
            self._trigger_fallback()

    def _invoke_reconnect(self) -> bool:
        """Call the connector's reconnect method, preferring connect_blocking."""
        try:
            connect_fn = getattr(self._connector, "connect_blocking", None)
            if connect_fn is None:
                connect_fn = getattr(self._connector, "connect", None)
            if connect_fn is None:
                return False
            result = connect_fn()
            return bool(result)
        except Exception as exc:
            logger.error("[HealthMonitor:%s] Reconnect exception: %s", self.connector_id, exc)
            return False

    def _trigger_fallback(self) -> None:
        snapshot = self.get_snapshot()
        self._persist_event(EVENT_FALLBACK_TRIGGERED, snapshot.root_cause, {})
        logger.warning(
            "[HealthMonitor:%s] Fallback triggered after %d attempts (cause=%s)",
            self.connector_id,
            snapshot.reconnect_attempts,
            snapshot.root_cause,
        )
        if self._on_fallback:
            try:
                self._on_fallback(snapshot)
            except Exception as exc:
                logger.error("[HealthMonitor:%s] Fallback callback error: %s", self.connector_id, exc)

    # ── Private — root cause classification ───────────────────────────────────

    def _classify_root_cause_from_connector(self) -> RootCause:
        try:
            last_error = getattr(self._connector, "last_error", None)
            return self._classify_root_cause(str(last_error) if last_error else "")
        except Exception:
            return RootCause.UNKNOWN

    def _classify_root_cause(self, error_message: str) -> RootCause:
        if not error_message or error_message.strip().lower() in ("none", ""):
            return RootCause.UNKNOWN

        msg = error_message.lower()

        if any(k in msg for k in ("auth", "login", "password", "unauthorized", "credential")):
            return RootCause.AUTH
        if any(k in msg for k in ("timeout", "timed out", "connection timed")):
            return RootCause.TIMEOUT
        if any(k in msg for k in ("feed", "tick", "market data", "no data")):
            return RootCause.FEED_INACTIVE
        if any(k in msg for k in ("network", "connection refused", "socket", "errno", "unreachable", "reset by peer")):
            return RootCause.NETWORK
        return RootCause.INTERNAL_ERROR

    # ── Private — callbacks & persistence ────────────────────────────────────

    def _emit_health_change(self) -> None:
        if self._on_health_change:
            try:
                self._on_health_change(self.get_snapshot())
            except Exception as exc:
                logger.error(
                    "[HealthMonitor:%s] on_health_change callback error: %s",
                    self.connector_id, exc,
                )

    def _persist_event(
        self,
        event_type: str,
        root_cause: Optional[RootCause],
        details: Dict[str, Any],
    ) -> None:
        """Write health event to DB. Never raises."""
        if not self._storage:
            return
        try:
            snapshot = self.get_snapshot()
            self._storage.record_connector_health_event(
                connector_id=self.connector_id,
                event_type=event_type,
                root_cause=root_cause.value if root_cause else None,
                latency_ms=snapshot.latency_ms,
                reconnect_attempts=snapshot.reconnect_attempts,
                is_healthy=snapshot.is_healthy,
                details=details,
            )
        except Exception as exc:
            logger.warning(
                "[HealthMonitor:%s] DB persist failed for event %s: %s",
                self.connector_id, event_type, exc,
            )
