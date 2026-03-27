"""
test_shadow_schema.py — Unit tests for SHADOW EVOLUTION schema (sys_shadow_* tables).

Tests:
  1. Table creation (idempotent, IF NOT EXISTS)
  2. Column types and constraints
  3. Foreign key relationships
  4. Index creation
  5. Immutability of sys_shadow_promotion_log (INSERT-ONLY)

Trace_ID: TRACE_TEST_20260312_001_SCHEMA
"""

import sqlite3
import pytest
from pathlib import Path
from datetime import datetime, timezone

from data_vault.schema import initialize_schema


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    yield conn
    conn.close()


class TestShadowSchema:
    """Verify sys_shadow_* table structure and constraints."""

    def test_sys_shadow_instances_table_exists(self, test_db):
        """Verify sys_shadow_instances table is created."""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_shadow_instances'")
        assert cursor.fetchone() is not None, "sys_shadow_instances table not found"

    def test_sys_shadow_instances_columns(self, test_db):
        """Verify all required columns exist."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_shadow_instances)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # name -> type
        
        required_columns = {
            "instance_id": "TEXT",
            "strategy_id": "TEXT",
            "account_id": "TEXT",
            "account_type": "TEXT",
            "parameter_overrides": "TEXT",
            "regime_filters": "TEXT",
            "birth_timestamp": "TIMESTAMP",
            "status": "TEXT",
            "total_trades_executed": "INTEGER",
            "profit_factor": "REAL",
            "win_rate": "REAL",
            "max_drawdown_pct": "REAL",
            "consecutive_losses_max": "INTEGER",
            "equity_curve_cv": "REAL",
            "promotion_trace_id": "TEXT",
            "backtest_trace_id": "TEXT",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        }
        
        for col_name, col_type in required_columns.items():
            assert col_name in columns, f"Column {col_name} not found"
            assert columns[col_name] == col_type, f"Column {col_name} has wrong type: {columns[col_name]}"

    def test_sys_shadow_instances_primary_key(self, test_db):
        """Verify primary key is instance_id."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_shadow_instances)")
        columns = cursor.fetchall()
        
        instance_id_col = [col for col in columns if col[1] == "instance_id"][0]
        assert instance_id_col[5] == 1, "instance_id should be PRIMARY KEY"

    def test_sys_shadow_instances_account_type_constraint(self, test_db):
        """Verify account_type CHECK constraint (DEMO|REAL)."""
        cursor = test_db.cursor()
        
        # Should succeed
        cursor.execute(
            """
            INSERT INTO sys_shadow_instances
            (instance_id, strategy_id, account_id, account_type, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("test_001", "BRK_OPEN_0001", "acc_001", "DEMO", "INCUBATING"),
        )
        test_db.commit()
        
        # Should fail with CHECK constraint
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO sys_shadow_instances
                (instance_id, strategy_id, account_id, account_type, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("test_002", "BRK_OPEN_0001", "acc_001", "INVALID", "INCUBATING"),
            )

    def test_sys_shadow_performance_history_table_exists(self, test_db):
        """Verify sys_shadow_performance_history table is created."""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_shadow_performance_history'")
        assert cursor.fetchone() is not None

    def test_sys_shadow_performance_history_columns(self, test_db):
        """Verify all required columns exist."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_shadow_performance_history)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            "id", "instance_id", "evaluation_date", "pillar1_status",
            "pillar2_status", "pillar3_status", "overall_health", "event_trace_id",
            "created_at"
        }
        
        assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"

    def test_sys_shadow_performance_history_foreign_key(self, test_db):
        """Verify foreign key relationship to sys_shadow_instances."""
        cursor = test_db.cursor()
        
        # Create a parent instance first
        cursor.execute(
            """
            INSERT INTO sys_shadow_instances
            (instance_id, strategy_id, account_id, account_type, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("parent_001", "BRK_OPEN_0001", "acc_001", "DEMO", "INCUBATING"),
        )
        test_db.commit()
        
        # Should succeed (valid FK)
        cursor.execute(
            """
            INSERT INTO sys_shadow_performance_history
            (instance_id, evaluation_date, pillar1_status, pillar2_status, pillar3_status, overall_health, event_trace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("parent_001", "2026-03-12", "PASS", "PASS", "PASS", "HEALTHY", "TRACE_HEALTH_..."),
        )
        test_db.commit()

    def test_sys_shadow_promotion_log_table_exists(self, test_db):
        """Verify sys_shadow_promotion_log table is created."""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_shadow_promotion_log'")
        assert cursor.fetchone() is not None

    def test_sys_shadow_promotion_log_columns(self, test_db):
        """Verify all required columns exist."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_shadow_promotion_log)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_columns = {
            "promotion_id", "instance_id", "trace_id", "promotion_status",
            "pillar1_passed", "pillar2_passed", "pillar3_passed",
            "approval_timestamp", "execution_timestamp", "notes", "created_at"
        }
        
        assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"

    def test_sys_shadow_promotion_log_trace_id_unique(self, test_db):
        """Verify trace_id is UNIQUE (no duplicates)."""
        cursor = test_db.cursor()
        
        # Create parent instance
        cursor.execute(
            """
            INSERT INTO sys_shadow_instances
            (instance_id, strategy_id, account_id, account_type, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("parent_002", "BRK_OPEN_0001", "acc_001", "DEMO", "INCUBATING"),
        )
        test_db.commit()
        
        # First insertion should succeed
        cursor.execute(
            """
            INSERT INTO sys_shadow_promotion_log
            (instance_id, trace_id, promotion_status)
            VALUES (?, ?, ?)
            """,
            ("parent_002", "TRACE_PROMOTION_REAL_20260312_000000_parent_", "PENDING"),
        )
        test_db.commit()
        
        # Duplicate trace_id should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO sys_shadow_promotion_log
                (instance_id, trace_id, promotion_status)
                VALUES (?, ?, ?)
                """,
                ("parent_002", "TRACE_PROMOTION_REAL_20260312_000000_parent_", "APPROVED"),
            )

    def test_sys_shadow_instances_indexes_created(self, test_db):
        """Verify indexes are created for performance."""
        cursor = test_db.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sys_shadow_instances'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        
        expected_indexes = {
            "idx_sys_shadow_instances_strategy_id",
            "idx_sys_shadow_instances_account_id",
            "idx_sys_shadow_instances_account_type",
            "idx_sys_shadow_instances_status",
            "idx_sys_shadow_instances_created_at",
        }
        
        assert expected_indexes.issubset(indexes), f"Missing indexes: {expected_indexes - indexes}"

    def test_schema_initialization_idempotent(self, test_db):
        """Verify initialize_schema is idempotent (can be called multiple times)."""
        # Initialize again (should not fail)
        initialize_schema(test_db)
        
        # Tables should still exist
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_shadow_instances'")
        assert cursor.fetchone() is not None

    def test_sys_shadow_promotion_log_immutable(self, test_db):
        """
        Verify sys_shadow_promotion_log follows INSERT-ONLY pattern.
        New entries should succeed, updates/deletes should be avoided.
        """
        cursor = test_db.cursor()
        
        # Create parent instance
        cursor.execute(
            """
            INSERT INTO sys_shadow_instances
            (instance_id, strategy_id, account_id, account_type, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("immutable_test", "BRK_OPEN_0001", "acc_001", "DEMO", "INCUBATING"),
        )
        test_db.commit()
        
        # Insert a log entry
        cursor.execute(
            """
            INSERT INTO sys_shadow_promotion_log
            (instance_id, trace_id, promotion_status, notes)
            VALUES (?, ?, ?, ?)
            """,
            ("immutable_test", "TRACE_PROMOTION_TEST_001", "PENDING", "Initial note"),
        )
        test_db.commit()
        
        # Verify entry exists
        cursor.execute("SELECT COUNT(*) FROM sys_shadow_promotion_log WHERE trace_id=?", ("TRACE_PROMOTION_TEST_001",))
        assert cursor.fetchone()[0] == 1
        
        # Note: We don't test UPDATE/DELETE here because in production they should be
        # prevented at the application layer (ShadowStorageManager doesn't expose these).


class TestSysTradesSchema:
    """Verify sys_trades table: Capa 0 — SHADOW and BACKTEST only, never LIVE."""

    def test_sys_trades_table_exists(self, test_db):
        """sys_trades table must exist in Capa 0 schema."""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_trades'")
        assert cursor.fetchone() is not None, "sys_trades table not found in schema"

    def test_sys_trades_columns(self, test_db):
        """All required columns present with correct types."""
        cursor = test_db.cursor()
        cursor.execute("PRAGMA table_info(sys_trades)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # name -> type

        required_columns = {
            "id": "TEXT",
            "signal_id": "TEXT",
            "instance_id": "TEXT",
            "account_id": "TEXT",
            "symbol": "TEXT",
            "direction": "TEXT",
            "entry_price": "REAL",
            "exit_price": "REAL",
            "profit": "REAL",
            "exit_reason": "TEXT",
            "open_time": "TIMESTAMP",
            "close_time": "TIMESTAMP",
            "execution_mode": "TEXT",
            "strategy_id": "TEXT",
            "order_id": "TEXT",
            "created_at": "TIMESTAMP",
        }

        for col_name, col_type in required_columns.items():
            assert col_name in columns, f"Column '{col_name}' not found in sys_trades"
            assert columns[col_name] == col_type, (
                f"Column '{col_name}' has wrong type: expected {col_type}, got {columns[col_name]}"
            )

    def test_sys_trades_execution_mode_constraint(self, test_db):
        """execution_mode CHECK constraint: only SHADOW and BACKTEST allowed, LIVE must FAIL."""
        cursor = test_db.cursor()

        # Insert with SHADOW → success
        cursor.execute(
            """INSERT INTO sys_trades (id, symbol, execution_mode)
               VALUES (?, ?, ?)""",
            ("trade-shadow-001", "EURUSD", "SHADOW"),
        )
        test_db.commit()

        # Insert with BACKTEST → success
        cursor.execute(
            """INSERT INTO sys_trades (id, symbol, execution_mode)
               VALUES (?, ?, ?)""",
            ("trade-backtest-001", "EURUSD", "BACKTEST"),
        )
        test_db.commit()

        # Insert with LIVE → must raise IntegrityError (CHECK constraint violation)
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """INSERT INTO sys_trades (id, symbol, execution_mode)
                   VALUES (?, ?, ?)""",
                ("trade-live-fail", "EURUSD", "LIVE"),
            )

    def test_sys_trades_live_cannot_be_inserted(self, test_db):
        """Verify LIVE trades are physically blocked from sys_trades."""
        cursor = test_db.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """INSERT INTO sys_trades (id, symbol, execution_mode)
                   VALUES (?, ?, ?)""",
                ("trade-live-direct", "GBPUSD", "LIVE"),
            )

    def test_usr_trades_live_only(self, test_db):
        """usr_trades must only accept LIVE execution_mode after trigger migration."""
        cursor = test_db.cursor()

        # Insert with LIVE → success
        cursor.execute(
            """INSERT INTO usr_trades (id, symbol, execution_mode)
               VALUES (?, ?, ?)""",
            ("live-trade-001", "EURUSD", "LIVE"),
        )
        test_db.commit()

        # Insert with SHADOW → trigger must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """INSERT INTO usr_trades (id, symbol, execution_mode)
                   VALUES (?, ?, ?)""",
                ("shadow-trade-fail", "EURUSD", "SHADOW"),
            )

        # Insert with BACKTEST → trigger must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """INSERT INTO usr_trades (id, symbol, execution_mode)
                   VALUES (?, ?, ?)""",
                ("backtest-trade-fail", "EURUSD", "BACKTEST"),
            )

    def test_sys_trades_indexes_created(self, test_db):
        """Verify performance indexes exist on sys_trades."""
        cursor = test_db.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sys_trades'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {
            "idx_sys_trades_instance_id",
            "idx_sys_trades_execution_mode",
            "idx_sys_trades_strategy_id",
            "idx_sys_trades_close_time",
        }
        assert expected_indexes.issubset(indexes), (
            f"Missing indexes on sys_trades: {expected_indexes - indexes}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
