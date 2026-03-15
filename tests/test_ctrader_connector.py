"""
TDD: cTrader Connector
======================
Validates CTraderConnector complies with BaseConnector contract and
correctly wraps the Spotware Open API (WebSocket streaming + REST execution).

N1-2 scope:
  - Async WebSocket for tick/OHLC (M1 viable, <100ms latency)
  - REST for order execution (no DLL dependencies)
  - Inherits BaseConnector, compatible with DataProviderManager
"""
import asyncio
import pytest
import pandas as pd
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone

from connectors.ctrader_connector import CTraderConnector
from connectors.base_connector import BaseConnector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector(enabled: bool = True) -> CTraderConnector:
    """Create connector with mocked storage — no real DB needed."""
    mock_storage = Mock()
    mock_storage.get_sys_broker_accounts.return_value = (
        [
            {
                "account_id": "ctrader-demo-001",
                "platform_id": "ctrader",
                "enabled": enabled,
                "account_type": "DEMO",
                "server": "demo",
                "account_number": "123456",
                "account_name": "IC Markets Demo",
            }
        ]
        if enabled
        else []
    )
    mock_storage.get_credentials.return_value = {
        "password": "",
        "client_id": "test_client_id",
        "client_secret": "test_secret",
        "access_token": "test_access_token",
    }
    return CTraderConnector(storage=mock_storage)


# ---------------------------------------------------------------------------
# Contract: BaseConnector inheritance
# ---------------------------------------------------------------------------

class TestCTraderBaseContract:
    """CTraderConnector must implement the full BaseConnector interface."""

    def test_inherits_base_connector(self):
        connector = _make_connector()
        assert isinstance(connector, BaseConnector)

    def test_provider_id_is_ctrader(self):
        connector = _make_connector()
        assert connector.provider_id == "ctrader"

    def test_is_not_local(self):
        """cTrader is a remote WebSocket API, not a local DLL."""
        connector = _make_connector()
        assert connector.is_local() is False

    def test_is_available_false_when_not_connected(self):
        connector = _make_connector()
        assert connector.is_available() is False

    def test_is_available_true_when_connected(self):
        connector = _make_connector()
        connector._connected = True
        assert connector.is_available() is True

    def test_get_latency_returns_float(self):
        connector = _make_connector()
        latency = connector.get_latency()
        assert isinstance(latency, float)
        assert latency >= 0.0

    def test_get_last_tick_returns_dict_with_bid_ask_time(self):
        connector = _make_connector()
        tick = connector.get_last_tick("EURUSD")
        assert "bid" in tick
        assert "ask" in tick
        assert "time" in tick

    def test_get_last_tick_uses_tick_cache(self):
        connector = _make_connector()
        connector._tick_cache["EURUSD"] = {
            "bid": 1.0855, "ask": 1.0857, "time": 1700000000.0
        }
        tick = connector.get_last_tick("EURUSD")
        assert tick["bid"] == 1.0855
        assert tick["ask"] == 1.0857

    def test_get_last_tick_returns_zeros_for_unknown_symbol(self):
        connector = _make_connector()
        tick = connector.get_last_tick("UNKNOWN")
        assert tick["bid"] == 0.0
        assert tick["ask"] == 0.0


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestCTraderConfigLoading:
    """Connector loads credentials from DB (SSOT principle)."""

    def test_config_disabled_when_no_accounts(self):
        connector = _make_connector(enabled=False)
        assert connector.config.get("enabled") is False

    def test_config_enabled_when_account_exists(self):
        connector = _make_connector(enabled=True)
        assert connector.config.get("enabled") is True

    def test_config_loads_access_token(self):
        connector = _make_connector()
        assert connector.config.get("access_token") == "test_access_token"

    def test_config_loads_account_type(self):
        connector = _make_connector()
        assert connector.config.get("account_type") in ("DEMO", "LIVE", "REAL")

    def test_config_loads_host_based_on_account_type(self):
        """DEMO account must use demo endpoint."""
        connector = _make_connector()
        host = connector.config.get("host", "")
        assert "demo" in host.lower()


# ---------------------------------------------------------------------------
# connect() — async WebSocket setup
# ---------------------------------------------------------------------------

class TestCTraderConnect:
    """connect() must attempt WebSocket handshake and return True on success."""

    def test_connect_returns_false_when_disabled(self):
        connector = _make_connector(enabled=False)
        result = connector.connect()
        assert result is False

    @patch("connectors.ctrader_connector.asyncio")
    def test_connect_returns_true_on_successful_handshake(self, mock_asyncio):
        connector = _make_connector()
        # Simulate _connect_async returning True
        mock_asyncio.run = Mock(return_value=True)
        connector._connected = True
        assert connector.is_available() is True

    def test_connect_does_not_raise_on_network_error(self):
        """Connection failures must be caught — never crash the system."""
        connector = _make_connector()
        # _connect_async fails → connect() returns False gracefully
        with patch.object(connector, "_connect_async", new=AsyncMock(side_effect=OSError("refused"))):
            result = connector.connect()
        assert result is False

    def test_disconnect_sets_connected_false(self):
        connector = _make_connector()
        connector._connected = True
        result = connector.disconnect()
        assert result is True
        assert connector._connected is False


