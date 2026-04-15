"""
schema_ddl.py — Database DDL (CREATE TABLE / indexes) for Aethelgard.

Responsibility: Define and create all tables and indexes.
Called exclusively by provision_tenant_db() and StorageManager.__init__.

Rules:
- DDL only (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).
- NO migrations (use schema_migrations.py).
- NO business logic.
- NO imports from connectors, core_brain, or models.
"""
import logging
import sqlite3

from .schema_seeds import (
    _seed_sys_regime_configs,
    _seed_sys_config,
    _seed_usr_notification_settings,
)

logger = logging.getLogger(__name__)

def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Create all database tables and indexes if they don't exist.
    Safe to call on every startup (idempotent via IF NOT EXISTS).
    Relies on SQLite WAL + busy_timeout for contention handling.
    """
    cursor = conn.cursor()

    # Belt-and-suspenders: ensure WAL mode and busy_timeout are active on this
    # connection regardless of how it was created (DatabaseManager pool, raw
    # sqlite3.connect, or test fixtures).  Idempotent — safe to call multiple times.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=120000")

    # ── 0. Identity & Authentication (SSOT - Single Database) ──────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'trader')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'deleted')),
            tier TEXT NOT NULL DEFAULT 'BASIC' CHECK(tier IN ('BASIC', 'PREMIUM', 'INSTITUTIONAL')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            created_by TEXT,
            updated_by TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_users_email ON sys_users (email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_users_role ON sys_users (role)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_users_status ON sys_users (status)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource TEXT NOT NULL,
            resource_id TEXT,
            old_value TEXT,
            new_value TEXT,
            status TEXT DEFAULT 'success',
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trace_id TEXT UNIQUE,
            FOREIGN KEY (user_id) REFERENCES sys_users (id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_audit_logs_user_id ON sys_audit_logs (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_audit_logs_action ON sys_audit_logs (action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_audit_logs_timestamp ON sys_audit_logs (timestamp DESC)")

    # ── 0.1. Session Tokens ───────────────────────────────────────────────────
    # LEGACY TABLE — mantenida solo para compatibilidad durante migración aditiva.
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
    # AUTORIDAD CANÓNICA: sys_session_tokens (ver abajo).
    # PROHIBIDO: nuevas escrituras/lecturas operativas sobre esta tabla desde session_manager.py.
    # PLAN DE RETIRO: eliminar en HU posterior una vez que sys_session_tokens sea la única fuente.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            token_type TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            revoked BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME,
            user_agent TEXT,
            ip_address TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_tokens_token_hash ON session_tokens (token_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_tokens_user_id ON session_tokens (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_tokens_expires_at ON session_tokens (expires_at)")

    # CANONICAL TABLE — Autoridad SSOT de sesiones a partir de HU 8.10.
    # Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
    # Toda lectura/escritura operativa de sesiones DEBE apuntar aquí.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_session_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            token_type TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            revoked BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME,
            user_agent TEXT,
            ip_address TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_session_tokens_token_hash ON sys_session_tokens (token_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_session_tokens_user_id ON sys_session_tokens (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_session_tokens_expires_at ON sys_session_tokens (expires_at)")
    cursor.execute("""
        INSERT OR IGNORE INTO sys_session_tokens (
            id, token_hash, user_id, token_type, expires_at, revoked,
            created_at, last_used_at, user_agent, ip_address
        )
        SELECT
            id, token_hash, user_id, token_type, expires_at, revoked,
            created_at, last_used_at, user_agent, ip_address
        FROM session_tokens
    """)

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
        CREATE TABLE IF NOT EXISTS sys_signals (
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_status TEXT DEFAULT 'NONE' CHECK(review_status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED', 'AUTO_EXECUTED')),
            trader_review_reason TEXT,
            review_timeout_at TEXT
        )
    """)
    # Existing DBs may still have the pre-DISC-001 sys_signals schema at this point.
    # Guard index creation to avoid startup failure before run_migrations adds review_status.
    cursor.execute("PRAGMA table_info(sys_signals)")
    _sys_signals_cols = [r[1] for r in cursor.fetchall()]
    if "review_status" in _sys_signals_cols:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_review_status ON sys_signals(review_status) WHERE review_status='PENDING'")
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
            FOREIGN KEY (signal_id) REFERENCES sys_signals (id)
        )
    """)

    # ── 2.1 sys_trades: Capa 0 — SHADOW and BACKTEST trades ONLY (SPRINT 22) ─
    # NEVER stores LIVE trades. LIVE trades go to usr_trades (Capa 1).
    # Used by ShadowManager for 3 Pilares evaluation and backtest auditing.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_trades (
            id          TEXT PRIMARY KEY,
            signal_id   TEXT,
            instance_id TEXT,
            account_id  TEXT,
            symbol      TEXT,
            direction   TEXT,
            entry_price REAL,
            exit_price  REAL,
            profit      REAL,
            exit_reason TEXT,
            open_time   TIMESTAMP,
            close_time  TIMESTAMP,
            execution_mode TEXT NOT NULL
                CHECK(execution_mode IN ('SHADOW', 'BACKTEST')),
            strategy_id TEXT,
            order_id    TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id)  REFERENCES sys_signals(id),
            FOREIGN KEY (account_id) REFERENCES sys_broker_accounts(account_id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_trades_instance_id "
        "ON sys_trades (instance_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_trades_execution_mode "
        "ON sys_trades (execution_mode)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_trades_strategy_id "
        "ON sys_trades (strategy_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_trades_close_time "
        "ON sys_trades (close_time)"
    )

    # MIGRATION (SPRINT 22): Enforce LIVE-only constraint on usr_trades via TRIGGER
    # SQLite doesn't support ADD CONSTRAINT, so we use a BEFORE INSERT trigger.
    # This physically prevents SHADOW/BACKTEST trades from contaminating trader metrics.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_usr_trades_live_only
        BEFORE INSERT ON usr_trades
        BEGIN
            SELECT CASE
                WHEN NEW.execution_mode IS NOT NULL AND NEW.execution_mode != 'LIVE'
                THEN RAISE(ABORT, 'usr_trades only accepts execution_mode=LIVE')
            END;
        END
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

    # ── 3.1. Position Metadata ───────────────────────────────────────────────
    # LEGACY TABLE — mantenida solo para compatibilidad durante migración aditiva.
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
    # AUTORIDAD CANÓNICA: sys_position_metadata (ver abajo).
    # PROHIBIDO: nuevas escrituras/lecturas operativas sobre esta tabla desde trades_db.py.
    # PLAN DE RETIRO: eliminar en HU posterior una vez que sys_position_metadata sea la única fuente.
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_metadata_symbol ON position_metadata (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_position_metadata_entry_time ON position_metadata (entry_time DESC)")

    # CANONICAL TABLE — Autoridad SSOT de position metadata a partir de HU 8.10.
    # Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
    # Toda lectura/escritura operativa de position metadata DEBE apuntar aquí.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_position_metadata (
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_position_metadata_symbol ON sys_position_metadata (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_position_metadata_entry_time ON sys_position_metadata (entry_time DESC)")
    cursor.execute("""
        INSERT OR IGNORE INTO sys_position_metadata (
            ticket, symbol, entry_price, entry_time, direction, sl, tp,
            volume, initial_risk_usd, entry_regime, timeframe, strategy, data
        )
        SELECT
            ticket, symbol, entry_price, entry_time, direction, sl, tp,
            volume, initial_risk_usd, entry_regime, timeframe, strategy, data
        FROM position_metadata
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

    # ── 4.7 Economic Calendar (News-Based Veto) ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_economic_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_name TEXT NOT NULL,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            impact_score INTEGER,
            event_time_utc TIMESTAMP NOT NULL,
            forecast REAL,
            previous REAL,
            actual REAL,
            source TEXT DEFAULT 'economic_data_gateway',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_economic_calendar_currency ON sys_economic_calendar (currency)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_economic_calendar_time ON sys_economic_calendar (event_time_utc)")

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

    # usr_broker_accounts: per-trader execution accounts (REAL or DEMO)
    # Implements the 2-layer architecture defined in docs/01_IDENTITY_SECURITY.md
    # Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_broker_accounts (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            user_id TEXT NOT NULL,
            broker_name TEXT NOT NULL,
            broker_account_id TEXT NOT NULL,
            account_type TEXT DEFAULT 'DEMO' CHECK(account_type IN ('REAL', 'DEMO')),
            account_status TEXT DEFAULT 'ACTIVE' CHECK(account_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
            credentials_encrypted TEXT,
            daily_loss_limit DECIMAL(10,2),
            max_position_size DECIMAL(10,4),
            max_open_positions INTEGER DEFAULT 3,
            balance DECIMAL(15,2),
            equity DECIMAL(15,2),
            last_sync_utc TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, broker_name, broker_account_id),
            FOREIGN KEY(user_id) REFERENCES sys_users(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_broker_accounts_user_id ON usr_broker_accounts(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_broker_accounts_status ON usr_broker_accounts(account_status)")

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
            FOREIGN KEY (signal_id) REFERENCES sys_signals (id)
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

    # ── 10. Notifications (Persistent internal alerts — SSOT) ────────────────
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | Renamed notifications → usr_notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usr_notifications (
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_notifications_user_id ON usr_notifications (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_notifications_read ON usr_notifications (read)")

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

    # ── 13. Strategy Ranking (Darwinismo Algorítmico — SSOT) ─────────────────
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | Renamed usr_performance → sys_signal_ranking
    # RATIONALE: Table is global (system-wide), not per-user. sys_* prefix is correct.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_signal_ranking (
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_ranking_mode ON sys_signal_ranking (execution_mode)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_ranking_profit_factor ON sys_signal_ranking (profit_factor DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_ranking_sharpe ON sys_signal_ranking (sharpe_ratio DESC)")

    # ── 14. Strategies (Strategy Metadata, Affinity Scoring & Lifecycle) ────────
    # Strategy Lifecycle Modes (EXEC-V5-BACKTEST-SCENARIO-ENGINE):
    #   BACKTEST → SHADOW → LIVE
    # Score formula: score = score_live×0.50 + score_shadow×0.30 + score_backtest×0.20
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_strategies (
            class_id TEXT PRIMARY KEY,
            mnemonic TEXT NOT NULL,
            version TEXT DEFAULT '1.0',
            affinity_scores TEXT DEFAULT '{}',
            market_whitelist TEXT DEFAULT '[]',
            description TEXT,
            mode TEXT NOT NULL DEFAULT 'BACKTEST'
                CHECK(mode IN ('BACKTEST', 'SHADOW', 'LIVE')),
            score_backtest   REAL DEFAULT 0.0,
            score_shadow     REAL DEFAULT 0.0,
            score_live       REAL DEFAULT 0.0,
            score            REAL DEFAULT 0.0,
            last_backtest_at TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_mnemonic ON sys_strategies (mnemonic)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_version ON sys_strategies (version)")
    # NOTE: idx_sys_strategies_mode and idx_sys_strategies_score are created in run_migrations()
    # AFTER the ALTER TABLE that adds those columns — safe for both new and existing DBs.

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
            FOREIGN KEY (strategy_id) REFERENCES sys_strategies (class_id),
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
            user_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            metadata TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (signal_id) REFERENCES sys_signals (id)
        )
    """)
    # Indexes will be created in migrations section below (after any schema fixes)

    # ── 15.1. Execution Feedback (Broker Rejection Logger — SSOT) ────────────
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | Moved from execution_feedback.py._ensure_feedback_table()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_execution_feedback (
            feedback_id TEXT PRIMARY KEY,
            signal_id TEXT,
            symbol TEXT NOT NULL,
            strategy TEXT,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_execution_feedback_symbol ON sys_execution_feedback (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_execution_feedback_timestamp ON sys_execution_feedback (timestamp DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_execution_feedback_reason ON sys_execution_feedback (reason)")

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

    # ── 17. Signal Deduplication Rules (HU 3.3) ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_dedup_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            base_window_minutes INTEGER DEFAULT 20,
            current_window_minutes INTEGER DEFAULT 20,
            volatility_factor REAL DEFAULT 1.0,
            regime_factor REAL DEFAULT 1.0,
            last_adjusted TIMESTAMP,
            data_points_observed INTEGER DEFAULT 0,
            learning_enabled BOOLEAN DEFAULT 1,
            manual_override BOOLEAN DEFAULT 0,
            override_comment TEXT,
            trace_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timeframe, strategy)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_rules_symbol ON sys_dedup_rules (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_rules_timeframe ON sys_dedup_rules (timeframe)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_rules_strategy ON sys_dedup_rules (strategy)")

    # ── 17B. Dedup Events (HU 3.3 - PHASE 3 Learning) ────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_dedup_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            signal_id TEXT NOT NULL,
            previous_signal_id TEXT,
            gap_minutes REAL NOT NULL,
            dedup_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_events_symbol ON sys_dedup_events (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_events_created_at ON sys_dedup_events (created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_dedup_events_key ON sys_dedup_events (symbol, timeframe, strategy)")

    # ── 18. Cooldown Tracker (HU 4.7) ─────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_cooldown_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            strategy TEXT,
            failure_reason TEXT NOT NULL,
            failure_time TIMESTAMP NOT NULL,
            retry_count INTEGER DEFAULT 1,
            cooldown_minutes INTEGER NOT NULL,
            cooldown_expires TIMESTAMP NOT NULL,
            volatility_zscore REAL DEFAULT 0.0,
            regime TEXT,
            trace_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_cooldown_tracker_signal_id ON sys_cooldown_tracker (signal_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_cooldown_tracker_symbol ON sys_cooldown_tracker (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_cooldown_tracker_expires ON sys_cooldown_tracker (cooldown_expires)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_cooldown_tracker_failure_reason ON sys_cooldown_tracker (failure_reason)")

    # ── 19. PHASE 4: Signal Quality Scoring ─────────────────────────────────────
    # Signal Quality Assessments (unified scoring authority before execution)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_signal_quality_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE,
            symbol TEXT NOT NULL,
            timeframe TEXT,
            grade TEXT NOT NULL CHECK(grade IN ('A+', 'A', 'B', 'C', 'F')),
            overall_score REAL NOT NULL,
            technical_score REAL NOT NULL,
            contextual_score REAL NOT NULL,
            consensus_bonus REAL DEFAULT 0.0,
            failure_penalty REAL DEFAULT 0.0,
            metadata TEXT,
            trace_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_quality_assessments_symbol ON sys_signal_quality_assessments (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_quality_assessments_grade ON sys_signal_quality_assessments (grade)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_quality_assessments_created_at ON sys_signal_quality_assessments (created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_quality_assessments_overall_score ON sys_signal_quality_assessments (overall_score DESC)")

    # Consensus Events (multi-strategy signal density analysis)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_consensus_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
            consensus_strength REAL NOT NULL,
            num_strategies INTEGER NOT NULL,
            bonus REAL NOT NULL,
            participating_strategies TEXT,
            confidence REAL DEFAULT 0.0,
            trace_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_consensus_events_symbol ON sys_consensus_events (symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_consensus_events_direction ON sys_consensus_events (direction)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_consensus_events_strength ON sys_consensus_events (consensus_strength DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_consensus_events_created_at ON sys_consensus_events (created_at DESC)")

    # ── SHADOW EVOLUTION v2.1: Multi-Instance Strategy Incubation (RULE DB-1) ────────
    # These tables implement the Darwinian selection protocol for strategy promotion.
    # TRACE_ID pattern: TRACE_PROMOTION_REAL_YYYYMMDD_HHMMSS_instanceid
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_shadow_instances (
            instance_id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK(account_type IN ('DEMO', 'REAL')),
            parameter_overrides TEXT,
            regime_filters TEXT,
            birth_timestamp TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'INCUBATING' CHECK(status IN ('INCUBATING', 'SHADOW_READY', 'PROMOTED_TO_REAL', 'DEAD', 'QUARANTINED')),
            total_trades_executed INTEGER DEFAULT 0,
            profit_factor REAL DEFAULT 0.0,
            win_rate REAL DEFAULT 0.0,
            max_drawdown_pct REAL DEFAULT 0.0,
            consecutive_losses_max INTEGER DEFAULT 0,
            equity_curve_cv REAL DEFAULT 0.0,
            promotion_trace_id TEXT,
            backtest_trace_id TEXT,
            target_regime TEXT,
            backtest_score REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_instances_strategy_id ON sys_shadow_instances (strategy_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_instances_account_id ON sys_shadow_instances (account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_instances_account_type ON sys_shadow_instances (account_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_instances_status ON sys_shadow_instances (status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_instances_created_at ON sys_shadow_instances (created_at DESC)")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_shadow_performance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT NOT NULL,
            evaluation_date DATE NOT NULL,
            pillar1_status TEXT CHECK(pillar1_status IN ('PASS', 'FAIL', 'UNKNOWN')),
            pillar2_status TEXT CHECK(pillar2_status IN ('PASS', 'FAIL', 'UNKNOWN')),
            pillar3_status TEXT CHECK(pillar3_status IN ('PASS', 'FAIL', 'UNKNOWN')),
            overall_health TEXT CHECK(overall_health IN ('HEALTHY', 'DEAD', 'QUARANTINED', 'MONITOR', 'INCUBATING')),
            event_trace_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (instance_id) REFERENCES sys_shadow_instances (instance_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_performance_history_instance_id ON sys_shadow_performance_history (instance_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_performance_history_evaluation_date ON sys_shadow_performance_history (evaluation_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_performance_history_overall_health ON sys_shadow_performance_history (overall_health)")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_shadow_promotion_log (
            promotion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT NOT NULL,
            trace_id TEXT UNIQUE NOT NULL,
            promotion_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(promotion_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED')),
            pillar1_passed BOOLEAN DEFAULT 0,
            pillar2_passed BOOLEAN DEFAULT 0,
            pillar3_passed BOOLEAN DEFAULT 0,
            approval_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            execution_timestamp TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (instance_id) REFERENCES sys_shadow_instances (instance_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_promotion_log_instance_id ON sys_shadow_promotion_log (instance_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_promotion_log_trace_id ON sys_shadow_promotion_log (trace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_promotion_log_promotion_status ON sys_shadow_promotion_log (promotion_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_shadow_promotion_log_created_at ON sys_shadow_promotion_log (created_at DESC)")

    # Seed sys_regime_configs with default weights (SSOT)
    _seed_sys_regime_configs(cursor)

    # Seed sys_config with default configurations (Regla 14)
    _seed_sys_config(cursor)

    # Seed usr_notification_settings
    _seed_usr_notification_settings(cursor)

    # ── HU 7.17 — EDGE Evaluation Framework: Per-pair coverage tracking ────────
    # TRACE_ID: EDGE-BKT-717-COVERAGE-TABLE-2026-03-24
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sys_strategy_pair_coverage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id       TEXT NOT NULL,
            symbol            TEXT NOT NULL,
            timeframe         TEXT NOT NULL,
            regime            TEXT NOT NULL,
            n_cycles          INTEGER   DEFAULT 0,
            n_trades_total    INTEGER   DEFAULT 0,
            effective_score   REAL      DEFAULT 0.0,
            status            TEXT      DEFAULT 'PENDING',
            last_evaluated_at TIMESTAMP,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, symbol, timeframe, regime)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_coverage_strategy_id "
        "ON sys_strategy_pair_coverage (strategy_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_coverage_status "
        "ON sys_strategy_pair_coverage (status)"
    )

    # Eliminar tabla huérfana edge_learning (reemplazada por usr_edge_learning — SSOT)
    row = cursor.execute("SELECT COUNT(*) FROM usr_edge_learning").fetchone()
    if row and row[0] >= 0:
        cursor.execute("DROP TABLE IF EXISTS edge_learning")

    conn.commit()
    logger.info("Schema initialized (all tables & indexes present).")


