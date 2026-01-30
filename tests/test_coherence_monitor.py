"""
Tests for CoherenceMonitor end-to-end consistency checks.
"""
from datetime import datetime, timedelta

from core_brain.coherence_monitor import CoherenceMonitor
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


def test_coherence_detects_unnormalized_and_missing_ticket():
    storage = StorageManager(db_path=':memory:')

    signal_id = storage.save_signal(Signal(
        symbol="USDJPY=X",
        signal_type=SignalType.BUY,
        confidence=0.8,
        connector_type=ConnectorType.METATRADER5,
        entry_price=150.0
    ))

    monitor = CoherenceMonitor(storage=storage, pending_timeout_minutes=15, lookback_minutes=120)
    events = monitor.run_once()

    reasons = {e.reason for e in events}
    assert signal_id is not None
    assert "UNNORMALIZED_SYMBOL" in reasons
    assert "EXECUTED_WITHOUT_TICKET" in reasons


def test_coherence_detects_pending_timeout():
    storage = StorageManager(db_path=':memory:')

    signal_id = storage.save_signal(Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.8,
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.1
    ))

    # Force status to PENDING and backdate timestamp
    storage.update_signal_status(signal_id, "PENDING")
    old_ts = (datetime.now() - timedelta(minutes=10)).isoformat()
    with storage._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE signals SET timestamp = ? WHERE id = ?", (old_ts, signal_id))
        conn.commit()

    monitor = CoherenceMonitor(storage=storage, pending_timeout_minutes=1, lookback_minutes=120)
    events = monitor.run_once()

    reasons = {e.reason for e in events}
    assert "PENDING_TIMEOUT" in reasons
