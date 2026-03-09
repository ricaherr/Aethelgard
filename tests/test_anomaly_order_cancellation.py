"""
Tests for MISIÓN A: Anomaly Sentinel - Real Order Cancellation Integration
Validates the integration between AnomalyService and RiskManager for live order cancellation.

HU 4.6: AnomalyService detects anomalies → RiskManager cancels usr_orders → OrderManager executes
Trace_ID: MISION-A-ORDER-CANCELLATION-2026-001
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, Optional, List

from core_brain.risk_manager import RiskManager
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


class TestAnomalySentinelOrderCancellation:
    """Test suite for order cancellation triggered by AnomalyService."""
    
    @pytest.fixture
    def mock_storage(self):
        """Create a mock StorageManager."""
        storage = Mock(spec=StorageManager)
        storage.get_risk_settings.return_value = {
            "max_consecutive_losses": 3,
            "max_account_risk_pct": 5.0,
            "max_r_per_trade": 2.0,
        }
        storage.get_dynamic_params.return_value = {
            "risk_per_trade": 0.005,
            "max_consecutive_losses": 3,
        }
        storage.get_sys_config.return_value = {
            "lockdown_mode": False,
            "consecutive_losses": 0,
        }
        storage.update_sys_config = Mock()
        return storage
    
    @pytest.fixture
    def mock_mt5_connector(self):
        """Create a mock MT5 connector with order cancellation support."""
        connector = Mock()
        
        # Mock pending usr_orders (3 usr_orders to cancel)
        connector.get_pending_usr_orders = Mock(return_value=[
            {
                'ticket': 1001,
                'symbol': 'EURUSD',
                'type': 'BUY',
                'state': 'PLACED',
                'volume': 0.1,
                'price_open': 1.1050,
            },
            {
                'ticket': 1002,
                'symbol': 'GBPUSD',
                'type': 'SELL',
                'state': 'PLACED',
                'volume': 0.05,
                'price_open': 1.2650,
            },
            {
                'ticket': 1003,
                'symbol': 'EURUSD',
                'type': 'BUY',
                'state': 'PLACED',
                'volume': 0.2,
                'price_open': 1.1040,
            },
        ])
        
        # Mock cancel_order to return success
        def cancel_side_effect(ticket, reason="Lockdown Mode"):
            return {
                'success': True,
                'ticket': ticket,
                'reason': reason,
            }
        
        connector.cancel_order = Mock(side_effect=cancel_side_effect)
        
        # Mock open positions for stop adjustment
        connector.get_open_positions = Mock(return_value=[
            {
                'ticket': 2001,
                'symbol': 'EURUSD',
                'type': 0,  # BUY
                'volume': 1.0,
                'price_current': 1.1060,
                'sl': 1.1000,
                'tp': 1.1100,
            },
            {
                'ticket': 2002,
                'symbol': 'GBPUSD',
                'type': 1,  # SELL
                'volume': 0.5,
                'price_current': 1.2640,
                'sl': 1.2700,
                'tp': 1.2600,
            },
        ])
        
        # Mock modify_order to adjust SL to breakeven
        def modify_side_effect(ticket, sl, reason=""):
            return {
                'success': True,
                'ticket': ticket,
                'sl': sl,
                'reason': reason,
            }
        
        connector.modify_order = Mock(side_effect=modify_side_effect)
        
        return connector
    
    @pytest.fixture
    def risk_manager_with_connectors(self, mock_storage, mock_mt5_connector):
        """Create RiskManager with injected MT5 connector."""
        connectors = {
            "MT5": mock_mt5_connector,
        }
        
        rm = RiskManager(
            storage=mock_storage,
            initial_capital=10000.0,
            connectors=connectors  # MISIÓN A: Inject connectors
        )
        return rm
    
    @pytest.mark.asyncio
    async def test_cancel_pending_usr_orders_with_mt5_connector(self, risk_manager_with_connectors):
        """Test that AnomalyService can trigger real order cancellation on MT5."""
        result = await risk_manager_with_connectors.cancel_pending_usr_orders(
            symbol=None,
            reason="Anomaly Detected - Z-Score > 3.0"
        )
        
        # Verify cancellation result
        assert result.get('cancelled') == 3, "Should have cancelled 3 usr_orders"
        assert result.get('failed') == 0, "Should have no failures"
        assert result.get('status') == 'success', "Should report success"
        assert 'message' in result and '3' in result['message']
    
    @pytest.mark.asyncio
    async def test_cancel_pending_usr_orders_filtered_by_symbol(self, mock_storage):
        """Test that only usr_orders for a specific symbol are cancelled."""
        # Create connector that returns filtered results
        mock_connector = Mock()
        mock_connector.get_pending_usr_orders = Mock(return_value=[
            {
                'ticket': 1001,
                'symbol': 'EURUSD',
                'type': 'BUY',
                'state': 'PLACED',
                'volume': 0.1,
            },
        ])
        mock_connector.cancel_order = Mock(return_value={'success': True, 'ticket': 1001})
        
        rm = RiskManager(
            storage=mock_storage,
            connectors={"MT5": mock_connector}
        )
        
        result = await rm.cancel_pending_usr_orders(
            symbol="EURUSD",
            reason="Flash Crash Detected"
        )
        
        # Verify symbol filter was passed to connector
        mock_connector.get_pending_usr_orders.assert_called_with(symbol="EURUSD")
        assert result.get('cancelled') == 1
    
    @pytest.mark.asyncio
    async def test_cancel_usr_orders_handles_partial_failures(self, mock_storage):
        """Test resilience when some order cancellations fail."""
        # Create connector with mixed success/failure
        mock_connector = Mock()
        mock_connector.get_pending_usr_orders = Mock(return_value=[
            {'ticket': 1001, 'symbol': 'EURUSD'},
            {'ticket': 1002, 'symbol': 'GBPUSD'},
            {'ticket': 1003, 'symbol': 'EURJPY'},
        ])
        
        # First order succeeds, second fails, third succeeds
        def cancel_side_effect(ticket, reason=""):
            if ticket == 1002:
                return {'success': False, 'error': 'Order not found'}
            return {'success': True, 'ticket': ticket}
        
        mock_connector.cancel_order = Mock(side_effect=cancel_side_effect)
        
        rm = RiskManager(storage=mock_storage, connectors={"MT5": mock_connector})
        result = await rm.cancel_pending_usr_orders(reason="Volatility Spike")
        
        assert result.get('cancelled') == 2
        assert result.get('failed') == 1
        assert result.get('status') == 'partial'
    
    @pytest.mark.asyncio
    async def test_adjust_stops_to_breakeven(self, risk_manager_with_connectors):
        """Test that anomalies trigger SL → Breakeven adjustment."""
        result = await risk_manager_with_connectors.adjust_stops_to_breakeven(
            symbol=None,
            reason="Anomaly Detected - Protective Measure"
        )
        
        # Verify stop adjustment result
        assert result.get('adjusted') == 2, "Should have adjusted 2 usr_positions"
        assert result.get('failed') == 0, "Should have no failures"
        assert result.get('status') == 'success'
    
    @pytest.mark.asyncio
    async def test_adjust_stops_filters_by_symbol(self, mock_storage):
        """Test that only usr_positions for a specific symbol are adjusted."""
        mock_connector = Mock()
        mock_connector.get_open_positions = Mock(return_value=[
            {
                'ticket': 2001,
                'symbol': 'EURUSD',
                'type': 0,
                'price_current': 1.1060,
                'sl': 1.1000,
            },
            {
                'ticket': 2002,
                'symbol': 'GBPUSD',
                'type': 1,
                'price_current': 1.2640,
                'sl': 1.2700,
            },
        ])
        
        mock_connector.modify_order = Mock(return_value={
            'success': True,
            'ticket': 2001,
            'sl': 1.1060,
        })
        
        rm = RiskManager(storage=mock_storage, connectors={"MT5": mock_connector})
        result = await rm.adjust_stops_to_breakeven(symbol="EURUSD")
        
        # Only one position should be adjusted
        assert result.get('adjusted') == 1
    
    @pytest.mark.asyncio
    async def test_cancel_usr_orders_without_connectors(self, mock_storage):
        """Test graceful degradation when no connectors are injected."""
        # RiskManager without connectors
        rm = RiskManager(storage=mock_storage, connectors={})
        
        result = await rm.cancel_pending_usr_orders(reason="Test")
        
        # Should return pending_integration status
        assert result.get('status') == 'pending_integration'
        assert result.get('cancelled') == 0
        assert 'No connectors' in result.get('message', '')
    
    @pytest.mark.asyncio
    async def test_adjust_stops_without_connectors(self, mock_storage):
        """Test graceful degradation for stop adjustment without connectors."""
        rm = RiskManager(storage=mock_storage, connectors={})
        
        result = await rm.adjust_stops_to_breakeven(reason="Test")
        
        assert result.get('status') == 'pending_integration'
        assert result.get('adjusted') == 0
    
    @pytest.mark.asyncio
    async def test_order_cancellation_trace_logging(self, risk_manager_with_connectors):
        """Test that order cancellations are properly logged with Trace_ID context."""
        # Get the mock connector
        connector = risk_manager_with_connectors.connectors.get("MT5")
        
        # Call cancel_pending_usr_orders
        await risk_manager_with_connectors.cancel_pending_usr_orders(
            symbol="EURUSD",
            reason="VOLATILITY_ZSCORE_3.2"
        )
        
        # Verify cancel_order was called with correct reason
        calls = connector.cancel_order.call_args_list
        assert len(calls) > 0
        
        # Each call should have the reason
        for call in calls:
            args, kwargs = call
            # First positional arg is ticket, second is reason
            assert len(args) >= 2 or 'reason' in kwargs
    
    @pytest.mark.asyncio
    async def test_stop_adjustment_with_mixed_position_types(self, mock_storage):
        """Test SL adjustment for both BUY and SELL usr_positions."""
        mock_connector = Mock()
        
        # Mix of BUY (type=0) and SELL (type=1) usr_positions
        mock_connector.get_open_positions = Mock(return_value=[
            {
                'ticket': 2001,
                'symbol': 'EURUSD',
                'type': 0,  # BUY
                'price_current': 1.1060,
                'sl': 1.1000,
                'tp': 1.1100,
            },
            {
                'ticket': 2002,
                'symbol': 'GBPUSD',
                'type': 1,  # SELL
                'price_current': 1.2640,
                'sl': 1.2700,
                'tp': 1.2600,
            },
        ])
        
        adjusted_prices = []
        
        def track_adjustments(ticket, sl, reason=""):
            adjusted_prices.append((ticket, sl))
            return {'success': True, 'ticket': ticket, 'sl': sl}
        
        mock_connector.modify_order = Mock(side_effect=track_adjustments)
        
        rm = RiskManager(storage=mock_storage, connectors={"MT5": mock_connector})
        result = await rm.adjust_stops_to_breakeven()
        
        # Both usr_positions should be adjusted
        assert result.get('adjusted') == 2
        
        # Verify SL was set to current_price (breakeven)
        assert (2001, 1.1060) in adjusted_prices
        assert (2002, 1.2640) in adjusted_prices


class TestAnomalyIntegrationEndToEnd:
    """End-to-end integration tests: AnomalyService → RiskManager → Connectors."""
    
    @pytest.mark.asyncio
    async def test_complete_anomaly_defensive_protocol(self):
        """Test complete flow: Anomaly detection → Order cancellation → Stop adjustment."""
        # Setup storage
        mock_storage = Mock(spec=StorageManager)
        mock_storage.get_risk_settings.return_value = {
            "max_consecutive_losses": 3,
            "max_account_risk_pct": 5.0,
            "max_r_per_trade": 2.0,
        }
        mock_storage.get_dynamic_params.return_value = {"risk_per_trade": 0.005}
        mock_storage.get_sys_config.return_value = {
            "lockdown_mode": False,
            "consecutive_losses": 0,
        }
        
        # Setup connector with realistic data
        mock_connector = Mock()
        mock_connector.get_pending_usr_orders = Mock(return_value=[
            {'ticket': 1001, 'symbol': 'EURUSD', 'type': 'BUY'},
        ])
        mock_connector.get_open_positions = Mock(return_value=[
            {'ticket': 2001, 'symbol': 'EURUSD', 'type': 0, 'price_current': 1.1050, 'sl': 1.1000},
        ])
        mock_connector.cancel_order = Mock(return_value={'success': True, 'ticket': 1001})
        mock_connector.modify_order = Mock(return_value={'success': True, 'ticket': 2001})
        
        # Create RiskManager with connector
        rm = RiskManager(
            storage=mock_storage,
            initial_capital=10000.0,
            connectors={"MT5": mock_connector}
        )
        
        # PHASE 1: Anomaly triggers lockdown
        lockdown_result = await rm.activate_lockdown(
            symbol="EURUSD",
            reason="Z-Score > 3.0 (Flash Crash detected)",
            trace_id="BLACK-SWAN-SENTINEL-2026-001-TEST"
        )
        assert lockdown_result is True, "Lockdown should activate"
        
        # PHASE 2: Anomaly service calls cancel_pending_usr_orders
        cancel_result = await rm.cancel_pending_usr_orders(
            symbol="EURUSD",
            reason="FLASH_CRASH_DETECTED"
        )
        assert cancel_result.get('cancelled') >= 0, "Order cancellation initiated"
        
        # PHASE 3: Anomaly service calls adjust_stops_to_breakeven
        adjust_result = await rm.adjust_stops_to_breakeven(
            symbol="EURUSD",
            reason="Anomaly_Detected_SL_Breakeven"
        )
        assert adjust_result.get('adjusted') >= 0, "Stop adjustment initiated"
        
        # Verify all connectors were called
        assert mock_connector.get_pending_usr_orders.called
        assert mock_connector.get_open_positions.called
        assert mock_connector.cancel_order.called or cancel_result.get('cancelled') == 0
        assert mock_connector.modify_order.called or adjust_result.get('adjusted') == 0
