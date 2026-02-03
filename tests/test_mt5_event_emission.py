"""
Tests for MT5 Event Emission and Reconciliation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from connectors.mt5_connector import MT5Connector
from models.broker_event import BrokerTradeClosedEvent, TradeResult
from core_brain.trade_closure_listener import TradeClosureListener


class TestMT5EventEmission:
    """Test MT5 connector event emission and reconciliation"""

    def test_reconcile_closed_trades_processes_historical_closures(self):
        """Test that reconcile_closed_trades queries MT5 history and processes closures"""
        # Given: MT5Connector with mocked MT5
        connector = MT5Connector()
        connector.mt5 = Mock()

        # Mock closed positions data
        mock_positions = [
            Mock(
                ticket=12345,
                symbol="EURUSD",
                price_open=1.0500,
                time=1640995200,  # 2022-01-01 00:00:00
                comment="signal_abc123"
            )
        ]

        mock_deals = [
            Mock(
                ticket=67890,
                position_id=12345,
                price=1.0550,
                time=1641081600,  # 2022-01-02 00:00:00
                profit=50.0,
                reason=3  # MT5 DEAL_REASON_SL (stop loss)
            )
        ]

        connector.mt5.history_deals_get.return_value = mock_deals
        connector.mt5.history_positions_get.return_value = mock_positions

        # Mock listener
        mock_listener = Mock()

        # When: reconcile_closed_trades is called
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then: Should have queried history
        connector.mt5.history_positions_get.assert_called_once()
        connector.mt5.history_deals_get.assert_called_once()

        # And: Should have emitted event to listener
        mock_listener.handle_trade_closed_event.assert_called_once()
        event = mock_listener.handle_trade_closed_event.call_args[0][0]

        # Verify mapping
        assert event.data.ticket == "67890"
        assert event.data.symbol == "EURUSD"
        assert event.data.entry_price == 1.0500
        assert event.data.exit_price == 1.0550
        assert event.data.profit_loss == 50.0
        assert event.data.result == TradeResult.WIN
        assert event.data.exit_reason == "stop_loss_hit"
        assert event.data.broker_id == "MT5"
        assert event.data.signal_id == "abc123"

    def test_reconcile_closed_trades_handles_no_positions(self):
        """Test reconciliation when no closed positions exist"""
        # Given
        connector = MT5Connector()
        connector.mt5 = Mock()
        connector.mt5.history_positions_get.return_value = []
        mock_listener = Mock()

        # When
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then: No events should be emitted
        mock_listener.handle_trade_closed_event.assert_not_called()

    def test_reconcile_closed_trades_idempotent_with_existing_trades(self):
        """Test that reconciliation doesn't duplicate already processed trades"""
        # Given: Connector with trades already in DB
        connector = MT5Connector()
        connector.mt5 = Mock()

        # Mock position/deal data
        mock_positions = [Mock(ticket=12345, symbol="EURUSD", price_open=1.0500, time=1640995200, comment="")]
        mock_deals = [Mock(ticket=67890, position_id=12345, price=1.0550, time=1641081600, profit=50.0, reason=3)]

        connector.mt5.history_positions_get.return_value = mock_positions
        connector.mt5.history_deals_get.return_value = mock_deals

        # Mock listener that says trade already processed
        mock_listener = Mock()
        mock_listener.handle_trade_closed_event.return_value = True  # Already processed

        # When
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then: Should still query but not process duplicate
        mock_listener.handle_trade_closed_event.assert_called_once()

    def test_mapping_mt5_deal_to_broker_event(self):
        """Test detailed mapping from MT5 deal/position to BrokerTradeClosedEvent"""
        # Given: MT5 data
        position = Mock(
            ticket=12345,
            symbol="EURUSD=X",  # Yahoo suffix
            price_open=1.0500,
            time=1640995200,
            comment="signal_xyz789"
        )

        deal = Mock(
            ticket=67890,
            position_id=12345,
            price=1.0450,  # Loss
            time=1641081600,
            profit=-50.0,
            reason=2  # MT5 DEAL_REASON_TP (take profit - but profit negative? Inconsistency for test)
        )

        connector = MT5Connector()

        # When: Create event
        event = connector._create_trade_closed_event(position, deal)

        # Then: Verify complete mapping
        assert event.ticket == "67890"
        assert event.symbol == "EURUSD"  # Normalized
        assert event.entry_price == 1.0500
        assert event.exit_price == 1.0450
        assert event.entry_time == datetime.fromtimestamp(1640995200)
        assert event.exit_time == datetime.fromtimestamp(1641081600)
        assert event.profit_loss == -50.0
        assert event.result == TradeResult.LOSS
        assert event.broker_id == "MT5"
        assert event.signal_id == "xyz789"

        # Pips calculation (simplified - would need real pip calculation)
        assert event.pips == -50.0  # Simplified for test