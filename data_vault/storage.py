import logging
import os
import sqlite3
import json
import shutil
import time
import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import Optional, Dict, Any, List, Union, cast
from pathlib import Path

from .base_repo import BaseRepository
from .signals_db import SignalsMixin, calculate_deduplication_window
from .trades_db import TradesMixin
from .accounts_db import AccountsMixin
from .market_db import MarketMixin
from .system_db import SystemMixin
from .sys_signal_ranking_db import StrategyRankingMixin
from .strategies_db import StrategiesMixin
from .execution_db import ExecutionMixin
from .anomalies_db import AnomaliesMixin
from .broker_accounts_db import BrokerAccountsMixin

from .schema import (
    initialize_schema,
    run_migrations,
    seed_default_usr_preferences,
    bootstrap_symbol_mappings,
)

logger: logging.Logger = logging.getLogger(__name__)

JSON_BOOTSTRAP_DONE_KEY = "_json_bootstrap_done_v1"


class StorageManager(
    SignalsMixin,
    TradesMixin,
    AccountsMixin,
    MarketMixin,
    SystemMixin,
    StrategyRankingMixin,
    StrategiesMixin,
    ExecutionMixin,
    AnomaliesMixin,
    BrokerAccountsMixin
):
    """
    Centralized storage manager for Aethelgard (ARCH-SSOT-2026-006).
    
    Acts as Orquestador de Contexto:
    - If tenant_id=None: Manages data_vault/global/aethelgard.db (sys_* tables only)
    - If tenant_id=VALUE: Manages data_vault/tenants/{tenant_id}/aethelgard.db (usr_* tables)
    
    Supports auto-provisioning of tenant databases via template cloning.
    """

    def __init__(self, db_path: Optional[str] = None, user_id: Optional[str] = None) -> None:
        """
        Initialize the storage manager with context awareness.
        
        Args:
            db_path: Explicit database path (overrides user_id logic). For backward compatibility.
            user_id: User identifier. If provided, infers path from user_id.
                      If None and db_path is None, defaults to global DB.
        
        Behavior:
        - db_path=None, user_id=None  → data_vault/global/aethelgard.db (Global Intelligence)
        - db_path=None, user_id=VALUE → data_vault/tenants/{id}/aethelgard.db (auto-create if needed)
        - db_path=VALUE                  → Use explicit path (backward compat; will resolve dynamically)
        """
        self.user_id: str | None = user_id
        
        # Resolve database path based on context
        resolved_db_path: str
        if db_path is None:
            resolved_db_path = self._resolve_db_path(user_id)
        else:
            resolved_db_path = db_path
        
        logger.info(f"StorageManager: user_id={user_id}, db_path={resolved_db_path}")
        
        # Initialize base repository
        super().__init__(resolved_db_path)
        
        # Ensure database file exists and is initialized
        if user_id is not None:
            self._ensure_tenant_db_exists()
        
        # Initialize database schema and migrations
        # Retry loop handles transient "database is locked" errors that can occur
        # when multiple processes start simultaneously (e.g., scripts + main app).
        # initialize_schema() sets PRAGMA busy_timeout=120000 as belt-and-suspenders,
        # but a Python-level retry provides a second layer of resilience.
        logger.info("Initializing database schema...")
        _max_schema_attempts = 5
        for _attempt in range(_max_schema_attempts):
            try:
                critical_context = nullcontext()
                if hasattr(self.db_driver, "force_critical_writes"):
                    # IMPORTANT: Build a fresh context manager per retry attempt.
                    # Reusing a consumed _GeneratorContextManager triggers
                    # "AttributeError: ... has no attribute 'args'" on re-entry.
                    critical_context = self.db_driver.force_critical_writes()
                with critical_context:
                    with self.transaction() as conn:
                        # DDL (idempotent via CREATE TABLE IF NOT EXISTS)
                        initialize_schema(conn)
                        # Incremental migrations
                        run_migrations(conn)
                        # Default user preferences
                        seed_default_usr_preferences(conn)
                        # Symbol mapping bootstrap
                        bootstrap_symbol_mappings(conn)
                        # JSON config migration (SSOT: once on first init)
                        self._bootstrap_from_json(conn)
                break  # success — exit retry loop
            except Exception as e:
                _is_lock_error = "locked" in str(e).lower() or "busy" in str(e).lower()
                if _is_lock_error and _attempt < _max_schema_attempts - 1:
                    _backoff = 0.5 * (2 ** _attempt)  # 0.5 → 1 → 2 → 4 s
                    logger.warning(
                        f"[StorageManager] Schema init locked (attempt {_attempt + 1}/{_max_schema_attempts}), "
                        f"retrying in {_backoff:.1f}s: {e}"
                    )
                    time.sleep(_backoff)
                else:
                    logger.error(f"Error during schema initialization: {e}")
                    raise

        # Default asset profiles (required for normalization)
        self.seed_initial_assets()

    @staticmethod
    def _resolve_db_path(user_id: Optional[str]) -> str:
        """
        Resolve database path based on user context.
        
        ARCH-SSOT-2026-006 Rules:
        - Global (user_id=None): data_vault/global/aethelgard.db
        - User (user_id=VALUE): data_vault/tenants/{user_id}/aethelgard.db
        
        Important: User ID is inferred from path, not stored as column in usr_* tables.
        """
        data_vault_root: Path = Path(__file__).parent.absolute()
        
        if user_id is None or user_id == "":
            # Global database (Capa 0)
            global_dir: Path = data_vault_root / "global"
            global_dir.mkdir(exist_ok=True)
            return str(global_dir / "aethelgard.db")
        else:
            # Tenant database (Capa 1)
            tenant_dir: Path = data_vault_root / "tenants" / user_id
            tenant_dir.mkdir(parents=True, exist_ok=True)
            return str(tenant_dir / "aethelgard.db")

    def _ensure_tenant_db_exists(self) -> None:
        """
        Auto-provisioning: If tenant DB does not exist, clone from template.
        
        Template location: data_vault/templates/usr_template.db
        This ensures new tenants get the correct usr_* schema without sys_* tables.
        """
        if self.user_id is None:
            return  # Global DB, no auto-provisioning needed
        
        tenant_db = Path(self.db_path)
        
        if tenant_db.exists():
            logger.debug(f"Tenant DB already exists: {tenant_db}")
            return  # Already provisioned
        
        template_db: Path = Path(__file__).parent / "templates" / "usr_template.db"
        
        if not template_db.exists():
            logger.warning(f"Template DB not found: {template_db}. Creating new tenant DB from scratch.")
            # Will be initialized by schema.py on first connection
            return
        
        try:
            logger.info(f"Auto-provisioning tenant DB by cloning template: {template_db} → {tenant_db}")
            shutil.copy2(template_db, tenant_db)
            logger.info(f"✅ Tenant DB provisioned: {tenant_db}")
        except Exception as e:
            logger.error(f"❌ Failed to clone template: {e}")
            # Fall through: schema initialization will handle it

    def _bootstrap_from_json(self, conn: sqlite3.Connection) -> None:
        """
        One-time migration logic for JSON configuration files.
        Loads seed data from data_vault/seed/ directory into database on first initialization.
        
        SSOT NOTE: This is idempotent (runs once, flag stored in sys_config).
        After bootstrap, database is the ONLY source of truth (aethelgard.db).
        """
        cursor: sqlite3.Cursor = conn.cursor()
        
        # Check if already done
        cursor.execute("SELECT value FROM sys_config WHERE key = ?", (JSON_BOOTSTRAP_DONE_KEY,))
        row = cursor.fetchone()
        if row and row[0] == "true":
            return
            
        logger.info("[BOOTSTRAP] Starting one-time JSON→SQLite migration...")
        
        try:
            # Seed symbols from config/
            instruments_path: str = os.path.join("config", "instruments.json")
            if os.path.exists(instruments_path):
                try:
                    with open(instruments_path, "r") as f:
                        data = json.load(f)
                        symbols = data.get("symbols", [])
                        if symbols:
                            cursor.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", 
                                           ('auto_trading_symbols', json.dumps(symbols)))
                            logger.info(f"[BOOTSTRAP] Seeded {len(symbols)} symbols from config/instruments.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load instruments.json for bootstrap: {e}")
            
            # Seed risk parameters from config/
            params_path: str = os.path.join("config", "dynamic_params.json")
            if os.path.exists(params_path):
                try:
                    with open(params_path, "r") as f:
                        params = json.load(f)
                        if params:
                            cursor.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", 
                                           ('dynamic_params', json.dumps(params)))
                            logger.info("[BOOTSTRAP] Seeded dynamic_params from config/dynamic_params.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load dynamic_params.json for bootstrap: {e}")
            
            # Seed sys_strategies from data_vault/seed/ (SSOT location for strategy registry)
            seed_sys_strategies_path: str = os.path.join("data_vault", "seed", "strategy_registry.json")
            if os.path.exists(seed_sys_strategies_path):
                try:
                    with open(seed_sys_strategies_path, "r", encoding="utf-8") as f:
                        registry = json.load(f)
                        sys_strategies = registry.get("strategies", [])  # JSON key is "strategies"
                        if sys_strategies:
                            for strat in sys_strategies:
                                cursor.execute("""
                                    INSERT OR REPLACE INTO sys_strategies 
                                    (
                                        class_id,
                                        mnemonic,
                                        version,
                                        affinity_scores,
                                        market_whitelist,
                                        readiness,
                                        readiness_notes,
                                        type,
                                        class_file,
                                        class_name,
                                        schema_file
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    strat.get("strategy_id"),
                                    strat.get("mnemonic"),
                                    strat.get("version", "1.0"),
                                    json.dumps(strat.get("affinity_scores", {})),
                                    json.dumps(strat.get("market_whitelist", [])),
                                    strat.get("readiness", "UNKNOWN"),
                                    strat.get("readiness_notes"),
                                    strat.get("type", "PYTHON_CLASS"),
                                    strat.get("class_file"),
                                    strat.get("class_name"),
                                    strat.get("schema_file"),
                                ))
                            logger.info(f"[BOOTSTRAP] Seeded {len(sys_strategies)} sys_strategies from data_vault/seed/strategy_registry.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load strategy_registry.json for bootstrap: {e}")
            
            # Mark bootstrap as complete
            cursor.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", 
                           (JSON_BOOTSTRAP_DONE_KEY, "true"))
            logger.info("[BOOTSTRAP] JSON→SQLite migration completed (SSOT: database is now canonical).")
        except Exception as e:
            logger.error(f"[BOOTSTRAP] Migration failed: {e}")
            raise

    def close(self) -> None:
        """Close underlying database connection for this storage instance."""
        try:
            if hasattr(self, "db_manager") and self.db_manager:
                self.db_manager.close_connection(self.db_path)
        except Exception as e:
            logger.warning(f"StorageManager.close failed for {self.db_path}: {e}")

    def run_legacy_json_bootstrap_once(self) -> None:
        """Public trigger: Legacy method name retained for backward compatibility."""
        with self.transaction() as conn:
            self._bootstrap_from_json(conn)

    def reload_global_config(self) -> Dict[str, Any]:
        """
        DB-first reload: returns current global_config from sys_config.
        """
        try:
            state: Dict[str, Any] = self.get_sys_config()
            cfg = state.get("global_config") or {}
            return cfg if isinstance(cfg, dict) else {}
        except Exception as e:
            logger.error(f"Error reloading global config: {e}")
            return {}

    def save_coherence_event(self, event: Dict[str, Any]) -> None:
        """
        Guarda un evento de coherencia en la base de datos.
        
        Args:
            event: Dict con los datos del evento
        """
        try:
            with self.transaction() as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO usr_coherence_events 
                    (signal_id, symbol, timeframe, strategy, stage, status, 
                     incoherence_type, reason, details, connector_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.get("signal_id"),
                    event.get("symbol"),
                    event.get("timeframe"),
                    event.get("strategy"),
                    event.get("stage"),
                    event.get("status"),
                    event.get("incoherence_type"),
                    event.get("reason"),
                    event.get("details"),
                    event.get("connector_type"),
                ))
        except Exception as e:
            logger.error(f"Error saving coherence event: {e}")

    async def get_user_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user configuration from database (SSOT).
        
        Args:
            user_id: User identifier
            
        Returns:
            User config dict or None
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn: sqlite3.Connection = self._get_conn()
            cursor: sqlite3.Cursor = conn.cursor()
            
            cursor.execute(
                "SELECT value FROM sys_config WHERE key = ?",
                (f"user:{user_id}:config",)
            )
            row = cursor.fetchone()
            
            if row:
                return cast(Optional[Dict[str, Any]], json.loads(row[0]) if isinstance(row[0], str) else row[0])
            
            # Create default config if not found
            default_config: Dict[str, str] = {
                "user_id": user_id,
                "strategy_runtime_mode": "legacy"
            }
            await self.update_user_config(user_id, default_config)
            return default_config
        
        except Exception as e:
            logger.error(f"Error getting user config for '{user_id}': {e}")
            return None
        finally:
            if conn is not None:
                self._close_conn(conn)

    async def update_user_config(self, user_id: str, updates: Dict[str, Any]) -> None:
        """
        Update user configuration in database (SSOT).
        
        Args:
            user_id: User identifier
            updates: Dict with updates to apply
        """
        try:
            with self.transaction() as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                # Get current config
                cursor.execute(
                    "SELECT value FROM sys_config WHERE key = ?",
                    (f"user:{user_id}:config",)
                )
                row = cursor.fetchone()

                current: Dict[str, Any]
                if row:
                    current = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                else:
                    current = {"user_id": user_id}

                # Merge updates
                current.update(updates)

                # Persist
                cursor.execute(
                    "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
                    (f"user:{user_id}:config", json.dumps(current))
                )
            logger.info(f"User config updated for '{user_id}'")

        except Exception as e:
            logger.error(f"Error updating user config for '{user_id}': {e}")

    async def append_to_system_ledger(self, entry: Dict[str, Any]) -> None:
        """
        Append an entry to the system ledger (audit trail).
        
        Args:
            entry: Event entry to log
        """
        try:
            with self.transaction() as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                # Get current ledger
                cursor.execute(
                    "SELECT value FROM sys_config WHERE key = ?",
                    ("system_ledger",)
                )
                row = cursor.fetchone()

                if row:
                    ledger = json.loads(row[0]) if isinstance(row[0], str) else []
                else:
                    ledger = []

                # Append entry
                ledger.append(entry)

                # Persist
                cursor.execute(
                    "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
                    ("system_ledger", json.dumps(ledger))
                )
            logger.debug(f"Ledger entry appended: {entry.get('event_type', 'UNKNOWN')}")

        except Exception as e:
            logger.error(f"Error appending to system ledger: {e}")

    def get_economic_calendar(
        self, 
        days_back: int = 30, 
        country_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve economic calendar events - UNIFIED PRIMARY METHOD.
        
        Consolidated from separate get_economic_calendar() and get_economic_events()
        to eliminate duplication (SSOT: Single Source of Truth).
        
        Args:
            days_back: Include events from last N days (default 30)
            country_filter: Filter by country code (optional, e.g., "USA", "EUR")
        
        Returns:
            List of economic events sorted by time DESC (newest first)
            Empty list if table doesn't exist (graceful degradation)
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn: sqlite3.Connection = self._get_conn()
            cursor: sqlite3.Cursor = conn.cursor()
            
            # Check if economic_calendar table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='economic_calendar'"
            )
            if not cursor.fetchone():
                logger.debug("[StorageManager] economic_calendar table not found (graceful degradation)")
                return []
            
            # Build query with optional filters
            query = """
                SELECT event_id, event_name, country, currency, impact_score,
                       forecast, actual, previous, event_time_utc, created_at
                FROM economic_calendar
                WHERE event_time_utc >= datetime('now', ? || ' days')
            """
            params: List[Any] = [f"-{days_back}"]
            
            if country_filter:
                query += " AND country = ?"
                params.append(country_filter)
            
            query += " ORDER BY event_time_utc DESC LIMIT 100"
            
            cursor.execute(query, params)
            rows: List[Any] = cursor.fetchall()
            
            if not rows:
                return []
            
            # Convert rows to dicts
            events = []
            for row in rows:
                events.append({
                    "event_id": row[0],
                    "event_name": row[1],
                    "country": row[2],
                    "currency": row[3],
                    "impact_score": row[4],
                    "forecast": row[5],
                    "actual": row[6],
                    "previous": row[7],
                    "event_time_utc": row[8],
                    "created_at": row[9],
                })
            
            logger.debug(f"[StorageManager] Retrieved {len(events)} economic events")
            return events
        
        except Exception as e:
            logger.warning(f"[StorageManager] get_economic_calendar() failed: {e}")
            return []
        finally:
            if conn is not None:
                self._close_conn(conn)

    def save_economic_event(self, event: Dict[str, Any]) -> str:
        """
        Persist a sanitized economic event to economic_calendar table.
        
        04_DATA_SOVEREIGNTY_INFRA.md Compliance:
        - Accepts ONLY sanitized events (from NewsSanitizer)
        - Assigns generated event_id (not from provider)
        - Enforces immutability: no updates allowed post-persistence
        - Logs success with event_id and impact_score
        
        Args:
            event: Sanitized event dict with keys:
                - event_id (UUID, system-assigned)
                - provider_source (BLOOMBERG, INVESTING, FOREXFACTORY)
                - event_name, country, currency, impact_score
                - event_time_utc (ISO format)
                - forecast, actual, previous (numeric, nullable)
                - created_at, data_version (system fields)
        
        Returns:
            event_id (UUID string) on success
        
        Raises:
            PersistenceError: If INSERT fails
        """
        from core_brain.news_errors import PersistenceError
        
        try:
            with self.transaction() as conn:
                cursor: sqlite3.Cursor = conn.cursor()

                # Ensure economic_calendar table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS economic_calendar (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT UNIQUE NOT NULL,
                        provider_source TEXT NOT NULL,
                        event_name TEXT NOT NULL,
                        country TEXT NOT NULL,
                        currency TEXT,
                        impact_score TEXT,
                        forecast REAL,
                        actual REAL,
                        previous REAL,
                        event_time_utc TEXT NOT NULL,
                        is_verified BOOLEAN DEFAULT 0,
                        data_version INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL
                    )
                """)

                # INSERT sanitized event
                cursor.execute("""
                    INSERT INTO economic_calendar (
                        event_id, provider_source, event_name, country, currency,
                        impact_score, forecast, actual, previous, event_time_utc,
                        is_verified, data_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.get("event_id"),
                    event.get("provider_source"),
                    event.get("event_name"),
                    event.get("country"),
                    event.get("currency"),
                    event.get("impact_score"),
                    event.get("forecast"),
                    event.get("actual"),
                    event.get("previous"),
                    event.get("event_time_utc"),
                    event.get("is_verified", False),
                    event.get("data_version", 1),
                    event.get("created_at"),
                ))

            event_id: str = cast(str, event.get("event_id"))

            logger.info(
                f"[StorageManager] SAVED economic event: "
                f"event_id={event_id}, impact={event.get('impact_score')}, "
                f"name={event.get('event_name')}"
            )

            return event_id

        except Exception as e:
            raise PersistenceError(f"Failed to save economic event: {str(e)}")

    def get_economic_events(
        self,
        days_back: int = 30,
        country_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Use get_economic_calendar() instead.
        
        This method is maintained for backwards compatibility but delegates
        to get_economic_calendar() to maintain single responsibility principle.
        
        Args:
            days_back: Include events from last N days (default 30)
            country_filter: Filter by country code (optional)
        
        Returns:
            List of economic events (delegates to get_economic_calendar)
        """
        logger.debug(
            "[StorageManager] get_economic_events() is deprecated, "
            "use get_economic_calendar() instead"
        )
        return self.get_economic_calendar(days_back=days_back, country_filter=country_filter)

    async def get_economic_events_by_window(
        self,
        symbol: str,
        start_time: Union[datetime, str],
        end_time: Union[datetime, str]
    ) -> List[Dict[str, Any]]:
        """
        Get economic events within a time window for a specific symbol.
        
        PHASE 8: Economic Veto Interface requirement.
        
        Args:
            symbol: Currency pair (e.g., 'EUR/USD', 'EURUSD')
            start_time: Start of time window (datetime or ISO string)
            end_time: End of time window (datetime or ISO string)
        
        Returns:
            List of economic events in window, sorted by event_time_utc
            Empty list if economic_calendar table doesn't exist (graceful degradation)
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            # Convert datetime objects to ISO format strings if needed
            from datetime import datetime
            if isinstance(start_time, datetime):
                start_str: str = start_time.isoformat()
            else:
                start_str = str(start_time)
                
            if isinstance(end_time, datetime):
                end_str: str = end_time.isoformat()
            else:
                end_str = str(end_time)
            
            conn: sqlite3.Connection = self._get_conn()
            cursor: sqlite3.Cursor = conn.cursor()
            
            # Check if economic_calendar table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='economic_calendar'"
            )
            if not cursor.fetchone():
                logger.debug("[StorageManager] economic_calendar table not found (graceful degradation)")
                return []
            
            # Query events in time window
            # Note: This is a basic query - currency filtering would be done by caller
            query = """
                SELECT event_id, event_name, country, currency, impact_score,
                       forecast, actual, previous, event_time_utc, created_at
                FROM economic_calendar
                WHERE event_time_utc >= ? AND event_time_utc <= ?
                ORDER BY event_time_utc ASC
                LIMIT 100
            """
            
            cursor.execute(query, (start_str, end_str))
            rows: List[Any] = cursor.fetchall()
            
            if not rows:
                return []
            
            # Convert rows to dicts
            events = []
            col_names: List[str] = [description[0] for description in cursor.description]
            for row in rows:
                event_dict: Dict[str | Any, Any] = dict(zip(col_names, row))
                events.append(event_dict)
            
            logger.debug(
                f"[StorageManager] get_economic_events_by_window: "
                f"symbol={symbol}, events={len(events)}, window={start_str} to {end_str}"
            )
            
            return events
            
        except Exception as e:
            logger.error(f"[StorageManager] Error querying economic events by window: {str(e)}")
            return []  # Graceful degradation
        finally:
            if conn is not None:
                self._close_conn(conn)

    def update_economic_event(self, event_id: str, updates: Dict[str, Any]) -> None:
        """
        IMMUTABILITY ENFORCEMENT: Updates to economic records are PROHIBITED.
        
        04_DATA_SOVEREIGNTY_INFRA.md Pilar 3:
        - Once persisted, economic_calendar records are READ-ONLY
        - Corrections must be new INSERTs with new event_id
        - This method ALWAYS raises ImmutabilityViolation
        
        Args:
            event_id: UUID of record (not updatable)
            updates: Requested fields (not allowed)
        
        Raises:
            ImmutabilityViolation: Always (by design)
        """
        from core_brain.news_errors import ImmutabilityViolation
        
        logger.error(f"[StorageManager] UPDATE BLOCKED on {event_id}: ImmutabilityViolation")
        raise ImmutabilityViolation(
            f"Update attempt on immutable economic record {event_id}. "
            f"POST-PERSISTENCE UPDATES ARE FORBIDDEN. "
            f"Corrections must be new INSERTs with new event_id."
        )


