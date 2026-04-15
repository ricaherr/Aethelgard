"""
schema_seeds.py — Default seed data and symbol mapping bootstrap.

Responsibility: Populate initial rows in sys_regime_configs, sys_config,
usr_notification_settings, usr_preferences, and symbol_mappings tables.
These are internal helpers called by initialize_schema() and storage.py.

Rules:
- NO DDL (no CREATE TABLE).
- NO imports from connectors, core_brain, or models.
"""
import json
import logging
import os

import sqlite3

from .default_instruments import DEFAULT_INSTRUMENTS_CONFIG

logger = logging.getLogger(__name__)


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


