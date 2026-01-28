import json
import os
import sqlite3
import logging
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Manages persistence of system state using SQLite for production reliability.
    Enhanced with signal tracking capabilities for session recovery.
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
            logger.error(f"Error getting signal by ID: {e}")
            return None
    
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
    
    def save_broker_account(self, account_config: Dict):
        """
        Save or update broker account.
        
        Args:
            account_config: Dict with keys: account_id, broker_id, platform_id, account_name, 
                           account_number, server, account_type, credentials_path, enabled
        """
        try:
            account_id = account_config.get('account_id') or str(uuid.uuid4())
            broker_id = account_config['broker_id']
            platform_id = account_config['platform_id']
            account_name = account_config.get('account_name', '')
            account_number = account_config.get('account_number', '')
            server = account_config.get('server', '')
            account_type = account_config.get('account_type', 'demo')
            credentials_path = account_config.get('credentials_path', '')
            enabled = account_config.get('enabled', True)
            balance = account_config.get('balance', 0.0)
            
            now = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Check if exists
                cursor.execute("SELECT account_id FROM broker_accounts WHERE account_id = ?", (account_id,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update
                    cursor.execute("""
                        UPDATE broker_accounts 
                        SET broker_id = ?, platform_id = ?, account_name = ?, 
                            account_number = ?, server = ?, account_type = ?, 
                            credentials_path = ?, enabled = ?, balance = ?, updated_at = ?
                        WHERE account_id = ?
                    """, (broker_id, platform_id, account_name, account_number, 
                          server, account_type, credentials_path, enabled, balance, 
                          now, account_id))
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO broker_accounts 
                        (account_id, broker_id, platform_id, account_name, account_number, 
                         server, account_type, credentials_path, enabled, balance, 
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (account_id, broker_id, platform_id, account_name, account_number, 
                          server, account_type, credentials_path, enabled, balance, now, now))
                
                conn.commit()
                logger.info(f"Account saved: {account_id}")
                return account_id
                
        except Exception as e:
            logger.error(f"Error saving broker account: {e}")
            raise
    
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
                return [dict(row) for row in rows]
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
                           enabled_only: bool = False) -> List[Dict]:
        """
        Get broker accounts, optionally filtered by broker_id
        
        Args:
            broker_id: Filter by specific broker (None = all)
            enabled_only: Only return enabled accounts
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
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY account_name"
                
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
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
                # En producción, esto debería cifrarse
                # Por ahora solo actualizamos credentials_path si se proporciona
                updates.append("credentials_path = ?")
                params.append(f"config/accounts/{account_id}.json")
            
            if not updates:
                logger.warning("No updates provided for account")
                return
            
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
    
    def delete_account(self, account_id: str):
        """Delete an account"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM broker_accounts WHERE account_id = ?", (account_id,))
                conn.commit()
                logger.info(f"Account {account_id} deleted")
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            raise
