"""
Tests for SignalExpirationManager - Dynamic signal expiration by timeframe

Tests core functionality:
1. M5 signals expire after 5 minutes
2. H1 signals expire after 60 minutes
3. D1 signals expire after 24 hours
4. Signals within window are NOT expired
5. Multiple timeframes expire correctly
6. EXECUTED signals are NOT expired (only PENDING)

TDD Approach: Tests created BEFORE implementation
"""
import pytest
from datetime import datetime, timedelta
from core_brain.signal_expiration_manager import SignalExpirationManager, EXPIRATION_WINDOWS
from models.signal import Signal, SignalType, ConnectorType


def test_m5_signal_expires_after_5_minutes(storage):
    """M5 signal should expire after 5 minutes"""
    # Create M5 signal 10 minutes ago (exceeds 5min window)
    old_time = datetime.now() - timedelta(minutes=10)
    signal = Signal(
        symbol='EURUSD',
        signal_type=SignalType.BUY,
        timeframe='M5',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.95,
        entry_price=1.10,
        stop_loss=1.08,
        take_profit=1.15,
        volume=1.0
    )
    signal_id = storage.save_signal(signal)
    
    # Manually update timestamp to 10 minutes ago
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['M5'] == 1
    
    # Check signal status
    signals = storage.get_signals()
    expired_signal = next(s for s in signals if s['id'] == signal_id)
    assert expired_signal['status'] == 'EXPIRED'
    assert 'expired_at' in expired_signal['metadata']
    assert 'reason' in expired_signal['metadata']


