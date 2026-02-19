import json
import uuid
import logging
import sqlite3
from datetime import date, datetime, timezone
from utils.time_utils import to_utc
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

def calculate_deduplication_window(timeframe: Optional[str]) -> int:
    """
    Calculate dynamic deduplication window based on trading timeframe.
    """
    if not timeframe:
        return 60  # Default 1 hour
    
    tf: str = timeframe.upper().strip()
    
    timeframe_windows: Dict[str, int] = {
        "1M": 10, "M1": 10, "3M": 15, "M3": 15, "5M": 20, "M5": 20,
        "10M": 30, "M10": 30, "15M": 45, "M15": 45, "30M": 90, "M30": 90,
        "1H": 120, "H1": 120, "2H": 240, "H2": 240, "4H": 480, "H4": 480,
        "6H": 720, "H6": 720, "8H": 960, "H8": 960,
        "1D": 1440, "D1": 1440, "1W": 10080, "W1": 10080,
    }
    
    if tf in timeframe_windows:
        return timeframe_windows[tf]
    
    try:
        if tf.endswith('M') and tf[:-1].isdigit():
            minutes = int(tf[:-1])
            return max(10, minutes * 5)
        elif tf.endswith('H') and tf[:-1].isdigit():
            hours = int(tf[:-1])
            return hours * 60 * 2
        elif tf.endswith('D') and tf[:-1].isdigit():
            days = int(tf[:-1])
            return days * 1440
    except (ValueError, IndexError):
        pass
    
    logger.warning(f"Unknown timeframe '{timeframe}', using default 60 minutes")
    return 60

