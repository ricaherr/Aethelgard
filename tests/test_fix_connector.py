"""
TDD tests for FIXConnector — HU 5.1: FIX Protocol Core Connector.
TRACE_ID: FIX-CORE-HU51-2026-001

These tests exercise:
  - BaseConnector interface compliance
  - TCP Logon handshake (MsgType=A)
  - Config sourced from storage (SSOT, not hardcoded)
  - is_available() lifecycle
  - New Order Single (MsgType=D) construction
  - Execution Report parsing (fill vs reject)
  - Logout handshake (MsgType=5)
  - get_latency() type contract
"""
import pytest
import simplefix
from unittest.mock import MagicMock

from connectors.base_connector import BaseConnector


# ─── Test Fixtures & Builders ─────────────────────────────────────────────────

class MockSocket:
    """Sync socket replacement for FIX connector tests (no real TCP needed)."""

    def __init__(self, responses=None) -> None:
        self.sent_data = b""
        self._responses = list(responses) if responses else []
        self._recv_idx = 0

    def sendall(self, data: bytes) -> None:
        self.sent_data += data

    def recv(self, n: int) -> bytes:
        if self._recv_idx < len(self._responses):
            resp = self._responses[self._recv_idx]
            self._recv_idx += 1
            return resp
        return b""

    def close(self) -> None:
        pass


def _make_storage(host="fix.broker.com", port=9876,
                  sender="AETHELGARD", target="BROKER"):
    """Return a mock StorageManager with pre-configured fix_prime provider."""
    storage = MagicMock()
    storage.get_data_provider_config.return_value = {
        "host": host,
        "port": port,
        "sender_comp_id": sender,
        "target_comp_id": target,
        "username": "test_user",
        "password": "test_pass",
    }
    return storage


def _socket_factory(responses=None):
    """Return (factory_callable, mock_socket)."""
    sock = MockSocket(responses)

    def factory(host: str, port: int) -> MockSocket:
        return sock

    return factory, sock


def _build_logon_ack(sender="BROKER", target="AETHELGARD") -> bytes:
    """Build an encoded FIX 4.2 Logon ACK."""
    msg = simplefix.FixMessage()
    msg.append_pair(8, b"FIX.4.2")
    msg.append_pair(35, b"A")
    msg.append_pair(49, sender.encode())
    msg.append_pair(56, target.encode())
    msg.append_pair(34, b"1")
    msg.append_pair(52, b"20260101-00:00:00")
    msg.append_pair(98, b"0")
    msg.append_pair(108, b"30")
    return msg.encode()


def _build_execution_report(ord_status="2") -> bytes:
    """Build an encoded FIX 4.2 Execution Report (2 = Filled, 8 = Rejected)."""
    msg = simplefix.FixMessage()
    msg.append_pair(8, b"FIX.4.2")
    msg.append_pair(35, b"8")
    msg.append_pair(49, b"BROKER")
    msg.append_pair(56, b"AETHELGARD")
    msg.append_pair(34, b"2")
    msg.append_pair(52, b"20260101-00:00:00")
    msg.append_pair(17, b"EXEC001")
    msg.append_pair(37, b"ORD001")
    msg.append_pair(39, ord_status.encode())
    exec_type = b"F" if ord_status == "2" else b"8"
    msg.append_pair(150, exec_type)
    msg.append_pair(55, b"EURUSD")
    msg.append_pair(54, b"1")
    msg.append_pair(14, b"1")
    msg.append_pair(6, b"1.10000")
    msg.append_pair(151, b"0")
    return msg.encode()


def _make_test_signal():
    """Return a minimal BUY Signal for EURUSD."""
    from models.signal import Signal, SignalType, ConnectorType
    return Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=75.0,
        connector_type=ConnectorType.GENERIC,
        entry_price=1.10000,
        stop_loss=1.09500,
        take_profit=1.11000,
        volume=0.01,
    )


# ─── Late import (will fail until fix_connector.py exists — expected in RED phase)

from connectors.fix_connector import FIXConnector  # noqa: E402


# ─── AC-01 / AC-02: Interface & Identity ─────────────────────────────────────

class TestFIXConnectorInterface:
    """AC-01: FIXConnector must implement the BaseConnector interface."""

    def test_inherits_base_connector(self):
        factory, _ = _socket_factory()
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        assert isinstance(connector, BaseConnector)

    def test_provider_id_is_fix_prime(self):
        """AC-02: provider_id must return 'fix_prime'."""
        factory, _ = _socket_factory()
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        assert connector.provider_id == "fix_prime"


# ─── AC-03: Logon Handshake ───────────────────────────────────────────────────

