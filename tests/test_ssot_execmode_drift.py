"""
test_ssot_execmode_drift.py — HU 8.8: SSOT Execution Mode Drift Fix
Trace_ID: SSOT-EXECMODE-DRIFT-FIX-2026-04-09

Verifica que:
1. get_strategy_lifecycle_mode lee sys_strategies.mode (SSOT real)
2. StrategyEngineFactory._get_execution_mode consulta SSOT, no sys_signal_ranking
3. La migración de reconciliación corrige divergencias históricas en sys_signal_ranking

Reglas:
- Happy path SHADOW
- Happy path BACKTEST
- Fallback SHADOW para estrategia inexistente
- Fallback SHADOW + log ante error de DB
- Migration: sys_signal_ranking.execution_mode queda alineado con sys_strategies.mode
"""
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from data_vault.storage import StorageManager
from core_brain.services.strategy_engine_factory import StrategyEngineFactory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path):
    """StorageManager con DB en disco temporal — esquema + migraciones completos."""
    db_path = tmp_path / "test_drift.db"
    return StorageManager(db_path=str(db_path))


def _upsert_strategy(storage: StorageManager, class_id: str, mode: str) -> None:
    """Inserta o actualiza sys_strategies.mode para el escenario de test."""
    conn = storage._get_conn()
    try:
        conn.execute(
            "UPDATE sys_strategies SET mode = ? WHERE class_id = ?",
            (mode, class_id),
        )
        if conn.execute(
            "SELECT 1 FROM sys_strategies WHERE class_id = ?", (class_id,)
        ).fetchone() is None:
            conn.execute(
                """
                INSERT INTO sys_strategies
                    (class_id, mnemonic, version, mode, readiness)
                VALUES (?, ?, '1.0', ?, 'READY_FOR_ENGINE')
                """,
                (class_id, f"MNEM_{class_id}", mode),
            )
        conn.commit()
    finally:
        storage._close_conn(conn)


