"""
Tests for MultiTimeframeLimiter - EDGE protection for multi-timeframe operations

TDD Tests for FASE 2: Límites exposición multi-timeframe
"""
import pytest
from datetime import datetime
from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
from models.signal import Signal, SignalType, ConnectorType


def test_max_positions_per_symbol_enforced(storage):
    """Should block 4th position for same symbol (max=3)"""
    config = {'multi_timeframe_limits': {'max_positions_per_symbol': 3}}
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create 3 open positions EURUSD
    for i, tf in enumerate(['M15', 'H1', 'H4']):
        signal = Signal(
            symbol='EURUSD',
            signal_type=SignalType.BUY,
            timeframe=tf,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.10,
            stop_loss=1.08,
            take_profit=1.15,
            volume=1.0,
            confidence=0.95,
            timestamp=datetime.now().isoformat()
        )
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 12345 + i})
    
    # Try 4th position (should be blocked)
    new_signal = Signal(
        symbol='EURUSD',
        signal_type=SignalType.BUY,
        timeframe='D1',
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.10,
        stop_loss=1.08,
        take_profit=1.15,
        volume=1.0,
        confidence=0.95,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(new_signal)
    
    assert not is_valid
    assert "MAX_POSITIONS_EXCEEDED" in reason
    assert "3/3" in reason
    assert "EURUSD" in reason


def test_max_volume_per_symbol_enforced(storage):
    """Should block if total volume exceeds limit (max=5.0 lots)"""
    config = {'multi_timeframe_limits': {'max_total_volume_per_symbol': 5.0}}
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create 2 positions: 2.0 + 2.5 = 4.5 lots total
    for volume, tf in [(2.0, 'H1'), (2.5, 'H4')]:
        signal = Signal(
            symbol='GBPUSD',
            signal_type=SignalType.SELL,
            timeframe=tf,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.2501,  # Theo=1.2501, Real_Bid=1.2500 => 1.0 pip slippage
            stop_loss=1.27,
            take_profit=1.20,
            volume=volume,
            confidence=0.92,
            timestamp=datetime.now().isoformat()
        )
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 99999, 'lot_size': volume})
    
    # Try adding 1.0 lot (total would be 5.5 > 5.0)
    new_signal = Signal(
        symbol='GBPUSD',
        signal_type=SignalType.SELL,
        timeframe='D1',
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.2501,  # Mantener realismo de slippage
        stop_loss=1.27,
        take_profit=1.20,
        volume=1.0,
        confidence=0.90,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(new_signal)
    
    assert not is_valid
    assert "MAX_VOLUME_EXCEEDED" in reason
    assert "5.5" in reason or "5.50" in reason
    assert "5.0" in reason or "5.00" in reason


def test_hedge_alert_logged_but_not_blocked(storage, caplog):
    """Should log warning for low net exposure (hedge) but allow signal"""
    config = {
        'multi_timeframe_limits': {
            'alert_hedge_threshold': 0.2,
            'allow_opposite_signals': True
        }
    }
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create BUY 2.0 lots
    signal_buy = Signal(
        symbol='AUDUSD',
        signal_type=SignalType.BUY,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        entry_price=0.70,
        stop_loss=0.68,
        take_profit=0.75,
        volume=2.0,
        confidence=0.93,
        timestamp=datetime.now().isoformat()
    )
    signal_id = storage.save_signal(signal_buy)
    storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 11111, 'lot_size': 2.0})
    
    # Try adding SELL 1.8 lots (net exposure = 0.2/3.8 = 5.3% < 20%)
    signal_sell = Signal(
        symbol='AUDUSD',
        signal_type=SignalType.SELL,
        timeframe='H4',
        connector_type=ConnectorType.METATRADER5,
        entry_price=0.71,
        stop_loss=0.73,
        take_profit=0.66,
        volume=1.8,
        confidence=0.91,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(signal_sell)
    
    # Signal should be ALLOWED (not blocked)
    assert is_valid
    assert reason == "OK"
    
    # But warning should be logged
    assert "HEDGE ALERT" in caplog.text
    assert "AUDUSD" in caplog.text


def test_opposite_signals_blocked_when_disabled(storage):
    """Should reject opposite signal if allow_opposite_signals=false"""
    config = {
        'multi_timeframe_limits': {
            'allow_opposite_signals': False
        }
    }
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create BUY position
    signal_buy = Signal(
        symbol='USDJPY',
        signal_type=SignalType.BUY,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        entry_price=110.0,
        stop_loss=108.0,
        take_profit=115.0,
        volume=1.0,
        confidence=0.94,
        timestamp=datetime.now().isoformat()
    )
    signal_id = storage.save_signal(signal_buy)
    storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 22222})
    
    # Try adding SELL position (opposite)
    signal_sell = Signal(
        symbol='USDJPY',
        signal_type=SignalType.SELL,
        timeframe='H4',
        connector_type=ConnectorType.METATRADER5,
        entry_price=111.0,
        stop_loss=113.0,
        take_profit=106.0,
        volume=1.0,
        confidence=0.92,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(signal_sell)
    
    assert not is_valid
    assert "OPPOSITE_SIGNAL_BLOCKED" in reason
    assert "USDJPY" in reason
    assert "BUY" in reason


def test_limiter_disabled_allows_all(storage):
    """Should allow all signals when limiter is disabled"""
    config = {'multi_timeframe_limits': {'enabled': False}}
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create 10 positions (way over any limit)
    for i in range(10):
        signal = Signal(
            symbol='NZDUSD',
            signal_type=SignalType.BUY,
            timeframe=f'TF{i}',
            connector_type=ConnectorType.METATRADER5,
            entry_price=0.60,
            stop_loss=0.58,
            take_profit=0.65,
            volume=5.0,  # High volume
            confidence=0.95,
            timestamp=datetime.now().isoformat()
        )
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 30000 + i})
    
    # Try adding another (should be allowed because limiter disabled)
    new_signal = Signal(
        symbol='NZDUSD',
        signal_type=SignalType.BUY,
        timeframe='TEST',
        connector_type=ConnectorType.METATRADER5,
        entry_price=0.60,
        stop_loss=0.58,
        take_profit=0.65,
        volume=100.0,
        confidence=0.95,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(new_signal)
    
    assert is_valid
    assert "disabled" in reason.lower()


def test_different_symbols_not_affected(storage):
    """Should NOT count positions from different symbols"""
    config = {'multi_timeframe_limits': {'max_positions_per_symbol': 2}}
    limiter = MultiTimeframeLimiter(storage, config)
    
    # Create 2 EURUSD positions
    for i in range(2):
        signal = Signal(
            symbol='EURUSD',
            signal_type=SignalType.BUY,
            timeframe=f'H{i+1}',
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.10,
            stop_loss=1.08,
            take_profit=1.15,
            volume=1.0,
            confidence=0.95,
            timestamp=datetime.now().isoformat()
        )
        signal_id = storage.save_signal(signal)
        storage.update_signal_status(signal_id, 'EXECUTED', {'ticket': 40000 + i})
    
    # Try adding GBPUSD position (different symbol, should be allowed)
    new_signal = Signal(
        symbol='GBPUSD',  # DIFFERENT symbol
        signal_type=SignalType.BUY,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.2499,  # Theo=1.2499, Real_Ask=1.2501 => 2.0 pips slippage
        stop_loss=1.23,
        take_profit=1.30,
        volume=1.0,
        confidence=0.95,
        timestamp=datetime.now().isoformat()
    )
    
    is_valid, reason = limiter.validate_new_signal(new_signal)
    
    assert is_valid
    assert reason == "OK"
