"""
schema_migrations.py — Incremental ALTER TABLE migrations for Aethelgard.

Responsibility: Apply idempotent ALTER TABLE changes to evolve the schema
across versions. Each migration checks column existence before altering.

Rules:
- NO DDL for new tables (use schema_ddl.py for that).
- NO imports from connectors, core_brain, or models.
"""
import json
import logging
import sqlite3
from pathlib import Path

from .default_instruments import DEFAULT_INSTRUMENTS_CONFIG

logger = logging.getLogger(__name__)

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

    # MIGRATION (DISC-001): Add review_status, trader_review_reason, review_timeout_at for B/C grade signal review queue
    # ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
    # Enables trader approval workflow for B/C-grade signals (moderate confidence)
    # TRACE_ID: DISC-SQ-001-2026-04-04
    cursor.execute("PRAGMA table_info(sys_signals)")
    sys_signals_cols = [r[1] for r in cursor.fetchall()]
    review_migrations = [
        ("review_status", "TEXT DEFAULT 'NONE' CHECK(review_status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED', 'AUTO_EXECUTED'))"),
        ("trader_review_reason", "TEXT"),
        ("review_timeout_at", "TEXT"),
    ]
    for col, col_type in review_migrations:
        if col not in sys_signals_cols:
            cursor.execute(f"ALTER TABLE sys_signals ADD COLUMN {col} {col_type}")
            logger.info(f"Migration applied: sys_signals.{col} added for signal review queue (DISC-001)")
    
    # Create index for efficient filtering of pending reviews
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_signals_review_status ON sys_signals(review_status) WHERE review_status='PENDING'")
    logger.info("Index created: idx_sys_signals_review_status for signal review queue optimization")

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
    strategy_registry_cols = [
        ("class_file", "TEXT DEFAULT NULL"),
        ("class_name", "TEXT DEFAULT NULL"),
        ("schema_file", "TEXT DEFAULT NULL"),
    ]
    for col, col_def in strategy_registry_cols:
        if col not in strat_cols:
            cursor.execute(f"ALTER TABLE sys_strategies ADD COLUMN {col} {col_def}")
            logger.info(f"Migration applied: sys_strategies.{col} added.")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_strategies_readiness ON sys_strategies (readiness)")

    # Repair partial strategy records from seed registry when metadata fields are missing.
    # This unblocks StrategyEngineFactory instantiation without overriding non-empty values.
    strategy_seed_path = Path("data_vault") / "seed" / "strategy_registry.json"
    if strategy_seed_path.exists():
        try:
            with strategy_seed_path.open("r", encoding="utf-8") as seed_file:
                registry_data = json.load(seed_file)
            strategy_seed = registry_data.get("strategies", [])
            repaired_rows = 0
            for entry in strategy_seed:
                class_id = entry.get("strategy_id")
                if not class_id:
                    continue
                cursor.execute(
                    """
                    UPDATE sys_strategies
                    SET
                        type = CASE
                            WHEN type IS NULL OR TRIM(type) = '' THEN ?
                            ELSE type
                        END,
                        readiness = CASE
                            WHEN readiness IS NULL OR TRIM(readiness) = '' THEN ?
                            ELSE readiness
                        END,
                        readiness_notes = CASE
                            WHEN (readiness_notes IS NULL OR TRIM(readiness_notes) = '') AND ? IS NOT NULL THEN ?
                            ELSE readiness_notes
                        END,
                        class_file = CASE
                            WHEN class_file IS NULL OR TRIM(class_file) = '' THEN ?
                            ELSE class_file
                        END,
                        class_name = CASE
                            WHEN class_name IS NULL OR TRIM(class_name) = '' THEN ?
                            ELSE class_name
                        END,
                        schema_file = CASE
                            WHEN schema_file IS NULL OR TRIM(schema_file) = '' THEN ?
                            ELSE schema_file
                        END
                    WHERE class_id = ?
                      AND (
                          type IS NULL OR TRIM(type) = ''
                          OR readiness IS NULL OR TRIM(readiness) = ''
                          OR class_file IS NULL OR TRIM(class_file) = ''
                          OR class_name IS NULL OR TRIM(class_name) = ''
                          OR schema_file IS NULL OR TRIM(schema_file) = ''
                      )
                    """,
                    (
                        entry.get("type", "PYTHON_CLASS"),
                        entry.get("readiness", "UNKNOWN"),
                        entry.get("readiness_notes"),
                        entry.get("readiness_notes"),
                        entry.get("class_file"),
                        entry.get("class_name"),
                        entry.get("schema_file"),
                        class_id,
                    ),
                )
                repaired_rows += cursor.rowcount
            if repaired_rows:
                logger.info(
                    "Migration applied: sys_strategies metadata repaired from seed for %d row(s).",
                    repaired_rows,
                )
        except Exception as repair_error:
            logger.warning(
                "Migration warning: could not repair sys_strategies metadata from seed (%s)",
                repair_error,
            )

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

    # MIGRATION (HU-8.8-SSOT-EXECMODE-DRIFT-FIX): Reconcile sys_signal_ranking.execution_mode
    # with sys_strategies.mode when they diverge.
    # Root cause: lazy initialization copied mode once; later changes to sys_strategies.mode
    # were never propagated, leaving sys_signal_ranking with stale BACKTEST values.
    # This migration realigns derived rows with the SSOT (sys_strategies).
    # Idempotent: only updates rows where a mismatch exists. Rows already in sync are untouched.
    # TRACE_ID: SSOT-EXECMODE-DRIFT-FIX-2026-04-09
    try:
        cursor.execute("""
            UPDATE sys_signal_ranking
            SET execution_mode = (
                SELECT mode FROM sys_strategies
                WHERE class_id = sys_signal_ranking.strategy_id
            )
            WHERE EXISTS (
                SELECT 1 FROM sys_strategies
                WHERE class_id = sys_signal_ranking.strategy_id
                  AND mode != sys_signal_ranking.execution_mode
            )
        """)
        reconciled = cursor.rowcount
        if reconciled:
            logger.info(
                "Migration applied: sys_signal_ranking.execution_mode reconciled for "
                "%d row(s) (HU-8.8 SSOT drift fix).",
                reconciled,
            )
        else:
            logger.debug(
                "Migration HU-8.8: no divergent rows found in sys_signal_ranking — "
                "no update needed."
            )
    except Exception as reconcile_err:
        logger.warning(
            "Migration HU-8.8 reconciliation failed (non-blocking): %s",
            reconcile_err,
        )

    conn.commit()
    logger.debug("Migrations completed.")


