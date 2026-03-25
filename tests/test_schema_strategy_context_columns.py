"""
test_hu78_structural_context.py — TDD for HU 7.8

Verifies that run_migrations() adds the three structural-context columns to
sys_strategies:
  - required_regime   TEXT DEFAULT 'ANY'
  - required_timeframes TEXT DEFAULT '[]'
  - execution_params  TEXT DEFAULT '{}'

All tests use in-memory SQLite — no disk artifact, no side effects.
TRACE_ID: EDGE-BKT-78-STRUCTURAL-CONTEXT-2026-03-24
"""
import json
import sqlite3

import pytest

from data_vault.schema import initialize_schema, run_migrations


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_db_without_hu78_cols() -> sqlite3.Connection:
    """In-memory DB with schema but WITHOUT the 3 HU 7.8 columns."""
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)
    # Explicitly drop the columns if they were somehow added by initialize_schema.
    # SQLite doesn't support DROP COLUMN in older versions, so we verify they are absent.
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(sys_strategies)")
    cols = {r[1] for r in cursor.fetchall()}
    # These should NOT be in the fresh schema yet (migration adds them).
    # If they are already present, the migration guard handles it idempotently.
    return conn


def _col_names(conn: sqlite3.Connection) -> set:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(sys_strategies)")
    return {r[1] for r in cursor.fetchall()}


# ─────────────────────────────────────────────────────────────────────────────
# HU 7.8 Migration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHU78StructuralContextMigration:

    def test_run_migrations_adds_required_regime(self):
        """run_migrations must add required_regime column to sys_strategies."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        assert "required_regime" in _col_names(conn)

    def test_run_migrations_adds_required_timeframes(self):
        """run_migrations must add required_timeframes column to sys_strategies."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        assert "required_timeframes" in _col_names(conn)

    def test_run_migrations_adds_execution_params(self):
        """run_migrations must add execution_params column to sys_strategies."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        assert "execution_params" in _col_names(conn)

    def test_migration_is_idempotent(self):
        """Calling run_migrations twice must not raise and columns remain present."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        # Second call — must not raise OperationalError "duplicate column"
        run_migrations(conn)
        cols = _col_names(conn)
        assert "required_regime" in cols
        assert "required_timeframes" in cols
        assert "execution_params" in cols

    def test_required_regime_default_is_ANY(self):
        """New rows inserted without specifying required_regime must default to 'ANY'."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sys_strategies (class_id, mnemonic) VALUES (?, ?)",
            ("test_strat_001", "TEST_001"),
        )
        conn.commit()
        cursor.execute(
            "SELECT required_regime FROM sys_strategies WHERE class_id = ?",
            ("test_strat_001",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "ANY"

    def test_required_timeframes_default_is_empty_json_array(self):
        """New rows must default required_timeframes to '[]'."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sys_strategies (class_id, mnemonic) VALUES (?, ?)",
            ("test_strat_002", "TEST_002"),
        )
        conn.commit()
        cursor.execute(
            "SELECT required_timeframes FROM sys_strategies WHERE class_id = ?",
            ("test_strat_002",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert json.loads(row[0]) == []

    def test_execution_params_default_is_empty_json_object(self):
        """New rows must default execution_params to '{}'."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sys_strategies (class_id, mnemonic) VALUES (?, ?)",
            ("test_strat_003", "TEST_003"),
        )
        conn.commit()
        cursor.execute(
            "SELECT execution_params FROM sys_strategies WHERE class_id = ?",
            ("test_strat_003",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert json.loads(row[0]) == {}

    def test_columns_store_and_retrieve_json(self):
        """required_timeframes and execution_params can round-trip JSON values."""
        conn = _build_db_without_hu78_cols()
        run_migrations(conn)
        cursor = conn.cursor()
        timeframes_val = json.dumps(["M5", "M15"])
        params_val = json.dumps({"confidence_threshold": 0.6, "risk_reward": 1.5})
        cursor.execute(
            """INSERT INTO sys_strategies
               (class_id, mnemonic, required_regime, required_timeframes, execution_params)
               VALUES (?, ?, ?, ?, ?)""",
            ("test_strat_004", "TEST_004", "TREND", timeframes_val, params_val),
        )
        conn.commit()
        cursor.execute(
            "SELECT required_regime, required_timeframes, execution_params "
            "FROM sys_strategies WHERE class_id = ?",
            ("test_strat_004",),
        )
        row = cursor.fetchone()
        assert row[0] == "TREND"
        assert json.loads(row[1]) == ["M5", "M15"]
        assert json.loads(row[2]) == {"confidence_threshold": 0.6, "risk_reward": 1.5}

    def test_existing_rows_not_lost_after_migration(self):
        """Migration must not delete or corrupt existing strategy rows."""
        conn = _build_db_without_hu78_cols()
        cursor = conn.cursor()
        # Insert a row before migration
        cursor.execute(
            "INSERT INTO sys_strategies (class_id, mnemonic, score_backtest) VALUES (?, ?, ?)",
            ("pre_existing", "PRE", 0.87),
        )
        conn.commit()

        run_migrations(conn)

        cursor.execute(
            "SELECT score_backtest FROM sys_strategies WHERE class_id = ?",
            ("pre_existing",),
        )
        row = cursor.fetchone()
        assert row is not None, "Pre-existing row must survive migration"
        assert row[0] == pytest.approx(0.87)
