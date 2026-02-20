"""
Test Suite for Dynamic Deduplication Window based on Timeframe
Tests that deduplication window adapts to trading timeframe.
"""
import pytest
from datetime import datetime, timedelta
from data_vault.storage import StorageManager, calculate_deduplication_window
from models.signal import Signal, SignalType, ConnectorType


class TestDynamicDeduplicationWindow:
    """Tests for timeframe-based deduplication window calculation."""
    
    @pytest.fixture
    def storage(self, tmp_path):
        """Create temporary database for testing."""
        db_path = tmp_path / "test_dynamic_dedup.db"
        return StorageManager(db_path=str(db_path))
    
    def test_calculate_window_for_1_minute_timeframe(self):
        """1-minute timeframe should have ~10 minute window."""
        assert calculate_deduplication_window("1m") == 10
        assert calculate_deduplication_window("M1") == 10
    
    def test_calculate_window_for_5_minute_timeframe(self):
        """5-minute timeframe should have ~20 minute window."""
        assert calculate_deduplication_window("5m") == 20
        assert calculate_deduplication_window("M5") == 20
    
    def test_calculate_window_for_15_minute_timeframe(self):
        """15-minute timeframe should have ~45 minute window."""
        assert calculate_deduplication_window("15m") == 45
        assert calculate_deduplication_window("M15") == 45
    
    def test_calculate_window_for_1_hour_timeframe(self):
        """1-hour timeframe should have ~2 hour (120 min) window."""
        assert calculate_deduplication_window("1h") == 120
        assert calculate_deduplication_window("H1") == 120
    
    def test_calculate_window_for_4_hour_timeframe(self):
        """4-hour timeframe should have ~8 hour (480 min) window."""
        assert calculate_deduplication_window("4h") == 480
        assert calculate_deduplication_window("H4") == 480
    
    def test_calculate_window_for_daily_timeframe(self):
        """Daily timeframe should have 24 hour (1440 min) window."""
        assert calculate_deduplication_window("1D") == 1440
        assert calculate_deduplication_window("D1") == 1440
    
    def test_calculate_window_for_unknown_timeframe(self):
        """Unknown timeframe should fallback to 60 minutes."""
        assert calculate_deduplication_window("INVALID") == 60
        assert calculate_deduplication_window("") == 60
        # Test None separately with type hint
        result: int = calculate_deduplication_window(None)  # type: ignore
        assert result == 60
    
    def test_has_recent_signal_respects_1m_timeframe(self, storage):
        """1-minute timeframe should only block signals within 10 minutes."""
        # Create signal with 1m timeframe 15 minutes ago (beyond window)
        old_signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            timeframe="1m"
        )
        old_signal.timestamp = datetime.now() - timedelta(minutes=15)
        storage.save_signal(old_signal)
        
        # Should NOT be detected as duplicate (15 min > 10 min window)
        assert not storage.has_recent_signal("EURUSD", "BUY", timeframe="1m")
    
    def test_has_recent_signal_respects_4h_timeframe(self, storage):
        """4-hour timeframe should block signals within 8 hours."""
        # Create signal with 4h timeframe 6 hours ago (within window)
        recent_signal = Signal(
            symbol="BTCUSD",
            signal_type=SignalType.SELL,
            confidence=0.85,
            connector_type=ConnectorType.METATRADER5,
            entry_price=50000,
            timeframe="4h"
        )
        recent_signal.timestamp = datetime.now() - timedelta(hours=6)
        storage.save_signal(recent_signal)
        
        # Should be detected as duplicate (6 hours < 8 hour window)
        assert storage.has_recent_signal("BTCUSD", "SELL", timeframe="4h")
    
    def test_has_recent_signal_allows_expired_4h_signals(self, storage):
        """4-hour timeframe should allow signals after 8 hours."""
        # Create signal 9 hours ago (beyond 8-hour window)
        old_signal = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.2500,
            timeframe="4h"
        )
        old_signal.timestamp = datetime.now() - timedelta(hours=9)
        storage.save_signal(old_signal)
        
        # Should NOT be detected as duplicate (9 hours > 8 hour window)
        assert not storage.has_recent_signal("GBPUSD", "BUY", timeframe="4h")
    
    def test_explicit_minutes_override_timeframe(self, storage):
        """Explicit minutes parameter should override timeframe calculation."""
        # Create signal 50 minutes ago
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            timeframe="1h"  # Would normally have 120 min window
        )
        signal.timestamp = datetime.now() - timedelta(minutes=50)
        storage.save_signal(signal)
        
        # With explicit minutes=30, should NOT detect (50 > 30)
        assert not storage.has_recent_signal("EURUSD", "BUY", minutes=30, timeframe="1h")
        
        # With explicit minutes=60, should detect (50 < 60)
        assert storage.has_recent_signal("EURUSD", "BUY", minutes=60, timeframe="1h")
    
    def test_different_timeframes_for_same_symbol(self, storage):
        """Signals with different timeframes should have independent windows."""
        # Create 1m signal 12 minutes ago
        signal_1m = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1050,
            timeframe="1m"
        )
        signal_1m.timestamp = datetime.now() - timedelta(minutes=12)
        storage.save_signal(signal_1m)
        
        # 1m check (12 min > 10 min window) -> should NOT detect (expired)
        assert not storage.has_recent_signal("EURUSD", "BUY", timeframe="1m")
        
        # 1h check (different timeframe) -> should NOT detect (different key)
        # NEW BEHAVIOR: Timeframe is part of deduplication key
        # This allows scalping on 1m and swing trading on 1h simultaneously
        assert not storage.has_recent_signal("EURUSD", "BUY", timeframe="1h")
    
    @pytest.mark.asyncio
    async def test_executor_uses_signal_timeframe(self, storage):
        """Executor should use signal's timeframe for deduplication."""
        from core_brain.executor import OrderExecutor
        from core_brain.risk_manager import RiskManager
        from core_brain.instrument_manager import InstrumentManager
        from unittest.mock import Mock
        
        from data_vault.storage import StorageManager
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
        storage = StorageManager(db_path=':memory:')
        state = storage.get_system_state()
        state["instruments_config"] = INSTRUMENTS_CONFIG_EXAMPLE
        storage.update_system_state(state)
        instrument_manager = InstrumentManager(storage=storage)
        risk_manager = RiskManager(storage=storage, initial_capital=10000, instrument_manager=instrument_manager)
        risk_manager.storage = storage  # Inject storage for persistence
        executor = OrderExecutor(
            risk_manager=risk_manager,
            storage=storage,
            connectors={}
        )
        
        # Create recent signal with 1m timeframe 8 minutes ago
        old_signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1050,
            timeframe="1m"
        )
        old_signal.timestamp = datetime.now() - timedelta(minutes=8)
        storage.save_signal(old_signal)
        
        # New signal with 1m timeframe (8 min < 10 min window)
        new_signal_1m = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1055,
            timeframe="1m"
        )
        
        # Should be rejected (within 10-minute window)
        result = await executor.execute_signal(new_signal_1m)
        assert result is False
        
        # Same symbol but 4h timeframe (8 min < 480 min window)
        new_signal_4h = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1055,
            timeframe="4h"
        )
        
        # Should also be rejected (within 8-hour window)
        result = await executor.execute_signal(new_signal_4h)
        assert result is False
