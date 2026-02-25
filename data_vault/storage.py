import logging
import os
import sqlite3
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

from .base_repo import BaseRepository
from .signals_db import SignalsMixin, calculate_deduplication_window
from .trades_db import TradesMixin
from .accounts_db import AccountsMixin
from .market_db import MarketMixin
from .system_db import SystemMixin
from .strategy_ranking_db import StrategyRankingMixin

logger = logging.getLogger(__name__)

JSON_BOOTSTRAP_DONE_KEY = "_json_bootstrap_done_v1"

class StorageManager(
    SignalsMixin,
    TradesMixin,
    AccountsMixin,
    MarketMixin,
    SystemMixin,
    StrategyRankingMixin
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
                    timestamp TEXT,
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
            
            # 3. Symbol Normalization (SSOT)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    internal_symbol TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    provider_symbol TEXT NOT NULL,
                    is_default INTEGER DEFAULT 0,
                    UNIQUE(internal_symbol, provider_id)
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
                    supports_data BOOLEAN DEFAULT 0,
                    supports_exec BOOLEAN DEFAULT 0,
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
                    supports_data BOOLEAN DEFAULT 0,
                    supports_exec BOOLEAN DEFAULT 0,
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
            
            # User Preferences (Perfiles y configuración de autonomía)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY DEFAULT 'default',
                    profile_type TEXT DEFAULT 'active_trader',
                    
                    -- AUTONOMÍA DEL SISTEMA
                    auto_trading_enabled BOOLEAN DEFAULT 0,
                    auto_trading_max_risk REAL DEFAULT 1.0,
                    auto_trading_symbols TEXT,
                    auto_trading_strategies TEXT,
                    auto_trading_timeframes TEXT,
                    
                    -- NOTIFICACIONES INTELIGENTES
                    notify_signals BOOLEAN DEFAULT 1,
                    notify_executions BOOLEAN DEFAULT 1,
                    notify_risks BOOLEAN DEFAULT 1,
                    notify_regime_changes BOOLEAN DEFAULT 1,
                    notify_threshold_score REAL DEFAULT 0.85,
                    
                    -- PREFERENCIAS DE VISTA
                    default_view TEXT DEFAULT 'feed',
                    active_filters TEXT,
                    
                    -- SEGURIDAD
                    require_confirmation BOOLEAN DEFAULT 1,
                    max_daily_trades INTEGER DEFAULT 10,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7. Notification Settings (Multi-channel)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    provider TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    config TEXT, -- JSON con credenciales encriptadas
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 8. Notifications Table (Persistent internal alerts)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    category TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT, -- JSON
                    actions TEXT, -- JSON
                    read BOOLEAN DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications (read)")

            # 9. Connector Control (Satellite Link)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS connector_settings (
                    provider_id TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 1,
                    last_manual_toggle TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 10. Universal Trading: Normalización de activos (ASSET PROFILES)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS asset_profiles (
                    symbol TEXT PRIMARY KEY,
                    asset_class TEXT NOT NULL, -- FOREX, CRYPTO, METAL, STOCK
                    tick_size REAL NOT NULL,
                    lot_step REAL NOT NULL,
                    contract_size REAL NOT NULL,
                    currency TEXT NOT NULL,
                    golden_hour_start TEXT, -- HH:MM
                    golden_hour_end TEXT,   -- HH:MM
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 11. Strategy Ranking (Darwinismo Algorítmico)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_ranking (
                    strategy_id TEXT PRIMARY KEY,
                    profit_factor REAL DEFAULT 0.0,
                    win_rate REAL DEFAULT 0.0,
                    drawdown_max REAL DEFAULT 0.0,
                    sharpe_ratio REAL DEFAULT 0.0,
                    consecutive_losses INTEGER DEFAULT 0,
                    execution_mode TEXT DEFAULT 'SHADOW',
                    trace_id TEXT UNIQUE,
                    last_update_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_trades INTEGER DEFAULT 0,
                    completed_last_50 INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_ranking_mode ON strategy_ranking (execution_mode)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_ranking_profit_factor ON strategy_ranking (profit_factor DESC)")

            # 12. Regime Configurations (Metric Weighting by Market Regime)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regime_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    regime TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    weight TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(regime, metric_name)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_configs_regime ON regime_configs (regime)")
            
            # Initialize regime_configs with default weights (SSOT)
            # TREND: Profit Factor & Win Rate prioritized (consistency in directional moves)
            # RANGE: Win Rate highest (consistency pays off in ranging markets)
            # VOLATILE: Sharpe Ratio highest (risk-adjusted returns matter most in turbulence)
            regime_data = [
                ('TREND', 'win_rate', '0.25'),
                ('TREND', 'sharpe_ratio', '0.35'),
                ('TREND', 'profit_factor', '0.30'),
                ('TREND', 'drawdown_max', '0.10'),
                
                ('RANGE', 'win_rate', '0.40'),
                ('RANGE', 'sharpe_ratio', '0.25'),
                ('RANGE', 'profit_factor', '0.25'),
                ('RANGE', 'drawdown_max', '0.10'),
                
                ('VOLATILE', 'win_rate', '0.20'),
                ('VOLATILE', 'sharpe_ratio', '0.50'),
                ('VOLATILE', 'profit_factor', '0.20'),
                ('VOLATILE', 'drawdown_max', '0.10'),
            ]
            
            for regime, metric, weight in regime_data:
                cursor.execute("""
                    INSERT OR IGNORE INTO regime_configs (regime, metric_name, weight)
                    VALUES (?, ?, ?)
                """, (regime, metric, weight))
            
            # CRITICAL: Commit after regime_data INSERTs before doing more SELECTs
            conn.commit()

            # Migrations / Fixes
            # Migrate strategy_ranking table: add sharpe_ratio if missing
            cursor.execute("PRAGMA table_info(strategy_ranking)")
            sr_columns = [row[1] for row in cursor.fetchall()]
            if 'sharpe_ratio' not in sr_columns:
                cursor.execute("ALTER TABLE strategy_ranking ADD COLUMN sharpe_ratio REAL DEFAULT 0.0")
                logger.info("✅ Migration: Added sharpe_ratio to strategy_ranking table")
            
            # Create index on sharpe_ratio after column exists
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_ranking_sharpe ON strategy_ranking (sharpe_ratio DESC)")
            
            # Commit migration before querying other tables
            conn.commit()
            
            cursor.execute("PRAGMA table_info(data_providers)")
            dp_columns = [row[1] for row in cursor.fetchall()]
            if 'type' not in dp_columns:
                cursor.execute("ALTER TABLE data_providers ADD COLUMN type TEXT DEFAULT 'api'")
            if 'supports_data' not in dp_columns:
                cursor.execute("ALTER TABLE data_providers ADD COLUMN supports_data BOOLEAN DEFAULT 0")
            if 'supports_exec' not in dp_columns:
                cursor.execute("ALTER TABLE data_providers ADD COLUMN supports_exec BOOLEAN DEFAULT 0")

            conn.commit()
            
            cursor.execute("PRAGMA table_info(broker_accounts)")
            ba_columns = [row[1] for row in cursor.fetchall()]
            if 'supports_data' not in ba_columns:
                cursor.execute("ALTER TABLE broker_accounts ADD COLUMN supports_data BOOLEAN DEFAULT 0")
            if 'supports_exec' not in ba_columns:
                cursor.execute("ALTER TABLE broker_accounts ADD COLUMN supports_exec BOOLEAN DEFAULT 0")

            # Enable WAL mode for performance
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            conn.commit()
            
            # Insertar perfil por defecto si no existe (después del commit)
            cursor.execute("""
                INSERT OR IGNORE INTO user_preferences (user_id, profile_type)
                VALUES ('default', 'active_trader')
            """)
            
            conn.commit()
            logger.info("Database initialized with modular schemas and WAL mode.")

            # Universal Trading: Seed initial data
            try:
                self.seed_initial_assets()
            except Exception as e:
                logger.error(f"Error seeding initial assets: {e}")
            
            # Seed symbol mappings from JSON if table is empty (SSOT Migration)
            self._bootstrap_symbol_mappings()
        finally:
            self._close_conn(conn)

    def get_tuning_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de ajustes de EdgeTuner.
        """
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
                item = dict(row)
                if item.get('adjustment_data'):
                    try:
                        item.update(json.loads(item['adjustment_data']))
                    except:
                        pass
                history.append(item)
            return history
        finally:
            self._close_conn(conn)

    def save_tuning_adjustment(self, adjustment_data: Dict[str, Any]) -> None:
        """
        Guarda un nuevo ajuste de EdgeTuner en la DB.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tuning_adjustments (adjustment_data)
                VALUES (?)
            """, (json.dumps(adjustment_data),))
            conn.commit()
            
        finally:
            self._close_conn(conn)

    def _bootstrap_symbol_mappings(self) -> None:
        """Seed the symbol_mappings table from config/symbol_map.json (One-time migration)."""
        mapping_path = os.path.join("config", "symbol_map.json")
        if not os.path.exists(mapping_path):
            return

        # Check if table already has data
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM symbol_mappings")
            if cursor.fetchone()[0] > 0:
                return # Already seeded
            
            logger.info(f"[SSOT] Seeding symbol_mappings from {mapping_path}...")
            with open(mapping_path, "r") as f:
                data = json.load(f)
            
            mappings = data.get("internal_to_provider", {})
            for internal, providers in mappings.items():
                for provider_id, provider_symbol in providers.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO symbol_mappings (internal_symbol, provider_id, provider_symbol)
                        VALUES (?, ?, ?)
                    """, (internal, provider_id, provider_symbol))
            
            conn.commit()
            logger.info("[SSOT] Symbol mappings successfully migrated to DB.")
        except Exception as e:
            logger.error(f"Error seeding symbol mappings: {e}")
        finally:
            self._close_conn(conn)

    def _bootstrap_from_json(self) -> None:
        """One-shot bootstrap: migrates legacy JSON config to DB only once."""
        try:
            state = self.get_system_state()
            if state.get(JSON_BOOTSTRAP_DONE_KEY):
                return

            migrated: List[str] = []

            # (Path, Section_Existence_Check, Update_Func, Label)
            # NOTE: dynamic_params.json and instruments.json removed (Phase 4 SSOT migration).
            # Their data lives exclusively in SQLite now.
            migration_map = [
                ("config/config.json", lambda: "global_config" not in self.get_system_state(), lambda cfg: self.update_system_state({"global_config": cfg}), "global_config"),
                ("config/risk_settings.json", lambda: not self.get_risk_settings(), self.update_risk_settings, "risk_settings"),
                ("config/modules.json", lambda: not self.get_modules_config(), self.save_modules_config, "modules_config"),
            ]

            for path_str, check_empty, update_func, label in migration_map:
                path = Path(path_str)
                if path.exists() and check_empty():
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data:
                            update_func(data)
                            migrated.append(label)
                    except Exception as e:
                        logger.error(f"Failed to migrate {label} from {path_str}: {e}")

            marker_payload = {
                "done": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "migrated_sections": migrated
            }
            self.update_system_state({JSON_BOOTSTRAP_DONE_KEY: marker_payload})

            if migrated:
                logger.warning("JSON bootstrap executed (one-shot). Migrated: %s", ", ".join(migrated))
            else:
                logger.debug("JSON bootstrap completed (no pending migrations).")
        except Exception as e:
            logger.error(f"Error during one-shot JSON bootstrap: {e}")

    def run_legacy_json_bootstrap_once(self) -> None:
        """
        Manual one-shot migration entrypoint.
        Kept for controlled migrations only (never automatic at runtime).
        """
        self._bootstrap_from_json()

    def reload_global_config(self) -> Dict[str, Any]:
        """
        DB-first reload: returns current global_config from system_state.
        """
        try:
            state = self.get_system_state()
            cfg = state.get("global_config", {})
            return cfg if isinstance(cfg, dict) else {}
        except Exception as e:
            logger.error(f"Error reloading global config: {e}")
            return {}

    # ========== DATABASE BACKUP ==========

    def create_db_backup(
        self,
        backup_dir: Optional[str] = None,
        retention_count: int = 24
    ) -> Optional[str]:
        """
        Create a point-in-time SQLite backup file.
        Returns backup path or None on failure.
        """
        if self.db_path == ":memory:":
            logger.warning("Skipping DB backup for in-memory database.")
            return None

        backup_root = Path(backup_dir or "backups")
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_root / f"aethelgard_{stamp}.db"

        def _backup(conn: sqlite3.Connection) -> None:
            dest = sqlite3.connect(str(backup_path))
            try:
                conn.backup(dest)
            finally:
                dest.close()

        try:
            self._execute_serialized(_backup)
            self.prune_old_backups(str(backup_root), retention_count=retention_count)
            logger.info("Database backup created: %s", backup_path)
            return str(backup_path)
        except Exception as e:
            logger.error("Failed to create DB backup: %s", e)
            return None

    def list_db_backups(self, backup_dir: Optional[str] = None) -> List[str]:
        """List backup files sorted by newest first."""
        backup_root = Path(backup_dir or "backups")
        if not backup_root.exists():
            return []
        backups = sorted(backup_root.glob("aethelgard_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [str(p) for p in backups]

    def prune_old_backups(self, backup_dir: Optional[str] = None, retention_count: int = 24) -> None:
        """Keep only the most recent N backups."""
        backups = self.list_db_backups(backup_dir)
        for old_path in backups[max(1, retention_count):]:
            try:
                Path(old_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed pruning old backup %s: %s", old_path, e)

    def restore_db_backup(self, backup_path: str) -> bool:
        """
        Restore DB from backup file.
        Note: should be used while system is stopped.
        """
        if self.db_path == ":memory:":
            logger.error("Cannot restore backup into in-memory database.")
            return False
        source = Path(backup_path)
        if not source.exists():
            logger.error("Backup file not found: %s", backup_path)
            return False
        try:
            with self._db_lock:
                shutil.copy2(source, self.db_path)
            logger.warning("Database restored from backup: %s", backup_path)
            return True
        except Exception as e:
            logger.error("Failed restoring DB backup: %s", e)
            return False

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
    
    def get_signal_pipeline_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent signal pipeline events.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM signal_pipeline 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            events = []
            for row in rows:
                event = dict(row)
                if event.get('metadata'):
                    try:
                        event['metadata'] = json.loads(event['metadata'])
                    except:
                        pass
                events.append(event)
            return events
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

    # ============================================================
    # USER PREFERENCES (Perfiles y Autonomía)
    # ============================================================
    
    def get_user_preferences(self, user_id: str = 'default') -> Optional[Dict[str, Any]]:
        """Obtiene las preferencias del usuario desde la base de datos."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            prefs = dict(zip(columns, row))
            
            # Parsear campos JSON
            for json_field in ['auto_trading_symbols', 'auto_trading_strategies', 
                              'auto_trading_timeframes', 'active_filters']:
                if prefs.get(json_field):
                    try:
                        prefs[json_field] = json.loads(prefs[json_field])
                    except:
                        prefs[json_field] = None
            
            return prefs
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return None
        finally:
            self._close_conn(conn)
    
    def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """Actualiza las preferencias del usuario en la base de datos."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Serializar campos JSON
            for json_field in ['auto_trading_symbols', 'auto_trading_strategies',
                              'auto_trading_timeframes', 'active_filters']:
                if json_field in preferences and preferences[json_field] is not None:
                    if not isinstance(preferences[json_field], str):
                        preferences[json_field] = json.dumps(preferences[json_field])
            
            # Construir UPDATE dinámico
            fields = [f"{k} = ?" for k in preferences.keys() if k != 'user_id']
            values = [v for k, v in preferences.items() if k != 'user_id']
            
            if not fields:
                return False
            
            fields.append("updated_at = CURRENT_TIMESTAMP")
            
            query = f"UPDATE user_preferences SET {', '.join(fields)} WHERE user_id = ?"
            values.append(user_id)
            
            cursor.execute(query, values)
            
            # Si no existe, insertar
            if cursor.rowcount == 0:
                preferences['user_id'] = user_id
                placeholders = ', '.join(['?' for _ in preferences])
                columns = ', '.join(preferences.keys())
                cursor.execute(f"INSERT INTO user_preferences ({columns}) VALUES ({placeholders})", 
                             list(preferences.values()))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            conn.rollback()
            return False
        finally:
            self._close_conn(conn)
    
    def get_default_profile(self, profile_type: str) -> Dict[str, Any]:
        """Retorna configuración por defecto para un tipo de perfil."""
        profiles = {
            'explorer': {
                'profile_type': 'explorer',
                'auto_trading_enabled': False,
                'notify_signals': True,
                'notify_executions': False,
                'notify_threshold_score': 0.90,
                'default_view': 'feed',
                'require_confirmation': True,
            },
            'active_trader': {
                'profile_type': 'active_trader',
                'auto_trading_enabled': False,
                'auto_trading_max_risk': 1.5,
                'notify_signals': True,
                'notify_executions': True,
                'notify_threshold_score': 0.85,
                'default_view': 'grid',
                'require_confirmation': True,
                'max_daily_trades': 10,
            },
            'analyst': {
                'profile_type': 'analyst',
                'auto_trading_enabled': False,
                'notify_signals': True,
                'notify_executions': False,
                'notify_threshold_score': 0.80,
                'default_view': 'charts',
                'require_confirmation': True,
            },
            'scalper': {
                'profile_type': 'scalper',
                'auto_trading_enabled': True,
                'auto_trading_max_risk': 1.0,
                'auto_trading_timeframes': ['M1', 'M5'],
                'notify_signals': False,
                'notify_executions': True,
                'notify_threshold_score': 0.90,
                'default_view': 'feed',
                'require_confirmation': False,
                'max_daily_trades': 20,
            },
            'custom': {
                'profile_type': 'custom',
                'auto_trading_enabled': False,
                'notify_signals': True,
                'notify_executions': True,
                'notify_threshold_score': 0.85,
                'default_view': 'feed',
                'require_confirmation': True,
            }
        }
        
        return profiles.get(profile_type, profiles['active_trader'])


    def save_coherence_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Guarda un evento de coherencia en la base de datos.
        Utilizado para trazabilidad de fallos de datos (Data Drift), 
        desajustes de señales y errores de ejecución.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO coherence_events (
                    signal_id, symbol, timeframe, strategy, 
                    stage, status, incoherence_type, reason, 
                    details, connector_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data.get('signal_id'),
                event_data.get('symbol'),
                event_data.get('timeframe'),
                event_data.get('strategy'),
                event_data.get('stage', 'SCANNER'),
                event_data.get('status', 'FAIL'),
                event_data.get('incoherence_type', 'DATA_DRIFT'),
                event_data.get('reason', 'Unknown'),
                event_data.get('details'),
                event_data.get('connector_type'),
                datetime.now().isoformat()
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error guardando evento de coherencia: {e}")
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
