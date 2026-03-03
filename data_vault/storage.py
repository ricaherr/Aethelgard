import logging
import os
import sqlite3
import json
from typing import Optional, Dict, Any

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
        except Exception as e:
            logger.error(f"Error during schema initialization: {e}")
            raise
        finally:
            self._close_conn(conn)

    def _bootstrap_from_json(self, conn: sqlite3.Connection) -> None:
        """
        One-time migration logic for JSON configuration.
        """
        cursor = conn.cursor()
        
        # Check if already done
        cursor.execute("SELECT value FROM system_state WHERE key = ?", (JSON_BOOTSTRAP_DONE_KEY,))
        row = cursor.fetchone()
        if row and row[0] == "true":
            return
            
        logger.info("[BOOTSTRAP] Starting one-time JSON to SQLite migration...")
        
        try:
            # Seed symbols
            instruments_path = os.path.join("config", "instruments.json")
            if os.path.exists(instruments_path):
                try:
                    with open(instruments_path, "r") as f:
                        data = json.load(f)
                        symbols = data.get("symbols", [])
                        if symbols:
                            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                                           ('auto_trading_symbols', json.dumps(symbols)))
                            logger.info(f"Seeded {len(symbols)} symbols from config.")
                except Exception as e:
                    logger.warning(f"Failed to load instruments.json for bootstrap: {e}")
            
            # Seed risk parameters
            params_path = os.path.join("config", "dynamic_params.json")
            if os.path.exists(params_path):
                try:
                    with open(params_path, "r") as f:
                        params = json.load(f)
                        if params:
                            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                                           ('dynamic_params', json.dumps(params)))
                            logger.info("Seeded dynamic_params from config.")
                except Exception as e:
                    logger.warning(f"Failed to load dynamic_params.json for bootstrap: {e}")
                    
            # Mark as done
            cursor.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)", 
                           (JSON_BOOTSTRAP_DONE_KEY, "true"))
            conn.commit()
            logger.info("[BOOTSTRAP] JSON migration completed.")
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

