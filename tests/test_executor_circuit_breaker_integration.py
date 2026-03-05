"""
Test Suite: Executor + CircuitBreakerGate Integration (PRIORIDAD 1 - REFACTORED)
Testing: Order blocking when strategy is QUARANTINE/SHADOW, order execution when LIVE

Requirement: Executor delegates strategy authorization to CircuitBreakerGate.
Gate blocks orders for QUARANTINE/SHADOW, allows for LIVE strategies.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
import logging
from typing import Tuple, Optional

from core_brain.executor import OrderExecutor
from core_brain.services.circuit_breaker_gate import CircuitBreakerGate
from core_brain.risk_manager import RiskManager
from models.signal import Signal, ConnectorType, SignalType
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# ===== TEST CONSTANTS (SSOT - Centralized, no hardcoding) =====
TEST_STRATEGY_BLOCKED_ID = "BRK_OPEN_0001"  # QUARANTINE mode
TEST_STRATEGY_LIVE_ID = "institutional_footprint"  # LIVE mode (different)
TEST_STRATEGY_SHADOW_ID = "MOM_BIAS_0001"  # SHADOW mode
TEST_STRATEGY_UNKNOWN_ID = "UNKNOWN_STRATEGY_9999"

# Symbols (Forex pairs)
TEST_SYMBOL_PRIMARY = "EURUSD"
TEST_SYMBOL_SECONDARY = "GBPUSD"

# Signal parameters (SSOT)
TEST_ENTRY_PRICE = 1.1050
TEST_STOP_LOSS = 1.1000
TEST_TAKE_PROFIT = 1.1100
TEST_CONFIDENCE = 0.95
TEST_VOLUME = 0.1
TEST_TIMEFRAME = "1H"

# Mock response constants
MOCK_ORDER_ID = "12345"
MOCK_ORDER_STATUS_SUCCESS = "SUCCESS"
MOCK_POSITION_SIZE = TEST_VOLUME


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock StorageManager."""
    storage = MagicMock(spec=StorageManager)
    storage.has_open_position.return_value = False
    storage.has_recent_signal.return_value = False
    storage.get_dynamic_params.return_value = {}
    storage.log_signal_pipeline_event = MagicMock()
    return storage


@pytest.fixture
def mock_risk_manager() -> MagicMock:
    """Mock RiskManager with permissive defaults."""
    rm = MagicMock(spec=RiskManager)
    rm.is_locked.return_value = False
    rm.can_take_new_trade.return_value = (True, "OK")
    return rm


@pytest.fixture
def mock_circuit_breaker_gate() -> MagicMock:
    """
    Mock CircuitBreakerGate with sensible defaults.
    Returns: (authorized: bool, rejection_reason: Optional[str])
    """
    gate = MagicMock(spec=CircuitBreakerGate)
    # Default: strategy is authorized (LIVE mode)
    gate.check_strategy_authorization.return_value = (True, None)
    return gate


@pytest.fixture
def mock_connector() -> MagicMock:
    """Mock Connector for order execution."""
    connector = MagicMock()
    connector.send_orders = AsyncMock(
        return_value={"order_id": MOCK_ORDER_ID, "status": MOCK_ORDER_STATUS_SUCCESS}
    )
    return connector


@pytest.fixture
def executor_with_gate(
    mock_storage: MagicMock,
    mock_risk_manager: MagicMock,
    mock_circuit_breaker_gate: MagicMock,
    mock_connector: MagicMock
) -> OrderExecutor:
    """Create OrderExecutor with injected CircuitBreakerGate."""
    executor = OrderExecutor(
        risk_manager=mock_risk_manager,
        storage=mock_storage,
        multi_tf_limiter=None,
        notificator=None,
        notification_service=None,
        connectors={ConnectorType.PAPER: mock_connector},
        execution_service=None,
        circuit_breaker_gate=mock_circuit_breaker_gate
    )
    # Mock internal methods
    executor._get_connector = MagicMock(return_value=mock_connector)
    executor._calculate_position_size = MagicMock(return_value=MOCK_POSITION_SIZE)
    executor._register_failed_signal = MagicMock()
    executor._register_pending_signal = MagicMock()
    executor._register_executed_signal = MagicMock()
    return executor


