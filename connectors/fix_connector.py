"""
FIX 4.2 Connector for institutional prime broker connectivity.
TRACE_ID: FIX-CORE-HU51-2026-001

Implements BaseConnector using the FIX 4.2 protocol over TCP.
Uses simplefix for message encoding/parsing.

Design principles:
  - Config from sys_data_providers table (SSOT — no hardcoded addresses).
  - socket_factory is injectable for unit testing without a real broker.
  - Synchronous implementation (compatible with run_in_executor caller pattern).
  - Scope: Logon (A), Logout (5), Heartbeat (0), New Order Single (D),
    Execution Report (8), Order Cancel (F).
"""
import logging
import socket as _socket_module
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import simplefix

from connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)

# ─── FIX 4.2 Tag Constants ────────────────────────────────────────────────────
_TAG_BEGIN_STRING = 8
_TAG_MSG_TYPE = 35
_TAG_SENDER_COMP_ID = 49
_TAG_TARGET_COMP_ID = 56
_TAG_MSG_SEQ_NUM = 34
_TAG_SENDING_TIME = 52
_TAG_ENCRYPT_METHOD = 98
_TAG_HEARTBT_INT = 108
_TAG_SYMBOL = 55
_TAG_SIDE = 54
_TAG_ORD_TYPE = 40
_TAG_ORDER_QTY = 38
_TAG_PRICE = 44
_TAG_TIME_IN_FORCE = 59
_TAG_ORD_STATUS = 39
_TAG_ORDER_ID = 37
_TAG_EXEC_ID = 17
_TAG_AVG_PX = 6
_TAG_CL_ORD_ID = 11

# ─── FIX 4.2 MsgType Values ───────────────────────────────────────────────────
_MSGTYPE_HEARTBEAT = b"0"
_MSGTYPE_LOGOUT = b"5"
_MSGTYPE_LOGON = b"A"
_MSGTYPE_NEW_ORDER_SINGLE = b"D"
_MSGTYPE_ORDER_CANCEL = b"F"
_MSGTYPE_EXECUTION_REPORT = b"8"

# ─── OrdStatus Values ─────────────────────────────────────────────────────────
_ORD_STATUS_FILLED = b"2"


