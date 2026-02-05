from _thread import lock
import threading
import time
import json
import os
import sqlite3
import logging
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Generator
from contextlib import contextmanager
from utils.encryption import CredentialEncryption, get_encryptor

logger: logging.Logger = logging.getLogger(__name__)

# Register datetime adapter to avoid deprecation warnings in Python 3.12+
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("timestamp", lambda s: datetime.fromisoformat(s.decode()))


def calculate_deduplication_window(timeframe: Optional[str]) -> int:
    """
    Calculate dynamic deduplication window based on trading timeframe.
    
    Args:
        timeframe: Trading timeframe (e.g., "1m", "5m", "15m", "1h", "4h", "1D")
    
    Returns:
        Deduplication window in minutes
        
    Examples:
        - "1m" or "M1" -> 10 minutes
        - "5m" or "M5" -> 20 minutes
        - "15m" or "M15" -> 45 minutes
        - "1h" or "H1" -> 120 minutes (2 hours)
        - "4h" or "H4" -> 480 minutes (8 hours)
        - "1D" or "D1" -> 1440 minutes (24 hours)
    """
    if not timeframe:
        return 60  # Default 1 hour
    
    # Normalize timeframe to uppercase
    tf: str = timeframe.upper().strip()
    
    # Timeframe mapping: timeframe -> window in minutes
    timeframe_windows: Dict[str, int] = {
        # Minutes
        "1M": 10,
        "M1": 10,
        "3M": 15,
        "M3": 15,
        "5M": 20,
        "M5": 20,
        "10M": 30,
        "M10": 30,
        "15M": 45,
        "M15": 45,
        "30M": 90,
        "M30": 90,
        # Hours
        "1H": 120,
        "H1": 120,
        "2H": 240,
        "H2": 240,
        "4H": 480,
        "H4": 480,
        "6H": 720,
        "H6": 720,
        "8H": 960,
        "H8": 960,
        # Days
        "1D": 1440,
        "D1": 1440,
        "1W": 10080,
        "W1": 10080,
    }
    
    # Return mapped value or calculate proportional window
    if tf in timeframe_windows:
        return timeframe_windows[tf]
    
    # Fallback: try to parse and calculate proportional window
    # For example: "2m" -> 2 * 5 = 10 minutes
    try:
        if tf.endswith('M') and tf[:-1].isdigit():
            minutes = int(tf[:-1])
            return max(10, minutes * 5)  # At least 10 minutes
        elif tf.endswith('H') and tf[:-1].isdigit():
            hours = int(tf[:-1])
            return hours * 60 * 2  # 2x the timeframe in minutes
        elif tf.endswith('D') and tf[:-1].isdigit():
            days = int(tf[:-1])
            return days * 1440  # Full day(s)
    except (ValueError, IndexError):
        pass
    
    # Default fallback
    logger.warning(f"Unknown timeframe '{timeframe}', using default 60 minutes")
    return 60

