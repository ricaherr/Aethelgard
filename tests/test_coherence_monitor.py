"""
Tests for CoherenceMonitor end-to-end consistency checks.
"""

from datetime import datetime, timedelta, timezone
from utils.time_utils import to_utc

from core_brain.coherence_monitor import CoherenceMonitor
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


def test_coherence_detects_unnormalized_and_missing_ticket():
    storage = StorageManager(db_path=':memory:')
    # Limpiar tabla signals por si acaso
    with storage._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM signals")
        conn.commit()

    from models.signal import ConnectorType
    from datetime import datetime
    signal = Signal(
        symbol="USDJPY=X",
        signal_type=SignalType.BUY,
        confidence=0.8,
        connector_type=ConnectorType.METATRADER5.value,
        entry_price=150.0,
        timestamp=to_utc(datetime.now(timezone.utc))
    )
    signal_id = storage.save_signal(signal)

    # Set signal to EXECUTED status to trigger EXECUTED_WITHOUT_TICKET check
    storage.update_signal_status(signal_id, "EXECUTED")

    # Debug: inspeccionar contenido real de la tabla signals
    with storage._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM signals")
        all_rows = cur.fetchall()
        print(f"Contenido real en signals tras insert: {all_rows}")
        for row in all_rows:
            print(f"Row id={row['id']} timestamp={row['timestamp']}")
        assert len(all_rows) > 0, "La tabla signals está vacía tras el insert."
        # Debug: mostrar timestamp insertado y resultado de consulta manual
        cur.execute("SELECT timestamp FROM signals")
        ts_row = cur.fetchone()
        print(f"Timestamp insertado: {ts_row['timestamp']}")
        cur.execute("SELECT datetime('now')")
        now_row = cur.fetchone()
        print(f"SQLite datetime('now'): {now_row[0]}")
        cur.execute("SELECT * FROM signals WHERE datetime(timestamp) >= datetime('now', '-120 minutes')")
        manual_rows = cur.fetchall()
        print(f"Resultado consulta manual: {manual_rows}")

    monitor = CoherenceMonitor(storage=storage, pending_timeout_minutes=15, lookback_minutes=120)
    signals = storage.get_recent_signals(minutes=120)
    # Validación funcional
    assert signals, "No se recuperaron señales recientes."
    events = monitor.run_once()
    assert events, "No se generaron eventos de coherencia."
    reasons = {e.reason for e in events}
    assert signal_id is not None
    assert "UNNORMALIZED_SYMBOL" in reasons
    assert "EXECUTED_WITHOUT_TICKET" in reasons


def test_coherence_detects_pending_timeout():
    storage = StorageManager(db_path=':memory:')
    # Limpiar tabla signals por si acaso
    with storage._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM signals")
        conn.commit()

    from models.signal import ConnectorType
    from datetime import datetime
    signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.8,
        connector_type=ConnectorType.METATRADER5.value,
        entry_price=1.1,
        timestamp=to_utc(datetime.now(timezone.utc))
    )
    signal_id = storage.save_signal(signal)

    # Force status to PENDING and backdate timestamp en UTC
    storage.update_signal_status(signal_id, "PENDING")
    old_ts = to_utc(datetime.now(timezone.utc) - timedelta(minutes=10))
    with storage._get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE signals SET timestamp = ? WHERE id = ?", (old_ts, signal_id))
        conn.commit()

    monitor = CoherenceMonitor(storage=storage, pending_timeout_minutes=1, lookback_minutes=120)
    signals = storage.get_recent_signals(minutes=120)
    # Validación funcional
    assert signals, "No se recuperaron señales recientes."
    events = monitor.run_once()
    assert events, "No se generaron eventos de coherencia."
    reasons = {e.reason for e in events}
    assert "PENDING_TIMEOUT" in reasons