class FIXConnector(BaseConnector):
    """
    FIX 4.2 Connector for institutional prime broker connectivity.

    Args:
        storage: StorageManager instance (reads host/port/IDs from DB).
        socket_factory: Optional callable(host, port) -> socket-like object.
                        Default: real TCP socket. Override in tests.
    """

    def __init__(self, storage: Any, socket_factory: Optional[Callable] = None) -> None:
        self._storage = storage
        self._socket_factory = socket_factory
        self._sock: Any = None
        self._logged_in: bool = False
        self._seq_num: int = 1
        self._sender_comp_id: str = ""
        self._target_comp_id: str = ""
        self._last_latency_ms: float = 0.0
        self._positions: List[Dict[str, Any]] = []

    # ─── BaseConnector Interface ──────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Establish TCP connection and perform FIX Logon handshake.

        Returns:
            True if Logon ACK was received, False otherwise.
        """
        try:
            config = self._storage.get_data_provider_config("fix_prime")
            host: str = config["host"]
            port: int = int(config["port"])
            self._sender_comp_id = config["sender_comp_id"]
            self._target_comp_id = config["target_comp_id"]

            self._sock = self._open_socket(host, port)

            logon = self._build_message(_MSGTYPE_LOGON, [
                (_TAG_ENCRYPT_METHOD, b"0"),
                (_TAG_HEARTBT_INT, b"30"),
            ])
            self._sock.sendall(logon.encode())

            data: bytes = self._sock.recv(4096)
            if not data:
                logger.warning("FIXConnector: empty response during Logon")
                return False

            parser = simplefix.FixParser()
            parser.append_buffer(data)
            ack = parser.get_message()

            if ack and ack.get(_TAG_MSG_TYPE) == _MSGTYPE_LOGON:
                self._logged_in = True
                logger.info("FIXConnector: Logon ACK from %s", self._target_comp_id)
                return True

            logger.warning(
                "FIXConnector: Logon not acknowledged (MsgType=%s)",
                ack.get(_TAG_MSG_TYPE) if ack else None,
            )
            return False

        except Exception as exc:
            logger.error("FIXConnector.connect() error: %s", exc)
            return False

    def disconnect(self) -> bool:
        """
        Send FIX Logout and close TCP socket.

        Returns:
            True always (best-effort teardown).
        """
        try:
            if self._sock and self._logged_in:
                logout = self._build_message(_MSGTYPE_LOGOUT)
                self._sock.sendall(logout.encode())
        except Exception:
            pass
        finally:
            self._logged_in = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        logger.info("FIXConnector: disconnected")
        return True

    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """
        Send a FIX New Order Single (D) and return a normalized result dict.

        Args:
            signal: Signal object (symbol, signal_type, entry_price, volume).

        Returns:
            {'success': bool, ...} — details vary by broker response.
        """
        if not self._logged_in:
            return {"success": False, "error": "FIXConnector not connected"}

        try:
            cl_ord_id = str(uuid.uuid4())[:16].upper().encode()
            side = b"1" if signal.signal_type.value in ("BUY", "LONG") else b"2"

            order = self._build_message(_MSGTYPE_NEW_ORDER_SINGLE, [
                (_TAG_CL_ORD_ID, cl_ord_id),
                (_TAG_SYMBOL, signal.symbol.encode()),
                (_TAG_SIDE, side),
                (_TAG_ORD_TYPE, b"2"),
                (_TAG_PRICE, str(signal.entry_price).encode()),
                (_TAG_ORDER_QTY, str(signal.volume).encode()),
                (_TAG_TIME_IN_FORCE, b"0"),
            ])
            self._sock.sendall(order.encode())

            data: bytes = self._sock.recv(4096)
            return self._parse_execution_report(data)

        except Exception as exc:
            logger.error("FIXConnector.execute_order() error: %s", exc)
            return {"success": False, "error": str(exc)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Return locally tracked positions.
        FIX 4.2 has no standard position query message.
        """
        return list(self._positions)

    def is_available(self) -> bool:
        """True only when the TCP socket is open AND Logon ACK has been received."""
        return self._logged_in and self._sock is not None

    def get_latency(self) -> float:
        """Return last measured round-trip latency in milliseconds."""
        return float(self._last_latency_ms)

    def get_market_data(self, symbol: str, timeframe: str, count: int) -> None:
        """FIX 4.2 is an order routing protocol — market data not supported."""
        return None

    def get_last_tick(self, symbol: str) -> Dict[str, float]:
        """FIX 4.2 does not provide tick data."""
        return {}

    @property
    def provider_id(self) -> str:
        """Unique identifier used when registering this connector."""
        return "fix_prime"

    # ─── Private Helpers ──────────────────────────────────────────────────────

    def _open_socket(self, host: str, port: int) -> Any:
        """Open a TCP socket using the injected factory or the real socket module."""
        if self._socket_factory:
            return self._socket_factory(host, port)
        sock = _socket_module.socket(_socket_module.AF_INET, _socket_module.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((host, port))
        return sock

    def _build_message(
        self,
        msg_type: bytes,
        extra_pairs: Optional[List[tuple]] = None,
    ) -> simplefix.FixMessage:
        """
        Construct a FIX 4.2 message with the standard header.

        Args:
            msg_type: FIX MsgType value (e.g. b"A", b"D").
            extra_pairs: Additional (tag, value) tuples appended after header.

        Returns:
            Encoded-ready simplefix.FixMessage.
        """
        sending_time = datetime.now(timezone.utc).strftime("%Y%m%d-%H:%M:%S").encode()
        msg = simplefix.FixMessage()
        msg.append_pair(_TAG_BEGIN_STRING, b"FIX.4.2")
        msg.append_pair(_TAG_MSG_TYPE, msg_type)
        msg.append_pair(_TAG_SENDER_COMP_ID, self._sender_comp_id.encode()
                        if isinstance(self._sender_comp_id, str) else self._sender_comp_id)
        msg.append_pair(_TAG_TARGET_COMP_ID, self._target_comp_id.encode()
                        if isinstance(self._target_comp_id, str) else self._target_comp_id)
        msg.append_pair(_TAG_MSG_SEQ_NUM, str(self._seq_num).encode())
        msg.append_pair(_TAG_SENDING_TIME, sending_time)
        self._seq_num += 1

        if extra_pairs:
            for tag, value in extra_pairs:
                msg.append_pair(tag, value)

        return msg

    def _parse_execution_report(self, data: bytes) -> Dict[str, Any]:
        """
        Parse raw Execution Report bytes into a normalized result dict.

        Returns:
            {'success': True, ...} on fill, {'success': False, ...} on reject.
        """
        if not data:
            return {"success": False, "error": "No response from broker"}

        parser = simplefix.FixParser()
        parser.append_buffer(data)
        msg = parser.get_message()

        if not msg:
            return {"success": False, "error": "Could not parse broker response"}

        # simplefix.get(tag) returns None when tag absent.
        # The second argument of .get() is nth-occurrence, NOT a default value.
        ord_status: bytes = msg.get(_TAG_ORD_STATUS)
        if ord_status == _ORD_STATUS_FILLED:
            avg_px_raw = msg.get(_TAG_AVG_PX)
            avg_px = float(avg_px_raw.decode(errors="ignore")) if avg_px_raw else 0.0
            order_id_raw = msg.get(_TAG_ORDER_ID)
            return {
                "success": True,
                "order_id": order_id_raw.decode(errors="ignore") if order_id_raw else "",
                "avg_price": avg_px,
            }

        return {
            "success": False,
            "ord_status": ord_status.decode(errors="ignore") if ord_status else None,
            "error": "Order rejected by broker",
        }
