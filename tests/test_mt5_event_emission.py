"""
Tests for MT5 Event Emission and Reconciliation
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from connectors.mt5_connector import MT5Connector
from models.broker_event import BrokerTradeClosedEvent, TradeResult


class TestMT5EventEmission:
    """Test MT5 connector event emission and reconciliation"""

    @patch('connectors.mt5_connector.mt5')
    def test_reconcile_closed_trades_processes_historical_closures(self, mock_mt5):
        """Test that reconcile_closed_trades queries MT5 history and processes closures"""
        # Given
        connector = MT5Connector()
        connector.is_connected = True
        connector.magic_number = 123456

        mock_deals = [
            Mock(
                ticket=67890,
                position_id=12345,
                price=1.0550,
                time=1641081600,
                profit=50.0,
                reason=3,
                magic=123456,
                entry=1,  # DEAL_ENTRY_OUT
                symbol="EURUSD",
                comment=""
            )
        ]
        mock_mt5.history_deals_get.return_value = mock_deals
        mock_mt5.DEAL_ENTRY_OUT = 1

        mock_position = Mock()
        mock_position.ticket = 12345
        mock_position.symbol = "EURUSD"
        mock_position.price_open = 1.0500
        mock_position.time = 1640995200
        mock_position.comment = "Aethelgard_abc123"
        connector._find_position_for_deal = Mock(return_value=mock_position)

        mock_listener = Mock()

        # When
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then
        mock_mt5.history_deals_get.assert_called_once()
        mock_listener.handle_trade_closed_event.assert_called_once()
        event = mock_listener.handle_trade_closed_event.call_args[0][0]
        assert event.data.ticket == "67890"
        assert event.data.symbol == "EURUSD"
        assert event.data.profit_loss == 50.0
        assert event.data.result == TradeResult.WIN
        assert event.data.signal_id == "abc123"

    @patch('connectors.mt5_connector.mt5')
    def test_reconcile_closed_trades_handles_no_positions(self, mock_mt5):
        """Test reconciliation when no closed positions exist"""
        # Given
        connector = MT5Connector()
        connector.is_connected = True
        connector.magic_number = 123456
        mock_mt5.history_deals_get.return_value = []
        mock_listener = Mock()

        # When
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then
        mock_listener.handle_trade_closed_event.assert_not_called()

    @patch('connectors.mt5_connector.mt5')
    def test_reconcile_closed_trades_idempotent_with_existing_trades(self, mock_mt5):
        """Test that reconciliation doesn't duplicate already processed trades"""
        # Given
        connector = MT5Connector()
        connector.is_connected = True
        connector.magic_number = 123456

        mock_deals = [
            Mock(
                ticket=67890,
                position_id=12345,
                price=1.0550,
                time=1641081600,
                profit=50.0,
                reason=3,
                magic=123456,
                entry=1,
                symbol="EURUSD",
                comment=""
            )
        ]
        mock_mt5.history_deals_get.return_value = mock_deals
        mock_mt5.DEAL_ENTRY_OUT = 1

        mock_position = Mock()
        mock_position.ticket = 12345
        mock_position.symbol = "EURUSD"
        mock_position.price_open = 1.0500
        mock_position.time = 1640995200
        mock_position.comment = ""
        connector._find_position_for_deal = Mock(return_value=mock_position)

        mock_listener = Mock()
        mock_listener.handle_trade_closed_event.return_value = True  # Already processed

        # When
        connector.reconcile_closed_trades(mock_listener, hours_back=24)

        # Then
        mock_listener.handle_trade_closed_event.assert_called_once()

    def test_mapping_mt5_deal_to_broker_event(self):
        """Test detailed mapping from MT5 deal/position to BrokerTradeClosedEvent"""
        # Given
        position = Mock(
            ticket=12345,
            symbol="EURUSD=X",
            price_open=1.0500,
            time=1640995200,
            comment="Aethelgard_xyz789"
        )

        deal = Mock(
            ticket=67890,
            position_id=12345,
            price=1.0450,
            time=1641081600,
            profit=-50.0,
            reason=2,
            comment="sl"
        )

        connector = MT5Connector()

        # When
        event = connector._create_trade_closed_event(position, deal)

        # Then
        assert event.ticket == "67890"
        assert event.symbol == "EURUSD"
        assert event.entry_price == 1.0500
        assert event.exit_price == 1.0450
        assert event.entry_time == datetime.fromtimestamp(1640995200)
        assert event.exit_time == datetime.fromtimestamp(1641081600)
        assert event.profit_loss == -50.0
        assert event.result == TradeResult.LOSS
        assert event.broker_id == "MT5"
        assert event.signal_id == "xyz789"
        assert event.exit_reason == "STOP_LOSS"
        assert abs(event.pips - (-50.0)) < 0.01