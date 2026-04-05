"""
TDD: Strategy registry metadata repair migration.

Validates that run_migrations() can recover missing class_file/class_name metadata
for strategy records that were inserted with partial fields.
"""

import sqlite3

from data_vault.schema import initialize_schema, run_migrations


def _get_sys_strategy_cols(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(sys_strategies)")
    return {row[1] for row in cursor.fetchall()}


def test_run_migrations_adds_strategy_metadata_columns() -> None:
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)

    run_migrations(conn)

    cols = _get_sys_strategy_cols(conn)
    assert "class_file" in cols
    assert "class_name" in cols
    assert "schema_file" in cols


def test_run_migrations_repairs_missing_python_class_mapping_from_seed() -> None:
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)
    run_migrations(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO sys_strategies (
            class_id, mnemonic, type, readiness, class_file, class_name
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("MOM_BIAS_0001", "MOM_BIAS_MOMENTUM_STRIKE", "PYTHON_CLASS", "READY_FOR_ENGINE", None, ""),
    )
    conn.commit()

    run_migrations(conn)

    cursor.execute(
        "SELECT class_file, class_name FROM sys_strategies WHERE class_id = ?",
        ("MOM_BIAS_0001",),
    )
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == "core_brain/strategies/mom_bias_0001.py"
    assert row[1] == "MomentumBias0001Strategy"
