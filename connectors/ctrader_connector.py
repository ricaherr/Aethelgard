"""
CTrader Connector — Spotware Open API
======================================
Primary FOREX connector for Aethelgard.

Architecture:
  - WebSocket streaming: OHLC bars via protobuf (ctrader-open-api, asyncio, no Twisted)
  - REST execution:      market orders via api.spotware.com (oauth_token + ctidTraderAccountId)
  - No DLL dependency:   natively async, compatible with asyncio event loop

Wire protocol (Spotware Open API):
  - Binary WebSocket frames, each frame = serialized ProtoMessage bytes
  - ProtoMessage envelope: {payloadType, payload (inner message bytes), clientMsgId}
  - Prices stored as integer points (×10^digits), delta-encoded relative to bar low

Credentials (sys_data_providers.additional_config for name="ctrader"):
  - access_token:          OAuth2 bearer token (Spotware Developer Portal)
  - account_number:        Broker-visible account number (e.g. 9920997)
  - ctid_trader_account_id: Internal Spotware ID (e.g. 46662210) — used in REST calls
  - client_id:             Application client ID
  - client_secret:         Application client secret
  - account_type:          "DEMO" or "LIVE"
"""
import asyncio
import logging
import struct
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from connectors.base_connector import BaseConnector
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# Spotware Open API endpoints
_DEMO_WS_HOST = "demo.ctraderapi.com"
_LIVE_WS_HOST = "live.ctraderapi.com"
_WS_PORT = 5035
_REST_BASE = "https://api.spotware.com"

# Timeframe → ProtoOATrendbarPeriod integer values (confirmed via protobuf enum)
_PERIOD_MAP: Dict[str, int] = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M10": 6,
    "M15": 7,
    "M30": 8,
    "H1": 9,
    "H4": 10,
    "H12": 11,
    "D1": 12,
    "W1": 13,
    "MN1": 14,
}

# ProtoOAPayloadType integer values (confirmed via protobuf enum)
_PT_APP_AUTH_REQ    = 2100
_PT_APP_AUTH_RES    = 2101
_PT_ACCT_AUTH_REQ   = 2102
_PT_ACCT_AUTH_RES   = 2103
_PT_ERROR_RES       = 2142
_PT_SYMBOLS_REQ     = 2114
_PT_SYMBOLS_RES     = 2115
_PT_TRENDBARS_REQ   = 2137
_PT_TRENDBARS_RES   = 2138
_PT_NEW_ORDER_REQ   = 2104
_PT_POSITIONS_REQ   = 2134  # ProtoOAReconcileReq — lists open positions
_PT_POSITIONS_RES   = 2135

# WebSocket connect timeout (seconds)
_WS_CONNECT_TIMEOUT = 30
# Per-message receive timeout (seconds)
_WS_MSG_TIMEOUT = 15


