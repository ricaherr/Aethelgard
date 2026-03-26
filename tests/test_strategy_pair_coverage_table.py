"""
Tests for HU 7.17 — Tabla sys_strategy_pair_coverage
Trace_ID: EDGE-BKT-717-COVERAGE-TABLE-2026-03-24

Acceptance criteria:
  AC1: Migration idempotente — llamar run_migrations() N veces no falla ni duplica la tabla
  AC2: BacktestOrchestrator escribe en esta tabla al completar cada evaluación de par
  AC3: Tests de migration verifican idempotencia
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_db() -> sqlite3.Connection:
    """In-memory DB with full schema (initialize + migrations)."""
    from data_vault.schema import initialize_schema, run_migrations
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    run_migrations(conn)
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


def _get_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [r[1] for r in rows]


def _make_ohlc_df(n: int = 50) -> pd.DataFrame:
    close = [1.1000 + 0.0001 * i for i in range(n)]
    return pd.DataFrame({
        "open":   close,
        "high":   [c + 0.0005 for c in close],
        "low":    [c - 0.0005 for c in close],
        "close":  close,
        "volume": [1000] * n,
    })


def _make_strategy(
    strategy_id: str = "strat_coverage_test",
    symbols: Optional[List[str]] = None,
) -> Dict:
    if symbols is None:
        symbols = ["EURUSD"]
    return {
        "class_id":         strategy_id,
        "name":             "Coverage Table Test",
        "mode":             "BACKTEST",
        "required_regime":  "ANY",
        "market_whitelist": json.dumps(symbols),
        "timeframes":       json.dumps(["M15"]),
        "affinity_scores":  "{}",
        "execution_params": json.dumps({"confidence_k": 20}),
        "updated_at":       "2026-01-01T00:00:00",
        "last_backtest_at": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# AC1 + AC3: Migration idempotente
# ──────────────────────────────────────────────────────────────────────────────

class TestCoverageTableMigration:
    """AC1 + AC3: La tabla se crea de forma idempotente."""

    def test_table_created_after_initialize_schema(self):
        """sys_strategy_pair_coverage debe existir tras initialize_schema()."""
        from data_vault.schema import initialize_schema
        conn = sqlite3.connect(":memory:")
        initialize_schema(conn)
        assert _table_exists(conn, "sys_strategy_pair_coverage")

    def test_table_has_required_columns(self):
        """Todos los campos del DDL spec deben estar presentes."""
        conn = _build_db()
        cols = _get_columns(conn, "sys_strategy_pair_coverage")
        required = [
            "id", "strategy_id", "symbol", "timeframe", "regime",
            "n_cycles", "n_trades_total", "effective_score", "status",
            "last_evaluated_at", "created_at",
        ]
        for col in required:
            assert col in cols, f"Column '{col}' missing from sys_strategy_pair_coverage"

    def test_unique_constraint_on_strategy_symbol_timeframe_regime(self):
        """UNIQUE(strategy_id, symbol, timeframe, regime) debe existir."""
        conn = _build_db()
        # Insert first row
        conn.execute("""
            INSERT INTO sys_strategy_pair_coverage
                (strategy_id, symbol, timeframe, regime, n_cycles, effective_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("strat_a", "EURUSD", "M15", "TREND", 1, 0.65, "QUALIFIED"))
        conn.commit()
        # Insert duplicate → must raise
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO sys_strategy_pair_coverage
                    (strategy_id, symbol, timeframe, regime, n_cycles, effective_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("strat_a", "EURUSD", "M15", "TREND", 2, 0.70, "QUALIFIED"))
            conn.commit()

    def test_migration_idempotent_single_call(self):
        """run_migrations() no falla si la tabla ya existe (idempotencia)."""
        from data_vault.schema import initialize_schema, run_migrations
        conn = sqlite3.connect(":memory:")
        initialize_schema(conn)
        # Should not raise
        run_migrations(conn)
        assert _table_exists(conn, "sys_strategy_pair_coverage")

    def test_migration_idempotent_multiple_calls(self):
        """Llamar run_migrations() tres veces no duplica la tabla ni falla."""
        from data_vault.schema import initialize_schema, run_migrations
        conn = sqlite3.connect(":memory:")
        initialize_schema(conn)
        for _ in range(3):
            run_migrations(conn)
        # Only one table with that name
        rows = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sys_strategy_pair_coverage'"
        ).fetchone()
        assert rows[0] == 1

    def test_default_values_correct(self):
        """Los valores DEFAULT del DDL deben aplicarse correctamente."""
        conn = _build_db()
        conn.execute("""
            INSERT INTO sys_strategy_pair_coverage (strategy_id, symbol, timeframe, regime)
            VALUES (?, ?, ?, ?)
        """, ("strat_defaults", "GBPUSD", "H1", "RANGE"))
        conn.commit()
        row = conn.execute(
            "SELECT n_cycles, n_trades_total, effective_score, status "
            "FROM sys_strategy_pair_coverage WHERE strategy_id=?",
            ("strat_defaults",)
        ).fetchone()
        assert row["n_cycles"] == 0
        assert row["n_trades_total"] == 0
        assert row["effective_score"] == 0.0
        assert row["status"] == "PENDING"