class TestFIXConnectorConnect:
    """AC-03: connect() must perform FIX 4.2 Logon handshake."""

    def test_connect_sends_logon_message(self):
        """Logon payload must contain MsgType=A (tag 35)."""
        factory, sock = _socket_factory([_build_logon_ack()])
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        connector.connect()
        assert b"35=A" in sock.sent_data

    def test_logon_reads_sender_comp_id_from_storage(self):
        """SenderCompID (tag 49) must come from storage, not be hardcoded."""
        logon_ack = _build_logon_ack(sender="PRIME_BROKER", target="MY_SYSTEM")
        factory, sock = _socket_factory([logon_ack])
        storage = _make_storage(sender="MY_SYSTEM", target="PRIME_BROKER")
        connector = FIXConnector(storage=storage, socket_factory=factory)
        connector.connect()
        assert b"49=MY_SYSTEM" in sock.sent_data

    def test_logon_reads_target_comp_id_from_storage(self):
        """TargetCompID (tag 56) must come from storage, not be hardcoded."""
        logon_ack = _build_logon_ack(sender="PRIME_BROKER", target="MY_SYSTEM")
        factory, sock = _socket_factory([logon_ack])
        storage = _make_storage(sender="MY_SYSTEM", target="PRIME_BROKER")
        connector = FIXConnector(storage=storage, socket_factory=factory)
        connector.connect()
        assert b"56=PRIME_BROKER" in sock.sent_data

    def test_connect_returns_false_when_no_logon_ack(self):
        """connect() must return False when broker returns no valid Logon ACK."""
        factory, _ = _socket_factory([b""])
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        result = connector.connect()
        assert result is False


# ─── AC-04: Availability Lifecycle ───────────────────────────────────────────

class TestFIXConnectorAvailability:
    """AC-04: is_available() must reflect connection state accurately."""

    def test_is_available_false_before_connect(self):
        factory, _ = _socket_factory()
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        assert connector.is_available() is False

    def test_is_available_true_after_successful_logon(self):
        factory, _ = _socket_factory([_build_logon_ack()])
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        result = connector.connect()
        assert result is True
        assert connector.is_available() is True


# ─── AC-05 / AC-06 / AC-07: Order Execution ──────────────────────────────────

class TestFIXConnectorExecuteOrder:
    """AC-05/06/07: execute_order() must build and parse FIX order messages."""

    def _make_connector(self, extra_responses=None):
        """Build a connector pre-connected with optional extra socket responses."""
        responses = [_build_logon_ack()]
        if extra_responses:
            responses.extend(extra_responses)
        factory, sock = _socket_factory(responses)
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        connector.connect()
        return connector, sock

    def test_execute_order_sends_new_order_single(self):
        """AC-05: execute_order() must send FIX New Order Single (MsgType=D)."""
        connector, sock = self._make_connector([_build_execution_report("2")])
        connector.execute_order(_make_test_signal())
        assert b"35=D" in sock.sent_data

    def test_execute_order_includes_symbol(self):
        """AC-05: New Order Single must include Symbol (tag 55)."""
        connector, sock = self._make_connector([_build_execution_report("2")])
        connector.execute_order(_make_test_signal())
        assert b"55=EURUSD" in sock.sent_data

    def test_execute_order_returns_success_on_fill(self):
        """AC-06: OrdStatus=2 (Filled) → success=True."""
        connector, _ = self._make_connector([_build_execution_report("2")])
        result = connector.execute_order(_make_test_signal())
        assert result.get("success") is True

    def test_execute_order_returns_failure_on_reject(self):
        """AC-07: OrdStatus=8 (Rejected) → success=False."""
        connector, _ = self._make_connector([_build_execution_report("8")])
        result = connector.execute_order(_make_test_signal())
        assert result.get("success") is False


# ─── AC-08: Logout Handshake ──────────────────────────────────────────────────

class TestFIXConnectorDisconnect:
    """AC-08: disconnect() must send FIX Logout (MsgType=5)."""

    def test_disconnect_sends_logout(self):
        factory, sock = _socket_factory([_build_logon_ack()])
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        connector.connect()
        connector.disconnect()
        assert b"35=5" in sock.sent_data


# ─── AC-09: Latency ───────────────────────────────────────────────────────────

class TestFIXConnectorLatency:
    """AC-09: get_latency() must return float without raising."""

    def test_get_latency_returns_float(self):
        factory, _ = _socket_factory()
        connector = FIXConnector(storage=_make_storage(), socket_factory=factory)
        latency = connector.get_latency()
        assert isinstance(latency, float)
