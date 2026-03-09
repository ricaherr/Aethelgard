"""
schema.py — Database Schema Initializer for Aethelgard.

Responsibility: DDL-only. Creates all tables, indexes, seeds sys_regime_configs
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

from .default_instruments import DEFAULT_INSTRUMENTS_CONFIG

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
        CREATE TABLE IF NOT EXISTS sys_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_edge_learning (
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
        CREATE TABLE IF NOT EXISTS usr_signals (
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
        CREATE TABLE IF NOT EXISTS usr_trades (
            id TEXT PRIMARY KEY,
            signal_id TEXT,
            symbol TEXT,
            entry_price REAL,
            exit_price REAL,
            profit REAL,
            exit_reason TEXT,
            close_time TIMESTAMP,
            execution_mode TEXT DEFAULT 'LIVE',
            provider TEXT DEFAULT 'MT5',
            account_type TEXT DEFAULT 'REAL',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES usr_signals (id)
        )
    """)

    # ── 3. Symbol Normalization (SSOT) ───────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_symbol_mappings (
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
        CREATE TABLE IF NOT EXISTS usr_position_history (
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
        CREATE TABLE IF NOT EXISTS sys_market_pulse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_coherence_events (
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

    # ── 4.5 Anomaly Events (HU 4.6: Anomaly Sentinel) ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_anomaly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            anomaly_type TEXT NOT NULL,
            z_score REAL,
            confidence REAL,
            drop_percentage REAL,
            volume_spike_detected BOOLEAN,
            trace_id TEXT NOT NULL UNIQUE,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_anomaly_events_symbol ON usr_anomaly_events (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_anomaly_events_type ON usr_anomaly_events (anomaly_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_anomaly_events_timestamp ON usr_anomaly_events (timestamp)")

    # ── 5. Accounts, Brokers & Providers ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_broker_accounts (
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
        CREATE TABLE IF NOT EXISTS sys_brokers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform_id TEXT NOT NULL,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_platforms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_credentials (
            id TEXT PRIMARY KEY,
            broker_account_id TEXT,
            encrypted_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (broker_account_id) REFERENCES sys_broker_accounts (account_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_data_providers (
            name TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            config TEXT,
            enabled BOOLEAN DEFAULT 1,
            supports_data BOOLEAN DEFAULT 0,
            supports_exec BOOLEAN DEFAULT 0,
            priority INTEGER DEFAULT 50,
            requires_auth BOOLEAN DEFAULT 0,
            api_key TEXT,
            api_secret TEXT,
            additional_config TEXT,
            is_system BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 6. Tuning ────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_tuning_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            adjustment_data TEXT
        )
    """)

    # ── 7. Signal Pipeline Tracking (Auditoría de señales) ──────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_signal_pipeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decision TEXT,
            reason TEXT,
            metadata TEXT,
            FOREIGN KEY (signal_id) REFERENCES usr_signals (id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_signal_pipeline_signal_id ON usr_signal_pipeline (signal_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_signal_pipeline_stage ON usr_signal_pipeline (stage)")

    # ── 8. User Preferences ──────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_preferences (
            user_id TEXT PRIMARY KEY DEFAULT 'default',
            profile_type TEXT DEFAULT 'active_trader',
            auto_trading_enabled BOOLEAN DEFAULT 0,
            auto_trading_max_risk REAL DEFAULT 1.0,
            auto_trading_symbols TEXT,
            auto_trading_usr_strategies TEXT,
            auto_trading_timeframes TEXT,
            notify_usr_signals BOOLEAN DEFAULT 1,
            notify_usr_executions BOOLEAN DEFAULT 1,
            notify_risks BOOLEAN DEFAULT 1,
            notify_regime_changes BOOLEAN DEFAULT 1,
            notify_threshold_score REAL DEFAULT 0.85,
            default_view TEXT DEFAULT 'feed',
            active_filters TEXT,
            require_confirmation BOOLEAN DEFAULT 1,
            max_daily_usr_trades INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 9. Notification Settings ─────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_notification_settings (
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
        CREATE TABLE IF NOT EXISTS usr_connector_settings (
            provider_id TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT 1,
            last_manual_toggle TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 12. Asset Profiles (Universal Trading) ───────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_assets_cfg (
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
        CREATE TABLE IF NOT EXISTS usr_performance (
            strategy_id TEXT PRIMARY KEY,
            profit_factor REAL DEFAULT 0.0,
            win_rate REAL DEFAULT 0.0,
            drawdown_max REAL DEFAULT 0.0,
            sharpe_ratio REAL DEFAULT 0.0,
            consecutive_losses INTEGER DEFAULT 0,
            execution_mode TEXT DEFAULT 'SHADOW',
            trace_id TEXT UNIQUE,
            last_update_utc TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_usr_trades INTEGER DEFAULT 0,
            completed_last_50 INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_performance_mode ON usr_performance (execution_mode)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_performance_profit_factor ON usr_performance (profit_factor DESC)")

    # ── 14. Strategies (Strategy Metadata & Affinity Scoring) ──────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_strategies (
            class_id TEXT PRIMARY KEY,
            mnemonic TEXT NOT NULL,
            version TEXT DEFAULT '1.0',
            affinity_scores TEXT DEFAULT '{}',
            market_whitelist TEXT DEFAULT '[]',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_mnemonic ON sys_strategies (mnemonic)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_version ON sys_strategies (version)")

    # ── 14.1. Strategy Performance Logs (Asset Efficiency Learning) ───────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_strategy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            pnl REAL DEFAULT 0.0,
            usr_trades_count INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            profit_factor REAL DEFAULT 0.0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trace_id TEXT,
            FOREIGN KEY (strategy_id) REFERENCES usr_strategies (class_id),
            UNIQUE(strategy_id, asset, timestamp)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_strategy_logs_strategy_id ON usr_strategy_logs (strategy_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_strategy_logs_asset ON usr_strategy_logs (asset)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_strategy_logs_timestamp ON usr_strategy_logs (timestamp DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_strategy_logs_trace_id ON usr_strategy_logs (trace_id)")

    # ── 15. Execution Shadow Logs (Shadow Reporting / Slippage) ────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            theoretical_price REAL NOT NULL,
            real_price REAL NOT NULL,
            slippage_pips REAL NOT NULL,
            latency_ms REAL NOT NULL,
            status TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            metadata TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES usr_signals (id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_signal_id ON usr_execution_logs (signal_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_tenant_id ON usr_execution_logs (tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_trace_id ON usr_execution_logs (trace_id)")

    # ── 16. Regime Configurations (Metric Weighting) ─────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_regime_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regime TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            weight TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(regime, metric_name)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_regime_configs_regime ON sys_regime_configs (regime)")

    # Seed sys_regime_configs with default weights (SSOT)
    _seed_sys_regime_configs(cursor)

    # Seed sys_config with default configurations (Regla 14)
    _seed_sys_config(cursor)

    # Seed usr_notification_settings
    _seed_usr_notification_settings(cursor)

    conn.commit()
    logger.info("Schema initialized (all tables & indexes present).")


def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply incremental ALTER TABLE migrations.
    Each migration is idempotent: checks column existence before altering.
    """
    cursor = conn.cursor()

    # usr_performance: add missing columns incrementally
    cursor.execute("PRAGMA table_info(usr_performance)")
    perf_cols = [r[1] for r in cursor.fetchall()]
    
    # Add sharpe_ratio if missing
    if "sharpe_ratio" not in perf_cols:
        cursor.execute("ALTER TABLE usr_performance ADD COLUMN sharpe_ratio REAL DEFAULT 0.0")
        logger.info("Migration applied: usr_performance.sharpe_ratio added.")
        perf_cols.append("sharpe_ratio")
    
    # Add total_usr_trades if missing
    if "total_usr_trades" not in perf_cols:
        cursor.execute("ALTER TABLE usr_performance ADD COLUMN total_usr_trades INTEGER DEFAULT 0")
        logger.info("Migration applied: usr_performance.total_usr_trades added.")
        perf_cols.append("total_usr_trades")
    
    # Add completed_last_50 if missing
    if "completed_last_50" not in perf_cols:
        cursor.execute("ALTER TABLE usr_performance ADD COLUMN completed_last_50 INTEGER DEFAULT 0")
        logger.info("Migration applied: usr_performance.completed_last_50 added.")
        perf_cols.append("completed_last_50")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_performance_sharpe ON usr_performance (sharpe_ratio DESC)")

    # sys_data_providers: add capability columns if missing
    cursor.execute("PRAGMA table_info(sys_data_providers)")
    dp_cols = [r[1] for r in cursor.fetchall()]
    migrations_to_add = [
        ("type", "TEXT DEFAULT 'api'"),
        ("supports_data", "BOOLEAN DEFAULT 0"),
        ("supports_exec", "BOOLEAN DEFAULT 0"),
        ("priority", "INTEGER DEFAULT 50"),
        ("requires_auth", "BOOLEAN DEFAULT 0"),
        ("api_key", "TEXT"),
        ("api_secret", "TEXT"),
        ("additional_config", "TEXT"),
        ("is_system", "BOOLEAN DEFAULT 0"),
    ]
    for col, col_type in migrations_to_add:
        if col not in dp_cols:
            cursor.execute(f"ALTER TABLE sys_data_providers ADD COLUMN {col} {col_type}")
            logger.info(f"Migration applied: sys_data_providers.{col} added.")

    # sys_broker_accounts: add capability columns if missing
    cursor.execute("PRAGMA table_info(sys_broker_accounts)")
    ba_cols = [r[1] for r in cursor.fetchall()]
    for col in ["supports_data", "supports_exec"]:
        if col not in ba_cols:
            cursor.execute(f"ALTER TABLE sys_broker_accounts ADD COLUMN {col} BOOLEAN DEFAULT 0")

    # Enable WAL mode for concurrency performance
    cursor.execute("PRAGMA journal_mode=WAL;")

    # MIGRATION (FASE D): Rename trade_results to usr_trades (one-time, safe)
    # ──────────────────────────────────────────────────────────────────────
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_results'")
    if cursor.fetchone():
        # Old table exists, rename to usr_trades
        try:
            cursor.execute("ALTER TABLE trade_results RENAME TO usr_trades")
            logger.info("Migration applied: trade_results renamed to usr_trades.")
        except sqlite3.OperationalError as e:
            # Trades table might already exist, skip if so
            logger.debug(f"trade_results rename skipped: {e}")
    
    # MIGRATION (FASE D): Add execution_mode, provider, account_type to usr_trades
    # ──────────────────────────────────────────────────────────────────────
    cursor.execute("PRAGMA table_info(usr_trades)")
    usr_trades_cols = [r[1] for r in cursor.fetchall()]
    usr_trades_migrations = [
        ("execution_mode", "TEXT DEFAULT 'LIVE'"),
        ("provider", "TEXT DEFAULT 'MT5'"),
        ("account_type", "TEXT DEFAULT 'REAL'"),
    ]
    for col, col_type in usr_trades_migrations:
        if col not in usr_trades_cols:
            cursor.execute(f"ALTER TABLE usr_trades ADD COLUMN {col} {col_type}")
            logger.info(f"Migration applied: usr_trades.{col} added with default.")
    
    # Create index for efficient filtering by execution_mode
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_trades_execution_mode ON usr_trades (execution_mode)")

    # sys_regime_configs: add tenant_id for multi-tenant isolation (nullable for backward compat)
    cursor.execute("PRAGMA table_info(sys_regime_configs)")
    rc_cols = [r[1] for r in cursor.fetchall()]
    if "tenant_id" not in rc_cols:
        cursor.execute("ALTER TABLE sys_regime_configs ADD COLUMN tenant_id TEXT DEFAULT NULL")
        logger.info("Migration applied: sys_regime_configs.tenant_id added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_regime_configs_tenant_id ON sys_regime_configs (tenant_id)")

    # sys_strategies: add readiness & readiness_notes (SSOT: Strategy Registry moved from JSON to BD)
    # TRACE_ID: EXEC-UNIVERSAL-ENGINE-REAL | CORRECTION: Soberanía de Persistencia
    cursor.execute("PRAGMA table_info(sys_strategies)")
    strat_cols = [r[1] for r in cursor.fetchall()]
    if "readiness" not in strat_cols:
        cursor.execute("ALTER TABLE sys_strategies ADD COLUMN readiness TEXT DEFAULT 'UNKNOWN'")
        logger.info("Migration applied: sys_strategies.readiness added.")
    if "readiness_notes" not in strat_cols:
        cursor.execute("ALTER TABLE sys_strategies ADD COLUMN readiness_notes TEXT DEFAULT NULL")
        logger.info("Migration applied: sys_strategies.readiness_notes added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_readiness ON sys_strategies (readiness)")

    # instruments_config: seed only when key is absent (never overwrite existing data)
    cursor.execute("SELECT 1 FROM sys_config WHERE key = ?", ("instruments_config",))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT OR IGNORE INTO sys_config (key, value) VALUES (?, ?)",
            ("instruments_config", json.dumps(DEFAULT_INSTRUMENTS_CONFIG)),
        )
        logger.info("Migration applied: sys_config.instruments_config seeded.")

    conn.commit()
    logger.debug("Migrations completed.")


def seed_default_usr_preferences(conn: sqlite3.Connection) -> None:
    """Insert the default user preferences row if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO usr_preferences (user_id, profile_type)
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
        seed_default_usr_preferences(conn)
        bootstrap_symbol_mappings(conn)
        logger.info("[TENANT] DB provisioned: %s", db_path)
    except Exception as exc:
        logger.error("[TENANT] Provisioning failed for %s: %s", db_path, exc)
        raise
    finally:
        conn.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _seed_sys_regime_configs(cursor: sqlite3.Cursor) -> None:
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
            INSERT OR IGNORE INTO sys_regime_configs (regime, metric_name, weight)
            VALUES (?, ?, ?)
        """, (regime, metric, weight))


def _seed_sys_config(cursor: sqlite3.Cursor) -> None:
    """Seed default system configurations into sys_config if missing."""
    defaults = {
        "instruments_config": DEFAULT_INSTRUMENTS_CONFIG,
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
        },
        "coherence_config": {
            "min_coherence_threshold": 0.80,
            "max_performance_degradation": 0.15,
            "min_usr_executions_for_analysis": 5
        }
    }

    for key, value in defaults.items():
        cursor.execute("""
            INSERT OR IGNORE INTO sys_config (key, value)
            VALUES (?, ?)
        """, (key, json.dumps(value)))


def _seed_usr_notification_settings(cursor: sqlite3.Cursor) -> None:
    """Seed default notification providers."""
    providers = [
        ("telegram", 0, "{}"),
        ("whatsapp", 0, "{}"),
        ("email", 0, "{}")
    ]
    for provider, enabled, config in providers:
        cursor.execute("""
            INSERT OR IGNORE INTO usr_notification_settings (provider, enabled, config)
            VALUES (?, ?, ?)
        """, (provider, enabled, config))
