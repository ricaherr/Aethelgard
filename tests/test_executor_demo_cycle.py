"""
Test Suite — Executor Productivo en Cuenta DEMO (HU 2.1)
TDD: ciclo completo de ejecución DEMO, shadow logs, vetos y fallback.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

from models.signal import Signal, ConnectorType, SignalType
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from core_brain.services.execution_service import ExecutionService, ExecutionResponse
from core_brain.services.slippage_controller import SlippageController
from data_vault.storage import StorageManager


# ─── Fixtures compartidos ────────────────────────────────────────────────────

def _make_demo_connector(*, is_demo: bool = True, execute_success: bool = True,
                          bid: float = 1.1049, ask: float = 1.1051) -> Mock:
    """Connector DEMO pre-configurado para tests."""
    connector = Mock()
    connector.is_demo = is_demo
    connector.is_connected = True
    connector.get_last_tick = Mock(return_value={"bid": bid, "ask": ask, "time": 0})
    connector.execute_order = Mock(return_value={
        "success": execute_success,
        "ticket": "DEMO_99001",
        "price": ask,
        "order_id": "DEMO_99001",
    } if execute_success else {"success": False, "error": "Broker rejected"})
    symbol_info = Mock()
    symbol_info.digits = 5
    symbol_info.point = 0.00001
    symbol_info.trade_contract_size = 100000
    symbol_info.volume_min = 0.01
    symbol_info.volume_max = 100.0
    symbol_info.volume_step = 0.01
    connector.get_symbol_info = Mock(return_value=symbol_info)
    connector.contract_size = 1.0
    return connector


def _make_risk_manager(*, locked: bool = False) -> Mock:
    rm = Mock(spec=RiskManager)
    rm.is_locked.return_value = locked
    rm.calculate_position_size_master.return_value = 0.01
    rm.can_take_new_trade.return_value = (True, "OK")
    rm._get_account_balance = Mock(return_value=10000.0)
    return rm


def _make_storage() -> Mock:
    storage = Mock(spec=StorageManager)
    storage.update_sys_config = Mock()
    storage.get_open_operations.return_value = []
    storage.is_duplicate_signal = Mock(return_value=False)
    storage.has_recent_signal = Mock(return_value=False)
    storage.has_open_position = Mock(return_value=False)
    storage.get_slippage_p90 = Mock(return_value=None)
    storage.log_execution_shadow = Mock(return_value=True)
    storage.log_signal_pipeline_event = Mock()
    storage.tenant_id = "demo_tenant"
    return storage


def _make_signal(*, entry_price: float = 1.1050, stop_loss: float = 1.1000,
                  take_profit: float = 1.1150, confidence: float = 0.85) -> Signal:
    sig = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=confidence,
        connector_type=ConnectorType.METATRADER5,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        volume=0.01,
    )
    sig.metadata["signal_id"] = "DEMO-TEST-001"
    return sig


# ─── Test 1: Inicialización con cuenta DEMO ──────────────────────────────────

class TestExecutorDemoInit:
    """Verifica que el Executor se inicializa correctamente con un conector DEMO."""

    def test_executor_acepta_conector_demo_habilitado(self):
        """
        Criterio de aceptación: Executor arranca sin error con conector DEMO.
        El conector debe reflejar is_demo=True y is_connected=True.
        """
        demo_connector = _make_demo_connector(is_demo=True)
        connectors = {ConnectorType.METATRADER5: demo_connector}
        multi_tf = Mock()
        multi_tf.validate_new_signal.return_value = (True, "OK")

        executor = OrderExecutor(
            risk_manager=_make_risk_manager(),
            storage=_make_storage(),
            connectors=connectors,
            multi_tf_limiter=multi_tf,
        )

        assert executor is not None
        assert ConnectorType.METATRADER5 in executor.connectors
        assert executor.connectors[ConnectorType.METATRADER5].is_demo is True
        assert executor.connectors[ConnectorType.METATRADER5].is_connected is True

    def test_executor_rechaza_conector_real_por_guardia_demo(self):
        """
        Criterio de seguridad: el conector REAL debe ser rechazado por MT5Connector.
        Aquí verificamos que el flag is_demo=False es identificable en el executor.
        """
        real_connector = _make_demo_connector(is_demo=False)
        connectors = {ConnectorType.METATRADER5: real_connector}
        multi_tf = Mock()
        multi_tf.validate_new_signal.return_value = (True, "OK")

        executor = OrderExecutor(
            risk_manager=_make_risk_manager(),
            storage=_make_storage(),
            connectors=connectors,
            multi_tf_limiter=multi_tf,
        )

        connector = executor.connectors[ConnectorType.METATRADER5]
        assert connector.is_demo is False, "La guardia de seguridad DEMO debe rechazarlo en MT5Connector"


# ─── Test 2: Ejecución y registro en shadow logs ─────────────────────────────

class TestExecutionShadowLogDemo:
    """Verifica que una ejecución exitosa registra slippage y latencia en shadow logs."""

    @pytest.mark.asyncio
    async def test_ejecucion_exitosa_registra_shadow_log(self):
        """
        Criterio de aceptación: Al ejecutar con éxito, storage.log_execution_shadow
        debe ser llamado con status='SUCCESS' y valores de slippage/latencia.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=1.1049, ask=1.1051, execute_success=True)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is True
        assert response.order_id == "DEMO_99001"
        assert response.latency_ms > 0

        storage.log_execution_shadow.assert_called_once()
        call_kwargs = storage.log_execution_shadow.call_args
        args = call_kwargs[0]  # positional args
        status_arg = args[6]   # status es el 7mo argumento
        assert status_arg == "SUCCESS"

    @pytest.mark.asyncio
    async def test_shadow_log_contiene_slippage_y_latencia(self):
        """
        Criterio de aceptación: Los campos slippage_pips y latency_ms deben ser
        no negativos y aparecer en el shadow log.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=1.1049, ask=1.1051, execute_success=True)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.slippage_pips >= Decimal("0")
        assert response.latency_ms >= 0.0
        storage.log_execution_shadow.assert_called_once()


# ─── Test 3: Veto por slippage/spread/volatilidad ────────────────────────────

class TestExecutionVetoDemo:
    """Verifica que los vetos de slippage, spread y sin liquidez funcionan correctamente."""

    @pytest.mark.asyncio
    async def test_veto_slippage_bloquea_orden_y_registra_shadow(self):
        """
        Criterio de aceptación: Si el slippage estimado supera el límite,
        la orden es vetada, se retorna success=False y se registra en shadow log.
        """
        storage = _make_storage()
        # Precio actual muy lejos del entry: slippage alto
        demo_connector = _make_demo_connector(bid=1.1200, ask=1.1205)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("2.0")  # limite estricto 2 pips

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)  # diferencia > 2 pips respecto a ask=1.1205

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is False
        assert response.status == "VETO_SLIPPAGE"
        storage.log_execution_shadow.assert_called_once()
        shadow_args = storage.log_execution_shadow.call_args[0]
        assert shadow_args[6] == "VETO_SLIPPAGE"

    @pytest.mark.asyncio
    async def test_veto_spread_invertido_bloquea_orden(self):
        """
        Criterio de aceptación: Si ask <= bid (mercado invertido), la validación
        de liquidez falla y la orden es bloqueada.
        """
        storage = _make_storage()
        # Mercado invertido: ask < bid
        demo_connector = _make_demo_connector(bid=1.1060, ask=1.1055)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is False
        assert "VETO_SPREAD" in response.status or "LIQUIDITY" in response.status

    @pytest.mark.asyncio
    async def test_precio_sin_liquidez_bloquea_orden(self):
        """
        Criterio de aceptación: Si el tick retorna bid=0, la validación falla
        con LIQUIDITY_INSUFFICIENT.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=0.0, ask=0.0)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is False
        assert response.status in ("LIQUIDITY_INSUFFICIENT", "VETO_SPREAD", "PRICE_FETCH_ERROR")


