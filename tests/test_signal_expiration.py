"""
Tests for SignalExpirationManager - Dynamic signal expiration by timeframe

Tests core functionality:
1. M5 sys_signals expire after 5 minutes
2. H1 sys_signals expire after 60 minutes
3. D1 sys_signals expire after 24 hours
4. Signals within window are NOT expired
5. Multiple timeframes expire correctly
6. EXECUTED sys_signals are NOT expired (only PENDING)

TDD Approach: Tests created BEFORE implementation
"""
import pytest
from datetime import datetime, timedelta
from core_brain.signal_expiration_manager import SignalExpirationManager, EXPIRATION_WINDOWS
from models.signal import Signal, SignalType, ConnectorType


def test_m5_signal_expires_after_5_minutes(storage):
    """M5 signal should expire after 20 minutes (4-candle rule: 4 × 5 = 20 min)"""
    # Create M5 signal 25 minutes ago (exceeds 20 min window)
    old_time = datetime.now() - timedelta(minutes=25)
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
            UPDATE sys_signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['M5'] == 1
    
    # Check signal status
    sys_signals = storage.get_sys_signals()
    expired_signal = next(s for s in sys_signals if s['id'] == signal_id)
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
            UPDATE sys_signals SET timestamp = ? WHERE id = ?
        """, (recent_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify NOT expired
    assert stats['total_expired'] == 0
    
    sys_signals = storage.get_sys_signals()
    pending_signal = next(s for s in sys_signals if s['id'] == signal_id)
    assert pending_signal['status'] == 'PENDING'  # Still PENDING


def test_d1_signal_expires_after_24_hours(storage):
    """D1 signal should expire after 4 days (4-candle rule: 4 × 1440 = 5760 min)"""
    # Create D1 signal 5 days ago (exceeds 5760 min = 4 day window)
    old_time = datetime.now() - timedelta(days=5)
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
            UPDATE sys_signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['D1'] == 1


def test_multiple_timeframes_expire_correctly(storage):
    """Multiple sys_signals with different timeframes expire according to their windows"""
    base_time = datetime.now()
    
    # M5 signal (3min ago) - NOT expired (within 20min window)
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
    
    # M5 signal (25min ago) - EXPIRED (exceeds 20min 4-candle window)
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

    # H1 signal (5h ago) - EXPIRED (exceeds 240min = 4h 4-candle window)
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

    # D1 signal (12h ago) - NOT expired (within 5760min = 4-day window)
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
        cursor.execute("UPDATE sys_signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(minutes=3), m5_recent_id))
        cursor.execute("UPDATE sys_signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(minutes=25), m5_old_id))
        cursor.execute("UPDATE sys_signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(hours=5), h1_old_id))
        cursor.execute("UPDATE sys_signals SET timestamp = ? WHERE id = ?",
                      (base_time - timedelta(hours=12), d1_recent_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify: 2 expired (M5 10min + H1 2h), 2 still PENDING
    assert stats['total_expired'] == 2
    assert stats['by_timeframe']['M5'] == 1
    assert stats['by_timeframe']['H1'] == 1
    
    # Verify individual statuses
    sys_signals = storage.get_sys_signals()
    sys_signals_dict = {s['id']: s for s in sys_signals}
    
    assert sys_signals_dict[m5_recent_id]['status'] == 'PENDING'  # Still valid
    assert sys_signals_dict[m5_old_id]['status'] == 'EXPIRED'
    assert sys_signals_dict[h1_old_id]['status'] == 'EXPIRED'
    assert sys_signals_dict[d1_recent_id]['status'] == 'PENDING'  # Still valid


def test_executed_sys_signals_not_expired(storage):
    """EXECUTED sys_signals should NOT be expired (only PENDING)"""
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
            UPDATE sys_signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify: 0 expired (EXECUTED sys_signals exempt)
    assert stats['total_expired'] == 0
    
    sys_signals = storage.get_sys_signals()
    executed_signal = next(s for s in sys_signals if s['id'] == signal_id)
    assert executed_signal['status'] == 'EXECUTED'  # Still EXECUTED


def test_h4_signal_expires_after_4_hours(storage):
    """H4 signal should expire after 16 hours (4-candle rule: 4 × 240 = 960 min)"""
    # Create H4 signal 17 hours ago (exceeds 960 min = 16 h window)
    old_time = datetime.now() - timedelta(hours=17)
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
            UPDATE sys_signals SET timestamp = ? WHERE id = ?
        """, (old_time, signal_id))
        conn.commit()
    finally:
        storage._close_conn(conn)
    
    # Run expiration
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_sys_signals()
    
    # Verify
    assert stats['total_expired'] == 1
    assert stats['by_timeframe']['H4'] == 1


def test_expiration_windows_configuration():
    """Verify EXPIRATION_WINDOWS configuration matches 4-candle rule (4 × timeframe minutes)"""
    assert EXPIRATION_WINDOWS['M5']  == 20    # 4 × 5 min
    assert EXPIRATION_WINDOWS['M15'] == 60    # 4 × 15 min
    assert EXPIRATION_WINDOWS['M30'] == 120   # 4 × 30 min
    assert EXPIRATION_WINDOWS['H1']  == 240   # 4 × 60 min
    assert EXPIRATION_WINDOWS['H4']  == 960   # 4 × 240 min
    assert EXPIRATION_WINDOWS['D1']  == 5760  # 4 × 1440 min
