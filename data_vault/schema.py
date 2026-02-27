"""
schema.py — Database Schema Initializer for Aethelgard.

Responsibility: DDL-only. Creates all tables, indexes, seeds regime_configs
and runs ALTER TABLE migrations. Called exclusively by StorageManager.__init__.

Rules:
- NO business logic here.
- NO imports from connectors, core_brain, or models.
- Pure SQLite DDL + migrations.
"""
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite3

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Create all database tables and indexes if they don't exist.
    Safe to call on every startup (idempotent via IF NOT EXISTS).
    """
    cursor = conn.cursor()

    # ── 1. System State & Learning ──────────────────────────────────────────
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

    # ── 2. Signals & Trades ──────────────────────────────────────────────────
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

    # ── 3. Symbol Normalization (SSOT) ───────────────────────────────────────
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

    # ── Position History ─────────────────────────────────────────────────────
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

    # ── 4. Market State & Coherence ──────────────────────────────────────────
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

    # ── 5. Accounts, Brokers & Providers ────────────────────────────────────
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

    # ── 6. Tuning ────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tuning_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            adjustment_data TEXT
        )
    """)

    # ── 7. Signal Pipeline Tracking (Auditoría de señales) ──────────────────
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

    # ── 8. User Preferences ──────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY DEFAULT 'default',
            profile_type TEXT DEFAULT 'active_trader',
            auto_trading_enabled BOOLEAN DEFAULT 0,
            auto_trading_max_risk REAL DEFAULT 1.0,
            auto_trading_symbols TEXT,
            auto_trading_strategies TEXT,
            auto_trading_timeframes TEXT,
            notify_signals BOOLEAN DEFAULT 1,
            notify_executions BOOLEAN DEFAULT 1,
            notify_risks BOOLEAN DEFAULT 1,
            notify_regime_changes BOOLEAN DEFAULT 1,
            notify_threshold_score REAL DEFAULT 0.85,
            default_view TEXT DEFAULT 'feed',
            active_filters TEXT,
            require_confirmation BOOLEAN DEFAULT 1,
            max_daily_trades INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 9. Notification Settings ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            provider TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT 0,
            config TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 10. Notifications (Persistent internal alerts) ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'default',
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT,
            actions TEXT,
            read BOOLEAN DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications (read)")

    # ── 11. Connector Control ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connector_settings (
            provider_id TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT 1,
            last_manual_toggle TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 12. Asset Profiles (Universal Trading) ───────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asset_profiles (
            symbol TEXT PRIMARY KEY,
            asset_class TEXT NOT NULL,
            tick_size REAL NOT NULL,
            lot_step REAL NOT NULL,
            contract_size REAL NOT NULL,
            currency TEXT NOT NULL,
            golden_hour_start TEXT,
            golden_hour_end TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 13. Strategy Ranking (Darwinismo Algorítmico) ────────────────────────
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

    # ── 14. Regime Configurations (Metric Weighting) ─────────────────────────
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

    # Seed regime_configs with default weights (SSOT)
    _seed_regime_configs(cursor)

    # Seed system_state with default configurations (Regla 14)
    _seed_system_state(cursor)

    # Seed notification_settings
    _seed_notification_settings(cursor)

    conn.commit()
    logger.info("Schema initialized (all tables & indexes present).")


def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply incremental ALTER TABLE migrations.
    Each migration is idempotent: checks column existence before altering.
    """
    cursor = conn.cursor()

    # strategy_ranking: add sharpe_ratio if missing
    cursor.execute("PRAGMA table_info(strategy_ranking)")
    sr_cols = [r[1] for r in cursor.fetchall()]
    if "sharpe_ratio" not in sr_cols:
        cursor.execute("ALTER TABLE strategy_ranking ADD COLUMN sharpe_ratio REAL DEFAULT 0.0")
        logger.info("Migration applied: strategy_ranking.sharpe_ratio added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_ranking_sharpe ON strategy_ranking (sharpe_ratio DESC)")

    # data_providers: add capability columns if missing
    cursor.execute("PRAGMA table_info(data_providers)")
    dp_cols = [r[1] for r in cursor.fetchall()]
    for col, col_type in [("type", "TEXT DEFAULT 'api'"), ("supports_data", "BOOLEAN DEFAULT 0"), ("supports_exec", "BOOLEAN DEFAULT 0")]:
        if col not in dp_cols:
            cursor.execute(f"ALTER TABLE data_providers ADD COLUMN {col} {col_type}")

    # broker_accounts: add capability columns if missing
    cursor.execute("PRAGMA table_info(broker_accounts)")
    ba_cols = [r[1] for r in cursor.fetchall()]
    for col in ["supports_data", "supports_exec"]:
        if col not in ba_cols:
            cursor.execute(f"ALTER TABLE broker_accounts ADD COLUMN {col} BOOLEAN DEFAULT 0")

    # Enable WAL mode for concurrency performance
    cursor.execute("PRAGMA journal_mode=WAL;")

    conn.commit()
    logger.debug("Migrations completed.")


def seed_default_user_preferences(conn: sqlite3.Connection) -> None:
    """Insert the default user preferences row if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_preferences (user_id, profile_type)
        VALUES ('default', 'active_trader')
    """)
    conn.commit()


def bootstrap_symbol_mappings(conn: sqlite3.Connection) -> None:
    """One-time migration: seed symbol_mappings table from config/symbol_map.json."""
    mapping_path = os.path.join("config", "symbol_map.json")
    if not os.path.exists(mapping_path):
        return

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM symbol_mappings")
    if cursor.fetchone()[0] > 0:
        return  # Already seeded

    logger.info("[SSOT] Seeding symbol_mappings from %s...", mapping_path)
    try:
        with open(mapping_path, "r") as f:
            data = json.load(f)
        for internal, providers in data.get("internal_to_provider", {}).items():
            for provider_id, provider_symbol in providers.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO symbol_mappings (internal_symbol, provider_id, provider_symbol)
                    VALUES (?, ?, ?)
                """, (internal, provider_id, provider_symbol))
        conn.commit()
        logger.info("[SSOT] Symbol mappings successfully migrated to DB.")
    except Exception as exc:
        logger.error("Error seeding symbol mappings: %s", exc)