def _set_signal_ranking_mode(storage: StorageManager, strategy_id: str, execution_mode: str) -> None:
    """Fuerza un execution_mode en sys_signal_ranking (simula el drift)."""
    conn = storage._get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sys_signal_ranking
                (strategy_id, execution_mode, profit_factor, win_rate, drawdown_max,
                 sharpe_ratio, consecutive_losses, total_usr_trades, completed_last_50,
                 trace_id, last_update_utc)
            VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0, 0, 0,
                    ?, CURRENT_TIMESTAMP)
            """,
            (strategy_id, execution_mode, f"DRIFT-TEST-{strategy_id}"),
        )
        conn.commit()
    finally:
        storage._close_conn(conn)


@pytest.fixture
def mock_storage():
    """Mock de StorageManager para tests unitarios de la factory."""
    mock = MagicMock()
    mock.get_all_sys_strategies.return_value = []
    return mock


@pytest.fixture
def factory(mock_storage):
    """StrategyEngineFactory con storage mockeado."""
    return StrategyEngineFactory(storage=mock_storage, config={}, available_sensors={})


# ---------------------------------------------------------------------------
# Test 1: Happy path — SHADOW leído desde sys_strategies (SSOT)
# ---------------------------------------------------------------------------

def test_lifecycle_mode_returns_shadow_from_ssot(storage):
    """
    GIVEN: Estrategia cuyo sys_strategies.mode = 'SHADOW'
    WHEN: get_strategy_lifecycle_mode es llamado
    THEN: Retorna 'SHADOW' (lee SSOT, no sys_signal_ranking)
    """
    _upsert_strategy(storage, "MOM_BIAS_0001", "SHADOW")

    result = storage.get_strategy_lifecycle_mode("MOM_BIAS_0001")

    assert result == "SHADOW", (
        f"Se esperaba SHADOW pero se obtuvo '{result}'. "
        "La factory debe leer sys_strategies.mode como SSOT."
    )


# ---------------------------------------------------------------------------
# Test 2: Happy path — BACKTEST leído desde sys_strategies (SSOT)
# ---------------------------------------------------------------------------

def test_lifecycle_mode_returns_backtest_from_ssot(storage):
    """
    GIVEN: Estrategia cuyo sys_strategies.mode = 'BACKTEST'
    WHEN: get_strategy_lifecycle_mode es llamado
    THEN: Retorna 'BACKTEST'
    """
    _upsert_strategy(storage, "LIQ_SWEEP_0001", "BACKTEST")

    result = storage.get_strategy_lifecycle_mode("LIQ_SWEEP_0001")

    assert result == "BACKTEST", (
        f"Se esperaba BACKTEST pero se obtuvo '{result}'."
    )


# ---------------------------------------------------------------------------
# Test 3: Edge case — strategy_id inexistente → fallback SHADOW seguro
# ---------------------------------------------------------------------------

def test_lifecycle_mode_fallback_for_unknown_strategy(storage):
    """
    GIVEN: strategy_id que NO existe en sys_strategies
    WHEN: get_strategy_lifecycle_mode es llamado
    THEN: Retorna 'SHADOW' como safe default (evita zombie runtime por drift silencioso)
    """
    result = storage.get_strategy_lifecycle_mode("NONEXISTENT_9999")

    assert result == "SHADOW", (
        f"Para estrategia inexistente se esperaba fallback SHADOW, se obtuvo '{result}'."
    )


# ---------------------------------------------------------------------------
# Test 4: Edge case — error de DB → fallback SHADOW + log de error
# ---------------------------------------------------------------------------

def test_factory_get_execution_mode_db_error_returns_shadow(factory, mock_storage):
    """
    GIVEN: storage.get_strategy_lifecycle_mode lanza una excepción
    WHEN: factory._get_execution_mode es llamado
    THEN: Retorna 'SHADOW' y loguea el error (no propaga la excepción)
    """
    mock_storage.get_strategy_lifecycle_mode.side_effect = RuntimeError("DB connection lost")

    result = factory._get_execution_mode("STRUC_SHIFT_0001")

    assert result == "SHADOW", (
        f"Ante error de DB se esperaba fallback SHADOW, se obtuvo '{result}'."
    )


# ---------------------------------------------------------------------------
# Test 5: Factory lee SSOT (verifica que llama get_strategy_lifecycle_mode)
# ---------------------------------------------------------------------------

def test_factory_get_execution_mode_reads_from_ssot_shadow(factory, mock_storage):
    """
    GIVEN: storage.get_strategy_lifecycle_mode retorna 'SHADOW'
    WHEN: factory._get_execution_mode es llamado
    THEN: Retorna 'SHADOW' (tomado del SSOT, no de sys_signal_ranking)
    """
    mock_storage.get_strategy_lifecycle_mode.return_value = "SHADOW"

    result = factory._get_execution_mode("MOM_BIAS_0001")

    assert result == "SHADOW"
    mock_storage.get_strategy_lifecycle_mode.assert_called_once_with("MOM_BIAS_0001")


def test_factory_get_execution_mode_reads_from_ssot_backtest(factory, mock_storage):
    """
    GIVEN: storage.get_strategy_lifecycle_mode retorna 'BACKTEST'
    WHEN: factory._get_execution_mode es llamado
    THEN: Retorna 'BACKTEST'
    """
    mock_storage.get_strategy_lifecycle_mode.return_value = "BACKTEST"

    result = factory._get_execution_mode("LIQ_SWEEP_0001")

    assert result == "BACKTEST"


# ---------------------------------------------------------------------------
# Test 6: Migration reconcila execution_mode divergente
# ---------------------------------------------------------------------------

def test_migration_reconciles_divergent_execution_mode(storage):
    """
    GIVEN: sys_strategies.mode = 'SHADOW' y sys_signal_ranking.execution_mode = 'BACKTEST'
           (drift histórico: sys_signal_ranking fue creado antes de que el mode cambiara)
    WHEN: run_migrations es ejecutado
    THEN: sys_signal_ranking.execution_mode queda en 'SHADOW' (alineado con SSOT)
          Las filas ya consistentes NO se modifican
    """
    from data_vault.schema import run_migrations

    # Escenario de drift: MOM_BIAS_0001 en SHADOW, pero sys_signal_ranking dice BACKTEST
    _upsert_strategy(storage, "MOM_BIAS_0001", "SHADOW")
    _set_signal_ranking_mode(storage, "MOM_BIAS_0001", "BACKTEST")

    # Escenario ya consistente: LIQ_SWEEP_0001 en SHADOW, ranking también en SHADOW
    _upsert_strategy(storage, "LIQ_SWEEP_0001", "SHADOW")
    _set_signal_ranking_mode(storage, "LIQ_SWEEP_0001", "SHADOW")

    # Ejecutar migraciones (reconciliación idempotente)
    conn = storage._get_conn()
    try:
        run_migrations(conn)
    finally:
        storage._close_conn(conn)

    # Verificar que la fila divergente fue corregida
    conn2 = storage._get_conn()
    try:
        row_drift = conn2.execute(
            "SELECT execution_mode FROM sys_signal_ranking WHERE strategy_id = ?",
            ("MOM_BIAS_0001",),
        ).fetchone()
        row_consistent = conn2.execute(
            "SELECT execution_mode FROM sys_signal_ranking WHERE strategy_id = ?",
            ("LIQ_SWEEP_0001",),
        ).fetchone()
    finally:
        storage._close_conn(conn2)

    assert row_drift is not None
    assert row_drift[0] == "SHADOW", (
        f"Migración debió corregir BACKTEST → SHADOW, "
        f"pero execution_mode sigue en '{row_drift[0]}'."
    )

    assert row_consistent is not None
    assert row_consistent[0] == "SHADOW", (
        "La fila ya consistente no debió ser modificada."
    )
