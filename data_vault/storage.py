import logging
import os
import sqlite3
import json
from typing import Optional, Dict, Any, List

from .base_repo import BaseRepository
from .signals_db import SignalsMixin, calculate_deduplication_window
from .trades_db import TradesMixin
from .accounts_db import AccountsMixin
from .market_db import MarketMixin
from .system_db import SystemMixin
from .strategy_ranking_db import StrategyRankingMixin
from .strategies_db import StrategiesMixin
from .execution_db import ExecutionMixin
from .anomalies_db import AnomaliesMixin

from .schema import (
    initialize_schema,
    run_migrations,
    seed_default_user_preferences,
    bootstrap_symbol_mappings,
)

logger = logging.getLogger(__name__)

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
    AnomaliesMixin
):
    """
    Centralized storage manager for Aethelgard.
    Acts as a Facade/Orchestrator for specialized database repositories.
    100% API Compatibility with previous versions.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the storage manager and its underlying database segments."""
        # Initialize base repository connection pool
        super().__init__(db_path)
        
        # Initialize database schema and migrations
        conn = self._get_conn()
        try:
            logger.info("Initializing database schema...")
            # DDL
            initialize_schema(conn)
            # Incremental updates
            run_migrations(conn)
            # Default profiles
            seed_default_user_preferences(conn)
            # Fixed symbol mapping
            bootstrap_symbol_mappings(conn)
            
            # Additional bootstrap for JSON configs to DB fallback
            self._bootstrap_from_json(conn)
            
            # Default asset profiles required for tests and normalization
            self.seed_initial_assets()
            
            self._close_conn(conn)
        except Exception as e:
            logger.error(f"Error during schema initialization: {e}")
            raise
        finally:
            self._close_conn(conn)

    def _bootstrap_from_json(self, conn: sqlite3.Connection) -> None:
        """
        One-time migration logic for JSON configuration files.
        Loads seed data from data_vault/seed/ directory into database on first initialization.
        
        SSOT NOTE: This is idempotent (runs once, flag stored in system_state).
        After bootstrap, database is the ONLY source of truth (aethelgard.db).
        """
        cursor = conn.cursor()
        
        # Check if already done
        cursor.execute("SELECT value FROM system_state WHERE key = ?", (JSON_BOOTSTRAP_DONE_KEY,))
        row = cursor.fetchone()
        if row and row[0] == "true":
            return
            
        logger.info("[BOOTSTRAP] Starting one-time JSON→SQLite migration...")
        
        try:
            # Seed symbols from config/
            instruments_path = os.path.join("config", "instruments.json")
            if os.path.exists(instruments_path):
                try:
                    with open(instruments_path, "r") as f:
                        data = json.load(f)
                        symbols = data.get("symbols", [])
                        if symbols:
                            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                                           ('auto_trading_symbols', json.dumps(symbols)))
                            logger.info(f"[BOOTSTRAP] Seeded {len(symbols)} symbols from config/instruments.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load instruments.json for bootstrap: {e}")
            
            # Seed risk parameters from config/
            params_path = os.path.join("config", "dynamic_params.json")
            if os.path.exists(params_path):
                try:
                    with open(params_path, "r") as f:
                        params = json.load(f)
                        if params:
                            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                                           ('dynamic_params', json.dumps(params)))
                            logger.info("[BOOTSTRAP] Seeded dynamic_params from config/dynamic_params.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load dynamic_params.json for bootstrap: {e}")
            
            # Seed strategies from data_vault/seed/ (SSOT location for strategy registry)
            seed_strategies_path = os.path.join("data_vault", "seed", "strategy_registry.json")
            if os.path.exists(seed_strategies_path):
                try:
                    with open(seed_strategies_path, "r", encoding="utf-8") as f:  # IMPORTANTE: especificar utf-8
                        registry = json.load(f)
                        strategies = registry.get("strategies", [])
                        if strategies:
                            for strat in strategies:
                                cursor.execute("""
                                    INSERT OR REPLACE INTO strategies 
                                    (class_id, mnemonic, version, affinity_scores, market_whitelist, readiness, readiness_notes)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    strat.get("strategy_id"),
                                    strat.get("mnemonic"),
                                    strat.get("version", "1.0"),
                                    json.dumps(strat.get("affinity_scores", {})),
                                    json.dumps(strat.get("market_whitelist", [])),
                                    strat.get("readiness", "UNKNOWN"),
                                    strat.get("readiness_notes")
                                ))
                            logger.info(f"[BOOTSTRAP] Seeded {len(strategies)} strategies from data_vault/seed/strategy_registry.json")
                except Exception as e:
                    logger.warning(f"[BOOTSTRAP] Failed to load strategy_registry.json for bootstrap: {e}")
            
            # Seed demo broker accounts and data providers from data_vault/seed/
            try:
                # Import here to avoid circular imports
                from scripts.migrations.seed_demo_data import seed_demo_broker_accounts, seed_data_providers
                
                seed_demo_broker_accounts()
                seed_data_providers()
                logger.info("[BOOTSTRAP] Seeded demo broker accounts and data providers")
            except Exception as e:
                logger.warning(f"[BOOTSTRAP] Could not seed demo data: {str(e)[:100]}")
                    
            # Mark bootstrap as done (idempotent flag)
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                           (JSON_BOOTSTRAP_DONE_KEY, "true"))
            conn.commit()
            logger.info("[BOOTSTRAP] JSON→SQLite migration completed (SSOT: database is now canonical).")
        except Exception as e:
            logger.error(f"[BOOTSTRAP] Migration failed: {e}")
            conn.rollback()

    def close(self) -> None:
        """Close connection pool"""
        if hasattr(self, '_pool') and self._pool:
            self._pool.close_all()

    def run_legacy_json_bootstrap_once(self) -> None:
        """Public trigger: Legacy method name retained for backward compatibility."""
        conn = self._get_conn()
        try:
            self._bootstrap_from_json(conn)
        finally:
            self._close_conn(conn)

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

    def save_coherence_event(self, event: Dict[str, Any]) -> None:
        """
        Guarda un evento de coherencia en la base de datos.
        
        Args:
            event: Dict con los datos del evento
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO coherence_events 
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
            
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving coherence event: {e}")
        finally:
            self._close_conn(conn)

    async def get_tenant_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get tenant configuration from database (SSOT).
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Tenant config dict or None
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT value FROM system_state WHERE key = ?",
                (f"tenant:{tenant_id}:config",)
            )
            row = cursor.fetchone()
            
            if row:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            
            # Create default config if not found
            default_config = {
                "tenant_id": tenant_id,
                "strategy_runtime_mode": "legacy"
            }
            await self.update_tenant_config(tenant_id, default_config)
            return default_config
        
        except Exception as e:
            logger.error(f"Error getting tenant config for '{tenant_id}': {e}")
            return None
        finally:
            self._close_conn(conn)

    async def update_tenant_config(self, tenant_id: str, updates: Dict[str, Any]) -> None:
        """
        Update tenant configuration in database (SSOT).
        
        Args:
            tenant_id: Tenant identifier
            updates: Dict with updates to apply
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Get current config
            cursor.execute(
                "SELECT value FROM system_state WHERE key = ?",
                (f"tenant:{tenant_id}:config",)
            )
            row = cursor.fetchone()
            
            if row:
                current = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            else:
                current = {"tenant_id": tenant_id}
            
            # Merge updates
            current.update(updates)
            
            # Persist
            cursor.execute(
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                (f"tenant:{tenant_id}:config", json.dumps(current))
            )
            conn.commit()
            logger.info(f"Tenant config updated for '{tenant_id}'")
        
        except Exception as e:
            logger.error(f"Error updating tenant config for '{tenant_id}': {e}")
        finally:
            self._close_conn(conn)

    async def append_to_system_ledger(self, entry: Dict[str, Any]) -> None:
        """
        Append an entry to the system ledger (audit trail).
        
        Args:
            entry: Event entry to log
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Get current ledger
            cursor.execute(
                "SELECT value FROM system_state WHERE key = ?",
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
                "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
                ("system_ledger", json.dumps(ledger))
            )
            conn.commit()
            logger.debug(f"Ledger entry appended: {entry.get('event_type', 'UNKNOWN')}")
        
        except Exception as e:
            logger.error(f"Error appending to system ledger: {e}")
        finally:
            self._close_conn(conn)

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
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
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
            rows = cursor.fetchall()
            
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
            self._close_conn(conn)

    def save_economic_event(self, event: Dict[str, Any]) -> str:
        """
        Persist a sanitized economic event to economic_calendar table.
        
        INTERFACE_CONTRACTS.md Compliance:
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
            conn = self._get_conn()
            cursor = conn.cursor()
            
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
            
            conn.commit()
            event_id = event.get("event_id")
            
            logger.info(
                f"[StorageManager] SAVED economic event: "
                f"event_id={event_id}, impact={event.get('impact_score')}, "
                f"name={event.get('event_name')}"
            )
            
            return event_id
            
        except Exception as e:
            raise PersistenceError(f"Failed to save economic event: {str(e)}")
        finally:
            self._close_conn(conn)

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

    def update_economic_event(self, event_id: str, updates: Dict[str, Any]) -> None:
        """
        IMMUTABILITY ENFORCEMENT: Updates to economic records are PROHIBITED.
        
        INTERFACE_CONTRACTS.md Pilar 3:
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