def provision_tenant_db(db_path: str) -> None:
    """
    Full DDL + migrations + default seeds for a brand-new tenant DB.
    Called exclusively by TenantDBFactory on first access (auto-provisioning).

    Idempotent: safe to call even if the DB already exists.
    """
    import os
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        initialize_schema(conn)
        run_migrations(conn)
        seed_default_user_preferences(conn)
        bootstrap_symbol_mappings(conn)
        logger.info("[TENANT] DB provisioned: %s", db_path)
    except Exception as exc:
        logger.error("[TENANT] Provisioning failed for %s: %s", db_path, exc)
        raise
    finally:
        conn.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _seed_regime_configs(cursor: sqlite3.Cursor) -> None:
    """Seed default metric weights per market regime (SSOT)."""
    regime_data = [
        ("TREND",    "win_rate",       "0.25"),
        ("TREND",    "sharpe_ratio",   "0.35"),
        ("TREND",    "profit_factor",  "0.30"),
        ("TREND",    "drawdown_max",   "0.10"),
        ("RANGE",    "win_rate",       "0.40"),
        ("RANGE",    "sharpe_ratio",   "0.25"),
        ("RANGE",    "profit_factor",  "0.25"),
        ("RANGE",    "drawdown_max",   "0.10"),
        ("VOLATILE", "win_rate",       "0.20"),
        ("VOLATILE", "sharpe_ratio",   "0.50"),
        ("VOLATILE", "profit_factor",  "0.20"),
        ("VOLATILE", "drawdown_max",   "0.10"),
    ]
    for regime, metric, weight in regime_data:
        cursor.execute("""
            INSERT OR IGNORE INTO regime_configs (regime, metric_name, weight)
            VALUES (?, ?, ?)
        """, (regime, metric, weight))


def _seed_system_state(cursor: sqlite3.Cursor) -> None:
    """Seed default system configurations into system_state if missing."""
    defaults = {
        "config_trading": {
            "assets": ["AAPL", "TSLA", "MES", "EURUSD"],
            "cpu_limit_pct": 80.0,
            "mt5_timeframe": "M5",
            "mt5_bars_count": 500,
            "loop_interval_trend": 5,
            "loop_interval_range": 30,
            "loop_interval_volatile": 15,
            "loop_interval_shock": 60
        },
        "config_risk": {
            "max_consecutive_losses": 3,
            "lockdown_mode_enabled": 1,
            "max_account_risk_pct": 5.0,
            "tuning_enabled": 1,
            "target_win_rate": 0.55
        },
        "config_system": {
            "global_log_level": "INFO",
            "performance_mode": 0,
            "auto_start_mt5": 1
        }
    }

    for key, value in defaults.items():
        cursor.execute("""
            INSERT OR IGNORE INTO system_state (key, value)
            VALUES (?, ?)
        """, (key, json.dumps(value)))


def _seed_notification_settings(cursor: sqlite3.Cursor) -> None:
    """Seed default notification providers."""
    providers = [
        ("telegram", 0, "{}"),
        ("whatsapp", 0, "{}"),
        ("email", 0, "{}")
    ]
    for provider, enabled, config in providers:
        cursor.execute("""
            INSERT OR IGNORE INTO notification_settings (provider, enabled, config)
            VALUES (?, ?, ?)
        """, (provider, enabled, config))
