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
    Uses EXCLUSIVE lock to serialize concurrent initializations.
    """
    cursor = conn.cursor()
    # Use BEGIN EXCLUSIVE to serialize schema initialization and seeding
    # Prevents "database is locked" errors when multiple StorageManager instances
    # call initialize_schema simultaneously (especially during tests)
    cursor.execute("BEGIN EXCLUSIVE")

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

    # ── 0.1. Session Tokens (API Auth — SSOT) ────────────────────────────────
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | Moved from session_manager.py._ensure_schema()
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

    # ── 3.1. Position Metadata (Open Position Monitoring — SSOT) ─────────────
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14 | Moved from trades_db.py.update_position_metadata()
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


def run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply incremental ALTER TABLE migrations.
    Each migration is idempotent: checks column existence before altering.
    """
    cursor = conn.cursor()

    # usr_performance: add missing columns incrementally
    # MIGRATION (NIVEL-0): sys_signal_ranking replaces usr_performance as Strategy Ranking SSOT
    # TRACE_ID: ARCH-SSOT-NIVEL0-2026-03-14
    # - New installs: table has all columns from initialize_schema() — ALTER checks are no-ops.
    # - Existing DBs: columns may be missing (added incrementally). Guards handle both cases.
    cursor.execute("PRAGMA table_info(sys_signal_ranking)")
    ranking_cols = [r[1] for r in cursor.fetchall()]
    if ranking_cols:  # Table exists (skip if somehow absent — initialize_schema creates it)
        if "sharpe_ratio" not in ranking_cols:
            cursor.execute("ALTER TABLE sys_signal_ranking ADD COLUMN sharpe_ratio REAL DEFAULT 0.0")
            logger.info("Migration applied: sys_signal_ranking.sharpe_ratio added.")
        if "total_usr_trades" not in ranking_cols:
            cursor.execute("ALTER TABLE sys_signal_ranking ADD COLUMN total_usr_trades INTEGER DEFAULT 0")
            logger.info("Migration applied: sys_signal_ranking.total_usr_trades added.")
        if "completed_last_50" not in ranking_cols:
            cursor.execute("ALTER TABLE sys_signal_ranking ADD COLUMN completed_last_50 INTEGER DEFAULT 0")
            logger.info("Migration applied: sys_signal_ranking.completed_last_50 added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signal_ranking_sharpe ON sys_signal_ranking (sharpe_ratio DESC)")

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
        # Dynamic loading: stored in DB so no code change is needed to add a new connector
        ("connector_module", "TEXT"),
        ("connector_class", "TEXT"),
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
    # NOTE: DatabaseManager already set these PRAGMA in get_connection()
    # These lines are kept for safety (idempotent) but DatabaseManager is SSOT
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=120000;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA wal_autocheckpoint=50000;")
    cursor.execute("PRAGMA temp_store=MEMORY;")

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
        ("order_id", "TEXT"),  # FASE 2C: Add order_id to usr_trades (moved from sys_signals)
    ]
    for col, col_type in usr_trades_migrations:
        if col not in usr_trades_cols:
            cursor.execute(f"ALTER TABLE usr_trades ADD COLUMN {col} {col_type}")
            logger.info(f"Migration applied: usr_trades.{col} added with default.")
    
    # Create index for efficient filtering by execution_mode
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_trades_execution_mode ON usr_trades (execution_mode)")

    # MIGRATION (FASE E): Add origin_mode to sys_signals for SHADOW/LIVE signal persistence
    # ──────────────────────────────────────────────────────────────────────
    cursor.execute("PRAGMA table_info(sys_signals)")
    sys_signals_cols = [r[1] for r in cursor.fetchall()]
    if "origin_mode" not in sys_signals_cols:
        cursor.execute("ALTER TABLE sys_signals ADD COLUMN origin_mode TEXT DEFAULT 'SHADOW'")
        logger.info("Migration applied: sys_signals.origin_mode added (DEFAULT='SHADOW' for safe fallback)")
    
    # Create index for efficient filtering by origin_mode (enables SHADOW signal audits)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_origin_mode ON sys_signals (origin_mode)")
    logger.info("Index created: idx_sys_signals_origin_mode for query optimization")

    # MIGRATION (FASE 2B): Add strategy_id, score, source to sys_signals for normalization
    # ──────────────────────────────────────────────────────────────────────
    if "strategy_id" not in sys_signals_cols:
        cursor.execute("ALTER TABLE sys_signals ADD COLUMN strategy_id TEXT")
        logger.info("Migration applied: sys_signals.strategy_id added for strategy link")
    if "score" not in sys_signals_cols:
        cursor.execute("ALTER TABLE sys_signals ADD COLUMN score REAL DEFAULT 0.0")
        logger.info("Migration applied: sys_signals.score added for signal quality metrics")
    if "source" not in sys_signals_cols:
        cursor.execute("ALTER TABLE sys_signals ADD COLUMN source TEXT")
        logger.info("Migration applied: sys_signals.source added for signal source tracking")
    
    # Create indexes for strategy_id lookups and score-based filtering
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_strategy_id ON sys_signals (strategy_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_score ON sys_signals (score DESC)")
    logger.info("Indexes created: idx_sys_signals_strategy_id, idx_sys_signals_score for optimization")
    
    # BACKFILL (FASE 2B): Extract strategy_id, score, source from existing metadata JSON
    # ──────────────────────────────────────────────────────────────────────
    logger.info("Starting BACKFILL: Extracting strategy_id, score, source from metadata JSON...")
    try:
        cursor.execute("""
            UPDATE sys_signals 
            SET 
                strategy_id = COALESCE(json_extract(metadata, '$.strategy_id'), strategy_id),
                score = COALESCE(CAST(json_extract(metadata, '$.score') AS REAL), 0.0),
                source = COALESCE(json_extract(metadata, '$.source'), source)
            WHERE metadata IS NOT NULL
        """)
        backfill_count = cursor.rowcount
        conn.commit()
        logger.info(f"BACKFILL completed: {backfill_count} signals updated with extracted metadata")
    except Exception as e:
        logger.warning(f"BACKFILL failed (non-blocking): {e}")
        conn.rollback()

    # MIGRATION (FASE 2C): Remove order_id column from sys_signals
    # ──────────────────────────────────────────────────────────────────────
    # SQLite doesn't support DROP COLUMN, so we recreate the table without it
    cursor.execute("PRAGMA table_info(sys_signals)")
    sys_signals_cols = [r[1] for r in cursor.fetchall()]
    if "order_id" in sys_signals_cols:
        logger.info("MIGRATION: Removing order_id from sys_signals (table recreation required)")
        try:
            # Step 1: Create temporary table without order_id
            cursor.execute("""
                CREATE TABLE sys_signals_new AS
                SELECT 
                    id, symbol, signal_type, confidence, timestamp, metadata, connector_type,
                    timeframe, price, direction, status, created_at, updated_at, origin_mode,
                    strategy_id, score, source
                FROM sys_signals
            """)
            
            # Step 2: Drop old table and recreate indexes
            cursor.execute("DROP TABLE sys_signals")
            cursor.execute("ALTER TABLE sys_signals_new RENAME TO sys_signals")
            
            # Step 3: Recreate all indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_origin_mode ON sys_signals (origin_mode)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_strategy_id ON sys_signals (strategy_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_score ON sys_signals (score DESC)")
            
            conn.commit()
            logger.info("MIGRATION completed: order_id removed from sys_signals, table recreated successfully")
        except Exception as e:
            logger.error(f"MIGRATION FAILED: {e}. Attempting rollback...")
            conn.rollback()
            raise

    # sys_regime_configs: add tenant_id for multi-tenant isolation (nullable for backward compat)
    cursor.execute("PRAGMA table_info(sys_regime_configs)")
    rc_cols = [r[1] for r in cursor.fetchall()]
    if "tenant_id" not in rc_cols:
        cursor.execute("ALTER TABLE sys_regime_configs ADD COLUMN tenant_id TEXT DEFAULT NULL")
        logger.info("Migration applied: sys_regime_configs.tenant_id added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_regime_configs_tenant_id ON sys_regime_configs (tenant_id)")

    # usr_execution_logs: Rename tenant_id to user_id (v2.0 architectural change)
    cursor.execute("PRAGMA table_info(usr_execution_logs)")
    exec_cols = [r[1] for r in cursor.fetchall()]
    if "tenant_id" in exec_cols and "user_id" not in exec_cols:
        try:
            # SQLite doesn't have ALTER COLUMN RENAME, so we use CREATE+COPY+DROP+RENAME pattern
            cursor.execute("""
                CREATE TABLE usr_execution_logs_new (
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
            cursor.execute("""
                INSERT INTO usr_execution_logs_new
                SELECT id, signal_id, symbol, theoretical_price, real_price, slippage_pips, latency_ms, status, tenant_id, trace_id, metadata, timestamp
                FROM usr_execution_logs
            """)
            cursor.execute("DROP TABLE usr_execution_logs")
            cursor.execute("ALTER TABLE usr_execution_logs_new RENAME TO usr_execution_logs")
            conn.commit()
            logger.info("Migration applied: usr_execution_logs.tenant_id renamed to user_id.")
        except Exception as e:
            logger.error(f"Migration failed for usr_execution_logs: {e}")
            conn.rollback()
    
    # Create indexes for usr_execution_logs (after potential migration)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_signal_id ON usr_execution_logs (signal_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_user_id ON usr_execution_logs (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usr_execution_logs_trace_id ON usr_execution_logs (trace_id)")

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
    # N2-1: JSON_SCHEMA Interpreter — strategy type + inline logic (SSOT: no schema_file at runtime)
    if "type" not in strat_cols:
        cursor.execute("ALTER TABLE sys_strategies ADD COLUMN type TEXT DEFAULT 'PYTHON_CLASS'")
        logger.info("Migration applied: sys_strategies.type added.")
    if "logic" not in strat_cols:
        cursor.execute("ALTER TABLE sys_strategies ADD COLUMN logic TEXT DEFAULT NULL")
        logger.info("Migration applied: sys_strategies.logic added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_readiness ON sys_strategies (readiness)")

    # MIGRATION (EXEC-V5-BACKTEST-SCENARIO-ENGINE): Regime specialisation columns
    # target_regime: which stress cluster this SHADOW instance targets.
    # backtest_score: Filtro 0 overall score from ScenarioBacktester.
    # TRACE_ID: EXEC-V5-BACKTEST-SCENARIO-ENGINE
    cursor.execute("PRAGMA table_info(sys_shadow_instances)")
    shadow_inst_cols = [r[1] for r in cursor.fetchall()]
    if "target_regime" not in shadow_inst_cols:
        cursor.execute("ALTER TABLE sys_shadow_instances ADD COLUMN target_regime TEXT")
        logger.info("Migration applied: sys_shadow_instances.target_regime added.")
    if "backtest_score" not in shadow_inst_cols:
        cursor.execute(
            "ALTER TABLE sys_shadow_instances ADD COLUMN backtest_score REAL DEFAULT 0.0"
        )
        logger.info("Migration applied: sys_shadow_instances.backtest_score added.")

    # MIGRATION (EXEC-V5-STRATEGY-LIFECYCLE): Strategy mode + per-mode scores
    # Pipeline: BACKTEST → SHADOW → LIVE
    # Consolidated: score = score_live×0.50 + score_shadow×0.30 + score_backtest×0.20
    # TRACE_ID: EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23
    cursor.execute("PRAGMA table_info(sys_strategies)")
    strat_lifecycle_cols = [r[1] for r in cursor.fetchall()]
    lifecycle_migrations = [
        ("mode",           "TEXT NOT NULL DEFAULT 'BACKTEST'"),
        ("score_backtest", "REAL DEFAULT 0.0"),
        ("score_shadow",   "REAL DEFAULT 0.0"),
        ("score_live",     "REAL DEFAULT 0.0"),
        ("score",          "REAL DEFAULT 0.0"),
    ]
    for col, col_def in lifecycle_migrations:
        if col not in strat_lifecycle_cols:
            cursor.execute(f"ALTER TABLE sys_strategies ADD COLUMN {col} {col_def}")
            logger.info(f"Migration applied: sys_strategies.{col} added.")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_strategies_mode ON sys_strategies (mode)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sys_strategies_score ON sys_strategies (score DESC)"
    )
    # MIGRATION (PIPELINE-UNBLOCK-BACKTEST-COOLDOWN): Dedicated last_backtest_at field
    # Prevents cooldown using general updated_at (which gets set by any DB write).
    # TRACE_ID: PIPELINE-UNBLOCK-BACKTEST-COOLDOWN-2026-03-24
    cursor.execute("PRAGMA table_info(sys_strategies)")
    strat_backtest_cols = [r[1] for r in cursor.fetchall()]
    if "last_backtest_at" not in strat_backtest_cols:
        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN last_backtest_at TIMESTAMP DEFAULT NULL"
        )
        logger.info("Migration applied: sys_strategies.last_backtest_at added.")

    # HU 7.8: Structural context columns (required_regime, required_timeframes, execution_params)
    # Allows ScenarioBacktester to know the strategy's operational context without hard-coding
    # assumptions. execution_params replaces the misuse of affinity_scores for threshold storage.
    # TRACE_ID: EDGE-BKT-78-STRUCTURAL-CONTEXT-2026-03-24
    cursor.execute("PRAGMA table_info(sys_strategies)")
    strat_ctx_cols = [r[1] for r in cursor.fetchall()]
    if "required_regime" not in strat_ctx_cols:
        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN required_regime TEXT DEFAULT 'ANY'"
        )
        logger.info("Migration applied: sys_strategies.required_regime added.")
    if "required_timeframes" not in strat_ctx_cols:
        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN required_timeframes TEXT DEFAULT '[]'"
        )
        logger.info("Migration applied: sys_strategies.required_timeframes added.")
    if "execution_params" not in strat_ctx_cols:
        cursor.execute(
            "ALTER TABLE sys_strategies ADD COLUMN execution_params TEXT DEFAULT '{}'"
        )
        logger.info("Migration applied: sys_strategies.execution_params added.")

    # HU 7.13: Reset affinity_scores to {} for strategies with legacy developer-opinion
    # content.  affinity_scores is now exclusively an empirical output written by
    # BacktestOrchestrator._write_pair_affinity(); old values are meaningless.
    # TRACE_ID: EDGE-BKT-713-AFFINITY-REDESIGN-2026-03-24
    cursor.execute(
        """
        UPDATE sys_strategies
        SET affinity_scores = '{}'
        WHERE affinity_scores != '{}'
          AND affinity_scores IS NOT NULL
          AND json_valid(affinity_scores) = 1
          AND (
              -- Legacy format: top-level keys look like "EUR/USD" or plain symbols with float values
              -- Detect by checking if ANY value is a plain number (not an object)
              EXISTS (
                  SELECT 1 FROM json_each(affinity_scores)
                  WHERE json_type(value) IN ('real', 'integer')
              )
          )
        """
    )
    if cursor.rowcount:
        logger.info(
            "Migration applied: affinity_scores reset to {} for %d strategies "
            "(HU 7.13 — legacy developer-opinion content removed).",
            cursor.rowcount,
        )

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
    Uses DatabaseManager for connection pooling (SSOT).
    """
    from .database_manager import get_database_manager

    import os
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # Use DatabaseManager singleton to get pooled connection (NOT direct sqlite3.connect)
    db_manager = get_database_manager()
    conn = db_manager.get_connection(db_path)

    try:
        initialize_schema(conn)
        run_migrations(conn)
        seed_default_usr_preferences(conn)
        bootstrap_symbol_mappings(conn)
        conn.commit()  # Explicit commit for provisioning
        logger.info("[TENANT] DB provisioned: %s", db_path)
    except Exception as exc:
        conn.rollback()
        logger.error("[TENANT] Provisioning failed for %s: %s", db_path, exc)
        raise
    # NOTE: DO NOT close conn - DatabaseManager owns lifecycle


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
        },
        # ── Backtesting pipeline (EXEC-V5-BACKTEST-SCENARIO-ENGINE) ───────────
        "config_backtest": {
            "cooldown_hours":           24,
            "min_trades_per_cluster":   15,
            "bars_per_window":          120,
            "bars_fetch_initial":       500,
            "bars_fetch_max":           1000,
            "bars_fetch_retry":         250,
            "promotion_min_score":      0.75,
            "default_symbol":           "EURUSD",
            "default_timeframe":        "H1",
            "symbols_priority":         ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
            "score_weights": {
                "w_live":     0.50,
                "w_shadow":   0.30,
                "w_backtest": 0.20
            }
        },
        "config_backtest_clusters": {
            "HIGH_VOLATILITY": {
                "description": "Eventos de alto impacto (NFP, BCE, Fed). Movimientos rápidos y bruscos.",
                "detection_criteria": {"volatility_ratio_min": 1.5, "atr_multiplier": 3.0}
            },
            "STAGNANT_RANGE": {
                "description": "Mercado lateralizado, baja liquidez, sin dirección institucional.",
                "detection_criteria": {"volatility_ratio_max": 0.9, "trend_strength_max": 0.3}
            },
            "INSTITUTIONAL_TREND": {
                "description": "Tendencia institucional fuerte y sostenida. Momentum limpio.",
                "detection_criteria": {"trend_strength_min": 0.6, "volatility_ratio_max": 1.4}
            }
        },
        "config_backtest_timeframes": {
            "_doc": "Sizing CLT por timeframe: min 15 trades / tasa_señal_esperada por cluster.",
            "M1":  {"bars_initial": 2000, "bars_per_window": 400,  "expected_signal_rate_pct": 8},
            "M5":  {"bars_initial": 1000, "bars_per_window": 200,  "expected_signal_rate_pct": 6},
            "M15": {"bars_initial": 600,  "bars_per_window": 150,  "expected_signal_rate_pct": 5},
            "H1":  {"bars_initial": 500,  "bars_per_window": 120,  "expected_signal_rate_pct": 4},
            "H4":  {"bars_initial": 300,  "bars_per_window": 80,   "expected_signal_rate_pct": 4},
            "D1":  {"bars_initial": 200,  "bars_per_window": 50,   "expected_signal_rate_pct": 5}
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


def bootstrap_tenant_template(global_conn: sqlite3.Connection, mode: str = "manual") -> bool:
    """
    Create template DB for new tenants by copying usr_* tables from global DB.
    
    Args:
        global_conn: Connection to data_vault/global/aethelgard.db
        mode: "manual" (default) or "automatic"
            - "manual": Only run if explicitly called, flag stored in sys_config
            - "automatic": Run on every startup (for convenience, not recommended)
    
    Returns:
        True if bootstrap succeeded, False if already done
    
    Idempotent: Safe to call multiple times, will skip if template already exists.
    """
    from pathlib import Path
    import shutil
    
    template_dir = Path("data_vault/templates")
    template_path = template_dir / "usr_template.db"
    
    # Check if bootstrap is enabled in config
    mode_config_key = "tenant_template_bootstrap_mode"
    cursor = global_conn.cursor()
    cursor.execute("SELECT value FROM sys_config WHERE key = ?", (mode_config_key,))
    result = cursor.fetchone()
    
    # First time: store config
    if result is None:
        cursor.execute(
            "INSERT INTO sys_config (key, value) VALUES (?, ?)",
            (mode_config_key, mode)
        )
        global_conn.commit()
        logger.info(f"[TEMPLATE] Bootstrap mode configured: {mode}")
    else:
        mode = result[0]  # Read from config
    
    # Check if already completed (manual mode only)
    if mode == "manual":
        bootstrap_done_key = "tenant_template_bootstrap_done"
        cursor.execute("SELECT value FROM sys_config WHERE key = ?", (bootstrap_done_key,))
        if cursor.fetchone():
            logger.debug("[TEMPLATE] Bootstrap already completed (manual mode)")
            return False
    
    # Skip if template already physically exists
    if template_path.exists():
        # Mark as done if manual mode
        if mode == "manual":
            cursor.execute(
                "INSERT OR IGNORE INTO sys_config (key, value) VALUES (?, ?)",
                ("tenant_template_bootstrap_done", "1")
            )
            global_conn.commit()
        logger.info(f"[TEMPLATE] Template already exists: {template_path}")
        return False
    
    # Create template: copy usr_* tables from global to template
    try:
        logger.info("[TEMPLATE] Creating tenant template DB...")
        template_dir.mkdir(parents=True, exist_ok=True)
        
        # Create new template DB
        template_conn = sqlite3.connect(str(template_path))
        template_cursor = template_conn.cursor()
        
        # Get list of usr_* tables from global DB
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE 'usr_%'
            ORDER BY name
        """)
        usr_tables = [row[0] for row in cursor.fetchall()]
        
        if not usr_tables:
            logger.warning("[TEMPLATE] No usr_* tables found in global DB")
            template_conn.close()
            return False
        
        logger.info(f"[TEMPLATE] Copying {len(usr_tables)} usr_* tables to template...")
        
        # Copy each usr_* table schema + data from global to template
        for table_name in usr_tables:
            # GET table creation SQL
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            create_sql = cursor.fetchone()[0]
            
            # Create table in template
            template_cursor.execute(create_sql)
            
            # Copy data from global to template
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            if rows:
                placeholders = ", ".join(["?" for _ in columns])
                template_cursor.execute(
                    f"INSERT INTO {table_name} VALUES ({placeholders})",
                    rows[0]
                )
                for row in rows[1:]:
                    template_cursor.execute(
                        f"INSERT INTO {table_name} VALUES ({placeholders})",
                        row
                    )
            
            logger.debug(f"[TEMPLATE] Copied {table_name}: {len(rows)} rows")
        
        template_conn.commit()
        template_conn.close()
        
        # Mark as done in global config
        if mode == "manual":
            cursor.execute(
                "INSERT OR IGNORE INTO sys_config (key, value) VALUES (?, ?)",
                ("tenant_template_bootstrap_done", "1")
            )
        
        global_conn.commit()
        logger.info(f"[TEMPLATE] Bootstrap successful: {template_path} ({len(usr_tables)} tables)")
        return True
        
    except Exception as e:
        logger.error(f"[TEMPLATE] Bootstrap failed: {e}", exc_info=True)
        return False