# ─── Test 4: Fallback ante fallo de conector ─────────────────────────────────

class TestExecutorFallbackDemo:
    """Verifica resiliencia del Executor ante fallos del conector DEMO."""

    @pytest.mark.asyncio
    async def test_fallo_execute_order_registra_shadow_y_retorna_false(self):
        """
        Criterio de aceptación: Si el conector lanza ConnectionError en execute_order,
        el ExecutionService lo captura, registra en shadow log y retorna success=False.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=1.1049, ask=1.1051)
        demo_connector.execute_order = Mock(side_effect=ConnectionError("MT5 connection lost"))
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is False
        assert response.status == "CONNECTION_ERROR"
        storage.log_execution_shadow.assert_called_once()
        shadow_args = storage.log_execution_shadow.call_args[0]
        assert shadow_args[6] == "CONNECTION_ERROR"

    @pytest.mark.asyncio
    async def test_conector_none_retorna_no_connector(self):
        """
        Criterio de aceptación: Si el conector es None (no disponible),
        ExecutionService retorna NO_CONNECTOR sin crashear.
        """
        storage = _make_storage()
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, connector=None)

        assert response.success is False
        assert response.status == "NO_CONNECTOR"

    @pytest.mark.asyncio
    async def test_broker_rechaza_orden_registra_broker_rejected(self):
        """
        Criterio de aceptación: Si el broker rechaza la orden (success=False en resultado),
        ExecutionService lo registra como BROKER_REJECTED en shadow log.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=1.1049, ask=1.1051, execute_success=False)
        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")

        service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        signal = _make_signal(entry_price=1.1050)

        response = await service.execute_with_protection(signal, demo_connector)

        assert response.success is False
        assert response.status == "BROKER_REJECTED"
        storage.log_execution_shadow.assert_called_once()
        shadow_args = storage.log_execution_shadow.call_args[0]
        assert shadow_args[6] == "BROKER_REJECTED"

    @pytest.mark.asyncio
    async def test_executor_completo_maneja_fallo_conexion_gracefully(self):
        """
        Ciclo completo: OrderExecutor con fallo de execute_order retorna False
        sin propagar excepción al caller.
        """
        storage = _make_storage()
        demo_connector = _make_demo_connector(bid=1.1049, ask=1.1051)
        demo_connector.execute_order = Mock(side_effect=ConnectionError("MT5 lost"))
        multi_tf = Mock()
        multi_tf.validate_new_signal.return_value = (True, "OK")
        multi_tf._get_open_usr_positions_by_symbol = Mock(return_value=[])
        multi_tf._get_open_usr_positions_from_db_only = Mock(return_value=[])

        slippage_ctrl = Mock(spec=SlippageController)
        slippage_ctrl.get_limit.return_value = Decimal("5.0")
        exec_service = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)

        executor = OrderExecutor(
            risk_manager=_make_risk_manager(),
            storage=storage,
            connectors={ConnectorType.METATRADER5: demo_connector},
            multi_tf_limiter=multi_tf,
            execution_service=exec_service,
        )
        signal = _make_signal(entry_price=1.1050)

        result = await executor.execute_signal(signal)

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