class SignalsMixin(BaseRepository):
    """Mixin for Signal-related database operations."""

    def _get_signal_type_value(self, signal: Any) -> str:
        """Extract signal type value, handling both string and Enum types"""
        signal_type = getattr(signal, 'signal_type', None)
        if signal_type is None:
            return 'unknown'
        if isinstance(signal_type, str):
            return signal_type
        if hasattr(signal_type, 'value'):
            return signal_type.value
        return str(signal_type)

    def save_signal(self, signal: dict) -> str:
        """Save a signal to persistent storage with full traceability."""
        signal_id = str(uuid.uuid4())
        metadata = getattr(signal, 'metadata', {})
        serialized_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                serialized_metadata[key] = value
            elif isinstance(value, Enum):
                serialized_metadata[key] = value.value
            else:
                serialized_metadata[key] = str(value)
        
        connector_type = getattr(signal, 'connector_type', 'unknown')
        if hasattr(signal, 'connector_type'):
            connector_type_value = getattr(signal, 'connector_type')
            connector_type = connector_type_value if isinstance(connector_type_value, str) else connector_type_value.value
        
        def _save(conn: sqlite3.Connection, signal_id: str) -> None:
            cursor = conn.cursor()
            timestamp = getattr(signal, 'timestamp', None)
            timestamp_value = None
            if timestamp:
                # Normaliza a UTC ISO 8601
                dt_utc = to_utc(timestamp)
                if isinstance(dt_utc, str):
                    # Si to_utc retorna string, parsear a datetime
                    from datetime import datetime
                    try:
                        dt_utc_obj = datetime.strptime(dt_utc, '%Y-%m-%d %H:%M:%S.%f')
                    except Exception:
                        dt_utc_obj = datetime.strptime(dt_utc, '%Y-%m-%d %H:%M:%S')
                else:
                    dt_utc_obj = dt_utc
                timestamp_value = dt_utc_obj.replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            
            base_columns = ['id', 'symbol', 'signal_type', 'confidence', 'metadata', 'connector_type', 'timeframe', 'price', 'direction']
            base_values = [
                signal_id,
                getattr(signal, 'symbol', 'unknown'),
                self._get_signal_type_value(signal),
                getattr(signal, 'confidence', None),
                json.dumps(serialized_metadata),
                connector_type,
                getattr(signal, 'timeframe', None),
                getattr(signal, 'price', None),
                getattr(signal, 'direction', None)
            ]
            
            entry_price = getattr(signal, 'entry_price', None)
            stop_loss = getattr(signal, 'stop_loss', None)
            take_profit = getattr(signal, 'take_profit', None)
            # Respect status from Signal object, default to PENDING if not set or None
            # Executor will update to 'EXECUTED' after confirmation
            status = getattr(signal, 'status', None) or 'PENDING'
            
            if timestamp_value is not None:
                columns = ['timestamp', 'status'] + base_columns
                values = [timestamp_value, status] + base_values
            else:
                columns = ['status'] + base_columns
                values = [status] + base_values
            
            placeholders = ','.join('?' for _ in values)
            columns_str = ','.join(columns)
            
            cursor.execute(f"""
                INSERT INTO signals ({columns_str})
                VALUES ({placeholders})
            """, values)
            conn.commit()
        
        self._execute_serialized(_save, signal_id)
        return signal_id

    def get_signals(self, limit: int = 100, status: Optional[str] = None) -> List[Dict]:
        """Get signals from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM signals"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            signals = []
            for row in rows:
                signal = dict(row)
                signal['metadata'] = json.loads(signal['metadata']) if signal['metadata'] else {}
                signals.append(signal)
            return signals
        finally:
            self._close_conn(conn)

    def get_signal_by_id(self, signal_id: str) -> Optional[Dict]:
        """Get a signal by its ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
            row = cursor.fetchone()
            if row:
                signal = dict(row)
                signal['metadata'] = json.loads(signal['metadata']) if signal['metadata'] else {}
                return signal
            return None
        finally:
            self._close_conn(conn)

    def get_signals_by_date(self, target_date: date, status: Optional[str] = None) -> List[Dict]:
        """Get all signals from a specific date"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM signals WHERE DATE(timestamp) = ?"
            params = [target_date.isoformat()]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY timestamp DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            signals = []
            for row in rows:
                signal = dict(row)
                signal['metadata'] = json.loads(signal['metadata']) if signal['metadata'] else {}
                signals.append(signal)
            return signals
        finally:
            self._close_conn(conn)

    def update_signal_status(self, signal_id: str, status: str, metadata_update: Optional[Dict] = None) -> None:
        """Update signal status and optionally metadata"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if metadata_update:
                cursor.execute("SELECT metadata FROM signals WHERE id = ?", (signal_id,))
                row = cursor.fetchone()
                if row:
                    current_metadata = json.loads(row['metadata']) if row['metadata'] else {}
                    current_metadata.update(metadata_update)
                else:
                    current_metadata = dict(metadata_update)

                # Normalizar updated_at
                now = datetime.now(timezone.utc).replace(microsecond=0)
                now_str = now.strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    UPDATE signals 
                    SET status = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                """, (status, json.dumps(current_metadata), now_str, signal_id))

                if 'ticket' in metadata_update:
                    cursor.execute("""
                        UPDATE signals 
                        SET order_id = ?
                        WHERE id = ?
                    """, (str(metadata_update['ticket']), signal_id))
            else:
                now = datetime.now(timezone.utc).replace(microsecond=0)
                now_str = now.strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    UPDATE signals 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (status, now_str, signal_id))
            conn.commit()
        finally:
            self._close_conn(conn)

    def has_recent_signal(self, symbol: str, signal_type: str, timeframe: Optional[str] = None, minutes: Optional[int] = None, exclude_id: Optional[str] = None) -> bool:
        """Check if there's a recent signal for the given symbol and type within the deduplication window"""
        if minutes is None:
            minutes = calculate_deduplication_window(timeframe)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Base query: Only consider PENDING or EXECUTED signals as duplicates
            # Exclude REJECTED, CLOSED, etc. (only get PENDING and EXECUTED)
            query = """
                SELECT COUNT(*) FROM signals 
                WHERE symbol = ? 
                AND signal_type = ? 
                AND timestamp >= datetime('now', 'localtime', '-' || ? || ' minutes')
                AND (timeframe = ? OR ? IS NULL)
                AND status IN ('PENDING', 'EXECUTED', 'EXPIRED', 'active')
            """
            params = [symbol, signal_type, minutes, timeframe, timeframe]
            
            # Support excluding the current signal ID (to avoid self-collision in Executor)
            if exclude_id:
                query += " AND id != ?"
                params.append(exclude_id)
                
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            
            if count > 0:
                logger.info(f"DEBUG DB: has_recent_signal({symbol}, {signal_type}, {timeframe}) -> TRUE (Count: {count})")
                
            return count > 0
        finally:
            self._close_conn(conn)

    def get_recent_signals(self, minutes: int = 60, limit: int = 100, symbol: str = None, timeframe: str = None, status: str = None) -> List[Dict]:
        """Get recent signals within the last N minutes with optional filters"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM signals WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' minutes')"
            params = [minutes]
            
            if symbol:
                symbol_list = [s.strip().upper().replace('=X', '') for s in symbol.split(',') if s.strip()]
                if symbol_list:
                    placeholders = ','.join(['?'] * len(symbol_list))
                    query += f" AND UPPER(REPLACE(symbol, '=X', '')) IN ({placeholders})"
                    params.extend(symbol_list)
            
            if timeframe:
                tf_list = [tf.strip().upper() for tf in timeframe.split(',') if tf.strip()]
                if tf_list:
                    placeholders = ','.join(['?'] * len(tf_list))
                    query += f" AND timeframe IN ({placeholders})"
                    params.extend(tf_list)

            if status:
                status_list = [s.strip().upper() for s in status.split(',') if s.strip()]
                if status_list:
                    placeholders = ','.join(['?'] * len(status_list))
                    query += f" AND UPPER(status) IN ({placeholders})"
                    params.extend(status_list)
                
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            signals = []
            for row in rows:
                signal = dict(row)
                metadata_raw = signal.get('metadata')
                if metadata_raw:
                    try:
                        signal['metadata'] = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                    except:
                        signal['metadata'] = {}
                else:
                    signal['metadata'] = {}
                signals.append(signal)
            return signals
        finally:
            self._close_conn(conn)

    def get_open_operations(self) -> List[Dict]:
        """Get signals that are executed but not closed (open operations)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.* FROM signals s
                LEFT JOIN trade_results t ON s.id = t.signal_id
                WHERE UPPER(s.status) = 'EXECUTED' 
                AND t.signal_id IS NULL
                ORDER BY s.timestamp DESC
            """)
            rows = cursor.fetchall()
            operations = []
            for row in rows:
                operation = dict(row)
                if operation.get('metadata'):
                    operation['metadata'] = json.loads(operation['metadata'])
                operations.append(operation)
            return operations
        finally:
            self._close_conn(conn)

    def count_executed_signals(self, date_filter: Optional[date] = None) -> int:
        """Count executed signals, optionally filtered by date"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if date_filter:
                cursor.execute("""
                    SELECT COUNT(*) FROM signals 
                    WHERE LOWER(status) = 'executed' 
                    AND DATE(timestamp) = ?
                """, (date_filter.isoformat(),))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM signals 
                    WHERE LOWER(status) = 'executed'
                """)
            return cursor.fetchone()[0]
        finally:
            self._close_conn(conn)

    def get_signals_today(self) -> List[Dict]:
        """Get signals from today (for dashboard compatibility)"""
        return self.get_signals_by_date(date.today())

    def get_open_signal_id(self, symbol: str) -> Optional[str]:
        """
        Get the signal ID of the open position for a symbol.
        Returns None if no open position.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id FROM signals s
                LEFT JOIN trade_results t ON s.id = t.signal_id
                WHERE s.symbol = ? 
                AND UPPER(s.status) = 'EXECUTED' 
                AND t.signal_id IS NULL
                ORDER BY s.timestamp DESC
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self._close_conn(conn)
