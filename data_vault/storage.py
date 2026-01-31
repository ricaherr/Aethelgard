from _thread import lock
import threading
import time
import json
import os
import sqlite3
import logging
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from contextlib import contextmanager
from utils.encryption import CredentialEncryption, get_encryptor

logger: logging.Logger = logging.getLogger(__name__)


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
        self._initialize_db()

    def _get_conn(self) -> sqlite3.Generator[sqlite3.Connection, threading.Any, None]:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        """Initialize database tables if they don't exist"""
        with self._get_conn() as conn:
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
                    id TEXT PRIMARY KEY,
                    platform_id TEXT NOT NULL,
                    login TEXT NOT NULL,
                    password TEXT,
                    server TEXT,
                    type TEXT DEFAULT 'demo',
                    enabled BOOLEAN DEFAULT 1,
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
                    FOREIGN KEY (broker_account_id) REFERENCES broker_accounts (id)
                )
            """)
            
            # Data providers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
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
            
            conn.commit()

    def _execute_serialized(self, func: Callable, *args, retries: int = 5, backoff: float = 0.2, **kwargs) -> Any:
        """
        Ejecuta una función crítica de DB serializadamente, con retry/backoff si la DB está locked.
        """
        last_exc = None
        for attempt in range(retries):
            with self._db_lock:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if 'locked' in str(e).lower():
                        logger.warning(f"DB locked, retrying ({attempt+1}/{retries})...")
                        time.sleep(backoff * (attempt+1))
                        continue
                    logger.error(f"DB error: {e}")
                    raise
        logger.error(f"DB error after retries: {last_exc}")
        if last_exc is not None:
            raise last_exc
        else:
            raise RuntimeError("DB error after retries, pero no se capturó excepción original.")

    def get_broker_provision_status(self) -> list:
        """
        Get current broker provisioning status.
        Returns list of broker account dicts with provisioning info.
        """
        accounts = self.get_broker_accounts()
        status = []
        for acc in accounts:
            status.append({
                'id': acc['id'],
                'platform_id': acc['platform_id'],
                'login': acc['login'],
                'type': acc['type'],
                'enabled': acc['enabled'],
                'has_credentials': bool(acc.get('password') or self.get_credentials(acc['id'])),
                'provisioned': True  # All accounts in DB are considered provisioned
            })
        return status

    def update_system_state(self, new_state: dict) -> None:
        """Update system state in database"""
        def _update(conn: sqlite3.Connection, new_state: dict) -> None:
            cursor = conn.cursor()
            for key, value in new_state.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO system_state (key, value, updated_at)
                    VALUES (?, ?, ?)
                """, (key, json.dumps(value), datetime.now()))
            conn.commit()
        
        try:
            with self._get_conn() as conn:
                _update(conn, new_state)
            self._execute_serialized(_update, new_state)
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    def get_system_state(self) -> Dict[str, Any]:
        """Get current system state from database"""
        with self._get_conn() as conn:
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
            connector_type = signal.connector_type if isinstance(signal.connector_type, str) else signal.connector_type.value
        
        def _save(conn: sqlite3.Connection, signal_id: str) -> None:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals (
                    id, symbol, signal_type, confidence, 
                    metadata, connector_type, timeframe, price, direction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id,
                signal.symbol,
                signal.signal_type if isinstance(signal.signal_type, str) else signal.signal_type.value,
                getattr(signal, 'confidence', None),
                json.dumps(serialized_metadata),
                connector_type,
                getattr(signal, 'timeframe', None),
                getattr(signal, 'price', None),
                getattr(signal, 'direction', None)
            ))
            conn.commit()
        
        self._execute_serialized(_save, signal_id)
        return signal_id

    def get_signals(self, limit: int = 100, status: Optional[str] = None) -> List[Dict]:
        """Get signals from database"""
        with self._get_conn() as conn:
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

    def update_signal_status(self, signal_id: str, status: str, metadata_update: Optional[Dict] = None) -> None:
        """Update signal status and optionally metadata"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if metadata_update:
                # Get current metadata
                cursor.execute("SELECT metadata FROM signals WHERE id = ?", (signal_id,))
                row = cursor.fetchone()
                if row:
                    current_metadata = json.loads(row['metadata']) if row['metadata'] else {}
                    current_metadata.update(metadata_update)
                    cursor.execute("""
                        UPDATE signals 
                        SET status = ?, metadata = ?, updated_at = ?
                        WHERE id = ?
                    """, (status, json.dumps(current_metadata), datetime.now(), signal_id))
                else:
                    logger.warning(f"Signal {signal_id} not found for status update")
            else:
                cursor.execute("""
                    UPDATE signals 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (status, datetime.now(), signal_id))
            conn.commit()

    def save_trade_result(self, trade_data: Dict) -> None:
        """Save trade result to database"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_results (
                    id, signal_id, symbol, entry_price, exit_price, 
                    profit, exit_reason, close_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                trade_data.get('signal_id'),
                trade_data.get('symbol'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                trade_data.get('profit'),
                trade_data.get('exit_reason'),
                trade_data.get('close_time')
            ))
            conn.commit()

    def get_trade_results(self, limit: int = 100) -> List[Dict]:
        """Get trade results from database"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                ORDER BY close_time DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def save_tuning_adjustment(self, adjustment: Dict) -> None:
        """Save tuning adjustment to database"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tuning_adjustments (adjustment_data)
                VALUES (?)
            """, (json.dumps(adjustment),))
            conn.commit()

    def get_tuning_history(self, limit: int = 50) -> List[Dict]:
        """Get tuning adjustment history"""
        with self._get_conn() as conn:
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

    def log_market_state(self, state_data: Dict) -> None:
        """Log market state data"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_state (symbol, data)
                VALUES (?, ?)
            """, (state_data.get('symbol'), json.dumps(state_data)))
            conn.commit()

    def get_market_state_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get market state history for a symbol"""
        with self._get_conn() as conn:
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

    def save_broker(self, broker_data: Dict) -> None:
        """Save broker configuration"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO brokers (id, name, platform_id, config)
                VALUES (?, ?, ?, ?)
            """, (
                broker_data['id'],
                broker_data['name'],
                broker_data['platform_id'],
                json.dumps(broker_data.get('config', {}))
            ))
            conn.commit()

    def get_brokers(self) -> List[Dict]:
        """Get all brokers"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM brokers")
            rows = cursor.fetchall()
            brokers = []
            for row in rows:
                broker = dict(row)
                broker['config'] = json.loads(broker['config']) if broker['config'] else {}
                brokers.append(broker)
            return brokers

    def save_platform(self, platform_data: Dict) -> None:
        """Save platform configuration"""
        with self._get_conn() as conn:
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

    def get_platforms(self) -> List[Dict]:
        """Get all platforms"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM platforms")
            rows = cursor.fetchall()
            platforms = []
            for row in rows:
                platform = dict(row)
                platform['config'] = json.loads(platform['config']) if platform['config'] else {}
                platforms.append(platform)
            return platforms

    def save_broker_account(self, account_data: Dict) -> None:
        """Save broker account"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO broker_accounts 
                (id, platform_id, login, password, server, type, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                account_data['id'],
                account_data['platform_id'],
                account_data['login'],
                account_data.get('password'),
                account_data.get('server'),
                account_data.get('type', 'demo'),
                account_data.get('enabled', True)
            ))
            conn.commit()

    def get_broker_accounts(self) -> List[Dict]:
        """Get all broker accounts"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM broker_accounts")
            rows = cursor.fetchall()
            accounts = []
            for row in rows:
                account = dict(row)
                accounts.append(account)
            return accounts

    def update_account_status(self, account_id: str, enabled: bool) -> None:
        """Update account enabled status"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broker_accounts 
                SET enabled = ?, updated_at = ?
                WHERE id = ?
            """, (enabled, datetime.now(), account_id))
            conn.commit()

    def update_account_connection(self, account_id: str, connected: bool) -> None:
        """Update account connection status (placeholder for future use)"""
        # This could be extended to track connection status
        logger.info(f"Account {account_id} connection status: {connected}")

    def save_broker_config(self, config_data: Dict) -> None:
        """Save broker configuration (placeholder)"""
        logger.info(f"Saving broker config: {config_data}")

    def update_account_type(self, account_id: str, account_type: str) -> None:
        """Update account type (demo/live)"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broker_accounts 
                SET type = ?, updated_at = ?
                WHERE id = ?
            """, (account_type, datetime.now(), account_id))
            conn.commit()

    def update_account_enabled(self, account_id: str, enabled: bool) -> None:
        """Update account enabled status"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE broker_accounts 
                SET enabled = ?, updated_at = ?
                WHERE id = ?
            """, (enabled, datetime.now(), account_id))
            conn.commit()

    def update_account(self, account_id: str, updates: Dict) -> None:
        """Update account with multiple fields"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [datetime.now(), account_id]
            cursor.execute(f"""
                UPDATE broker_accounts 
                SET {set_clause}, updated_at = ?
                WHERE id = ?
            """, values)
            conn.commit()

    def update_credential(self, account_id: str, credential_data: Dict) -> None:
        """Update encrypted credentials for account"""
        encrypted_data = get_encryptor().encrypt(json.dumps(credential_data))
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO credentials (broker_account_id, encrypted_data)
                VALUES (?, ?)
            """, (account_id, encrypted_data))
            conn.commit()

    def get_credentials(self, account_id: str) -> Optional[Dict]:
        """Get decrypted credentials for account"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT encrypted_data FROM credentials 
                WHERE broker_account_id = ?
            """, (account_id,))
            row = cursor.fetchone()
            if row:
                decrypted = get_encryptor().decrypt(row['encrypted_data'])
                return json.loads(decrypted)
            return None

    def delete_credential(self, account_id: str) -> None:
        """Delete credentials for account"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            conn.commit()

    def delete_account(self, account_id: str) -> None:
        """Delete broker account and associated credentials"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Delete credentials first (foreign key)
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            # Delete account
            cursor.execute("DELETE FROM broker_accounts WHERE id = ?", (account_id,))
            conn.commit()

    def save_data_provider(self, provider_data: Dict) -> None:
        """Save data provider configuration"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO data_providers 
                (id, name, type, config, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (
                provider_data['id'],
                provider_data['name'],
                provider_data['type'],
                json.dumps(provider_data.get('config', {})),
                provider_data.get('enabled', True)
            ))
            conn.commit()

    def get_data_providers(self) -> List[Dict]:
        """Get all data providers"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM data_providers")
            rows = cursor.fetchall()
            providers = []
            for row in rows:
                provider = dict(row)
                provider['config'] = json.loads(provider['config']) if provider['config'] else {}
                providers.append(provider)
            return providers

    def update_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """Update data provider enabled status"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE data_providers 
                SET enabled = ?
                WHERE id = ?
            """, (enabled, provider_id))
            conn.commit()

    @contextmanager
    def op(self) -> None:
        """Context manager for database operations"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager  
    def op(self) -> None:
        """Alternative context manager for database operations"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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