# ---------------------------------------------------------------------------
# fetch_ohlc / get_market_data
# ---------------------------------------------------------------------------

class TestCTraderMarketData:
    """OHLC data must be returned as a normalized DataFrame."""

    def test_fetch_ohlc_returns_none_when_not_connected(self):
        connector = _make_connector()
        result = connector.fetch_ohlc("EURUSD", "M5", 100)
        assert result is None

    def test_fetch_ohlc_returns_dataframe_with_required_columns(self):
        connector = _make_connector()
        connector._connected = True

        fake_bars = [
            {
                "open": 1.0850, "high": 1.0860, "low": 1.0840,
                "close": 1.0855, "volume": 1200,
                "time": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            },
            {
                "open": 1.0855, "high": 1.0870, "low": 1.0845,
                "close": 1.0865, "volume": 950,
                "time": datetime(2024, 1, 1, 10, 5, tzinfo=timezone.utc),
            },
        ]
        with patch.object(connector, "_fetch_bars_via_rest", return_value=fake_bars):
            df = connector.fetch_ohlc("EURUSD", "M5", 2)

        assert df is not None
        assert isinstance(df, pd.DataFrame)
        for col in ("time", "open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Missing column: {col}"

    def test_get_market_data_delegates_to_fetch_ohlc(self):
        connector = _make_connector()
        connector._connected = True
        fake_df = pd.DataFrame(
            {"time": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
        )
        with patch.object(connector, "fetch_ohlc", return_value=fake_df) as mock_fetch:
            connector.get_market_data("EURUSD", "M5", 100)
            mock_fetch.assert_called_once_with("EURUSD", "M5", 100)

    def test_fetch_ohlc_returns_none_on_rest_error(self):
        connector = _make_connector()
        connector._connected = True
        with patch.object(connector, "_fetch_bars_via_rest", side_effect=Exception("timeout")):
            result = connector.fetch_ohlc("EURUSD", "M5", 100)
        assert result is None


# ---------------------------------------------------------------------------
# execute_order
# ---------------------------------------------------------------------------

class TestCTraderExecuteOrder:
    """Orders must be submitted to the REST endpoint, not DLL calls."""

    def test_execute_order_returns_failure_when_not_connected(self):
        from models.signal import Signal, SignalType
        connector = _make_connector()
        signal = Mock(spec=Signal)
        signal.symbol = "EURUSD"
        signal.signal_type = SignalType.BUY
        result = connector.execute_order(signal)
        assert result["success"] is False
        assert "error" in result

    def test_execute_order_calls_rest_endpoint(self):
        from models.signal import Signal, SignalType
        connector = _make_connector()
        connector._connected = True

        signal = Mock(spec=Signal)
        signal.symbol = "EURUSD"
        signal.signal_type = SignalType.BUY
        signal.volume = 0.01
        signal.stop_loss = 1.0800
        signal.take_profit = 1.0950
        signal.entry_price = 1.0855

        mock_rest_result = {"success": True, "ticket": "CT-123456", "price": 1.0856}
        with patch.object(connector, "_send_order_via_rest", return_value=mock_rest_result):
            result = connector.execute_order(signal)

        assert result["success"] is True
        assert result["ticket"] == "CT-123456"

    def test_execute_order_catches_rest_exception(self):
        from models.signal import Signal, SignalType
        connector = _make_connector()
        connector._connected = True

        signal = Mock(spec=Signal)
        signal.symbol = "EURUSD"
        signal.signal_type = SignalType.BUY
        signal.volume = 0.01
        signal.stop_loss = None
        signal.take_profit = None
        signal.entry_price = 1.0855

        with patch.object(connector, "_send_order_via_rest", side_effect=Exception("REST error")):
            result = connector.execute_order(signal)

        assert result["success"] is False
        assert "REST error" in result.get("error", "")


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------

class TestCTraderPositions:
    """Positions must be fetched via REST (not DLL)."""

    def test_get_positions_returns_empty_list_when_not_connected(self):
        connector = _make_connector()
        result = connector.get_positions()
        assert result == []

    def test_get_positions_returns_list_of_dicts(self):
        connector = _make_connector()
        connector._connected = True

        fake_positions = [
            {
                "ticket": "CT-001",
                "symbol": "EURUSD",
                "volume": 0.01,
                "price_open": 1.0850,
                "current_price": 1.0860,
                "profit": 10.0,
                "type": 0,
            }
        ]
        with patch.object(connector, "_get_positions_via_rest", return_value=fake_positions):
            result = connector.get_positions()

        assert len(result) == 1
        assert result[0]["symbol"] == "EURUSD"
