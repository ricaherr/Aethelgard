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
            
            # Position History - Trazabilidad de gestión de operaciones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    old_sl REAL,
                    new_sl REAL,
                    old_tp REAL,
                    new_tp REAL,
                    reason TEXT,
                    success BOOLEAN,
                    error_message TEXT,
                    metadata TEXT
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

            # 6. Signal Pipeline Tracking (Auditoría de señales)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_pipeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    decision TEXT,
                    reason TEXT,
                    metadata TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_pipeline_signal_id ON signal_pipeline (signal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_pipeline_stage ON signal_pipeline (stage)")

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
        Merges new metadata with existing data to preserve required fields.
        
        Args:
            ticket: The ticket number of the position
            metadata: Dict with position metadata (symbol, entry_price, sl, tp, etc.)
                     Can be partial - will merge with existing data if available
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Get existing metadata and merge with new values
            existing = self.get_position_metadata(ticket)
            if existing:
                # Merge: existing data + new updates (new values overwrite old)
                merged_metadata = {**existing, **metadata}
                # Ensure ticket is correct (in case it was changed in metadata dict)
                merged_metadata['ticket'] = ticket
            else:
                # No existing metadata - use new data as-is
                merged_metadata = metadata
                merged_metadata['ticket'] = ticket
            
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_metadata (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    direction TEXT,
                    sl REAL,
                    tp REAL,
                    volume REAL NOT NULL,
                    initial_risk_usd REAL,
                    entry_regime TEXT,
                    timeframe TEXT,
                    strategy TEXT,
                    data TEXT
                )
            """)
            
            # AUTO-MIGRATION: Add direction column if it doesn't exist
            # (for existing databases created before direction tracking)
            try:
                cursor.execute("SELECT direction FROM position_metadata LIMIT 1")
            except Exception:
                logger.info("[MIGRATION] Adding 'direction' column to position_metadata table")
                cursor.execute("ALTER TABLE position_metadata ADD COLUMN direction TEXT")
                conn.commit()
            
            # AUTO-MIGRATION: Add strategy column if it doesn't exist
            # (for existing databases created before strategy tracking)
            try:
                cursor.execute("SELECT strategy FROM position_metadata LIMIT 1")
            except Exception:
                logger.info("[MIGRATION] Adding 'strategy' column to position_metadata table")
                cursor.execute("ALTER TABLE position_metadata ADD COLUMN strategy TEXT")
                conn.commit()
            
            # Extract known fields from merged metadata
            symbol = merged_metadata.get('symbol')
            entry_price = merged_metadata.get('entry_price')
            entry_time = merged_metadata.get('entry_time')
            direction = merged_metadata.get('direction')
            sl = merged_metadata.get('sl')
            tp = merged_metadata.get('tp')
            volume = merged_metadata.get('volume')
            initial_risk_usd = merged_metadata.get('initial_risk_usd')
            entry_regime = merged_metadata.get('entry_regime')
            timeframe = merged_metadata.get('timeframe')
            strategy = merged_metadata.get('strategy')
            
            # Store remaining fields as JSON in 'data' column
            known_fields = {
                'ticket', 'symbol', 'entry_price', 'entry_time', 'direction',
                'sl', 'tp', 'volume', 'initial_risk_usd', 
                'entry_regime', 'timeframe', 'strategy'
            }
            extra_data = {k: v for k, v in merged_metadata.items() if k not in known_fields}
            data_json = json.dumps(extra_data) if extra_data else None
            
            # REPLACE: insert new or update existing
            cursor.execute("""
                REPLACE INTO position_metadata 
                (ticket, symbol, entry_price, entry_time, direction, sl, tp, volume, 
                 initial_risk_usd, entry_regime, timeframe, strategy, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket, symbol, entry_price, entry_time, direction, sl, tp, volume,
                initial_risk_usd, entry_regime, timeframe, strategy, data_json
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save position metadata for ticket {ticket}: {e}", exc_info=True)
            return False
            
        finally:
            self._close_conn(conn)
    
    def rollback_position_modification(self, ticket: int) -> bool:
        """
        Rollback position metadata modification (no-op).
        
        NOTE: Metadata is already persisted BEFORE MT5 modification attempt.
        If MT5 modification fails, we keep the metadata as-is.
        Future monitoring cycles will retry adjustment if regime still changed.
        
        Args:
            ticket: Position ticket number
            
        Returns:
            True (no-op always succeeds)
        """
        logger.debug(f"[ROLLBACK] Position {ticket} - Metadata preserved (no-op)")
        return True
    
    def log_position_event(
        self,
        ticket: int,
        symbol: str,
        event_type: str,
        old_sl: Optional[float] = None,
        new_sl: Optional[float] = None,
        old_tp: Optional[float] = None,
        new_tp: Optional[float] = None,
        reason: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log position management event to position_history table.
        
        Event types:
        - 'SL_MODIFIED': Stop Loss adjusted
        - 'TP_MODIFIED': Take Profit adjusted
        - 'BREAKEVEN': Breakeven applied
        - 'TRAILING_STOP': Trailing stop activated
        - 'REGIME_CHANGE': SL/TP adjusted by regime change
        - 'SYNC': Reconciliation/sync event
        - 'CLOSE_ATTEMPT': Attempt to close position
        - 'MODIFICATION_FAILED': Failed modification attempt
        
        Args:
            ticket: Position ticket number
            symbol: Trading symbol
            event_type: Type of event (see above)
            old_sl: Previous SL level
            new_sl: New SL level
            old_tp: Previous TP level
            new_tp: New TP level
            reason: Human-readable reason for change
            success: Whether operation succeeded
            error_message: Error message if failed
            metadata: Additional metadata as dict
            
        Returns:
            True if logged successfully, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Serialize metadata to JSON
            import json
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor.execute("""
                INSERT INTO position_history 
                (ticket, symbol, event_type, old_sl, new_sl, old_tp, new_tp, 
                 reason, success, error_message, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket, symbol, event_type, old_sl, new_sl, old_tp, new_tp,
                reason, success, error_message, metadata_json
            ))
            
            conn.commit()
            logger.debug(
                f"[HISTORY] Logged {event_type} for {ticket} ({symbol}) - "
                f"SL: {old_sl}→{new_sl}, TP: {old_tp}→{new_tp}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[HISTORY] Failed to log event for {ticket}: {e}")
            return False
        finally:
            self._close_conn(conn)
    
    def get_position_history(
        self,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get position history events.
        
        Args:
            ticket: Filter by ticket (None = all positions)
            symbol: Filter by symbol (None = all symbols)
            limit: Max number of events to return
            
        Returns:
            List of history events (newest first)
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM position_history WHERE 1=1"
            params = []
            
            if ticket:
                query += " AND ticket = ?"
                params.append(ticket)
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert to dict list
            import json
            events = []
            for row in rows:
                event = dict(row)
                # Deserialize metadata if present
                if event.get('metadata'):
                    try:
                        event['metadata'] = json.loads(event['metadata'])
                    except:
                        pass
                events.append(event)
            
            return events
            
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

    def log_signal_pipeline_event(
        self,
        signal_id: str,
        stage: str,
        decision: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log signal pipeline event for audit trail.
        
        Stages:
        - CREATED: Signal created by scanner
        - STRATEGY_ANALYSIS: Strategy evaluation
        - RISK_VALIDATION: Risk manager validation
        - EXECUTED: Order executed
        - REJECTED: Signal rejected at any stage
        
        Args:
            signal_id: Signal ID
            stage: Pipeline stage
            decision: APPROVED, REJECTED, PENDING
            reason: Human-readable reason
            metadata: Additional metadata as dict
            
        Returns:
            True if logged successfully, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Serialize metadata to JSON
            metadata_json = json.dumps(metadata) if metadata else None
            
            cursor.execute("""
                INSERT INTO signal_pipeline 
                (signal_id, stage, decision, reason, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                signal_id, stage, decision, reason, metadata_json
            ))
            
            conn.commit()
            logger.debug(
                f"[PIPELINE] {signal_id} → {stage} ({decision}): {reason}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[PIPELINE] Failed to log event for {signal_id}: {e}")
            return False
        finally:
            self._close_conn(conn)
    
    def get_signal_pipeline_trace(self, signal_id: str) -> List[Dict[str, Any]]:
        """
        Get complete pipeline trace for a signal.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            List of pipeline events (chronological order)
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM signal_pipeline 
                WHERE signal_id = ?
                ORDER BY timestamp ASC
            """, (signal_id,))
            
            rows = cursor.fetchall()
            
            # Convert to dict list
            events = []
            for row in rows:
                event = dict(row)
                # Deserialize metadata if present
                if event.get('metadata'):
                    try:
                        event['metadata'] = json.loads(event['metadata'])
                    except:
                        pass
                events.append(event)
            
            return events
            
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