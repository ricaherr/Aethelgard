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
    StrategyRankingMixin
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