def test_h1_signal_not_expired_within_60_minutes(storage):
    """H1 signal should NOT expire within 60 minutes"""
    # Create H1 signal 30 minutes ago (within 60min window)
    recent_time = datetime.now() - timedelta(minutes=30)
    signal = Signal(
        symbol='GBPUSD',
        signal_type=SignalType.SELL,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.92,
        entry_price=1.25,
        stop_loss=1.27,
        take_profit=1.20,
        volume=1.0
    )
    signal_id = storage.save_signal(signal)
    
    # Update timestamp
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET timestamp = ? WHERE id = ?
        """, (recent_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify NOT expired
    assert stats['total_expired'] == 0
    
    signals = storage.get_signals()
    pending_signal = next(s for s in signals if s['id'] == signal_id)
    assert pending_signal['status'] == 'PENDING'  # Still PENDING


def test_d1_signal_expires_after_24_hours(storage):
    """D1 signal should expire after 24 hours"""
    # Create D1 signal 25 hours ago (exceeds 24h window)
    old_time = datetime.now() - timedelta(hours=25)
    signal = Signal(
        symbol='USDJPY',
        signal_type=SignalType.BUY,
        timeframe='D1',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.88,
        entry_price=110.0,
        stop_loss=108.0,
        take_profit=115.0,
        volume=1.0
    )
    signal_id = storage.save_signal(signal)
    
    # Update timestamp
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['D1'] == 1


def test_multiple_timeframes_expire_correctly(storage):
    """Multiple signals with different timeframes expire according to their windows"""
    base_time = datetime.now()
    
    # M5 signal (3min ago) - NOT expired (within 5min window)
    m5_recent = Signal(
        symbol='EURUSD',
        signal_type=SignalType.BUY,
        timeframe='M5',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.95,
        entry_price=1.10,
        stop_loss=1.08,
        take_profit=1.15,
        volume=1.0
    )
    m5_recent_id = storage.save_signal(m5_recent)
    
    # M5 signal (10min ago) - EXPIRED (exceeds 5min window)
    m5_old = Signal(
        symbol='GBPUSD',
        signal_type=SignalType.SELL,
        timeframe='M5',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.92,
        entry_price=1.25,
        stop_loss=1.27,
        take_profit=1.20,
        volume=1.0
    )
    m5_old_id = storage.save_signal(m5_old)
    
    # H1 signal (2h ago) - EXPIRED (exceeds 60min window)
    h1_old = Signal(
        symbol='USDJPY',
        signal_type=SignalType.BUY,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.88,
        entry_price=110.0,
        stop_loss=108.0,
        take_profit=115.0,
        volume=1.0
    )
    h1_old_id = storage.save_signal(h1_old)
    
    # D1 signal (12h ago) - NOT expired (within 24h window)
    d1_recent = Signal(
        symbol='AUDUSD',
        signal_type=SignalType.BUY,
        timeframe='D1',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.90,
        entry_price=0.70,
        stop_loss=0.68,
        take_profit=0.75,
        volume=1.0
    )
    d1_recent_id = storage.save_signal(d1_recent)
    
    # Update timestamps
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(minutes=3), m5_recent_id))
        cursor.execute("UPDATE signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(minutes=10), m5_old_id))
        cursor.execute("UPDATE signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(hours=2), h1_old_id))
        cursor.execute("UPDATE signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(hours=12), d1_recent_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify: 2 expired (M5 10min + H1 2h), 2 still PENDING
    assert stats['total_expired'] == 2
    assert stats['by_timeframe']['M5'] == 1
    assert stats['by_timeframe']['H1'] == 1
    
    # Verify individual statuses
    signals = storage.get_signals()
    signals_dict = {s['id']: s for s in signals}
    
    assert signals_dict[m5_recent_id]['status'] == 'PENDING'  # Still valid
    assert signals_dict[m5_old_id]['status'] == 'EXPIRED'
    assert signals_dict[h1_old_id]['status'] == 'EXPIRED'
    assert signals_dict[d1_recent_id]['status'] == 'PENDING'  # Still valid


def test_executed_signals_not_expired(storage):
    """EXECUTED signals should NOT be expired (only PENDING)"""
    # Create old signal and mark as EXECUTED
    old_time = datetime.now() - timedelta(hours=5)
    signal = Signal(
        symbol='EURUSD',
        signal_type=SignalType.BUY,
        timeframe='H1',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.94,
        entry_price=1.10,
        stop_loss=1.08,
        take_profit=1.15,
        volume=1.0
    )
    signal_id = storage.save_signal(signal)
    
    # Mark as EXECUTED
    storage.update_signal_status(signal_id, 'EXECUTED', {
        'ticket': 12345,
        'execution_price': 1.10,
        'execution_time': datetime.now().isoformat()
    })
    
    # Update timestamp to 5h ago (exceeds H1 60min window)
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify: 0 expired (EXECUTED signals exempt)
    assert stats['total_expired'] == 0
    
    signals = storage.get_signals()
    executed_signal = next(s for s in signals if s['id'] == signal_id)
    assert executed_signal['status'] == 'EXECUTED'  # Still EXECUTED


def test_h4_signal_expires_after_4_hours(storage):
    """H4 signal should expire after 4 hours"""
    # Create H4 signal 5 hours ago (exceeds 240min window)
    old_time = datetime.now() - timedelta(hours=5)
    signal = Signal(
        symbol='EURGBP',
        signal_type=SignalType.SELL,
        timeframe='H4',
        connector_type=ConnectorType.METATRADER5,
        confidence=0.91,
        entry_price=0.85,
        stop_loss=0.87,
        take_profit=0.80,
        volume=1.0
    )
    signal_id = storage.save_signal(signal)
    
    # Update timestamp
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['H4'] == 1


def test_expiration_windows_configuration():
    """Verify EXPIRATION_WINDOWS configuration matches 1-candle rule"""
    assert EXPIRATION_WINDOWS['M5'] == 5
    assert EXPIRATION_WINDOWS['M15'] == 15
    assert EXPIRATION_WINDOWS['M30'] == 30
    assert EXPIRATION_WINDOWS['H1'] == 60
    assert EXPIRATION_WINDOWS['H4'] == 240
    assert EXPIRATION_WINDOWS['D1'] == 1440
