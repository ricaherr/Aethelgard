from unittest.mock import MagicMock

import pandas as pd

from core_brain.risk_manager import RiskManager
from models.signal import Signal, SignalType, ConnectorType


def test_risk_manager_vetoes_trade_when_sentiment_service_blocks() -> None:
    storage = MagicMock()
    storage.get_risk_settings.return_value = {
        "max_account_risk_pct": 5.0,
        "max_r_per_trade": 5.0,
    }
    storage.get_dynamic_params.return_value = {
        "risk_per_trade": 0.01,
    }
    storage.get_system_state.return_value = {"lockdown_mode": False}

    risk_manager = RiskManager(
        storage=storage,
        initial_capital=10000.0,
        instrument_manager=MagicMock(),
    )

    risk_manager.confluence_service.validate_confluence = MagicMock(return_value=(True, "Aligned", 0.0))
    risk_manager.sentiment_service.evaluate_trade_veto = MagicMock(
        return_value=(
            False,
            "[SENTIMENT_VETO][Trace_ID: TEST] Bearish Sentiment detected (84%).",
            {"bias": "BEARISH", "bearish_pct": 84.0, "high_impact_macro": True},
        )
    )

    connector = MagicMock()
    connector.get_account_balance.return_value = 10000.0
    connector.get_open_positions.return_value = []
    connector.fetch_ohlc.return_value = pd.DataFrame()

    signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.92,
        connector_type=ConnectorType.PAPER,
        entry_price=1.0800,
        stop_loss=0.0,
        take_profit=1.0900,
        timeframe="M5",
        metadata={},
    )

    can_trade, reason = risk_manager.can_take_new_trade(signal, connector)

    assert can_trade is False
    assert "[SENTIMENT_VETO]" in reason
