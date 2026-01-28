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