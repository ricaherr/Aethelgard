import logging
import os
import sqlite3
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