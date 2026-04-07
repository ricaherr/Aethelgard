from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core_brain.orchestrators import _background_tasks
from models.signal import ConnectorType


class _DummyConnector:
    def __init__(self, *, is_connected: bool, closed_positions: list[dict], provider_id: str) -> None:
        self.is_connected = is_connected
        self._closed_positions = closed_positions
        self.provider_id = provider_id

    def get_closed_usr_positions(self, hours: int = 24) -> list[dict]:
        return self._closed_positions


@pytest.mark.asyncio
async def test_background_closed_positions_uses_capability_based_connector_selection() -> None:
    close_time = datetime.now(timezone.utc)
    generic_connector = _DummyConnector(
        is_connected=True,
        closed_positions=[
            {
                "ticket": 1001,
                "signal_id": "SIG-1001",
                "symbol": "EURUSD",
                "entry_price": 1.1,
                "exit_price": 1.101,
                "profit": 10.0,
                "close_time": close_time,
                "exit_reason": "take_profit_hit",
            }
        ],
        provider_id="ctrader",
    )

    storage = MagicMock()
    storage.get_signal_by_id.return_value = {
        "id": "SIG-1001",
        "timestamp": close_time.isoformat(),
        "entry_price": 1.1,
    }
    storage.get_sys_signals.return_value = []

    orch = SimpleNamespace(
        executor=SimpleNamespace(connectors={ConnectorType.GENERIC: generic_connector}),
        storage=storage,
        trade_closure_listener=SimpleNamespace(handle_trade_closed_event=AsyncMock()),
        _last_checked_deal_ticket=0,
    )

    await _background_tasks.check_closed_usr_positions(orch)

    orch.trade_closure_listener.handle_trade_closed_event.assert_awaited_once()
    assert orch._last_checked_deal_ticket == 1001


@pytest.mark.asyncio
async def test_background_closed_positions_keeps_mt5_compatibility() -> None:
    close_time = datetime.now(timezone.utc)
    mt5_connector = _DummyConnector(
        is_connected=True,
        closed_positions=[
            {
                "ticket": 2001,
                "signal_id": "SIG-2001",
                "symbol": "GBPUSD",
                "entry_price": 1.3,
                "exit_price": 1.299,
                "profit": -10.0,
                "close_time": close_time,
                "exit_reason": "stop_loss_hit",
            }
        ],
        provider_id="mt5",
    )

    storage = MagicMock()
    storage.get_signal_by_id.return_value = {
        "id": "SIG-2001",
        "timestamp": close_time.isoformat(),
        "entry_price": 1.3,
    }
    storage.get_sys_signals.return_value = []

    orch = SimpleNamespace(
        executor=SimpleNamespace(connectors={ConnectorType.METATRADER5: mt5_connector}),
        storage=storage,
        trade_closure_listener=SimpleNamespace(handle_trade_closed_event=AsyncMock()),
        _last_checked_deal_ticket=0,
    )

    await _background_tasks.check_closed_usr_positions(orch)

    orch.trade_closure_listener.handle_trade_closed_event.assert_awaited_once()
    assert orch._last_checked_deal_ticket == 2001
