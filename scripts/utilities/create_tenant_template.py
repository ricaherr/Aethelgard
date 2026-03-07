#!/usr/bin/env python3
"""
create_tenant_template.py — Generate clean tenant database template

TRACE_ID: EXEC-SSOT-IMPLEMENT-2026-007 (Phase 2: Provisioning)

This script creates a clean SQLite template database containing ONLY usr_* tables
(Capa 1: tenant-isolated tables). This template is cloned when a new tenant is provisioned.

Template location: data_vault/templates/usr_template.db

The global database (sys_* tables) is managed separately in data_vault/global/aethelgard.db
and is NOT included in this template.
"""

import sqlite3
import os
from pathlib import Path

# Minimal DDL for tenant tables (usr_* only)
TENANT_SCHEMA_DDL = """
-- Capa 1: Tenant-Isolated Tables (usr_*)
-- These tables reside in data_vault/tenants/{tenant_id}/aethelgard.db

-- User Asset Configuration
CREATE TABLE IF NOT EXISTS usr_assets_cfg (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL UNIQUE,
    asset_class TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    active BOOLEAN DEFAULT 1,
    timeframe TEXT NOT NULL,
    min_qty REAL DEFAULT 0.01,
    max_qty REAL DEFAULT 100.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usr_assets_cfg_asset ON usr_assets_cfg (asset);
CREATE INDEX IF NOT EXISTS idx_usr_assets_cfg_enabled_active ON usr_assets_cfg (enabled, active);

-- User Strategies
CREATE TABLE IF NOT EXISTS usr_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL UNIQUE,
    description TEXT,
    file_path TEXT NOT NULL,
    signal_types TEXT NOT NULL,
    assets TEXT NOT NULL,
    execution_mode TEXT DEFAULT 'LIVE',
    status TEXT DEFAULT 'DISABLED',
    enabled_for_live_trading BOOLEAN DEFAULT 0,
    affinity_score REAL DEFAULT 0.5,
    min_win_rate REAL DEFAULT 0.50,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usr_strategies_strategy_name ON usr_strategies (strategy_name);
CREATE INDEX IF NOT EXISTS idx_usr_strategies_status ON usr_strategies (status);

-- User Signals (Tenant-Isolated)
CREATE TABLE IF NOT EXISTS usr_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    strategy_id INTEGER,
    confidence REAL DEFAULT 0.5,
    status TEXT DEFAULT 'PENDING',
    validation_result TEXT,
    execution_id INTEGER,
    generated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    trace_id TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_usr_signals_asset_timeframe ON usr_signals (asset, timeframe);
CREATE INDEX IF NOT EXISTS idx_usr_signals_status ON usr_signals (status);
CREATE INDEX IF NOT EXISTS idx_usr_signals_trace_id ON usr_signals (trace_id);

-- User Trades (Soberanía Total del Tenant)
CREATE TABLE IF NOT EXISTS usr_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    direction TEXT NOT NULL,
    pnl_pips REAL,
    pnl_money REAL,
    status TEXT DEFAULT 'OPEN',
    execution_mode TEXT DEFAULT 'LIVE',
    provider TEXT DEFAULT 'MT5',
    account_type TEXT DEFAULT 'REAL',
    commission REAL DEFAULT 0.0,
    slippage_pips REAL DEFAULT 0.0,
    entry_at TIMESTAMP NOT NULL,
    exit_at TIMESTAMP,
    trace_id TEXT NOT NULL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_usr_trades_asset_status ON usr_trades (asset, status);
CREATE INDEX IF NOT EXISTS idx_usr_trades_entry_at ON usr_trades (entry_at);
CREATE INDEX IF NOT EXISTS idx_usr_trades_execution_mode ON usr_trades (execution_mode);

-- User Performance (Strategy Ranking)
CREATE TABLE IF NOT EXISTS usr_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    trades_count INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    sharpe_ratio REAL DEFAULT 0.0,
    max_drawdown_pct REAL DEFAULT 0.0,
    cumulative_pnl REAL DEFAULT 0.0,
    avg_pnl_per_trade REAL DEFAULT 0.0,
    ranking_score REAL DEFAULT 0.0,
    ranking_date TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usr_performance_strategy_id ON usr_performance (strategy_id);
CREATE INDEX IF NOT EXISTS idx_usr_performance_asset ON usr_performance (asset);
CREATE INDEX IF NOT EXISTS idx_usr_performance_win_rate ON usr_performance (win_rate DESC);
CREATE INDEX IF NOT EXISTS idx_usr_performance_sharpe ON usr_performance (sharpe_ratio DESC);

-- Position History (Tenant-Isolated)
CREATE TABLE IF NOT EXISTS position_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    asset TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    floating_pnl REAL NOT NULL,
    realized_pnl REAL DEFAULT 0.0,
    direction TEXT NOT NULL,
    status TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usr_position_history_asset_status ON position_history (asset, status);
CREATE INDEX IF NOT EXISTS idx_usr_position_history_snapshot_at ON position_history (snapshot_at);

-- Coherence Events (Tenant-Isolated)
CREATE TABLE IF NOT EXISTS coherence_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    coherence_score REAL NOT NULL,
    conflicting_signals TEXT NOT NULL,
    resolution_method TEXT NOT NULL,
    final_action TEXT NOT NULL,
    reasons TEXT,
    event_at TIMESTAMP NOT NULL,
    trace_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coherence_events_signal_id ON coherence_events (signal_id);
CREATE INDEX IF NOT EXISTS idx_coherence_events_trace_id ON coherence_events (trace_id);

-- Anomaly Events (Tenant-Isolated)
CREATE TABLE IF NOT EXISTS anomaly_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_type TEXT NOT NULL,
    asset TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    metrics TEXT,
    action_taken TEXT,
    event_at TIMESTAMP NOT NULL,
    trace_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomaly_events_asset_severity ON anomaly_events (asset, severity);
CREATE INDEX IF NOT EXISTS idx_anomaly_events_event_at ON anomaly_events (event_at);
"""


def create_template() -> str:
    """
    Create a clean tenant database template with usr_* tables only.
    
    Returns: Path to the created template file
    """
    script_dir = Path(__file__).parent
    template_dir = script_dir.parent.parent / "data_vault" / "templates"
    template_path = template_dir / "usr_template.db"
    
    # Create template directory if it doesn't exist
    template_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove existing template if present
    if template_path.exists():
        template_path.unlink()
        print(f"🗑️  Removed existing template: {template_path}")
    
    # Create new template
    conn = sqlite3.connect(str(template_path))
    cursor = conn.cursor()
    
    try:
        # Execute DDL to create tables
        cursor.executescript(TENANT_SCHEMA_DDL)
        conn.commit()
        print(f"✅ Template created successfully: {template_path}")
        
        # Verify tables were created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE 'usr_%'
            ORDER BY name
        """)
        tables = cursor.fetchall()
        print(f"   Tables created: {len(tables)}")
        for table in tables:
            print(f"     - {table[0]}")
        
        return str(template_path)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        path = create_template()
        print(f"\n✅ SUCCESS: Tenant template is ready at: {path}")
        print(f"   This template will be cloned for each new tenant via StorageManager")
    except Exception as e:
        print(f"❌ ERROR: Failed to create template: {e}")
        exit(1)
