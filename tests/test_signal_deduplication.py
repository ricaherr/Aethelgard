"""
Tests for Signal Deduplication System
Ensures no duplicate sys_signals are generated or executed
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from data_vault.storage import StorageManager
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from core_brain.instrument_manager import InstrumentManager
from models.signal import Signal, ConnectorType, SignalType
from utils.time_utils import to_utc

INSTRUMENTS_CONFIG_EXAMPLE = {
    "FOREX": {
        "majors": {"instruments": ["EURUSD", "GBPUSD", "USDJPY"], "enabled": True, "min_score": 70.0},
        "minors": {"instruments": ["EURGBP", "EURJPY", "GBPJPY"], "enabled": True, "min_score": 75.0},
        "exotics": {"instruments": ["USDTRY", "USDZAR", "USDMXN"], "enabled": False, "min_score": 90.0},
    },
    "CRYPTO": {
        "tier1": {"instruments": ["BTCUSDT", "ETHUSDT"], "enabled": True, "min_score": 75.0},
        "altcoins": {"instruments": ["ADAUSDT", "DOGEUSDT"], "enabled": False, "min_score": 85.0},
    }
}


def _insert_execution_shadow_for_testing(
    storage: StorageManager,
    symbol: str,
    num_usr_executions: int = 5
) -> bool:
    """Pre-populate execution shadow logs so CoherenceService has baseline data"""
    from datetime import datetime, timezone, timedelta
    try:
        now = datetime.now(timezone.utc)
        # Base price depends on symbol (realistic values)
        base_prices = {
            "EURUSD": 1.0850,
            "GBPUSD": 1.2700,
            "USDJPY": 110.0,
        }
        base_price = base_prices.get(symbol, 1.0)
        
        for i in range(num_usr_executions):
            timestamp = to_utc(now - timedelta(minutes=30-i*10))
            # Use PERFECT execution data (0 slippage, low latency) to ensure coherence > 80%
            storage.log_execution_shadow(
                signal_id=f"setup_{symbol}_{i}",
                symbol=symbol,
                theoretical_price=Decimal(str(base_price)),
                real_price=Decimal(str(base_price)),  # Perfect execution
                slippage_pips=Decimal("0.0"),   # Zero slippage
                latency_ms=5.0,                  # Low latency
                status="SUCCESS",
                tenant_id="default",
                trace_id=f"setup_{i}",
                metadata=None,
            )
        return True
    except Exception as e:
        print(f"Warning: Could not pre-populate execution logs for {symbol}: {e}")
        return False

class TestSignalDeduplication:
    """Test cases for signal deduplication logic"""
    
    @pytest.fixture
    def storage(self, tmp_path):
        """Create isolated storage for testing"""
        db_path = tmp_path / "test_dedup.db"
        return StorageManager(db_path=str(db_path))
    
    @pytest.fixture
    def instrument_manager(self, storage):
        state = storage.get_sys_config()
        state["instruments_config"] = INSTRUMENTS_CONFIG_EXAMPLE
        storage.update_sys_config(state)
        return InstrumentManager(storage=storage)

    @pytest.fixture
    def risk_manager(self, storage, instrument_manager):
        """Create risk manager"""
        return RiskManager(storage=storage, initial_capital=10000.0, instrument_manager=instrument_manager)
    
    @pytest.fixture
    def executor(self, risk_manager, storage, instrument_manager):
        """Create executor with paper connector (DI InstrumentManager real)
        Also pre-populates shadow execution logs for CoherenceService baseline"""
        from connectors.paper_connector import PaperConnector
        
        # Pre-populate execution shadow logs for multiple symbols so CoherenceService has baseline data
        # This prevents coherence veto due to insufficient data (0 usr_executions = 0% coherence)
        for symbol in ["EURUSD", "GBPUSD"]:
            _insert_execution_shadow_for_testing(storage, symbol, num_usr_executions=5)

        paper_connector = PaperConnector(instrument_manager=instrument_manager)
        connectors = {ConnectorType.PAPER: paper_connector}
        return OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors=connectors
        )
    
    def test_has_open_position_detection(self, storage):
        """Test detection of open usr_positions"""
        # Initially no open position
        assert not storage.has_open_position("EURUSD")
        
        # Create and execute a signal
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,  # 1.0R risk (0.0010 dist)
            take_profit=1.1020
        )
        
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 12345})
        
        # Now should have open position
        assert storage.has_open_position("EURUSD")
        
        # Other symbols should not have open position
        assert not storage.has_open_position("GBPUSD")
    
    def test_has_recent_signal_detection(self, storage):
        """Test detection of recent sys_signals"""
        # Initially no recent signal
        assert not storage.has_recent_signal("EURUSD", "BUY", minutes=60)
        
        # Create a signal
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020
        )
        
        storage.save_signal(signal)
        
        # Now should have recent signal
        assert storage.has_recent_signal("EURUSD", "BUY", minutes=60)
        
        # Different type should not match
        assert not storage.has_recent_signal("EURUSD", "SELL", minutes=60)
        
        # Different symbol should not match
        assert not storage.has_recent_signal("GBPUSD", "BUY", minutes=60)
    
    @pytest.mark.asyncio
    async def test_executor_rejects_duplicate_open_position(self, executor, storage):
        """Test executor rejects signal when position already open"""
        # Create and execute first signal
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020
        )
        
        # Simulate SignalFactory assigning ID (required by Opción B)
        signal1_id = storage.save_signal(signal1)
        signal1.metadata['signal_id'] = signal1_id
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Try to execute duplicate signal
        signal2 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000, # Ajustado de 1.1050 para evitar slippage masivo contra baseline 1.1000
            stop_loss=1.0990,
            take_profit=1.1020
        )
        
        # Simulate SignalFactory assigning ID (required by Opción B)
        signal2_id = storage.save_signal(signal2)
        signal2.metadata['signal_id'] = signal2_id
        
        result2 = await executor.execute_signal(signal2)
        assert result2 is False  # Should be rejected
    
    @pytest.mark.asyncio
    async def test_executor_rejects_recent_signal(self, executor, storage):
        """
        Test executor rejects signal if position already EXECUTED (NEW ARCHITECTURE)
        
        ARCHITECTURE CHANGE:
        - SignalFactory: generates freely (no dedup)
        - Executor: validates against EXECUTED usr_positions only
        """
        # Execute first signal and mark as EXECUTED (simulating MT5 execution)
        signal1 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2500,
            stop_loss=1.2490,  # 1.0R
            take_profit=1.2520
        )
        
        # Save and mark as EXECUTED (position open)
        signal_id = storage.save_signal(signal1)
        signal1.metadata['signal_id'] = signal_id  # Assign ID like SignalFactory does
        storage.update_signal_status(signal_id, 'EXECUTED', {
            'ticket': 12345,
            'execution_price': 1.2500,
            'connector': 'PAPER'
        })
        
        # Try to execute another signal for same symbol (should be rejected)
        signal2 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2500, # Ajustado de 1.2510 para que slippage sea 1 pip (ask=1.2501)
            stop_loss=1.2490,
            take_profit=1.2520
        )
        signal2_id = storage.save_signal(signal2)
        signal2.metadata['signal_id'] = signal2_id  # Assign ID like SignalFactory does
        
        result = await executor.execute_signal(signal2)
        assert result is False  # Should be rejected - position already open
    
    @pytest.mark.asyncio
    async def test_executor_allows_different_symbols(self, executor, storage):
        """Test executor allows sys_signals for different symbols"""
        # Execute signal for EURUSD
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020
        )
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Execute signal for GBPUSD (different symbol)
        signal2 = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.2500,
            stop_loss=1.2490,
            take_profit=1.2520
        )
        
        result2 = await executor.execute_signal(signal2)
        assert result2 is True  # Should be allowed
    
    @pytest.mark.asyncio
    async def test_executor_allows_opposite_sys_signals(self, executor, storage):
        """Test executor behavior with opposite signal types (BUY vs SELL)"""
        # Execute BUY signal
        signal1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020
        )
        signal1_id = storage.save_signal(signal1)
        signal1.metadata['signal_id'] = signal1_id  # Assign ID like SignalFactory does
        
        result1 = await executor.execute_signal(signal1)
        assert result1 is True
        
        # Try opposite signal type (SELL)
        # This SHOULD be rejected because there's an open BUY position
        # Our deduplication logic prevents opening opposite usr_positions on the same symbol
        signal2 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.SELL,
            confidence=0.8,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1001, # Ajustado para SELL: real_bid=1.1000, entry=1.1001 -> 1 pip slippage
            stop_loss=1.1011,
            take_profit=1.0991
        )
        signal2_id = storage.save_signal(signal2)
        signal2.metadata['signal_id'] = signal2_id  # Assign ID like SignalFactory does
        
        result2 = await executor.execute_signal(signal2)
        # Should be rejected because there's an open position (even if opposite direction)
        # This prevents hedging and ensures clear risk management
        assert result2 is False
