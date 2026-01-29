import json
import os
import sqlite3
import logging
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional
from utils.encryption import get_encryptor

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Manages persistence of system state using SQLite for production reliability.
    Enhanced with signal tracking and open operation management for session recovery.
    """
    def __init__(self, db_path='data_vault/aethelgard.db'):
        self.db_path = db_path
        self._conn = None  # Persistent connection for :memory: databases
        self._initialize_db()
    
    def _get_conn(self):
        """Creates or returns a database connection"""
        # For in-memory databases, reuse the same connection
        if self.db_path == ':memory:':
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path)
            return self._conn
        # For file databases, create new connection each time
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        """Initialize SQLite database with proper schema"""
        # Only create directories for file-based databases, not :memory:
        if self.db_path != ':memory:':
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        logger.info(f"Checking database schema at {self.db_path}...")
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Tabla de Señales
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    signal_type TEXT,
                    confidence REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    timestamp TEXT,
                    date TEXT,
                    status TEXT,
                    metadata TEXT
                )
            ''')
            
            # Tabla de Trades (Resultados)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT,
                    symbol TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    pips REAL,
                    profit_loss REAL,
                    duration_minutes INTEGER,
                    is_win BOOLEAN,
                    exit_reason TEXT,
                    market_regime TEXT,
                    volatility_atr REAL,
                    parameters_used TEXT,
                    timestamp TEXT,
                    date TEXT
                )
            ''')
            
            # Tabla Key-Value para estado del sistema (SessionStats, Lockdown, etc)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Historial de Tuning
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tuning_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    data TEXT
                )
            ''')
            
            # Estados de Mercado (para análisis histórico)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timestamp TEXT,
                    regime TEXT,
                    data TEXT
                )
            ''')
            
            # Tabla de Brokers (Proveedores de liquidez)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS brokers (
                    broker_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT,
                    website TEXT,
                    platforms_available TEXT,
                    data_server TEXT,
                    auto_provision_available BOOLEAN DEFAULT 0,
                    registration_url TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # Tabla de Plataformas (Software de ejecución)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS platforms (
                    platform_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    vendor TEXT,
                    type TEXT,
                    capabilities TEXT,
                    connector_class TEXT,
                    created_at TEXT
                )
            ''')
            
            # Tabla de Cuentas (Cuentas configuradas por usuario)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS broker_accounts (
                    account_id TEXT PRIMARY KEY,
                    broker_id TEXT,
                    platform_id TEXT,
                    account_name TEXT,
                    account_number TEXT,
                    server TEXT,
                    account_type TEXT,
                    credentials_path TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    last_connection TEXT,
                    balance REAL,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (broker_id) REFERENCES brokers(broker_id),
                    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id)
                )
            ''')
            
            # Tabla de Credenciales Encriptadas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS broker_credentials (
                    credential_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    credential_type TEXT NOT NULL,
                    credential_key TEXT NOT NULL,
                    encrypted_value BLOB NOT NULL,
                    created_at TEXT,
                    expires_at TEXT,
                    FOREIGN KEY (account_id) REFERENCES broker_accounts(account_id) ON DELETE CASCADE
                )
            ''')
            
            # Tabla de Configuración de Proveedores de Datos (MIGRE FROM JSON TO DB)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS data_providers (
                    name TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    priority INTEGER DEFAULT 50,
                    requires_auth BOOLEAN DEFAULT 0,
                    api_key TEXT,
                    api_secret TEXT,
                    additional_config TEXT,
                    is_system BOOLEAN DEFAULT 0,
                    updated_at TEXT
                )
            ''')
            
            conn.commit()
            logger.info("Database schema verified/initialized successfully.")

    def get_system_state(self) -> dict:
        """Retrieves the current system state from the database."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM system_state")
                rows = cursor.fetchall()
                
                state = {}
                for key, value in rows:
                    try:
                        state[key] = json.loads(value)
                    except json.JSONDecodeError:
                        state[key] = value
                return state
        except Exception as e:
            logger.error(f"Error reading system state: {e}")
            return {}

    def update_system_state(self, new_state: dict):
        """Updates and saves the system state."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                for key, value in new_state.items():
                    json_value = json.dumps(value)
                    cursor.execute(
                        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                        (key, json_value)
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    def save_signal(self, signal) -> str:
        """
        Save a signal to persistent storage.
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
                serialized_metadata[key] = str(value)
        
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO signals (id, symbol, signal_type, confidence, entry_price, stop_loss, take_profit, timestamp, date, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    signal_id,
                    signal.symbol,
                    signal.signal_type if isinstance(signal.signal_type, str) else signal.signal_type.value,
                    getattr(signal, 'confidence', 0.0),
                    signal.entry_price,
                    signal.stop_loss,
                    signal.take_profit,
                    datetime.now().isoformat(),
                    date.today().isoformat(),
                    "executed",
                    json.dumps(serialized_metadata)
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving signal: {e}")
            raise
        
        return signal_id
    
    def count_executed_signals(self, target_date: Optional[date] = None) -> int:
        """
        Count signals executed on a specific date.
        """
        if target_date is None:
            target_date = date.today()
        
        target_date_str = target_date.isoformat()
        
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM signals WHERE date = ? AND status = 'executed'",
                    (target_date_str,)
                )
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting signals: {e}")
            return 0
    
    def get_signals_by_date(self, target_date: Optional[date] = None) -> List[Dict]:
        """
        Retrieve all signals for a specific date.
        """
        if target_date is None:
            target_date = date.today()
        
        target_date_str = target_date.isoformat()
        
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM signals WHERE date = ?",
                    (target_date_str,)
                )
                rows = cursor.fetchall()
                
                signals = []
                for row in rows:
                    sig = dict(row)
                    sig['metadata'] = json.loads(sig['metadata']) if sig['metadata'] else {}
                    signals.append(sig)
                return signals
        except Exception as e:
            logger.error(f"Error getting signals: {e}")
            return []
    
    def get_signals_today(self) -> List[Dict]:
        """
        Retrieve all signals for today.
        Alias for get_signals_by_date() with no arguments.
        
        Returns:
            List of today's signal records
        """
        return self.get_signals_by_date()
    
    def get_all_signals(self, limit: int = 100) -> List[Dict]:
        """
        Retrieve all signals with an optional limit.
        
        Args:
            limit: Maximum number of signals to return (most recent)
        
        Returns:
            List of signal records
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                
                signals = []
                for row in rows:
                    sig = dict(row)
                    sig['metadata'] = json.loads(sig['metadata']) if sig['metadata'] else {}
                    signals.append(sig)
                return signals
        except Exception as e:
            logger.error(f"Error getting all signals: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """
        Get comprehensive statistics about the system.
        Used by the dashboard to display current state.
        
        Returns:
            Dictionary with system statistics
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Total signals
                cursor.execute("SELECT COUNT(*) FROM signals")
                total_signals = cursor.fetchone()[0]
                
                # Signals today
                today_str = date.today().isoformat()
                cursor.execute("SELECT COUNT(*) FROM signals WHERE date = ?", (today_str,))
                signals_today = cursor.fetchone()[0]
                
                # Executed today
                cursor.execute("SELECT COUNT(*) FROM signals WHERE date = ? AND status = 'executed'", (today_str,))
                executed_today = cursor.fetchone()[0]
                
                # System state
                system_state = self.get_system_state()
                
                return {
                    "total_signals": total_signals,
                    "signals_today": signals_today,
                    "executed_today": executed_today,
                    "system_state": system_state
                }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {
                "total_signals": 0,
                "signals_today": 0,
                "executed_today": 0,
                "system_state": {}
            }
    
    def save_trade_result(self, trade_result: Dict) -> str:
        """
        Save trade result for EDGE learning.
        
        Args:
            trade_result: Dictionary with trade outcome data
                {
                    "signal_id": str,
                    "symbol": str,
                    "entry_price": float,
                    "exit_price": float,
                    "pips": float,
                    "profit_loss": float,  # En moneda base
                    "duration_minutes": int,
                    "is_win": bool,
                    "exit_reason": str,  # "take_profit", "stop_loss", "manual"
                    "market_regime": str,
                    "volatility_atr": float,
                    "parameters_used": dict  # Parámetros activos al generar la señal
                }
        
        Returns:
            Trade ID (UUID)
        """
        trade_id = str(uuid.uuid4())
        
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO trades (
                        id, signal_id, symbol, entry_price, exit_price, pips, profit_loss,
                        duration_minutes, is_win, exit_reason, market_regime, volatility_atr,
                        parameters_used, timestamp, date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade_id,
                    trade_result.get("signal_id"),
                    trade_result.get("symbol"),
                    trade_result.get("entry_price"),
                    trade_result.get("exit_price"),
                    trade_result.get("pips"),
                    trade_result.get("profit_loss"),
                    trade_result.get("duration_minutes"),
                    trade_result.get("is_win"),
                    trade_result.get("exit_reason"),
                    trade_result.get("market_regime"),
                    trade_result.get("volatility_atr"),
                    json.dumps(trade_result.get("parameters_used", {})),
                    datetime.now().isoformat(),
                    date.today().isoformat()
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving trade result: {e}")
            raise
        
        return trade_id
    
    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """
        Get recent trade results for EDGE analysis.
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                
                trades = []
                for row in rows:
                    trade = dict(row)
                    trade['parameters_used'] = json.loads(trade['parameters_used']) if trade['parameters_used'] else {}
                    trade['is_win'] = bool(trade['is_win'])
                    trades.append(trade)
                return trades
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    def save_tuning_adjustment(self, adjustment: Dict):
        """
        Save parameter adjustment made by tuner for audit trail.
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO tuning_history (timestamp, data) VALUES (?, ?)",
                    (datetime.now().isoformat(), json.dumps(adjustment))
                )
                # Cleanup old records (keep last 500)
                cursor.execute("""
                    DELETE FROM tuning_history 
                    WHERE id NOT IN (
                        SELECT id FROM tuning_history ORDER BY id DESC LIMIT 500
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving tuning adjustment: {e}")

    def log_market_state(self, state_data: Dict):
        """
        Log market state for historical analysis and auto-calibration.
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO market_states (symbol, timestamp, regime, data) VALUES (?, ?, ?, ?)",
                    (
                        state_data.get('symbol'),
                        state_data.get('timestamp'),
                        state_data.get('regime'),
                        json.dumps(state_data)
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error logging market state: {e}")

    def get_market_states(self, limit: int = 1000, symbol: Optional[str] = None) -> List[Dict]:
        """
        Retrieve historical market states for analysis.
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT data FROM market_states"
                params = []
                
                if symbol:
                    query += " WHERE symbol = ?"
                    params.append(symbol)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                
                return [json.loads(row['data']) for row in rows]
        except Exception as e:
            logger.error(f"Error getting market states: {e}")
            return []
    
    # ==================== FEEDBACK LOOP METHODS ====================
    
    def get_signals_by_status(self, status: str) -> List[Dict]:
        """
        Get all signals with a specific status (for monitoring loop).
        
        Args:
            status: Signal status ('EXECUTED', 'PENDING', 'CLOSED', etc.)
        
        Returns:
            List of matching signals
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM signals WHERE status = ? ORDER BY timestamp DESC",
                    (status,)
                )
                rows = cursor.fetchall()
                
                signals = []
                for row in rows:
                    sig = dict(row)
                    sig['metadata'] = json.loads(sig['metadata']) if sig['metadata'] else {}
                    signals.append(sig)
                return signals
        except Exception as e:
            logger.error(f"Error getting signals by status: {e}")
            return []
    
    def get_signal_by_id(self, signal_id: str) -> Optional[Dict]:
        """
        Get a specific signal by ID.
        
        Args:
            signal_id: Signal UUID
        
        Returns:
            Signal dict or None if not found
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
                row = cursor.fetchone()
                if row:
                    sig = dict(row)
                    sig['metadata'] = json.loads(sig['metadata']) if sig['metadata'] else {}
                    return sig
                return None
        except Exception as e:
            logger.error(f"Error getting signal by id {signal_id}: {e}")
            return None

    def get_open_operations(self) -> List[Dict]:
        """
        Get signals that are currently considered 'open' (executed but not closed).
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Signals with status 'executed' that don't have a corresponding entry in 'trades'
                cursor.execute("""
                    SELECT s.* FROM signals s
                    LEFT JOIN trades t ON s.id = t.signal_id
                    WHERE s.status = 'executed' AND t.id IS NULL
                    ORDER BY s.timestamp DESC
                """)
                rows = cursor.fetchall()
                signals = []
                for row in rows:
                    sig = dict(row)
                    sig['metadata'] = json.loads(sig['metadata']) if sig['metadata'] else {}
                    signals.append(sig)
                return signals
        except Exception as e:
            logger.error(f"Error getting open operations: {e}")
            return []
    
    def update_signal_status(self, signal_id: str, status: str, metadata_update: Dict = None):
        """
        Update signal status and optionally merge metadata.
        
        Args:
            signal_id: Signal UUID
            status: New status
            metadata_update: Additional metadata to merge
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Get current signal
                cursor.execute("SELECT metadata FROM signals WHERE id = ?", (signal_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Signal {signal_id} not found for update")
                    return
                
                # Merge metadata
                current_metadata = json.loads(row[0]) if row[0] else {}
                if metadata_update:
                    current_metadata.update(metadata_update)
                
                # Update signal
                cursor.execute(
                    "UPDATE signals SET status = ?, metadata = ? WHERE id = ?",
                    (status, json.dumps(current_metadata), signal_id)
                )
                conn.commit()
                
                logger.debug(f"Signal {signal_id} updated to status: {status}")
        except Exception as e:
            logger.error(f"Error updating signal status: {e}")
    
    def get_all_trades(self, limit: int = 100) -> List[Dict]:
        """
        Get all trade results (alias for get_recent_trades for clarity).
        
        Args:
            limit: Maximum number of trades to return
        
        Returns:
            List of trade records
        """
        return self.get_recent_trades(limit)
    
    def get_win_rate(self, symbol: Optional[str] = None, days: int = 30) -> float:
        """
        Calculate win rate percentage.
        
        Args:
            symbol: Optional filter by symbol
            days: Number of days to look back
        
        Returns:
            Win rate as percentage (0-100)
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Build query
                base_query = "SELECT COUNT(*) FROM trades WHERE 1=1"
                params = []
                
                if symbol:
                    base_query += " AND symbol = ?"
                    params.append(symbol)
                
                if days:
                    from datetime import timedelta
                    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
                    base_query += " AND date >= ?"
                    params.append(cutoff_date)
                
                # Total trades
                cursor.execute(base_query, tuple(params))
                total = cursor.fetchone()[0]
                
                if total == 0:
                    return 0.0
                
                # Winning trades
                win_query = base_query + " AND is_win = 1"
                cursor.execute(win_query, tuple(params))
                wins = cursor.fetchone()[0]
                
                win_rate = (wins / total) * 100
                return round(win_rate, 2)
        except Exception as e:
            logger.error(f"Error calculating win rate: {e}")
            return 0.0
    
    def get_total_profit(self, symbol: Optional[str] = None, days: int = 30) -> float:
        """
        Calculate total profit/loss.
        
        Args:
            symbol: Optional filter by symbol
            days: Number of days to look back
        
        Returns:
            Total profit in account currency
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                query = "SELECT SUM(profit_loss) FROM trades WHERE 1=1"
                params = []
                
                if symbol:
                    query += " AND symbol = ?"
                    params.append(symbol)
                
                if days:
                    from datetime import timedelta
                    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
                    query += " AND date >= ?"
                    params.append(cutoff_date)
                
                cursor.execute(query, tuple(params))
                result = cursor.fetchone()[0]
                
                return round(result or 0.0, 2)
        except Exception as e:
            logger.error(f"Error calculating total profit: {e}")
            return 0.0
    
    def get_profit_by_symbol(self, days: int = 30) -> List[Dict]:
        """
        Get profit breakdown by symbol (for asset analysis).
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of dicts: [{'symbol': 'EURUSD', 'total_trades': 10, 'win_rate': 60.0, 'profit': 150.50}]
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Date filter
                params = []
                date_filter = ""
                if days:
                    from datetime import timedelta
                    cutoff_date = (date.today() - timedelta(days=days)).isoformat()
                    date_filter = "WHERE date >= ?"
                    params.append(cutoff_date)
                
                # Query with grouping and aggregation
                query = f"""
                    SELECT 
                        symbol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                        SUM(profit_loss) as total_profit,
                        AVG(profit_loss) as avg_profit,
                        SUM(pips) as total_pips
                    FROM trades
                    {date_filter}
                    GROUP BY symbol
                    ORDER BY total_profit DESC
                """
                
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        'symbol': row['symbol'],
                        'total_trades': row['total_trades'],
                        'win_rate': round((row['wins'] / row['total_trades'] * 100), 2) if row['total_trades'] > 0 else 0.0,
                        'profit': round(row['total_profit'] or 0.0, 2),
                        'avg_profit': round(row['avg_profit'] or 0.0, 2),
                        'total_pips': round(row['total_pips'] or 0.0, 1)
                    })
                
                return results
        except Exception as e:
            logger.error(f"Error getting profit by symbol: {e}")
            return []
    
    # ==================== BROKER MANAGEMENT ====================
    
    def save_broker(self, broker_config: Dict):
        """
        Save or update broker (provider) configuration.
        
        Args:
            broker_config: Dict with keys: broker_id, name, type, website, platforms_available, etc.
        """
        try:
            broker_id = broker_config['broker_id']
            name = broker_config['name']
            broker_type = broker_config.get('type', '')
            website = broker_config.get('website', '')
            platforms = broker_config.get('platforms_available', [])
            data_server = broker_config.get('data_server', '')
            auto_provision = broker_config.get('auto_provision_available', False)
            registration_url = broker_config.get('registration_url', '')
            
            # Serialize platforms list to JSON
            platforms_json = json.dumps(platforms)
            
            now = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Check if exists
                cursor.execute("SELECT broker_id FROM brokers WHERE broker_id = ?", (broker_id,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update
                    cursor.execute("""
                        UPDATE brokers 
                        SET name = ?, type = ?, website = ?, platforms_available = ?, 
                            data_server = ?, auto_provision_available = ?, 
                            registration_url = ?, updated_at = ?
                        WHERE broker_id = ?
                    """, (name, broker_type, website, platforms_json, data_server, 
                          auto_provision, registration_url, now, broker_id))
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO brokers 
                        (broker_id, name, type, website, platforms_available, 
                         data_server, auto_provision_available, registration_url, 
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (broker_id, name, broker_type, website, platforms_json, 
                          data_server, auto_provision, registration_url, now, now))
                
                conn.commit()
                logger.info(f"Broker saved: {broker_id}")
                
        except Exception as e:
            logger.error(f"Error saving broker: {e}")
            raise
    
    def save_platform(self, platform_config: Dict):
        """
        Save platform configuration.
        
        Args:
            platform_config: Dict with keys: platform_id, name, vendor, type, capabilities, connector_class
        """
        try:
            platform_id = platform_config['platform_id']
            name = platform_config['name']
            vendor = platform_config.get('vendor', '')
            platform_type = platform_config.get('type', '')
            capabilities = platform_config.get('capabilities', [])
            connector_class = platform_config.get('connector_class', '')
            
            # Serialize capabilities
            capabilities_json = json.dumps(capabilities)
            now = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO platforms 
                    (platform_id, name, vendor, type, capabilities, connector_class, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (platform_id, name, vendor, platform_type, capabilities_json, 
                      connector_class, now))
                conn.commit()
                logger.info(f"Platform saved: {platform_id}")
                
        except Exception as e:
            logger.error(f"Error saving platform: {e}")
            raise
    
    def save_broker_account(self, broker_id: str, platform_id: str, account_name: str, 
                          account_type: str = 'demo', server: str = '', login: str = '', 
                          password: str = '', enabled: bool = True):
        """
        Save or update broker account.
        """
        try:
            account_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Insert account
                cursor.execute("""
                    INSERT INTO broker_accounts 
                    (account_id, broker_id, platform_id, account_name, account_number, 
                        server, account_type, enabled, balance, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (account_id, broker_id, platform_id, account_name, login, 
                        server, account_type, enabled, 0.0, now, now))
                
                conn.commit()
            
            # Save credentials if provided
            if password:
                self.save_credential(account_id, "password", "password", password)
            
            # Special synchronization for MT5 (Aethelgard specific)
            if platform_id == 'mt5' and password:
                self._sync_mt5_config(login, password, server, broker_id)
            
            logger.info(f"Account saved: {account_id}")
            return account_id
                
        except Exception as e:
            logger.error(f"Error saving broker account: {e}")
            raise
    
    def _sync_mt5_config(self, login: str, password: str, server: str, broker_id: str):
        """Sync MT5 credentials to local config files (mt5.env and mt5_config.json)"""
        try:
            from pathlib import Path
            # Sync to mt5.env
            env_path = Path('config/mt5.env')
            env_path.parent.mkdir(exist_ok=True)
            
            with open(env_path, 'w') as f:
                f.write(f"# MetaTrader 5 Configuration (Sync from Dashboard)\n")
                f.write(f"MT5_LOGIN={login}\n")
                f.write(f"MT5_PASSWORD={password}\n")
                f.write(f"MT5_SERVER={server}\n")
                f.write(f"MT5_ENABLED=true\n")
            
            # Sync to mt5_config.json
            json_path = Path('config/mt5_config.json')
            config_data = {
                'login': login,
                'server': server,
                'broker_name': broker_id,
                'enabled': True,
                'configured_at': datetime.now().isoformat()
            }
            with open(json_path, 'w') as f:
                json.dump(config_data, f, indent=2)
                
            # Sync to data_providers table (DB) for the MT5 data provider
            try:
                self.save_data_provider(
                    name='mt5',
                    enabled=True,
                    priority=95,
                    requires_auth=True,
                    additional_config={
                        'login': login,
                        'server': server,
                        'password': password
                    }
                )
                logger.info("MT5 Data Provider configuration synchronized in DB.")
            except Exception as ex:
                logger.error(f"Error syncing MT5 to data_providers table: {ex}")
                
            logger.info("MT5 configuration files synchronized with database.")
        except Exception as e:
            logger.error(f"Error syncing MT5 config files: {e}")

    def get_brokers(self) -> List[Dict]:
        """Get all brokers (providers)"""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT broker_id, name, type, website, platforms_available, 
                           data_server, auto_provision_available, registration_url,
                           created_at, updated_at
                    FROM brokers
                    ORDER BY name
                """)
                rows = cursor.fetchall()
                brokers = []
                for row in rows:
                    broker = dict(row)
                    # Alias for backward compatibility
                    broker['auto_provisioning'] = 'full' if broker.get('auto_provision_available') else 'none'
                    brokers.append(broker)
                return brokers
        except Exception as e:
            logger.error(f"Error getting brokers: {e}")
            return []
    
    def get_broker(self, broker_id: str) -> Optional[Dict]:
        """Get specific broker"""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT broker_id, name, type, website, platforms_available, 
                           data_server, auto_provision_available, registration_url,
                           created_at, updated_at
                    FROM brokers
                    WHERE broker_id = ?
                """, (broker_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting broker {broker_id}: {e}")
            return None
    
    def get_platforms(self) -> List[Dict]:
        """Get all platforms"""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT platform_id, name, vendor, type, capabilities, 
                           connector_class, created_at
                    FROM platforms
                    ORDER BY name
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting platforms: {e}")
            return []
    
    def get_broker_accounts(self, broker_id: Optional[str] = None, 
                           enabled_only: bool = False,
                           account_type: Optional[str] = None) -> List[Dict]:
        """
        Get broker accounts, optionally filtered by broker_id and account_type
        
        Args:
            broker_id: Filter by specific broker (None = all)
            enabled_only: Only return enabled accounts
            account_type: Filter by account type ('demo' or 'real')
        """
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT account_id, broker_id, platform_id, account_name, 
                           account_number, server, account_type, credentials_path,
                           enabled, last_connection, balance, created_at, updated_at
                    FROM broker_accounts
                """
                
                params = []
                conditions = []
                
                if broker_id:
                    conditions.append("broker_id = ?")
                    params.append(broker_id)
                
                if enabled_only:
                    conditions.append("enabled = 1")
                
                if account_type:
                    conditions.append("account_type = ?")
                    params.append(account_type)
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY account_name"
                
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                accounts = []
                for row in rows:
                    acc = dict(row)
                    # Alias account_number to login for consistency
                    acc['login'] = acc.get('account_number')
                    accounts.append(acc)
                return accounts
        except Exception as e:
            logger.error(f"Error getting broker accounts: {e}")
            return []
    
    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get specific account"""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT account_id, broker_id, platform_id, account_name, 
                           account_number, server, account_type, credentials_path,
                           enabled, last_connection, balance, created_at, updated_at
                    FROM broker_accounts
                    WHERE account_id = ?
                """, (account_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting account {account_id}: {e}")
            return None
    
    def update_account_status(self, account_id: str, enabled: bool):
        """Enable or disable an account"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE broker_accounts 
                    SET enabled = ?, updated_at = ?
                    WHERE account_id = ?
                """, (enabled, datetime.now().isoformat(), account_id))
                conn.commit()
                logger.info(f"Account {account_id} {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error updating account status: {e}")
            raise
    
    def update_account_connection(self, account_id: str, balance: Optional[float] = None):
        """Update last connection timestamp and optionally balance"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                if balance is not None:
                    cursor.execute("""
                        UPDATE broker_accounts 
                        SET last_connection = ?, balance = ?
                        WHERE account_id = ?
                    """, (datetime.now().isoformat(), balance, account_id))
                else:
                    cursor.execute("""
                        UPDATE broker_accounts 
                        SET last_connection = ?
                        WHERE account_id = ?
                    """, (datetime.now().isoformat(), account_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating account connection: {e}")
    
    # Legacy methods for backwards compatibility (deprecated)
    def save_broker_config(self, broker_config: Dict):
        """DEPRECATED: Use save_broker() instead"""
        logger.warning("save_broker_config() is deprecated, use save_broker()")
        return self.save_broker(broker_config)
    
    def get_enabled_brokers(self) -> List[Dict]:
        """DEPRECATED: Use get_broker_accounts(enabled_only=True) instead"""
        logger.warning("get_enabled_brokers() is deprecated")
        return self.get_broker_accounts(enabled_only=True)
    
    # Account management methods for Dashboard
    def update_account_type(self, account_id: str, account_type: str):
        """Update account type (demo/real)"""
        try:
            if account_type not in ['demo', 'real']:
                raise ValueError("account_type must be 'demo' or 'real'")
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE broker_accounts 
                    SET account_type = ?, updated_at = ?
                    WHERE account_id = ?
                """, (account_type, datetime.now().isoformat(), account_id))
                conn.commit()
                logger.info(f"Account {account_id} type changed to {account_type}")
        except Exception as e:
            logger.error(f"Error updating account type: {e}")
            raise
    
    def update_account_enabled(self, account_id: str, enabled: bool):
        """Update account enabled status (alias for update_account_status)"""
        return self.update_account_status(account_id, enabled)
    
    def update_account(self, account_id: str, account_name: str = None, 
                      server: str = None, login: str = None, password: str = None):
        """Update account details"""
        try:
            updates = []
            params = []
            
            if account_name is not None:
                updates.append("account_name = ?")
                params.append(account_name)
            
            if server is not None:
                updates.append("server = ?")
                params.append(server)
            
            if login is not None:
                updates.append("account_number = ?")
                params.append(login)
            
            if password is not None:
                # Save password safely using encrypted credentials
                try:
                    # Check if credential exists
                    existing = self.get_credentials(account_id, "password")
                    if existing:
                        self.update_credential(account_id, "password", password)
                    else:
                        self.save_credential(account_id, "password", "password", password)
                except Exception as e:
                    logger.error(f"Error updating password credential: {e}")
            
            if not updates:
                # Still might need to update password even if no other fields changed
                if password is None:
                    logger.warning("No updates provided for account")
                    return
            else:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(account_id)
                
                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    query = f"UPDATE broker_accounts SET {', '.join(updates)} WHERE account_id = ?"
                    cursor.execute(query, params)
                    conn.commit()
                    
            logger.info(f"Account {account_id} updated successfully")
        except Exception as e:
            logger.error(f"Error updating account: {e}")
            raise
    
    # ========================================
    # Credential Management (Encrypted)
    # ========================================
    
    def save_credential(self, account_id: str, credential_type: str, 
                       credential_key: str, value: str, expires_at: str = None) -> str:
        """
        Save encrypted credential for a broker account
        
        Args:
            account_id: Account ID (FK to broker_accounts)
            credential_type: Type of credential (api_key, password, oauth_token, etc)
            credential_key: Name/key of the credential (e.g., 'api_key', 'api_secret', 'password')
            value: Plain text value to encrypt and store
            expires_at: Optional expiration timestamp
        
        Returns:
            credential_id: ID of saved credential
        """
        try:
            encryptor = get_encryptor()
            encrypted_value = encryptor.encrypt(value)
            credential_id = str(uuid.uuid4())
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO broker_credentials 
                    (credential_id, account_id, credential_type, credential_key, 
                     encrypted_value, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    credential_id,
                    account_id,
                    credential_type,
                    credential_key,
                    encrypted_value,
                    datetime.now().isoformat(),
                    expires_at
                ))
                conn.commit()
                logger.info(f"Saved encrypted credential {credential_key} for account {account_id}")
                return credential_id
        except Exception as e:
            logger.error(f"Error saving credential: {e}")
            raise
    
    def get_credentials(self, account_id: str, credential_type: str = None) -> Dict[str, str]:
        """
        Get decrypted credentials for an account
        
        Args:
            account_id: Account ID
            credential_type: Optional filter by credential type
        
        Returns:
            Dict mapping credential_key -> decrypted_value
        """
        try:
            encryptor = get_encryptor()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                if credential_type:
                    cursor.execute("""
                        SELECT credential_key, encrypted_value 
                        FROM broker_credentials
                        WHERE account_id = ? AND credential_type = ?
                    """, (account_id, credential_type))
                else:
                    cursor.execute("""
                        SELECT credential_key, encrypted_value 
                        FROM broker_credentials
                        WHERE account_id = ?
                    """, (account_id,))
                
                rows = cursor.fetchall()
                
                credentials = {}
                for key, encrypted_value in rows:
                    try:
                        credentials[key] = encryptor.decrypt(encrypted_value)
                    except Exception as e:
                        logger.error(f"Failed to decrypt credential {key}: {e}")
                
                return credentials
        except Exception as e:
            logger.error(f"Error getting credentials: {e}")
            return {}
    
    def update_credential(self, account_id: str, credential_key: str, new_value: str):
        """Update an existing credential value"""
        try:
            encryptor = get_encryptor()
            encrypted_value = encryptor.encrypt(new_value)
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE broker_credentials 
                    SET encrypted_value = ?
                    WHERE account_id = ? AND credential_key = ?
                """, (encrypted_value, account_id, credential_key))
                conn.commit()
                logger.info(f"Updated encrypted credential {credential_key} for account {account_id}")
        except Exception as e:
            logger.error(f"Error updating credential: {e}")
            raise

    # ========================================
    # Data Provider Management (DB BACKEND)
    # ========================================
    
    def get_data_providers(self) -> List[Dict]:
        """Get all data provider configurations from DB"""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM data_providers ORDER BY priority DESC")
                rows = cursor.fetchall()
                
                providers = []
                for row in rows:
                    p = dict(row)
                    # Deserialize additional_config
                    if p.get('additional_config'):
                        p['additional_config'] = json.loads(p['additional_config'])
                    else:
                        p['additional_config'] = {}
                    providers.append(p)
                return providers
        except Exception as e:
            logger.error(f"Error getting data providers from DB: {e}")
            return []

    def save_data_provider(self, name: str, enabled: bool, priority: int, 
                          requires_auth: bool, api_key: str = None, 
                          api_secret: str = None, additional_config: Dict = None,
                          is_system: bool = False):
        """Save or update data provider configuration in DB"""
        try:
            config_json = json.dumps(additional_config or {})
            now = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO data_providers 
                    (name, enabled, priority, requires_auth, api_key, api_secret, additional_config, is_system, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, enabled, priority, requires_auth, api_key, api_secret, config_json, 1 if is_system else 0, now))
                conn.commit()
                logger.info(f"Data provider {name} saved to DB (is_system={is_system})")
        except Exception as e:
            logger.error(f"Error saving data provider {name} to DB: {e}")
            raise

    def update_provider_enabled(self, name: str, enabled: bool):
        """Update enabled status for a provider"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE data_providers 
                    SET enabled = ?, updated_at = ?
                    WHERE name = ?
                """, (enabled, datetime.now().isoformat(), name))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating provider {name} status: {e}")
            raise
    
    def delete_credential(self, account_id: str, credential_key: str = None):
        """Delete credential(s) for an account"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                if credential_key:
                    cursor.execute("""
                        DELETE FROM broker_credentials 
                        WHERE account_id = ? AND credential_key = ?
                    """, (account_id, credential_key))
                    logger.info(f"Deleted credential {credential_key} for account {account_id}")
                else:
                    cursor.execute("""
                        DELETE FROM broker_credentials 
                        WHERE account_id = ?
                    """, (account_id,))
                    logger.info(f"Deleted all credentials for account {account_id}")
                
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting credential: {e}")
            raise
    
    def delete_account(self, account_id: str):
        """Delete account and all its credentials (CASCADE)"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Delete credentials first
                cursor.execute("DELETE FROM broker_credentials WHERE account_id = ?", (account_id,))
                
                # Delete account
                cursor.execute("DELETE FROM broker_accounts WHERE account_id = ?", (account_id,))
                
                conn.commit()
                logger.info(f"Deleted account {account_id} and all credentials")
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            raise
