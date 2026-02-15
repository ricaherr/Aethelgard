"""
Test Suite for OrderExecutor Module (TDD)
Tests the execution of trading signals with RiskManager validation and agnostic connector routing.
Follows TDD methodology as per Aethelgard's golden rules.
"""
import pytest
import unittest.mock
from unittest.mock import Mock, call, ANY, AsyncMock
from datetime import datetime

from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from models.signal import Signal, ConnectorType, SignalType
from data_vault.storage import StorageManager


class TestOrderExecutor:
    """Test suite for OrderExecutor following TDD principles."""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create a mock RiskManager."""
        risk_manager = Mock(spec=RiskManager)
        risk_manager.is_locked.return_value = False  # Default: not locked
        risk_manager.calculate_position_size_master.return_value = 0.01  # Default position size (UPDATED to master method)
        risk_manager.can_take_new_trade.return_value = (True, "OK") # Default: Trade allowed
        return risk_manager
    
    @pytest.fixture
    def mock_storage(self):
        """Create a mock StorageManager."""
        storage = Mock(spec=StorageManager)
        storage.update_system_state = Mock()
        return storage
    
    @pytest.fixture
    def mock_notificator(self):
        """Create a mock Notificator."""
        notificator = Mock()
        notificator.send_alert = AsyncMock()  # Must be AsyncMock for await
        return notificator
    
    @pytest.fixture
    def mock_mt5_connector(self):
        """Create a mock MT5 connector."""
        connector = Mock()
        connector.execute_signal = Mock(return_value={"status": "success", "order_id": "MT5_12345"})
        return connector
    
    @pytest.fixture
    def mock_nt8_connector(self):
        """Create a mock NT8 connector."""
        connector = Mock()
        connector.execute_signal = Mock(return_value={"status": "success", "order_id": "NT8_67890"})
        return connector
    
    @pytest.fixture
    def executor(self, mock_risk_manager, mock_storage, mock_notificator, mock_mt5_connector, mock_nt8_connector):
        """Create OrderExecutor with mocked dependencies."""
        connectors = {
            ConnectorType.METATRADER5: mock_mt5_connector,
            ConnectorType.NINJATRADER8: mock_nt8_connector
        }
        
        executor = OrderExecutor(
            risk_manager=mock_risk_manager,
            storage=mock_storage,
            notificator=mock_notificator,
            connectors=connectors
        )
        return executor
    
    @pytest.fixture
    def sample_signal(self):
        """Create a sample trading signal."""
        return Signal(
            symbol="EURUSD",
            signal_type="BUY",
            confidence=0.85,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            stop_loss=1.1000,
            take_profit=1.1150,
            volume=0.01
        )

    @pytest.mark.asyncio
    async def test_executor_blocks_signal_when_risk_manager_locked(self, executor, mock_risk_manager, sample_signal, mock_storage):
        """
        TEST 1: Executor debe bloquear señales cuando RiskManager está en lockdown.
        Critical: Ensures no orders are sent when system is locked.
        Verifica que execute_signal() retorna False y registra el intento fallido.
        """
        # Arrange: RiskManager en lockdown
        mock_risk_manager.is_locked.return_value = True
        mock_storage.has_open_position.return_value = False
        
        # Simulate signal_id assigned by SignalFactory (required by Opción B)
        sample_signal.metadata['signal_id'] = 'test-signal-id-123'
        
        # Act: Intentar ejecutar señal
        result = await executor.execute_signal(sample_signal)
        
        # Assert: Señal debe ser rechazada
        assert result is False
        mock_risk_manager.is_locked.assert_called_once()
        
        # Verificar que señal fue marcada como REJECTED en DB
        mock_storage.update_signal_status.assert_called_once_with(
            'test-signal-id-123', 'REJECTED', {'reason': 'REJECTED_LOCKDOWN'}
        )
    
    @pytest.mark.asyncio
    async def test_executor_sends_signal_when_risk_manager_allows(self, executor, mock_risk_manager, sample_signal, mock_mt5_connector, mock_storage):
        """
        TEST 2: Executor debe enviar señales cuando RiskManager lo permite.
        Validates that signals are routed to the correct connector using Factory pattern.
        """
        # Arrange: RiskManager permite trading
        mock_risk_manager.is_locked.return_value = False
        mock_storage.has_open_position.return_value = False
        
        # Act: Ejecutar señal
        result = await executor.execute_signal(sample_signal)
        
        # Assert: Señal enviada al conector MT5
        assert result is True
        mock_mt5_connector.execute_signal.assert_called_once_with(sample_signal)
        mock_risk_manager.is_locked.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_rejects_mt5_success_without_ticket(
        self, executor, sample_signal, mock_mt5_connector, mock_storage
    ):
        """
        TEST 2.1: MT5 requiere ticket/order_id para marcar EXECUTED.
        Si no hay ticket, debe rechazarse.
        """
        mock_storage.has_open_position.return_value = False
        mock_mt5_connector.execute_signal.return_value = {"success": True}

        result = await executor.execute_signal(sample_signal)

        assert result is False
        assert mock_storage.update_system_state.called
    
    @pytest.mark.asyncio
    async def test_executor_uses_factory_pattern_for_connector_routing(
        self, executor, mock_mt5_connector, mock_nt8_connector, mock_risk_manager, mock_storage
    ):
        """
        TEST 3: Executor debe usar Factory Pattern para enrutar al conector correcto.
        Tests agnostic connector routing based on ConnectorType.
        """
        mock_storage.has_open_position.return_value = False
        
        # Test MT5 routing
        signal_mt5 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            volume=0.01
        )
        
        result_mt5 = await executor.execute_signal(signal_mt5)
        assert result_mt5 is True
        mock_mt5_connector.execute_signal.assert_called_once_with(signal_mt5)
        
        # Test NT8 routing
        signal_nt8 = Signal(
            symbol="NQ",
            signal_type=SignalType.SELL,
            confidence=0.88,
            connector_type=ConnectorType.NINJATRADER8,
            entry_price=15000,
            volume=1
        )
        
        result_nt8 = await executor.execute_signal(signal_nt8)
        assert result_nt8 is True
        mock_nt8_connector.execute_signal.assert_called_once_with(signal_nt8)
    
    @pytest.mark.asyncio
    async def test_executor_handles_connector_failure_with_resilience(
        self, executor, mock_mt5_connector, mock_storage, mock_notificator, mock_risk_manager
    ):
        """
        TEST 4: Executor debe manejar fallas de conexión con resiliencia.
        When connector fails, mark signal as REJECTED and notify Telegram.
        """
        # Arrange: Simular falla de conexión
        mock_mt5_connector.execute_signal.side_effect = ConnectionError("Broker disconnected")
        mock_storage.has_open_position.return_value = False
        
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            volume=0.01
        )
        
        # Simulate SignalFactory assigning ID (required by Opción B)
        signal.metadata['signal_id'] = 'test-signal-connection-failure'
        
        # Act: Intentar ejecutar señal
        result = await executor.execute_signal(signal)
        
        # Assert: Señal debe ser rechazada
        assert result is False
        
        # Verificar registro en data_vault con estado REJECTED
        # update_signal_status is called with (signal_id, status, metadata_dict)
        mock_storage.update_signal_status.assert_called_once_with(
            'test-signal-connection-failure',
            'REJECTED',
            {'reason': ANY}
        )
        
        # Verificar notificación a Telegram
        mock_notificator.send_alert.assert_called_once()
        alert_message = str(mock_notificator.send_alert.call_args)
        assert "connection" in alert_message.lower() or "fail" in alert_message.lower()
    
    @pytest.mark.asyncio
    async def test_executor_registers_pending_signal_before_execution(self, executor, mock_storage, sample_signal, mock_risk_manager):
        """
        TEST 5: Executor debe registrar señal con estado PENDING antes de ejecutar.
        Ensures audit trail and order tracking.
        """
        mock_storage.has_open_position.return_value = False
        
        # Act
        await executor.execute_signal(sample_signal)
        
        # Assert: Verificar que se registró con estado PENDING
        assert mock_storage.update_system_state.called
        
        # Buscar la llamada que registra PENDING
        calls = [str(call) for call in mock_storage.update_system_state.call_args_list]
        pending_found = any("PENDING" in call or "pending" in call.lower() for call in calls)
        assert pending_found, "Signal should be registered with PENDING status"
    
    @pytest.mark.asyncio
    async def test_executor_handles_missing_connector_gracefully(self, executor, mock_storage, mock_notificator):
        """
        TEST 6: Executor debe manejar conectores faltantes sin crashear.
        Resilience test for missing connector types.
        """
        mock_storage.has_open_position.return_value = False
        
        signal = Signal(
            symbol="BTCUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.WEBHOOK,  # No configurado
            entry_price=50000,
            volume=0.1
        )
        
        # Simulate SignalFactory assigning ID (required by Opción B)
        signal.metadata['signal_id'] = 'test-signal-missing-connector'
        
        result = await executor.execute_signal(signal)
        
        # Assert: Debe retornar False sin crashear
        assert result is False
        
        # Debe notificar el error
        mock_notificator.send_alert.assert_called()
    
    @pytest.mark.asyncio
    async def test_executor_validates_signal_data_before_execution(self, executor):
        """
        TEST 7: Executor debe validar datos de señal antes de ejecutar.
        Security principle: validate all external inputs.
        """
        # Señal con confidence inválida (fuera de rango 0-1)
        invalid_signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=1.5,  # Inválido
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            volume=0.01
        )
        
        result = await executor.execute_signal(invalid_signal)
        
        # Debe rechazar señales inválidas
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

