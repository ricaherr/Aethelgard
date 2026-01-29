"""
Test: Multi-Timeframe Signal Deduplication
===========================================

Validates that signals from the same symbol on different timeframes
are NOT considered duplicates, allowing strategies like:
- Scalping on M1/M5
- Day trading on M15/H1
- Swing trading on H4/D1

Simultaneously on the same instrument.
"""
import pytest
from datetime import datetime
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


@pytest.fixture
def storage():
    """Fresh storage for each test"""
    storage = StorageManager(db_path=":memory:")
    yield storage


def create_signal(symbol: str, signal_type: SignalType, timeframe: str) -> Signal:
    """Helper to create test signals"""
    return Signal(
        symbol=symbol,
        signal_type=signal_type,
        confidence=0.85,
        connector_type=ConnectorType.GENERIC,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        timeframe=timeframe,
        strategy_id="test_strategy"
    )


def test_same_symbol_different_timeframes_not_duplicates(storage):
    """
    CRITICAL: Signals for the same symbol on different timeframes
    should NOT be considered duplicates.
    
    Use case: Scalper trades EURUSD on M5, swing trader on H4.
    """
    # Save M5 signal
    signal_m5 = create_signal("EURUSD", SignalType.BUY, "M5")
    storage.save_signal(signal_m5)
    
    # Check H4 signal should NOT be duplicate
    has_duplicate_h4 = storage.has_recent_signal(
        symbol="EURUSD",
        signal_type="BUY",
        timeframe="H4"
    )
    
    assert not has_duplicate_h4, "H4 signal should NOT be duplicate of M5 signal"


def test_same_symbol_same_timeframe_is_duplicate(storage):
    """
    Signals for the same symbol on the SAME timeframe
    SHOULD be considered duplicates within the deduplication window.
    """
    # Save M5 signal
    signal_m5 = create_signal("EURUSD", SignalType.BUY, "M5")
    storage.save_signal(signal_m5)
    
    # Check another M5 signal should be duplicate
    has_duplicate_m5 = storage.has_recent_signal(
        symbol="EURUSD",
        signal_type="BUY",
        timeframe="M5"
    )
    
    assert has_duplicate_m5, "M5 signal should BE duplicate of another M5 signal"


def test_multiple_timeframes_same_instrument(storage):
    """
    Test that we can have active signals on M5, H1, and H4
    for the same instrument simultaneously.
    """
    # Save signals on different timeframes
    signal_m5 = create_signal("BTCUSD", SignalType.BUY, "M5")
    signal_h1 = create_signal("BTCUSD", SignalType.BUY, "H1")
    signal_h4 = create_signal("BTCUSD", SignalType.BUY, "H4")
    
    storage.save_signal(signal_m5)
    storage.save_signal(signal_h1)
    storage.save_signal(signal_h4)
    
    # Verify each timeframe has its own signal tracked
    assert storage.has_recent_signal("BTCUSD", "BUY", timeframe="M5")
    assert storage.has_recent_signal("BTCUSD", "BUY", timeframe="H1")
    assert storage.has_recent_signal("BTCUSD", "BUY", timeframe="H4")
    
    # D1 should NOT have a signal
    assert not storage.has_recent_signal("BTCUSD", "BUY", timeframe="D1")


def test_different_signal_types_same_timeframe(storage):
    """
    BUY and SELL on the same timeframe should be independent.
    """
    signal_buy = create_signal("GBPUSD", SignalType.BUY, "M15")
    signal_sell = create_signal("GBPUSD", SignalType.SELL, "M15")
    
    storage.save_signal(signal_buy)
    storage.save_signal(signal_sell)
    
    # Both should exist independently
    assert storage.has_recent_signal("GBPUSD", "BUY", timeframe="M15")
    assert storage.has_recent_signal("GBPUSD", "SELL", timeframe="M15")


def test_deduplication_window_varies_by_timeframe(storage):
    """
    Verify that deduplication windows scale with timeframe.
    
    M5 should have shorter window than H4.
    """
    from data_vault.storage import calculate_deduplication_window
    
    window_m5 = calculate_deduplication_window("M5")
    window_h4 = calculate_deduplication_window("H4")
    window_d1 = calculate_deduplication_window("D1")
    
    # Higher timeframes should have larger windows
    assert window_m5 < window_h4 < window_d1
    assert window_m5 == 20  # 20 minutes for M5
    assert window_h4 == 480  # 8 hours for H4
    assert window_d1 == 1440  # 24 hours for D1


def test_legacy_fallback_without_timeframe(storage):
    """
    If timeframe is not provided, system should still work
    but will deduplicate globally (legacy behavior).
    """
    signal = create_signal("ETHUSD", SignalType.BUY, "M5")
    storage.save_signal(signal)
    
    # Check without specifying timeframe (should find any signal)
    has_duplicate = storage.has_recent_signal("ETHUSD", "BUY")
    assert has_duplicate, "Should find signal even without timeframe specified"