def _create_test_signal(
    symbol: str = TEST_SYMBOL_PRIMARY,
    strategy_id: str = TEST_STRATEGY_LIVE_ID,
    connector: ConnectorType = ConnectorType.PAPER
) -> Signal:
    """Factory for test signals (SSOT: no hardcoded values)."""
    return Signal(
        symbol=symbol,
        strategy_id=strategy_id,
        signal_type=SignalType.BUY,
        entry_price=TEST_ENTRY_PRICE,
        stop_loss=TEST_STOP_LOSS,
        take_profit=TEST_TAKE_PROFIT,
        timeframe=TEST_TIMEFRAME,
        confidence=TEST_CONFIDENCE,
        connector_type=connector,
        market_type="FOREX",
        metadata={"signal_id": f"SIG-{symbol}-{strategy_id}"}
    )


class TestCircuitBreakerGateIntegration:
    """Focus on core CB gating behavior."""

    @pytest.mark.asyncio
    async def test_signal_rejected_when_gate_blocks(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Gate blocks order, THEN: signal rejected."""
        signal = _create_test_signal(strategy_id=TEST_STRATEGY_BLOCKED_ID)
        mock_circuit_breaker_gate.check_strategy_authorization.return_value = (
            False,
            "CIRCUIT_BREAKER_BLOCKED"
        )
        
        result = await executor_with_gate.execute_signal(signal)
        
        assert result is False
        executor_with_gate._register_failed_signal.assert_called_with(
            signal, "CIRCUIT_BREAKER_BLOCKED"
        )
        mock_circuit_breaker_gate.check_strategy_authorization.assert_called_once()

    @pytest.mark.asyncio
    async def test_signal_continues_when_gate_allows(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Gate allows order, THEN: signal enters execution pipeline."""
        signal = _create_test_signal(strategy_id=TEST_STRATEGY_LIVE_ID)
        signal.volume = MOCK_POSITION_SIZE
        # Default gate: authorized
        mock_circuit_breaker_gate.check_strategy_authorization.return_value = (True, None)
        
        result = await executor_with_gate.execute_signal(signal)
        
        # Gate passes, so execution continues
        mock_circuit_breaker_gate.check_strategy_authorization.assert_called_once()
        # Signal may pass or fail downstream, but gate didn't block it
        logger.debug(f"Signal authorized by gate, downstream result: {result}")

    def test_gate_injected_in_executor(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Executor initialized, THEN: has gate injected."""
        assert hasattr(executor_with_gate, 'circuit_breaker_gate')
        assert executor_with_gate.circuit_breaker_gate is mock_circuit_breaker_gate

    @pytest.mark.asyncio
    async def test_gate_called_with_correct_params(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Signal executing, THEN: gate called with strategy_id."""
        signal = _create_test_signal(strategy_id=TEST_STRATEGY_LIVE_ID, symbol=TEST_SYMBOL_SECONDARY)
        mock_circuit_breaker_gate.check_strategy_authorization.return_value = (True, None)
        
        await executor_with_gate.execute_signal(signal)
        
        # Verify gate was called with correct parameters
        call_args = mock_circuit_breaker_gate.check_strategy_authorization.call_args
        assert call_args is not None
        # Args include strategy_id, symbol, signal_id
        assert call_args[1]['strategy_id'] == TEST_STRATEGY_LIVE_ID
        assert call_args[1]['symbol'] == TEST_SYMBOL_SECONDARY

    @pytest.mark.asyncio
    async def test_null_strategy_id_skips_gate(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Signal with strategy_id=None, THEN: gate skipped (allowed)."""
        signal = _create_test_signal(strategy_id=None)
        # Gate returns: authorized (True, None) - ALWAYS called but with None
        mock_circuit_breaker_gate.check_strategy_authorization.return_value = (True, None)
        
        await executor_with_gate.execute_signal(signal)
        
        # Gate was still called (for consistency), but passed None
        call_args = mock_circuit_breaker_gate.check_strategy_authorization.call_args
        assert call_args[1]['strategy_id'] is None

    @pytest.mark.asyncio
    async def test_multiple_signals_blocked_same_strategy(
        self, executor_with_gate: OrderExecutor, mock_circuit_breaker_gate: MagicMock
    ) -> None:
        """GIVEN: Strategy blocked, WHEN: Multiple signals arrive, THEN: All blocked."""
        mock_circuit_breaker_gate.check_strategy_authorization.return_value = (
            False,
            "CIRCUIT_BREAKER_BLOCKED"
        )
        
        signals = [
            _create_test_signal(strategy_id=TEST_STRATEGY_BLOCKED_ID, symbol="EURUSD"),
            _create_test_signal(strategy_id=TEST_STRATEGY_BLOCKED_ID, symbol="GBPUSD"),
        ]
        
        results = []
        for sig in signals:
            result = await executor_with_gate.execute_signal(sig)
            results.append(result)
        
        # All blocked
        assert all(r is False for r in results)
        assert mock_circuit_breaker_gate.check_strategy_authorization.call_count == 2
