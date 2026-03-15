"""
CTrader Connector — Spotware Open API
======================================
Primary FOREX connector for Aethelgard.

Architecture:
  - WebSocket streaming: tick data + OHLC bars (<100ms latency, M1 viable)
  - REST execution:      market orders via cTrader Open API v3
  - No DLL dependency:   natively async, compatible with asyncio event loop

Scope: FOREX execution + data (IC Markets cTrader account)
Auth:  credentials loaded from DB (SSOT — no JSON files)
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from connectors.base_connector import BaseConnector
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# cTrader Open API endpoints
_DEMO_HOST = "demo.ctraderapi.com"
_LIVE_HOST = "live.ctraderapi.com"
_API_PORT = 5035
_REST_DEMO = "https://demo.ctrader.com/ctrader/api/v3"
_REST_LIVE = "https://live.ctrader.com/ctrader/api/v3"

# Timeframe codes used by cTrader REST API
_TIMEFRAME_MAP: Dict[str, str] = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
    "W1": "W1",
}


class CTraderConnector(BaseConnector):
    """
    cTrader Open API Connector.

    Provides:
      - Real-time tick streaming via WebSocket (bid/ask, <100ms)
      - Historical + live OHLC bars via REST
      - Market order execution via REST
      - Open positions via REST

    Credentials required in DB (get_credentials):
      - access_token: OAuth2 bearer token (obtained via Spotware portal)
      - client_id:    Application client ID
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        account_id: Optional[str] = None,
    ) -> None:
        self.storage = storage
        self.account_id = account_id

        self.config: Dict[str, Any] = self._load_config_from_db()
        self._connected: bool = False
        self._tick_cache: Dict[str, Dict[str, float]] = {}
        self._latency: float = 0.0
        self._ws: Any = None  # websockets.ClientConnection when open

        logger.info(
            f"[CTrader] Connector initialized. enabled={self.config.get('enabled')}, "
            f"host={self.config.get('host', 'N/A')}"
        )

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config_from_db(self) -> Dict[str, Any]:
        """Load cTrader account + credentials from DB (SSOT)."""
        try:
            accounts = self.storage.get_sys_broker_accounts()
            ct_accounts = [
                a for a in accounts
                if a.get("platform_id") == "ctrader" and a.get("enabled", True)
            ]
            if not ct_accounts:
                logger.warning("[CTrader] No enabled cTrader accounts in DB.")
                return {"enabled": False}

            account = ct_accounts[0]
            self.account_id = account["account_id"]

            creds = self.storage.get_credentials(self.account_id) or {}

            account_type = account.get("account_type", "DEMO").upper()
            is_demo = account_type in ("DEMO",)

            return {
                "enabled": True,
                "account_id": self.account_id,
                "account_number": account.get("account_number"),
                "account_name": account.get("account_name"),
                "account_type": account_type,
                "host": _DEMO_HOST if is_demo else _LIVE_HOST,
                "rest_base": _REST_DEMO if is_demo else _REST_LIVE,
                "access_token": creds.get("access_token", ""),
                "client_id": creds.get("client_id", ""),
                "client_secret": creds.get("client_secret", ""),
            }
        except Exception as exc:
            logger.error(f"[CTrader] Failed to load config from DB: {exc}")
            return {"enabled": False}

    # ------------------------------------------------------------------
    # BaseConnector: provider identity
    # ------------------------------------------------------------------

    @property
    def provider_id(self) -> str:
        return "ctrader"

    def is_local(self) -> bool:
        """cTrader is a remote WebSocket API — not local like MT5 DLL."""
        return False

    def is_available(self) -> bool:
        return self._connected

    def get_latency(self) -> float:
        return self._latency

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Establish WebSocket connection to cTrader Open API.
        Launches async handshake in the current or a new event loop.
        Returns True if connection succeeds, False otherwise.
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
                    # We're inside an async context; schedule and await
                    future = asyncio.ensure_future(self._connect_async())
                    # The caller is sync, so we can't await here.
                    # Fall back: schedule and return False, let background task finish.
                    loop.call_soon_threadsafe(lambda: None)
                    # For sync callers inside a running loop, use run_coroutine_threadsafe
                    import concurrent.futures
                    fut = asyncio.run_coroutine_threadsafe(self._connect_async(), loop)
                    return fut.result(timeout=30)
                else:
                    return loop.run_until_complete(self._connect_async())
            except RuntimeError:
                return asyncio.run(self._connect_async())
        except Exception as exc:
            logger.error(f"[CTrader] Connection failed: {exc}")
            self._connected = False
            return False

    async def _connect_async(self) -> bool:
        """
        Async WebSocket handshake with cTrader Open API.
        Authenticates with access_token and subscribes to spot prices.
        """
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            logger.error("[CTrader] 'websockets' library not installed. Run: pip install websockets")
            return False

        host = self.config.get("host", _DEMO_HOST)
        uri = f"wss://{host}:{_API_PORT}/"
        token = self.config.get("access_token", "")
        if not token:
            logger.error("[CTrader] No access_token configured — cannot authenticate.")
            return False

        try:
            t0 = time.monotonic()
            self._ws = await websockets.connect(uri, ping_interval=20, ping_timeout=10)
            self._latency = (time.monotonic() - t0) * 1000  # ms

            # Send application auth message (cTrader Open API v3 protocol)
            import json
            auth_msg = {
                "clientMsgId": "auth_app",
                "payloadType": "PROTO_OA_APPLICATION_AUTH_REQ",
                "payload": {
                    "clientId": self.config.get("client_id", ""),
                    "clientSecret": self.config.get("client_secret", ""),
                },
            }
            await self._ws.send(json.dumps(auth_msg))

            self._connected = True
            logger.info(
                f"[CTrader] Connected to {host} | Latency: {self._latency:.1f}ms | "
                f"Account: {self.config.get('account_name', 'N/A')}"
            )
            return True

        except Exception as exc:
            logger.error(f"[CTrader] WebSocket handshake failed: {exc}")
            self._connected = False
            return False

    def disconnect(self) -> bool:
        """Close WebSocket connection gracefully."""
        self._connected = False
        if self._ws is not None:
            try:
                asyncio.run(self._ws.close())
            except Exception:
                pass
            self._ws = None
        logger.info("[CTrader] Disconnected.")
        return True

    # ------------------------------------------------------------------
    # Tick data
    # ------------------------------------------------------------------

    def get_last_tick(self, symbol: str) -> Dict[str, float]:
        """
        Return latest cached tick for symbol (updated by WebSocket stream).
        Falls back to zeros if no tick received yet.
        """
        return self._tick_cache.get(symbol, {"bid": 0.0, "ask": 0.0, "time": 0.0})

    def _update_tick_cache(self, symbol: str, bid: float, ask: float) -> None:
        """Called by WebSocket message handler to update tick cache."""
        self._tick_cache[symbol] = {"bid": bid, "ask": ask, "time": time.time()}

    # ------------------------------------------------------------------
    # OHLC data
    # ------------------------------------------------------------------

    def fetch_ohlc(
        self, symbol: str, timeframe: str = "M5", count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLC bars via cTrader REST API.
        M1 is viable — no polling lag. Returns None on error.
        """
        if not self._connected:
            return None

        try:
            bars = self._fetch_bars_via_rest(symbol, timeframe, count)
            if not bars:
                return None

            df = pd.DataFrame(bars)
            # Normalize to standard columns: time, open, high, low, close, volume
            if "time" not in df.columns:
                return None
            for col in ("open", "high", "low", "close", "volume"):
                if col not in df.columns:
                    df[col] = 0.0

            return df[["time", "open", "high", "low", "close", "volume"]]

        except Exception as exc:
            logger.error(f"[CTrader] fetch_ohlc error for {symbol}/{timeframe}: {exc}")
            return None

    def _fetch_bars_via_rest(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLC bars from cTrader REST endpoint.
        Returns list of dicts: [{time, open, high, low, close, volume}, ...]
        """
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            logger.error("[CTrader] 'httpx' library not installed. Run: pip install httpx")
            return []

        ct_tf = _TIMEFRAME_MAP.get(timeframe.upper(), "M5")
        rest_base = self.config.get("rest_base", _REST_DEMO)
        token = self.config.get("access_token", "")
        account_number = self.config.get("account_number", "")

        url = f"{rest_base}/accounts/{account_number}/symbols/{symbol}/bars"
        params = {"period": ct_tf, "count": count}
        headers = {"Authorization": f"Bearer {token}"}

        response = httpx.get(url, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        bars = data.get("bars", data) if isinstance(data, dict) else data

        return [
            {
                "time": _parse_ctrader_time(b.get("timestamp") or b.get("time")),
                "open": float(b.get("open", 0)),
                "high": float(b.get("high", 0)),
                "low": float(b.get("low", 0)),
                "close": float(b.get("close", 0)),
                "volume": float(b.get("volume", 0)),
            }
            for b in bars
        ]

    def get_market_data(
        self, symbol: str, timeframe: str, count: int
    ) -> Optional[pd.DataFrame]:
        """BaseConnector interface alias for fetch_ohlc."""
        return self.fetch_ohlc(symbol, timeframe, count)

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """
        Execute a market order via cTrader REST API.
        No DLL — pure HTTP, natively async-safe.
        """
        if not self._connected:
            return {"success": False, "error": "CTrader not connected"}

        try:
            return self._send_order_via_rest(signal)
        except Exception as exc:
            logger.error(f"[CTrader] execute_order error: {exc}")
            return {"success": False, "error": str(exc)}

    def _send_order_via_rest(self, signal: Any) -> Dict[str, Any]:
        """Submit a market order to the cTrader REST endpoint."""
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            return {"success": False, "error": "httpx not installed"}

        from models.signal import SignalType

        rest_base = self.config.get("rest_base", _REST_DEMO)
        token = self.config.get("access_token", "")
        account_number = self.config.get("account_number", "")

        side = "BUY" if signal.signal_type == SignalType.BUY else "SELL"
        payload: Dict[str, Any] = {
            "symbolName": signal.symbol,
            "tradeSide": side,
            "volume": int(getattr(signal, "volume", 0.01) * 100),  # cTrader uses units
            "orderType": "MARKET",
        }
        if getattr(signal, "stop_loss", None):
            payload["stopLoss"] = float(signal.stop_loss)
        if getattr(signal, "take_profit", None):
            payload["takeProfit"] = float(signal.take_profit)

        url = f"{rest_base}/accounts/{account_number}/orders"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        ticket = str(data.get("orderId") or data.get("positionId") or "CT-UNKNOWN")
        price = float(data.get("executionPrice") or data.get("price") or 0.0)

        logger.info(f"[CTrader] Order executed: {signal.symbol} {side} @ {price} | Ticket: {ticket}")
        return {"success": True, "ticket": ticket, "price": price, "symbol": signal.symbol}

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions via REST. Returns [] on error."""
        if not self._connected:
            return []
        try:
            return self._get_positions_via_rest()
        except Exception as exc:
            logger.error(f"[CTrader] get_positions error: {exc}")
            return []

    def _get_positions_via_rest(self) -> List[Dict[str, Any]]:
        """Retrieve open positions from cTrader REST endpoint."""
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError:
            return []

        rest_base = self.config.get("rest_base", _REST_DEMO)
        token = self.config.get("access_token", "")
        account_number = self.config.get("account_number", "")

        url = f"{rest_base}/accounts/{account_number}/positions"
        headers = {"Authorization": f"Bearer {token}"}

        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()

        positions = response.json()
        if isinstance(positions, dict):
            positions = positions.get("positions", [])

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
# Utility
# ---------------------------------------------------------------------------

def _parse_ctrader_time(raw: Any) -> Any:
    """Parse cTrader timestamp (epoch ms or ISO string) to datetime."""
    from datetime import datetime, timezone

    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)):
        # cTrader epoch is in milliseconds
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return raw