# ──────────────────────────────────────────────────────────────────────────────
# AC2: BacktestOrchestrator escribe en la tabla
# ──────────────────────────────────────────────────────────────────────────────

class TestCoverageTableWrittenByOrchestrator:
    """AC2: BacktestOrchestrator debe escribir en sys_strategy_pair_coverage."""

    def _make_orchestrator_with_db(self, conn: sqlite3.Connection, detected_regime: str = "TREND"):
        """Create a BacktestOrchestrator whose storage._get_conn() returns our in-memory DB."""
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        import threading

        storage = MagicMock()
        storage._get_conn.return_value = conn

        dpm = MagicMock()
        dpm.fetch_ohlc.return_value = _make_ohlc_df(50).to_dict("records")

        mock_backtester = MagicMock()
        mock_backtester.MIN_REGIME_SCORE = 0.75
        mock_backtester._detect_regime.return_value = detected_regime

        from core_brain.backtest_orchestrator import AptitudeMatrix, ScenarioSlice
        matrix = MagicMock(spec=AptitudeMatrix)
        matrix.overall_score = 0.70
        matrix.total_trades = 30
        matrix.win_rate = 0.60
        matrix.profit_factor = 1.8
        matrix.max_drawdown = 0.08
        matrix.regime_scores = {}
        matrix.trace_id = "TEST-TRACE"
        matrix.timestamp = datetime.now(timezone.utc).isoformat()
        mock_backtester.run_scenario_backtest.return_value = matrix

        orc = BacktestOrchestrator.__new__(BacktestOrchestrator)
        orc.storage = storage
        orc.dpm = dpm
        orc.backtester = mock_backtester
        orc._cfg = {"cooldown_hours": 0, "confidence_k": 20, "max_bars": 200}
        orc._rr_state = {}
        orc._rr_lock = threading.Lock()
        return orc

    def test_coverage_row_written_after_pair_evaluation(self):
        """Una fila en sys_strategy_pair_coverage debe existir tras evaluar un par."""
        conn = _build_db()
        # Insert strategy row required by orchestrator writes
        conn.execute("""
            INSERT OR IGNORE INTO sys_strategies
                (class_id, mnemonic, mode, score, affinity_scores, execution_params)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("strat_coverage_test", "Coverage Test", "BACKTEST", 0.0, "{}", "{}"))
        conn.commit()

        orc = self._make_orchestrator_with_db(conn)
        strategy = _make_strategy(strategy_id="strat_coverage_test", symbols=["EURUSD"])

        cursor = conn.cursor()
        orc._write_pair_coverage(cursor, "strat_coverage_test", "EURUSD", "M15", "TREND",
                                  n_trades=30, effective_score=0.65, status="QUALIFIED")
        conn.commit()

        row = conn.execute(
            "SELECT * FROM sys_strategy_pair_coverage "
            "WHERE strategy_id=? AND symbol=? AND timeframe=? AND regime=?",
            ("strat_coverage_test", "EURUSD", "M15", "TREND")
        ).fetchone()
        assert row is not None
        assert row["effective_score"] == pytest.approx(0.65, abs=0.001)
        assert row["status"] == "QUALIFIED"
        assert row["n_trades_total"] == 30

    def test_coverage_row_has_timestamp(self):
        """last_evaluated_at debe ser un timestamp ISO 8601 válido."""
        conn = _build_db()
        orc = self._make_orchestrator_with_db(conn)

        cursor = conn.cursor()
        orc._write_pair_coverage(cursor, "strat_x", "GBPUSD", "H1", "RANGE",
                                  n_trades=15, effective_score=0.55, status="QUALIFIED")
        conn.commit()

        row = conn.execute(
            "SELECT last_evaluated_at FROM sys_strategy_pair_coverage "
            "WHERE strategy_id=? AND symbol=?",
            ("strat_x", "GBPUSD")
        ).fetchone()
        assert row is not None
        ts = row["last_evaluated_at"]
        assert ts is not None
        datetime.fromisoformat(ts)  # raises if invalid

    def test_coverage_row_upsert_increments_cycles(self):
        """Segunda evaluación del mismo par incrementa n_cycles."""
        conn = _build_db()
        orc = self._make_orchestrator_with_db(conn)

        cursor = conn.cursor()
        # First evaluation
        orc._write_pair_coverage(cursor, "strat_upsert", "EURUSD", "M15", "TREND",
                                  n_trades=20, effective_score=0.60, status="QUALIFIED")
        conn.commit()
        # Second evaluation
        orc._write_pair_coverage(cursor, "strat_upsert", "EURUSD", "M15", "TREND",
                                  n_trades=25, effective_score=0.65, status="QUALIFIED")
        conn.commit()

        rows = conn.execute(
            "SELECT n_cycles FROM sys_strategy_pair_coverage WHERE strategy_id=?",
            ("strat_upsert",)
        ).fetchall()
        assert len(rows) == 1  # only one row (UNIQUE constraint)
        assert rows[0]["n_cycles"] == 2

    def test_coverage_row_upsert_updates_score(self):
        """Segunda evaluación actualiza effective_score al valor más reciente."""
        conn = _build_db()
        orc = self._make_orchestrator_with_db(conn)

        cursor = conn.cursor()
        orc._write_pair_coverage(cursor, "strat_score_upd", "EURUSD", "M15", "TREND",
                                  n_trades=10, effective_score=0.40, status="PENDING")
        conn.commit()
        orc._write_pair_coverage(cursor, "strat_score_upd", "EURUSD", "M15", "TREND",
                                  n_trades=40, effective_score=0.72, status="QUALIFIED")
        conn.commit()

        row = conn.execute(
            "SELECT effective_score, status, n_trades_total "
            "FROM sys_strategy_pair_coverage WHERE strategy_id=?",
            ("strat_score_upd",)
        ).fetchone()
        assert row["effective_score"] == pytest.approx(0.72, abs=0.001)
        assert row["status"] == "QUALIFIED"
        assert row["n_trades_total"] == 40

    def test_coverage_different_regimes_stored_separately(self):
        """Mismo par con distintos regímenes genera filas separadas."""
        conn = _build_db()
        orc = self._make_orchestrator_with_db(conn)

        cursor = conn.cursor()
        orc._write_pair_coverage(cursor, "strat_multi_regime", "EURUSD", "M15", "TREND",
                                  n_trades=30, effective_score=0.65, status="QUALIFIED")
        orc._write_pair_coverage(cursor, "strat_multi_regime", "EURUSD", "M15", "RANGE",
                                  n_trades=12, effective_score=0.45, status="PENDING")
        conn.commit()

        rows = conn.execute(
            "SELECT regime FROM sys_strategy_pair_coverage WHERE strategy_id=?",
            ("strat_multi_regime",)
        ).fetchall()
        regimes = {r["regime"] for r in rows}
        assert "TREND" in regimes
        assert "RANGE" in regimes
        assert len(rows) == 2
