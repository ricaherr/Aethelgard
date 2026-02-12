import logging
import os
import sqlite3
import json
from typing import Optional, Dict

# Base and Mixins
from .base_repo import BaseRepository
from .signals_db import SignalsMixin, calculate_deduplication_window
from .trades_db import TradesMixin
from .accounts_db import AccountsMixin
from .market_db import MarketMixin
from .system_db import SystemMixin

logger = logging.getLogger(__name__)

class StorageManager(
    SignalsMixin,
    TradesMixin,
    AccountsMixin,
    MarketMixin,
    SystemMixin
):
    """
    Centralized storage manager for Aethelgard.
    Acts as a Facade/Orchestrator for specialized database repositories.
    100% API Compatibility with previous versions.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the storage manager and its underlying database segments."""
        # Initialize base repository
        super().__init__(db_path)
        
        # Initialize database tables
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize database tables if they don't exist"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # 1. System state & Learning
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS edge_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    detection TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    learning TEXT NOT NULL,
                    details TEXT
                )
            """)

            # 2. Signals & Trades
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

            # 3. Market State & Coherence
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT
                )
            """)
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

            # 4. Accounts, Brokers & Providers
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brokers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform_id TEXT NOT NULL,
                    config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS platforms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY,
                    broker_account_id TEXT,
                    encrypted_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (broker_account_id) REFERENCES broker_accounts (account_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_providers (
                    name TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    config TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 5. Tuning
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tuning_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    adjustment_data TEXT
                )
            """)

            # Migrations / Fixes
            cursor.execute("PRAGMA table_info(data_providers)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'type' not in columns:
                cursor.execute("ALTER TABLE data_providers ADD COLUMN type TEXT DEFAULT 'api'")

            # Enable WAL mode for performance
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            conn.commit()
            logger.info("Database initialized with modular schemas and WAL mode.")
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
            required_columns = ['symbol', 'timeframe', 'direction', 'price', 'timestamp']
            cursor.execute("PRAGMA table_info(signals)")
            columns = [row[1] for row in cursor.fetchall()]
            for col in required_columns:
                if col not in columns:
                    logger.warning(f"Columna faltante en signals: {col}. Intentando agregar...")
                    try:
                        if col == 'direction':
                            cursor.execute("ALTER TABLE signals ADD COLUMN direction TEXT")
                        elif col == 'price':
                            cursor.execute("ALTER TABLE signals ADD COLUMN price REAL")
                        logger.info(f"Columna {col} agregada exitosamente.")
                    except sqlite3.OperationalError as e:
                        logger.error(f"No se pudo agregar columna {col}: {e}")
                        return False

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error verificando integridad de DB: {e}")
            return False
        finally:
            self._close_conn(conn)
    
    # ========== POSITION METADATA (INTEGRATION SUPPORT) ==========
    
    def get_position_metadata(self, ticket: int) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific position/trade by ticket number.
        Returns None if metadata doesn't exist.
        
        Args:
            ticket: The ticket number of the position/trade
            
        Returns:
            Dict with metadata fields or None if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Check if metadata table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='position_metadata'"
            )
            if not cursor.fetchone():
                # Table doesn't exist yet, return None
                return None
            
            cursor.execute(
                "SELECT * FROM position_metadata WHERE ticket = ?",
                (ticket,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Convert row to dict
            metadata = dict(row)
            
            # Parse JSON fields if they exist
            if 'data' in metadata and metadata['data']:
                try:
                    import json
                    metadata['data'] = json.loads(metadata['data'])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return metadata
            
        finally:
            self._close_conn(conn)
    
    def update_position_metadata(self, ticket: int, metadata: Dict[str, Any]) -> bool:
        """
        Save or update position metadata for monitoring.
        
        Creates position_metadata table if it doesn't exist.
        Uses REPLACE to insert new or update existing metadata.
        
        Args:
            ticket: The ticket number of the position
            metadata: Dict with position metadata (symbol, entry_price, sl, tp, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_metadata (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    sl REAL,
                    tp REAL,
                    volume REAL NOT NULL,
                    initial_risk_usd REAL,
                    entry_regime TEXT,
                    timeframe TEXT,
                    data TEXT
                )
            """)
            
            # Extract known fields
            symbol = metadata.get('symbol')
            entry_price = metadata.get('entry_price')
            entry_time = metadata.get('entry_time')
            sl = metadata.get('sl')
            tp = metadata.get('tp')
            volume = metadata.get('volume')
            initial_risk_usd = metadata.get('initial_risk_usd')
            entry_regime = metadata.get('entry_regime')
            timeframe = metadata.get('timeframe')
            
            # Store remaining fields as JSON in 'data' column
            known_fields = {
                'ticket', 'symbol', 'entry_price', 'entry_time', 
                'sl', 'tp', 'volume', 'initial_risk_usd', 
                'entry_regime', 'timeframe'
            }
            extra_data = {k: v for k, v in metadata.items() if k not in known_fields}
            data_json = json.dumps(extra_data) if extra_data else None
            
            # REPLACE: insert new or update existing
            cursor.execute("""
                REPLACE INTO position_metadata 
                (ticket, symbol, entry_price, entry_time, sl, tp, volume, 
                 initial_risk_usd, entry_regime, timeframe, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket, symbol, entry_price, entry_time, sl, tp, volume,
                initial_risk_usd, entry_regime, timeframe, data_json
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save position metadata for ticket {ticket}: {e}", exc_info=True)
            return False
            
        finally:
            self._close_conn(conn)
    
    # ========== MODULE TOGGLES (RESOLUTION LOGIC) ==========
    
    def resolve_module_enabled(self, account_id: Optional[str], module_name: str) -> bool:
        """
        Resolve final module enabled status with priority logic:
        
        Priority:
        1. GLOBAL disabled -> ALWAYS disabled (no matter individual)
        2. GLOBAL enabled + INDIVIDUAL disabled -> disabled only for that account
        3. GLOBAL enabled + no individual override -> enabled
        
        Args:
            account_id: The account ID (None for global-only check)
            module_name: Name of the module to check
            
        Returns:
            True if module is enabled, False otherwise
        """
        # Get global setting
        global_modules = self.get_global_modules_enabled()
        global_enabled = global_modules.get(module_name, True)
        
        # PRIORITY 1: If global disabled, module is disabled for everyone
        if not global_enabled:
            logger.debug(f"[RESOLVE] Module '{module_name}' DISABLED globally")
            return False
        
        # If no account specified, return global
        if not account_id:
            return global_enabled
        
        # Get individual overrides
        individual_modules = self.get_individual_modules_enabled(account_id)
        
        # If no individual override, use global
        if module_name not in individual_modules:
            logger.debug(f"[RESOLVE] Module '{module_name}' using GLOBAL setting (enabled={global_enabled})")
            return global_enabled
        
        # Individual override exists
        individual_enabled = individual_modules[module_name]
        logger.debug(
            f"[RESOLVE] Module '{module_name}' for account {account_id}: "
            f"global={global_enabled}, individual={individual_enabled}, final={individual_enabled}"
        )
        return individual_enabled

    def close(self) -> None:
        """Close persistent connection if it exists"""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None


# Test utilities (Keeping for local testing compatibility)
def temp_db_path(tmp_path: str) -> str:
    """Create temporary database path for testing"""
    return os.path.join(tmp_path, "test.db")

def storage(tmp_path: str) -> StorageManager:
    """Create storage manager for testing"""
    return StorageManager(temp_db_path(tmp_path))