class StorageManager:
    _db_lock: lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "aethelgard.db")
        # For in-memory databases, keep a persistent connection
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = self._get_conn()
        self._initialize_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        """Close connection only if it's NOT the persistent connection"""
        if conn is not self._persistent_conn:
            conn.close()

    def _initialize_db(self) -> None:
        """Initialize database tables if they don't exist"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # System state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                confidence REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                connector_type TEXT,
                timeframe TEXT,
                price REAL,
                direction TEXT,
                status TEXT DEFAULT 'active',
                order_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Trade results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_results (
                id TEXT PRIMARY KEY,
                signal_id TEXT,
                symbol TEXT,
                entry_price REAL,
                exit_price REAL,
                profit REAL,
                exit_reason TEXT,
                close_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals (id)
            )
        """)
        
        # Market state logging table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data TEXT
            )
        """)
        
        # Broker accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broker_accounts (
                account_id TEXT PRIMARY KEY,
                broker_id TEXT,
                platform_id TEXT NOT NULL,
                account_name TEXT,
                account_number TEXT,
                server TEXT,
                account_type TEXT DEFAULT 'demo',
                credentials_path TEXT,
                enabled BOOLEAN DEFAULT 1,
                last_connection TEXT,
                balance REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Brokers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS brokers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform_id TEXT NOT NULL,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Platforms table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS platforms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Credentials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY,
                broker_account_id TEXT,
                encrypted_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (broker_account_id) REFERENCES broker_accounts (account_id)
            )
        """)
        
        # Data providers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_providers (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                config TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tuning adjustments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tuning_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                adjustment_data TEXT
            )
        """)
        
        # Coherence events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coherence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT,
                strategy TEXT,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                incoherence_type TEXT,
                reason TEXT NOT NULL,
                details TEXT,
                connector_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add type column to data_providers if it doesn't exist
        cursor.execute("PRAGMA table_info(data_providers)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'type' not in columns:
            cursor.execute("ALTER TABLE data_providers ADD COLUMN type TEXT DEFAULT 'api'")
        
        conn.commit()
        self._close_conn(conn)

    def _execute_serialized(self, func: Callable, *args, retries: int = 5, backoff: float = 0.2, **kwargs) -> Any:
        """
        Ejecuta una función crítica de DB serializadamente, con retry/backoff si la DB está locked.
        """
        last_exc = None
        for attempt in range(retries):
            with self._db_lock:
                conn = self._get_conn()
                try:
                    result = func(conn, *args, **kwargs)
                    return result
                except Exception as e:
                    last_exc = e
                    if 'locked' in str(e).lower():
                        logger.warning(f"DB locked, retrying ({attempt+1}/{retries})...")
                        time.sleep(backoff * (attempt+1))
                        continue
                    logger.error(f"DB error: {e}")
                    raise
                finally:
                    self._close_conn(conn)
        logger.error(f"DB error after retries: {last_exc}")
        if last_exc is not None:
            raise last_exc
        else:
            raise RuntimeError("DB error after retries, pero no se capturó excepción original.")

    def get_broker_provision_status(self) -> list:
        """
        Get current broker provisioning status.
        Returns list of broker dicts with their associated accounts.
        """
        accounts = self.get_broker_accounts()
        brokers = {}

        # Group accounts by broker_id
        for acc in accounts:
            broker_id = acc['broker_id']
            if broker_id not in brokers:
                brokers[broker_id] = {
                    'broker_id': broker_id,
                    'platform_id': acc['platform_id'],
                    'type': acc.get('type', 'unknown'),
                    'auto_provision': False,  # Default, can be extended
                    'demo_accounts': []
                }

            # Add account to broker's demo_accounts
            brokers[broker_id]['demo_accounts'].append({
                'id': acc['account_id'],
                'login': acc['account_number'],
                'account_type': acc['account_type'],
                'enabled': acc['enabled'],
                'has_credentials': bool(acc.get('password') or self.get_credentials(acc['account_id']))
            })

        return list(brokers.values())

    def update_system_state(self, new_state: dict) -> None:
        """Update system state in database"""
        def _update(conn: sqlite3.Connection, new_state: dict) -> None:
            cursor = conn.cursor()
            for key, value in new_state.items():
                # Try with updated_at first, fallback to key-value only
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO system_state (key, value, updated_at)
                        VALUES (?, ?, ?)
                    """, (key, json.dumps(value), datetime.now()))
                except sqlite3.OperationalError:
                    # Fallback: table might not have updated_at column
                    cursor.execute("""
                        INSERT OR REPLACE INTO system_state (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(value)))
            conn.commit()
        
        try:
            # Use _execute_serialized for thread-safe execution
            self._execute_serialized(_update, new_state)
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    def get_system_state(self) -> Dict[str, Any]:
        """Get current system state from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM system_state")
            rows = cursor.fetchall()
            state = {}
            for row in rows:
                try:
                    state[row['key']] = json.loads(row['value'])
                except json.JSONDecodeError:
                    state[row['key']] = row['value']
            return state
        finally:
            self._close_conn(conn)

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
        """
        Save a signal to persistent storage with full traceability.
        Includes connector, account, platform, and market information.
        """
        signal_id = str(uuid.uuid4())
        # Serialize metadata properly (convert non-JSON types)
        metadata = getattr(signal, 'metadata', {})
        serialized_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                serialized_metadata[key] = value
            elif isinstance(value, Enum):
                serialized_metadata[key] = value.value
            else:
                serialized_metadata[key] = str(value)  # Fallback to string
        
        connector_type = getattr(signal, 'connector_type', 'unknown')
        if hasattr(signal, 'connector_type'):
            connector_type_value = getattr(signal, 'connector_type')
            connector_type = connector_type_value if isinstance(connector_type_value, str) else connector_type_value.value
        
        def _save(conn: sqlite3.Connection, signal_id: str) -> None:
            cursor = conn.cursor()
            
            # Use signal timestamp if provided, otherwise use current time
            timestamp = getattr(signal, 'timestamp', None)
            if timestamp:
                if isinstance(timestamp, datetime):
                    # Keep naive datetimes as-is (they're in local time)
                    # Only convert aware datetimes to UTC
                    if timestamp.tzinfo is not None:
                        timestamp_utc = timestamp.astimezone(timezone.utc)
                        timestamp_value = timestamp_utc.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        # Naive datetime - keep as-is
                        timestamp_value = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    timestamp_value = str(timestamp)
            else:
                timestamp_value = None  # Will use DEFAULT CURRENT_TIMESTAMP
            
            # Build columns and values dynamically
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
            
            # Auto-detect if signal was executed: if it has entry_price, stop_loss, and take_profit
            entry_price = getattr(signal, 'entry_price', None)
            stop_loss = getattr(signal, 'stop_loss', None)
            take_profit = getattr(signal, 'take_profit', None)
            is_executed = entry_price and stop_loss and take_profit
            status = 'executed' if is_executed else 'active'
            
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

    def get_signals_by_date(self, target_date: 'date', status: Optional[str] = None) -> List[Dict]:
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

                cursor.execute("""
                    UPDATE signals 
                    SET status = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                """, (status, json.dumps(current_metadata), datetime.now(), signal_id))

                if 'ticket' in metadata_update:
                    cursor.execute("""
                        UPDATE signals 
                        SET order_id = ?
                        WHERE id = ?
                    """, (str(metadata_update['ticket']), signal_id))
            else:
                cursor.execute("""
                    UPDATE signals 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (status, datetime.now(), signal_id))
            conn.commit()
        finally:
            self._close_conn(conn)

    def save_trade_result(self, trade_data: Dict) -> None:
        """Save trade result to database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Accept both 'profit' and 'profit_loss' for compatibility
            profit = trade_data.get('profit') or trade_data.get('profit_loss')
            # Use provided ID (ticket from broker) or generate UUID as fallback
            trade_id = trade_data.get('id') or str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO trade_results (
                    id, signal_id, symbol, entry_price, exit_price, 
                    profit, exit_reason, close_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                trade_data.get('signal_id'),
                trade_data.get('symbol'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                profit,
                trade_data.get('exit_reason'),
                trade_data.get('close_time')
            ))
            conn.commit()
        finally:
            self._close_conn(conn)
    
    def trade_exists(self, ticket_id: str) -> bool:
        """
        Check if a trade with given ticket_id already exists in database.
        
        This is used for idempotent trade processing: prevents duplicate
        processing of the same trade closure event.
        
        Args:
            ticket_id: Unique trade identifier from broker
        
        Returns:
            True if trade exists, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM trade_results WHERE id = ? LIMIT 1",
                (ticket_id,)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            self._close_conn(conn)

    def get_trade_results(self, limit: int = 100) -> List[Dict]:
        """Get trade results from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                ORDER BY close_time DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def save_tuning_adjustment(self, adjustment: Dict) -> None:
        """Save tuning adjustment to database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tuning_adjustments (adjustment_data)
                VALUES (?)
            """, (json.dumps(adjustment),))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_tuning_history(self, limit: int = 50) -> List[Dict]:
        """Get tuning adjustment history"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tuning_adjustments 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            history = []
            for row in rows:
                adjustment = dict(row)
                adjustment['adjustment_data'] = json.loads(adjustment['adjustment_data'])
                history.append(adjustment)
            return history
        finally:
            self._close_conn(conn)

    def log_market_state(self, state_data: Dict) -> None:
        """Log market state data"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_state (symbol, data)
                VALUES (?, ?)
            """, (state_data.get('symbol'), json.dumps(state_data)))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_market_state_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get market state history for a symbol"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM market_state 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (symbol, limit))
            rows = cursor.fetchall()
            history = []
            for row in rows:
                state = dict(row)
                state['data'] = json.loads(state['data'])
                history.append(state)
            return history
        finally:
            self._close_conn(conn)

    def save_broker(self, broker_data: Dict) -> None:
        """Save broker configuration"""
        # Check if table has broker_id column (existing data) or id column (new schema)
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(brokers)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'broker_id' in columns:
                # Existing schema with broker_id column
                cursor.execute("""
                    INSERT OR REPLACE INTO brokers (broker_id, name, type, website, platforms_available, 
                                                   data_server, auto_provision_available, registration_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    broker_data.get('broker_id') or broker_data.get('id'),
                    broker_data['name'],
                    broker_data.get('type'),
                    broker_data.get('website'),
                    json.dumps(broker_data.get('platforms_available', [])),
                    broker_data.get('data_server'),
                    broker_data.get('auto_provision_available', False),
                    broker_data.get('registration_url')
                ))
            else:
                # New schema with id column
                db_data = dict(broker_data)
                if 'broker_id' in db_data:
                    db_data['id'] = db_data['broker_id']

                cursor.execute("""
                    INSERT OR REPLACE INTO brokers (id, name, platform_id, config)
                    VALUES (?, ?, ?, ?)
                """, (
                    db_data.get('id') or db_data.get('broker_id'),
                    db_data['name'],
                    db_data.get('platform_id', 'unknown'),
                    json.dumps(db_data)
                ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def _get_broker_id_column(self, cursor: sqlite3.Cursor) -> str:
        """Detect broker identifier column for schema compatibility."""
        cursor.execute("PRAGMA table_info(brokers)")
        columns = [row[1] for row in cursor.fetchall()]
        return "broker_id" if "broker_id" in columns else "id"

    def _normalize_broker_row(self, broker: Dict) -> Dict:
        """Normalize broker row for old/new schema compatibility."""
        if 'config' in broker and broker['config']:
            config = json.loads(broker['config'])
            broker['broker_id'] = broker.get('broker_id') or broker.get('id')
            broker['auto_provisioning'] = 'full' if config.get('auto_provision_available') else 'none'

            for key, value in config.items():
                if key not in broker:
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        broker[key] = value
                    elif isinstance(value, (list, dict)):
                        broker[key] = json.dumps(value)
        else:
            broker['broker_id'] = broker.get('broker_id', broker.get('id'))
            broker['auto_provisioning'] = 'full' if broker.get('auto_provision_available') else 'none'

        return broker

    def get_brokers(self) -> List[Dict]:
        """Get all brokers"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM brokers")
            rows = cursor.fetchall()
            return [self._normalize_broker_row(dict(row)) for row in rows]
        finally:
            self._close_conn(conn)

    def get_broker(self, broker_id: str) -> Optional[Dict]:
        """Get specific broker by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            lookup_column = self._get_broker_id_column(cursor)
            cursor.execute(f"SELECT * FROM brokers WHERE {lookup_column} = ?", (broker_id,))

            row = cursor.fetchone()
            if row:
                return self._normalize_broker_row(dict(row))
            return None
        finally:
            self._close_conn(conn)

    def save_platform(self, platform_data: Dict) -> None:
        """Save platform configuration"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO platforms (id, name, type, config)
                VALUES (?, ?, ?, ?)
            """, (
                platform_data['id'],
                platform_data['name'],
                platform_data['type'],
                json.dumps(platform_data.get('config', {}))
            ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_platforms(self) -> List[Dict]:
        """Get all platforms"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM platforms")
            rows = cursor.fetchall()
            platforms = []
            for row in rows:
                platform = dict(row)
                if 'config' in platform and platform['config']:
                    config = json.loads(platform['config']) if platform['config'] else {}
                    platform.update(config)
                platforms.append(platform)
            return platforms
        finally:
            self._close_conn(conn)

    def save_broker_account(self, *args, **kwargs) -> str:
        """Save broker account - accepts dict, named params, or positional args"""
        if args:
            # Positional arguments: broker_id, platform_id, account_name, enabled=True
            if len(args) >= 3:
                account_data = {
                    'broker_id': args[0],
                    'platform_id': args[1], 
                    'account_name': args[2],
                    'enabled': args[3] if len(args) > 3 else True
                }
                account_data.update(kwargs)
            else:
                raise ValueError("Not enough positional arguments")
        elif kwargs and 'account_data' not in kwargs:
            # Named parameters
            account_data = kwargs
        else:
            # Dict passed as account_data
            account_data = kwargs.get('account_data', {})
        
        # Generate account_id if not provided
        if 'id' not in account_data and 'account_id' not in account_data:
            account_data['id'] = str(uuid.uuid4())
        elif 'account_id' in account_data:
            account_data['id'] = account_data['account_id']
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO broker_accounts 
                (account_id, broker_id, platform_id, account_name, account_number, server, account_type, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                account_data['id'],
                account_data.get('broker_id'),
                account_data.get('platform_id'),
                account_data.get('account_name'),
                account_data.get('account_number', account_data.get('login')),  # Use account_number, default to login
                account_data.get('server'),
                account_data.get('account_type', account_data.get('type', 'demo')),
                account_data.get('enabled', True),
                datetime.now(),
                datetime.now()
            ))
            conn.commit()
        finally:
            self._close_conn(conn)
        
        # Save credentials if password provided
        if account_data.get('password'):
            self.update_credential(account_data['id'], {'password': account_data['password']})
        
        return account_data['id']

    def get_broker_accounts(self, enabled_only: bool = False, broker_id: Optional[str] = None, account_type: Optional[str] = None) -> List[Dict]:
        """Get all broker accounts, optionally filtered by enabled status, broker_id, and account_type"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM broker_accounts WHERE 1=1"
            params = []
            
            if enabled_only:
                query += " AND enabled = 1"
            
            if broker_id:
                query += " AND broker_id = ?"
                params.append(broker_id)
            
            if account_type:
                query += " AND account_type = ?"
                params.append(account_type)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            accounts = []
            for row in rows:
                account = dict(row)
                accounts.append(account)
            return accounts
        finally:
            self._close_conn(conn)

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get specific broker account by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM broker_accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            self._close_conn(conn)

    def log_coherence_event(self, signal_id: Optional[str], symbol: str, timeframe: Optional[str],
                           strategy: Optional[str], stage: str, status: str, incoherence_type: Optional[str],
                           reason: str, details: Optional[str], connector_type: Optional[str]) -> None:
        """Log coherence monitoring event"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO coherence_events 
                (signal_id, symbol, timeframe, strategy, stage, status, incoherence_type, reason, details, connector_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (signal_id, symbol, timeframe, strategy, stage, status, incoherence_type, reason, details, connector_type))
            conn.commit()
        finally:
            self._close_conn(conn)

    def has_recent_signal(self, symbol: str, signal_type: str, timeframe: Optional[str] = None, minutes: Optional[int] = None) -> bool:
        """Check if there's a recent signal for the given symbol and type within the deduplication window"""
        if minutes is None:
            minutes = calculate_deduplication_window(timeframe)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Use 'localtime' to match the local time stored in timestamps
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE symbol = ? 
                AND signal_type = ? 
                AND timestamp >= datetime('now', 'localtime', '-' || ? || ' minutes')
                AND (timeframe = ? OR ? IS NULL)
            """, (symbol, signal_type, minutes, timeframe, timeframe))
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            self._close_conn(conn)

    def has_open_position(self, symbol: str) -> bool:
        """Check if there's an open position for the given symbol"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE symbol = ? 
                AND status = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            """, (symbol,))
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            self._close_conn(conn)

    def get_recent_signals(self, minutes: int = 60, limit: int = 100) -> List[Dict]:
        """Get recent signals within the last N minutes"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM signals 
                WHERE timestamp >= datetime('now', 'localtime', '-' || ? || ' minutes')
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (minutes, limit))
            rows = cursor.fetchall()
            signals = []
            for row in rows:
                signal = dict(row)
                if signal.get('metadata'):
                    signal['metadata'] = json.loads(signal['metadata'])
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

    def update_account_enabled(self, account_id: str, enabled: bool) -> None:
        """Update account enabled status with verification"""
        self.update_account_credentials(account_id=account_id, enabled=enabled)

    def update_account_credentials(self, account_id: str, account_number: str = None, 
                                   password: str = None, server: str = None, 
                                   account_name: str = None, account_type: str = None,
                                   enabled: bool = None) -> None:
        """
        Update account credentials with explicit mapping and post-write verification.
        
        Args:
            account_id: Account ID to update
            account_number: New account number/login
            password: New password (will be encrypted)
            server: New server
            account_name: New account name
            account_type: New account type
            enabled: New enabled status
            
        Raises:
            ValueError: If post-write verification fails
            sqlite3.Error: If database operation fails
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Begin explicit transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # Build update query with explicit column mapping
            update_fields = []
            update_values = []
            
            if account_name is not None:
                update_fields.append("account_name = ?")
                update_values.append(account_name)
                
            if account_number is not None:
                update_fields.append("account_number = ?")
                update_values.append(account_number)
                
            if server is not None:
                update_fields.append("server = ?")
                update_values.append(server)
                
            if account_type is not None:
                update_fields.append("account_type = ?")
                update_values.append(account_type)
                
            if enabled is not None:
                update_fields.append("enabled = ?")
                update_values.append(enabled)
            
            # Always update timestamp
            update_fields.append("updated_at = ?")
            update_values.append(datetime.now())
            update_values.append(account_id)  # WHERE clause
            
            if update_fields:
                set_clause = ", ".join(update_fields)
                cursor.execute(f"""
                    UPDATE broker_accounts
                    SET {set_clause}
                    WHERE account_id = ?
                """, update_values)
            
            # Handle password update with explicit cleanup
            if password is not None:
                # First, delete existing credentials for this account
                cursor.execute("""
                    DELETE FROM credentials 
                    WHERE broker_account_id = ?
                """, (account_id,))
                
                # Then insert new encrypted credentials
                encrypted_data = get_encryptor().encrypt(json.dumps({'password': password}))
                cursor.execute("""
                    INSERT INTO credentials (broker_account_id, encrypted_data)
                    VALUES (?, ?)
                """, (account_id, encrypted_data))
            
            # Commit the transaction
            conn.commit()
            
            # === POST-WRITE VERIFICATION ===
            # Verify account data was saved correctly
            cursor.execute("""
                SELECT account_name, account_number, server, account_type, enabled
                FROM broker_accounts
                WHERE account_id = ?
            """, (account_id,))
            
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Account {account_id} not found after update")
                
            saved_name, saved_number, saved_server, saved_type, saved_enabled = row
            
            # Verify each field that was supposed to be updated
            if account_name is not None and saved_name != account_name:
                raise ValueError(f"Account name verification failed: expected '{account_name}', got '{saved_name}'")
            if account_number is not None and saved_number != account_number:
                raise ValueError(f"Account number verification failed: expected '{account_number}', got '{saved_number}'")
            if server is not None and saved_server != server:
                raise ValueError(f"Server verification failed: expected '{server}', got '{saved_server}'")
            if account_type is not None and saved_type != account_type:
                raise ValueError(f"Account type verification failed: expected '{account_type}', got '{saved_type}'")
            if enabled is not None and saved_enabled != enabled:
                raise ValueError(f"Enabled status verification failed: expected {enabled}, got {saved_enabled}")
            
            # Verify password was saved (if provided)
            if password is not None:
                cursor.execute("""
                    SELECT encrypted_data FROM credentials
                    WHERE broker_account_id = ?
                """, (account_id,))
                
                cred_row = cursor.fetchone()
                if not cred_row:
                    raise ValueError(f"Password credentials not found after update for account {account_id}")
                    
                # We can't decrypt to verify exact password, but we can verify structure
                try:
                    decrypted = get_encryptor().decrypt(cred_row[0])
                    cred_data = json.loads(decrypted)
                    if 'password' not in cred_data:
                        raise ValueError(f"Password not found in decrypted credentials for account {account_id}")
                except Exception as e:
                    raise ValueError(f"Password verification failed: {e}")
            
        except Exception as e:
            # Rollback on any error
            conn.rollback()
            raise e
        finally:
            self._close_conn(conn)

    def update_credential(self, account_id: str, credential_data: Dict) -> None:
        """Update encrypted credentials for account"""
        encrypted_data = get_encryptor().encrypt(json.dumps(credential_data))
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO credentials (broker_account_id, encrypted_data)
                VALUES (?, ?)
            """, (account_id, encrypted_data))
            conn.commit()
        finally:
            self._close_conn(conn)

    def save_credential(self, account_id: str, credential_type: str, credential_key: str, value: str) -> None:
        """Save a specific credential for an account"""
        # Get existing credentials
        existing = self.get_credentials(account_id) or {}
        
        # Update with new credential
        existing[credential_key] = value
        
        # Save back
        self.update_credential(account_id, existing)

    def get_credentials(self, account_id: str, credential_type: Optional[str] = None) -> Optional[Union[Dict, str]]:
        """Get decrypted credentials for account. If credential_type specified, return just that credential."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT encrypted_data FROM credentials 
                WHERE broker_account_id = ?
            """, (account_id,))
            row = cursor.fetchone()
            if row:
                decrypted = get_encryptor().decrypt(row['encrypted_data'])
                credentials = json.loads(decrypted)

                if credential_type:
                    return credentials.get(credential_type)
                return credentials
            return None
        finally:
            self._close_conn(conn)

    def delete_credential(self, account_id: str) -> None:
        """Delete credentials for account"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            conn.commit()
        finally:
            self._close_conn(conn)

    def delete_account(self, account_id: str) -> None:
        """Delete broker account and associated credentials"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            cursor.execute("DELETE FROM broker_accounts WHERE account_id = ?", (account_id,))
            conn.commit()
        finally:
            self._close_conn(conn)

    def save_data_provider(self, name: str, enabled: bool = True, priority: int = 50, 
                          requires_auth: bool = False, api_key: Optional[str] = None, 
                          api_secret: Optional[str] = None, additional_config: Optional[Dict] = None,
                          is_system: bool = False, provider_type: str = "generic") -> None:
        """Save data provider configuration"""
        if additional_config is None:
            additional_config = {}
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO data_providers 
                (name, type, enabled, priority, requires_auth, api_key, api_secret, additional_config, is_system)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                provider_type,
                enabled,
                priority,
                requires_auth,
                api_key,
                api_secret,
                json.dumps(additional_config) if additional_config else "{}",
                is_system
            ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_data_providers(self) -> List[Dict]:
        """Get all data providers"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM data_providers")
            rows = cursor.fetchall()

            # Get column names
            column_names = [description[0] for description in cursor.description]

            providers = []
            for row in rows:
                provider = dict(zip(column_names, row))
                
                # Handle backward compatibility: if there's a 'config' column with JSON, extract fields
                if 'config' in provider and provider['config']:
                    try:
                        config_data = json.loads(provider['config'])
                        # Merge config fields into provider dict at top level
                        provider.update(config_data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Also handle additional_config - it's stored as JSON string
                if 'additional_config' in provider and provider['additional_config']:
                    try:
                        if isinstance(provider['additional_config'], str):
                            provider['additional_config'] = json.loads(provider['additional_config'])
                    except (json.JSONDecodeError, TypeError):
                        provider['additional_config'] = {}
                else:
                    provider['additional_config'] = {}
                
                # Wrap in 'config' dict for backward compatibility
                provider['config'] = {
                    'priority': provider.get('priority', 50),
                    'requires_auth': provider.get('requires_auth', False),
                    'api_key': provider.get('api_key'),
                    'api_secret': provider.get('api_secret'),
                    'additional_config': provider.get('additional_config', {}),
                    'is_system': provider.get('is_system', False)
                }
                
                # For backward compatibility, set id = name if no id column
                if 'id' not in provider or not provider['id']:
                    provider['id'] = provider.get('name')
                providers.append(provider)
            return providers
        finally:
            self._close_conn(conn)

    def update_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """Update data provider enabled status"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE data_providers 
                SET enabled = ?
                WHERE name = ?
            """, (enabled, provider_id))
            conn.commit()
        finally:
            self._close_conn(conn)

    @contextmanager
    def close(self) -> None:
        """Close persistent connection if it exists"""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None

    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get recent trades"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                WHERE profit IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                profit = row[5]
                if profit is not None:
                    trade = {
                        'id': row[0],
                        'signal_id': row[1],
                        'symbol': row[2],
                        'entry_price': row[3],
                        'exit_price': row[4],
                        'profit_loss': profit,  # Alias for compatibility with tuner
                        'profit': profit,       # Keep original field
                        'exit_reason': row[6],
                        'close_time': row[7],
                        'created_at': row[8],
                        'is_win': profit > 0,
                        'pips': abs(profit) * 100  # Rough pips calculation
                    }
                    trades.append(trade)
            return trades
        finally:
            self._close_conn(conn)

    def get_signals_today(self) -> List[Dict]:
        """Get signals from today (for dashboard compatibility)"""
        from datetime import date
        return self.get_signals_by_date(date.today())

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics for dashboard"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Total signals
            cursor.execute("SELECT COUNT(*) FROM signals")
            total_signals = cursor.fetchone()[0]
            
            # Executed signals
            cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'executed'")
            executed_signals_count = cursor.fetchone()[0]
            
            # Win rate calculation from trade results
            cursor.execute("SELECT COUNT(*) FROM trade_results WHERE profit > 0")
            wins = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM trade_results WHERE profit < 0")
            losses = cursor.fetchone()[0]
            
            total_trades = wins + losses
            win_rate = (wins / total_trades) if total_trades > 0 else 0
            
            # Average PNL from trade results
            cursor.execute("SELECT AVG(profit) FROM trade_results")
            avg_pnl_result = cursor.fetchone()[0]
            avg_pnl = float(avg_pnl_result) if avg_pnl_result else 0.0
            
            # Executed signals statistics (nested dict as expected by dashboard)
            executed_stats = {
                'total': executed_signals_count,
                'avg_pnl': avg_pnl,
                'winning_trades': wins,
                'win_rate': win_rate
            }
            
            return {
                'total_signals': total_signals,
                'executed_signals': executed_stats,  # Now a dict, not just a count
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate
            }
        finally:
            self._close_conn(conn)

    def get_total_profit(self, days: int = 30) -> float:
        """Get total profit for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(profit), 0) 
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
            """.format(days))
            result = cursor.fetchone()[0]
            return float(result) if result else 0.0
        finally:
            self._close_conn(conn)

    def get_all_accounts(self) -> List[Dict]:
        """Get all broker accounts (alias for get_broker_accounts)"""
        return self.get_broker_accounts()

    def get_win_rate(self, days: int = 30) -> float:
        """Get win rate for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Count wins and losses from trade results in the last N days
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN profit > 0 THEN 1 END) as wins,
                    COUNT(CASE WHEN profit < 0 THEN 1 END) as losses
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
            """.format(days))
            
            row = cursor.fetchone()
            wins = row[0] if row[0] else 0
            losses = row[1] if row[1] else 0
            
            total_trades = wins + losses
            win_rate = (wins / total_trades) if total_trades > 0 else 0.0
            
            return win_rate
        finally:
            self._close_conn(conn)

    def get_profit_by_symbol(self, days: int = 30) -> Dict[str, float]:
        """Get total profit grouped by symbol for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, SUM(profit) as total_profit
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
                GROUP BY symbol
                ORDER BY total_profit DESC
            """.format(days))
            
            rows = cursor.fetchall()
            profit_by_symbol = {row[0]: float(row[1]) for row in rows}
            return profit_by_symbol
        finally:
            self._close_conn(conn)

    def get_all_trades(self, limit: int = 1000) -> List[Dict]:
        """Get all trade results with optional limit"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                trade = dict(row)
                trades.append(trade)
            return trades
        finally:
            self._close_conn(conn)

    def check_integrity(self) -> bool:
        """
        Verifica la integridad de la base de datos y repara esquemas si es necesario.
        Retorna True si la DB está íntegra, False si hay problemas.
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            # Verificar tablas críticas
            required_tables = ['signals', 'trade_results', 'system_state', 'broker_accounts']
            for table in required_tables:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if not cursor.fetchone():
                    logger.error(f"Tabla faltante: {table}")
                    return False

            # Verificar columnas críticas en signals
            required_columns = ['symbol', 'timeframe', 'direction', 'price', 'sl', 'tp', 'score', 'timestamp']
            cursor.execute("PRAGMA table_info(signals)")
            columns = [row[1] for row in cursor.fetchall()]
            for col in required_columns:
                if col not in columns:
                    logger.warning(f"Columna faltante en signals: {col}. Intentando agregar...")
                    # Intentar agregar columna
                    try:
                        if col == 'direction':
                            cursor.execute("ALTER TABLE signals ADD COLUMN direction TEXT")
                        elif col == 'sl':
                            cursor.execute("ALTER TABLE signals ADD COLUMN sl REAL")
                        elif col == 'tp':
                            cursor.execute("ALTER TABLE signals ADD COLUMN tp REAL")
                        elif col == 'score':
                            cursor.execute("ALTER TABLE signals ADD COLUMN score REAL")
                        logger.info(f"Columna {col} agregada exitosamente.")
                    except sqlite3.OperationalError as e:
                        logger.error(f"No se pudo agregar columna {col}: {e}")
                        return False

            conn.commit()
            logger.info("Integridad de base de datos verificada y reparada si fue necesario.")
            return True

        except Exception as e:
            logger.error(f"Error verificando integridad de DB: {e}")
            return False
        finally:
            self._close_conn(conn)


# Test utilities
def temp_db_path(tmp_path: str) -> str:
    """Create temporary database path for testing"""
    return os.path.join(tmp_path, "test.db")

def storage(tmp_path: str) -> StorageManager:
    """Create storage manager for testing"""
    return StorageManager(temp_db_path(tmp_path))

def test_system_state_persistence(storage: StorageManager) -> None:
    """Test system state persistence"""
    test_state = {"test_key": "test_value", "number": 42}
    storage.update_system_state(test_state)
    retrieved = storage.get_system_state()
    assert retrieved["test_key"] == "test_value"
    assert retrieved["number"] == 42

def test_signal_persistence(storage: StorageManager) -> None:
    """Test signal persistence"""
    test_signal = {
        "symbol": "EURUSD",
        "signal_type": "BUY",
        "confidence": 0.8,
        "metadata": {"test": True}
    }
    signal_id = storage.save_signal(test_signal)
    signals = storage.get_signals()
    assert len(signals) == 1
    assert signals[0]["symbol"] == "EURUSD"

def test_trade_result_persistence(storage: StorageManager) -> None:
    """Test trade result persistence"""
    test_trade = {
        "signal_id": "test_signal",
        "symbol": "EURUSD",
        "entry_price": 1.1000,
        "exit_price": 1.1050,
        "profit": 50.0,
        "exit_reason": "TAKE_PROFIT"
    }
    storage.save_trade_result(test_trade)
    results = storage.get_trade_results()
    assert len(results) == 1
    assert results[0]["profit"] == 50.0

def test_market_state_logging(storage: StorageManager) -> None:
    """Test market state logging"""
    test_state = {"symbol": "EURUSD", "price": 1.1000}
    storage.log_market_state(test_state)
    history = storage.get_market_state_history("EURUSD")
    assert len(history) == 1
    assert history[0]["data"]["price"] == 1.1000