class CTraderConnector(BaseConnector):
    """
    cTrader Open API Connector.

    Provides:
      - Historical OHLC bars via WebSocket protobuf (Spotware Open API)
      - Market order execution via REST (api.spotware.com + oauth_token)
      - Open positions via REST
      - Real-time tick cache updated by WebSocket spot events

    Credentials injected by DataProviderManager from sys_data_providers.additional_config.
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        account_id: Optional[str] = None,
        access_token: Optional[str] = None,
        account_number: Optional[str] = None,
        ctid_trader_account_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        account_type: str = "DEMO",
        account_name: Optional[str] = None,
    ) -> None:
        self.storage = storage
        self.account_id = account_id

        self.config: Dict[str, Any] = self._build_config(
            access_token=access_token,
            account_number=account_number,
            ctid_trader_account_id=ctid_trader_account_id,
            client_id=client_id,
            client_secret=client_secret,
            account_type=account_type,
            account_name=account_name,
        )
        self._connected: bool = False
        self._tick_cache: Dict[str, Dict[str, float]] = {}
        self._symbol_id_cache: Dict[str, int] = {}   # "EURUSD" → symbolId
        self._symbol_digits_cache: Dict[int, int] = {}  # symbolId → digits
        self._latency: float = 0.0
        # Serialise fetch_ohlc calls: only one WebSocket operation at a time.
        self._ws_lock = threading.Lock()

        # Persistent WebSocket session (N1-8 — CTRADER-SESSION-PERSIST-2026-03-25).
        # Authenticated once per process lifetime; reused across all fetch_ohlc()
        # calls. The session lives on _event_loop (a dedicated background thread).
        # Using asyncio.run() or run_until_complete() would close the loop after
        # each call, destroying the WebSocket — hence the dedicated loop pattern.
        self._session_ws: Optional[Any] = None
        # Proactive session management: invalidate before CTrader server expires (~120s idle).
        # This eliminates the reactive payloadType=2142 error on stale sessions.
        self._session_last_used_at: float = 0.0
        _SESSION_MAX_IDLE_SECS = 90  # preemptive reconnect at 90s (server expires at ~120s)
        self._SESSION_MAX_IDLE_SECS = _SESSION_MAX_IDLE_SECS
        self._event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._event_loop.run_forever,
            daemon=True,
            name="CTrader-EventLoop",
        )
        self._loop_thread.start()

        logger.info(
            f"[CTrader] Connector initialized. enabled={self.config.get('enabled')}, "
            f"host={self.config.get('ws_host', 'N/A')}"
        )

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _build_config(
        self,
        access_token: Optional[str],
        account_number: Optional[str],
        ctid_trader_account_id: Optional[str],
        client_id: Optional[str],
        client_secret: Optional[str],
        account_type: str,
        account_name: Optional[str],
    ) -> Dict[str, Any]:
        """Build connector config from injected credentials (sys_data_providers)."""
        if not access_token or not account_number:
            logger.warning(
                "[CTrader] Credentials not configured. "
                "Set access_token and account_number in sys_data_providers.additional_config."
            )
            return {"enabled": False}

        account_type = (account_type or "DEMO").upper()
        is_demo = account_type == "DEMO"

        return {
            "enabled": True,
            "account_id": self.account_id,
            "account_number": account_number,
            "ctid_trader_account_id": ctid_trader_account_id or "",
            "account_name": account_name,
            "account_type": account_type,
            "ws_host": _DEMO_WS_HOST if is_demo else _LIVE_WS_HOST,
            "access_token": access_token,
            "client_id": client_id or "",
            "client_secret": client_secret or "",
        }

    # ------------------------------------------------------------------
    # BaseConnector: provider identity
    # ------------------------------------------------------------------

    @property
    def provider_id(self) -> str:
        return "ctrader"

    def is_local(self) -> bool:
        """cTrader is a remote WebSocket API — not local like MT5 DLL."""
        return False

    def _is_rest_ready(self) -> bool:
        """True when credentials are present (independent of active WebSocket state)."""
        return bool(
            self.config.get("enabled")
            and self.config.get("access_token")
            and self.config.get("account_number")
        )

    def is_available(self) -> bool:
        """Available when valid credentials exist; WebSocket is established on first use."""
        return self._is_rest_ready()

    def get_latency(self) -> float:
        return self._latency

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Establish WebSocket connection to cTrader Open API.
        Runs the async handshake synchronously. Returns True on success.
        """
        if not self.config.get("enabled"):
            logger.warning("[CTrader] Connector disabled — no account configured.")
            return False

        if self._connected:
            return True

        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    fut = asyncio.run_coroutine_threadsafe(self._connect_async(), loop)
                    return fut.result(timeout=_WS_CONNECT_TIMEOUT)
                else:
                    return loop.run_until_complete(self._connect_async())
            except RuntimeError:
                return asyncio.run(self._connect_async())
        except Exception as exc:
            logger.error(f"[CTrader] Connection failed: {exc}")
            self._connected = False
            return False

    async def _connect_async(self) -> bool:
        """Async WebSocket handshake — APP_AUTH + ACCOUNT_AUTH."""
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("[CTrader] 'websockets' not installed. Run: pip install websockets")
            return False

        host = self.config.get("ws_host", _DEMO_WS_HOST)
        uri = f"wss://{host}:{_WS_PORT}/"
        try:
            t0 = time.monotonic()
            ws = await websockets.connect(uri, ping_interval=20, ping_timeout=10)
            self._latency = (time.monotonic() - t0) * 1000

            # Step 1: Application authentication
            app_auth = _build_app_auth_req(
                client_id=self.config.get("client_id", ""),
                client_secret=self.config.get("client_secret", ""),
            )
            await ws.send(app_auth)
            resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
            pt, _ = _parse_proto_response(resp)
            if pt != _PT_APP_AUTH_RES:
                logger.error(f"[CTrader] App auth failed — unexpected payloadType {pt}")
                await ws.close()
                return False

            # Step 2: Account authentication
            ctid = self.config.get("ctid_trader_account_id", "")
            if ctid:
                acct_auth = _build_acct_auth_req(
                    ctid_trader_account_id=int(ctid),
                    access_token=self.config.get("access_token", ""),
                )
                await ws.send(acct_auth)
                resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
                pt, _ = _parse_proto_response(resp)
                if pt != _PT_ACCT_AUTH_RES:
                    logger.warning(
                        f"[CTrader] Account auth returned payloadType={pt} "
                        f"(may still work for data-only)"
                    )

            self._connected = True
            logger.info(
                f"[CTrader] Connected | host={host} | latency={self._latency:.1f}ms | "
                f"account={self.config.get('account_name', 'N/A')}"
            )
            await ws.close()
            return True

        except Exception as exc:
            logger.error(f"[CTrader] WebSocket handshake failed: {exc}")
            self._connected = False
            return False

    def disconnect(self) -> bool:
        """Mark connector as disconnected (clears symbol cache and persistent session)."""
        self._connected = False
        self._symbol_id_cache.clear()
        self._symbol_digits_cache.clear()
        self._session_ws = None
        logger.info("[CTrader] Disconnected.")
        return True

    # ------------------------------------------------------------------
    # Tick data
    # ------------------------------------------------------------------

    def get_last_tick(self, symbol: str) -> Dict[str, float]:
        """Return latest cached tick for symbol. Falls back to zeros if not cached."""
        return self._tick_cache.get(symbol, {"bid": 0.0, "ask": 0.0, "time": 0.0})

    def _update_tick_cache(self, symbol: str, bid: float, ask: float) -> None:
        """Called by WebSocket spot event handler to update tick cache."""
        self._tick_cache[symbol] = {"bid": bid, "ask": ask, "time": time.time()}

    # ------------------------------------------------------------------
    # OHLC data — WebSocket protobuf protocol
    # ------------------------------------------------------------------

    def fetch_ohlc(
        self, symbol: str, timeframe: str = "M5", count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLC bars via Spotware Open API WebSocket protocol.
        Returns normalized DataFrame or None on error.
        """
        if not self._is_rest_ready():
            return None

        # Serialise calls and dispatch to the dedicated persistent event loop.
        # _event_loop never closes → session WebSocket survives across calls.
        with self._ws_lock:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._fetch_bars_via_websocket(symbol, timeframe, count),
                    self._event_loop,
                )
                bars = fut.result(timeout=_WS_CONNECT_TIMEOUT)
            except Exception as exc:
                logger.error(f"[CTrader] fetch_ohlc error for {symbol}/{timeframe}: {exc}")
                return None

        if not bars:
            return None

        df = pd.DataFrame(bars)
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = 0.0

        return df[["time", "open", "high", "low", "close", "volume"]]

    async def _fetch_bars_via_websocket(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLC bars via Spotware Open API with persistent session.

        Session lifecycle (N1-8):
          - First call: connect + authenticate (steps 1-2) + fetch (steps 3-4).
            Session stored in self._session_ws for reuse.
          - Subsequent calls: reuse existing session → only steps 3-4 (no re-auth).
          - On ConnectionClosed or any send/recv error: invalidate session,
            reconnect transparently and re-authenticate before fetching.

        This reduces APP_AUTH_REQ from O(N_symbols × N_cycles) to O(1_per_session),
        staying within Spotware's rate-limit window.
        """
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("[CTrader] 'websockets' not installed.")
            return []

        # Reuse existing authenticated session when possible.
        # All calls arrive on self._event_loop (dedicated thread), so no loop
        # identity check is needed — the loop is always the same.
        if self._session_ws is not None:
            idle_secs = time.monotonic() - self._session_last_used_at
            if idle_secs > self._SESSION_MAX_IDLE_SECS:
                logger.info(
                    f"[CTrader] Sesión inactiva {idle_secs:.0f}s — reconexión preventiva "
                    f"(límite={self._SESSION_MAX_IDLE_SECS}s)."
                )
                await self._invalidate_session()
            else:
                try:
                    bars = await self._fetch_bars_on_session(self._session_ws, symbol, timeframe, count)
                    self._session_last_used_at = time.monotonic()
                    return bars
                except Exception as exc:
                    logger.warning(f"[CTrader] Reutilización de sesión fallida: {exc}. Intentando reconexión.")
                    await self._invalidate_session()

        # (Re)connect and authenticate.
        host = self.config.get("ws_host", _DEMO_WS_HOST)
        uri = f"wss://{host}:{_WS_PORT}/"
        try:
            ws = await websockets.connect(uri, ping_interval=20, ping_timeout=10)
        except Exception as exc:
            logger.error(f"[CTrader] WS connect failed: {exc}")
            return []

        if not await self._authenticate_session(ws):
            try:
                await ws.close()
            except Exception:
                pass
            return []

        self._session_ws = ws
        self._session_last_used_at = time.monotonic()
        logger.debug("[CTrader] New authenticated session established.")

        try:
            bars = await self._fetch_bars_on_session(ws, symbol, timeframe, count)
            self._session_last_used_at = time.monotonic()
            return bars
        except Exception as exc:
            logger.error(f"[CTrader] fetch after fresh auth failed: {exc}")
            await self._invalidate_session()
            return []

    async def _authenticate_session(self, ws: Any) -> bool:
        """Steps 1-2: APP_AUTH_REQ + ACCOUNT_AUTH_REQ. Returns True on success."""
        client_id = self.config.get("client_id", "")
        client_secret = self.config.get("client_secret", "")
        access_token = self.config.get("access_token", "")
        ctid_raw = self.config.get("ctid_trader_account_id", "")

        if not ctid_raw:
            logger.error("[CTrader] ctid_trader_account_id no configurado — autenticación imposible.")
            return False

        ctid = int(ctid_raw)

        try:
            await ws.send(_build_app_auth_req(client_id, client_secret))
            resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
            pt, _ = _parse_proto_response(resp)
            if pt == _PT_ERROR_RES:
                logger.error(f"[CTrader] App auth falló: RATE-LIMIT o credenciales inválidas (payloadType=2142)")
                return False
            if pt != _PT_APP_AUTH_RES:
                logger.error(f"[CTrader] App auth falló: payloadType inesperado {pt}")
                return False
            logger.info("[CTrader] App auth OK")

            await ws.send(_build_acct_auth_req(ctid, access_token))
            resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
            pt, _ = _parse_proto_response(resp)
            if pt == _PT_ERROR_RES:
                logger.error(f"[CTrader] Account auth falló: RATE-LIMIT o credenciales inválidas (payloadType=2142)")
                return False
            if pt != _PT_ACCT_AUTH_RES:
                logger.error(f"[CTrader] Account auth falló: payloadType inesperado {pt}")
                return False
            logger.info("[CTrader] Account auth OK")
        except Exception as exc:
            logger.error(f"[CTrader] Error de autenticación: {exc}")
            return False

        return True

    async def _fetch_bars_on_session(
        self, ws: Any, symbol: str, timeframe: str, count: int
    ) -> List[Dict[str, Any]]:
        """Steps 3-4 on an already-authenticated WebSocket: resolve symbol + get trendbars."""
        ctid = int(self.config.get("ctid_trader_account_id", 0))

        symbol_id = self._symbol_id_cache.get(symbol)
        digits = self._symbol_digits_cache.get(symbol_id or -1, 5)

        if symbol_id is None:
            symbol_id, digits = await self._resolve_symbol_id(ws, ctid, symbol)
            if symbol_id is None:
                logger.error(f"[CTrader] Symbol not found: {symbol}")
                return []
            self._symbol_id_cache[symbol] = symbol_id
            self._symbol_digits_cache[symbol_id] = digits

        period_int = _PERIOD_MAP.get(timeframe.upper(), _PERIOD_MAP["M5"])
        to_ts = _get_last_market_close_ts()
        from_ts = _compute_from_timestamp(to_ts, timeframe, count)

        await ws.send(_build_trendbars_req(ctid, symbol_id, period_int, from_ts, to_ts))
        resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
        pt, payload_bytes = _parse_proto_response(resp)
        if pt != _PT_TRENDBARS_RES:
            logger.error(f"[CTrader] GetTrendbars failed: payloadType={pt}")
            raise RuntimeError(f"GetTrendbars unexpected payloadType={pt}")

        bars = _decode_trendbars_response(payload_bytes, digits)
        logger.info(f"[CTrader] Received {len(bars)} bars for {symbol}/{timeframe}")
        return bars

    async def _invalidate_session(self) -> None:
        """Close and discard the persistent session."""
        ws = self._session_ws
        self._session_ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def _resolve_symbol_id(
        self, ws: Any, ctid: int, symbol: str
    ) -> tuple:
        """Request symbols list from Spotware and return (symbolId, digits) for symbol."""
        await ws.send(_build_symbols_list_req(ctid))
        resp = await asyncio.wait_for(ws.recv(), timeout=_WS_MSG_TIMEOUT)
        pt, payload_bytes = _parse_proto_response(resp)
        if pt != _PT_SYMBOLS_RES:
            logger.error(f"[CTrader] SymbolsList failed: payloadType={pt}")
            return None, 5

        return _parse_symbol_from_list(payload_bytes, symbol)

    def get_market_data(
        self, symbol: str, timeframe: str, count: int
    ) -> Optional[pd.DataFrame]:
        """BaseConnector interface alias for fetch_ohlc."""
        return self.fetch_ohlc(symbol, timeframe, count)

    # ------------------------------------------------------------------
    # Order execution — REST (api.spotware.com)
    # ------------------------------------------------------------------

    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """
        Execute a market order via Spotware REST API.
        Requires ctid_trader_account_id to be configured.
        """
        if not self._connected:
            return {"success": False, "error": "CTrader not connected"}

        try:
            return self._send_order_via_rest(signal)
        except Exception as exc:
            logger.error(f"[CTrader] execute_order error: {exc}")
            return {"success": False, "error": str(exc)}

    def _send_order_via_rest(self, signal: Any) -> Dict[str, Any]:
        """Submit market order to api.spotware.com."""
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            return {"success": False, "error": "httpx not installed"}

        from models.signal import SignalType

        token = self.config.get("access_token", "")
        ctid = self.config.get("ctid_trader_account_id", "")
        if not ctid:
            return {"success": False, "error": "ctid_trader_account_id not configured"}

        side = "BUY" if signal.signal_type == SignalType.BUY else "SELL"
        payload: Dict[str, Any] = {
            "symbolName": signal.symbol,
            "tradeSide": side,
            "volume": int(getattr(signal, "volume", 0.01) * 100),
            "orderType": "MARKET",
        }
        if getattr(signal, "stop_loss", None):
            payload["stopLoss"] = float(signal.stop_loss)
        if getattr(signal, "take_profit", None):
            payload["takeProfit"] = float(signal.take_profit)

        url = f"{_REST_BASE}/connect/tradingaccounts/{ctid}/orders"
        params = {"oauth_token": token}

        response = httpx.post(url, json=payload, params=params, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        ticket = str(data.get("orderId") or data.get("positionId") or "CT-UNKNOWN")
        price = float(data.get("executionPrice") or data.get("price") or 0.0)

        logger.info(f"[CTrader] Order executed: {signal.symbol} {side} @ {price} | {ticket}")
        return {"success": True, "ticket": ticket, "price": price, "symbol": signal.symbol}

    # ------------------------------------------------------------------
    # Position management — REST (api.spotware.com)
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions via Spotware REST API. Returns [] on error."""
        if not self._is_rest_ready():
            return []
        try:
            return self._get_positions_via_rest()
        except Exception as exc:
            logger.error(f"[CTrader] get_positions error: {exc}")
            return []

    def _get_positions_via_rest(self) -> List[Dict[str, Any]]:
        """Retrieve open positions from api.spotware.com."""
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            return []

        token = self.config.get("access_token", "")
        ctid = self.config.get("ctid_trader_account_id", "")
        if not ctid:
            logger.warning("[CTrader] ctid_trader_account_id not set — cannot fetch positions")
            return []

        url = f"{_REST_BASE}/connect/tradingaccounts/{ctid}/positions"
        params = {"oauth_token": token}

        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        positions = data if isinstance(data, list) else data.get("position", [])

        return [
            {
                "ticket": str(p.get("positionId", "")),
                "symbol": p.get("symbolName", ""),
                "volume": float(p.get("volume", 0)) / 100,
                "price_open": float(p.get("entryPrice", 0)),
                "current_price": float(p.get("currentPrice", 0)),
                "profit": float(p.get("unrealizedPnl", 0)),
                "type": 0 if p.get("tradeSide") == "BUY" else 1,
                "sl": float(p.get("stopLoss") or 0),
                "tp": float(p.get("takeProfit") or 0),
            }
            for p in positions
        ]


# ---------------------------------------------------------------------------
# Spotware protobuf message builders
# ---------------------------------------------------------------------------

def _wrap_in_proto_message(inner_message: Any) -> bytes:
    """Wrap a protobuf OA message in ProtoMessage envelope and serialize."""
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
    envelope = ProtoMessage(
        payloadType=inner_message.payloadType,
        payload=inner_message.SerializeToString(),
    )
    return envelope.SerializeToString()


def _build_app_auth_req(client_id: str, client_secret: str) -> bytes:
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
    msg = ProtoOAApplicationAuthReq(clientId=client_id, clientSecret=client_secret)
    return _wrap_in_proto_message(msg)


def _build_acct_auth_req(ctid_trader_account_id: int, access_token: str) -> bytes:
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAccountAuthReq
    msg = ProtoOAAccountAuthReq(
        ctidTraderAccountId=ctid_trader_account_id,
        accessToken=access_token,
    )
    return _wrap_in_proto_message(msg)


def _build_symbols_list_req(ctid_trader_account_id: int) -> bytes:
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolsListReq
    msg = ProtoOASymbolsListReq(ctidTraderAccountId=ctid_trader_account_id)
    return _wrap_in_proto_message(msg)


def _build_trendbars_req(
    ctid_trader_account_id: int,
    symbol_id: int,
    period: int,
    from_timestamp: int,
    to_timestamp: int,
) -> bytes:
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetTrendbarsReq
    msg = ProtoOAGetTrendbarsReq(
        ctidTraderAccountId=ctid_trader_account_id,
        symbolId=symbol_id,
        period=period,
        fromTimestamp=from_timestamp,
        toTimestamp=to_timestamp,
    )
    return _wrap_in_proto_message(msg)


# ---------------------------------------------------------------------------
# Spotware protobuf message parsers
# ---------------------------------------------------------------------------

def _parse_proto_response(data: bytes) -> tuple:
    """
    Deserialize a binary WebSocket frame into (payloadType, payload_bytes).
    The frame is a serialized ProtoMessage envelope.
    """
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
    envelope = ProtoMessage()
    envelope.ParseFromString(data)
    return envelope.payloadType, envelope.payload


def _parse_symbol_from_list(payload_bytes: bytes, symbol_name: str) -> tuple:
    """
    Parse ProtoOASymbolsListRes payload and find symbolId + digits for symbol_name.
    Returns (symbolId, digits) or (None, 5) if not found.
    """
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolsListRes
    res = ProtoOASymbolsListRes()
    res.ParseFromString(payload_bytes)

    # ProtoOALightSymbol has: symbolId, symbolName
    for sym in res.symbol:
        if sym.symbolName == symbol_name:
            # digits not available in LightSymbol; default to 5 for FOREX
            return sym.symbolId, 5

    return None, 5


def _decode_trendbars_response(
    payload_bytes: bytes, digits: int
) -> List[Dict[str, Any]]:
    """
    Parse ProtoOAGetTrendbarsRes and convert delta-encoded bars to OHLC dicts.

    Spotware price encoding:
      price_divisor = 10 ** digits  (digits=5 for FOREX → divisor=100000)
      low   = trendbar.low / price_divisor
      open  = (trendbar.low + trendbar.deltaOpen) / price_divisor
      close = (trendbar.low + trendbar.deltaClose) / price_divisor
      high  = (trendbar.low + trendbar.deltaHigh) / price_divisor
    """
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetTrendbarsRes

    res = ProtoOAGetTrendbarsRes()
    res.ParseFromString(payload_bytes)

    price_divisor = 10 ** digits
    bars: List[Dict[str, Any]] = []

    for tb in res.trendbar:
        low_raw = tb.low
        low   = low_raw / price_divisor
        open_ = (low_raw + tb.deltaOpen) / price_divisor
        close = (low_raw + tb.deltaClose) / price_divisor
        high  = (low_raw + tb.deltaHigh) / price_divisor
        volume = tb.volume
        # timestamp is epoch seconds for bar open
        ts = datetime.fromtimestamp(tb.utcTimestampInMinutes * 60, tz=timezone.utc)

        bars.append({
            "time": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": float(volume),
        })

    return bars


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _compute_from_timestamp(to_ts_ms: int, timeframe: str, count: int) -> int:
    """Compute from_timestamp in ms based on count of bars and timeframe."""
    _TF_MINUTES: Dict[str, int] = {
        "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M10": 10,
        "M15": 15, "M30": 30, "H1": 60, "H4": 240, "H12": 720,
        "D1": 1440, "W1": 10080, "MN1": 43200,
    }
    minutes = _TF_MINUTES.get(timeframe.upper(), 5)
    from_ts_ms = to_ts_ms - (count * minutes * 60 * 1000)
    return from_ts_ms


def _get_last_market_close_ts() -> int:
    """
    Return the most recent FOREX market close timestamp in ms.
    During weekends, anchors to last Friday 21:00 UTC (NY close).
    During weekdays, returns current time.
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday … 4=Friday, 5=Saturday, 6=Sunday

    if weekday == 5:  # Saturday → anchor to Friday 21:00 UTC
        last_close = now - timedelta(days=1)
    elif weekday == 6:  # Sunday → anchor to Friday 21:00 UTC
        last_close = now - timedelta(days=2)
    else:
        return int(now.timestamp() * 1000)

    last_close = last_close.replace(hour=21, minute=0, second=0, microsecond=0)
    return int(last_close.timestamp() * 1000)
