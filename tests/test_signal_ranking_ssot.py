"""
test_signal_ranking_ssot.py — Verifica que ensure_signal_ranking_for_strategy
usa sys_strategies.mode como SSOT, nunca hardcodea 'SHADOW'.

Regla: el execution_mode en sys_signal_ranking debe reflejar el mode de sys_strategies,
no asignarse con un default fijo que ignore la configuración registrada en DB.

Naming: test_<componente>_<comportamiento>
"""
import pytest
from pathlib import Path
from data_vault.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    """StorageManager con DB en disco temporal — esquema completo inicializado."""
    db_path = tmp_path / "test_ssot.db"
    return StorageManager(db_path=str(db_path))


def _set_strategy_mode(storage: StorageManager, class_id: str, mode: str) -> None:
    """
    Establece el mode en sys_strategies para el escenario de test.
    Usa UPSERT para cubrir tanto estrategias pre-seeded como nuevas.
    """
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
                INSERT INTO sys_strategies (class_id, mnemonic, version, mode, readiness)
                VALUES (?, ?, '1.0', ?, 'READY_FOR_ENGINE')
                """,
                (class_id, f"MNEM_{class_id}", mode),
            )
        conn.commit()
    finally:
        storage._close_conn(conn)


# ---------------------------------------------------------------------------
# Tests SSOT
# ---------------------------------------------------------------------------

def test_ensure_signal_ranking_respects_backtest_mode(storage):
    """
    Estrategia con mode='BACKTEST' en sys_strategies debe crear entrada con
    execution_mode='BACKTEST', nunca con 'SHADOW'.
    """
    _set_strategy_mode(storage, "SESS_EXT_0001", "BACKTEST")

    result = storage.ensure_signal_ranking_for_strategy("SESS_EXT_0001")

    assert result["execution_mode"] == "BACKTEST", (
        f"Se esperaba BACKTEST pero se obtuvo {result['execution_mode']}. "
        "ensure_signal_ranking_for_strategy debe leer sys_strategies.mode."
    )


def test_ensure_signal_ranking_respects_shadow_mode(storage):
    """
    Estrategia con mode='SHADOW' en sys_strategies debe crear entrada con
    execution_mode='SHADOW'.
    """
    _set_strategy_mode(storage, "LIQ_SWEEP_0001", "SHADOW")

    result = storage.ensure_signal_ranking_for_strategy("LIQ_SWEEP_0001")

    assert result["execution_mode"] == "SHADOW"


def test_ensure_signal_ranking_defaults_to_backtest_when_strategy_missing(storage):
    """
    Estrategia que no existe en sys_strategies debe inicializarse con
    execution_mode='BACKTEST' (safe default conservador, no 'SHADOW').
    Evita que estrategias no registradas lleguen a producción.
    """
    result = storage.ensure_signal_ranking_for_strategy("ESTRATEGIA_INEXISTENTE")

    assert result["execution_mode"] == "BACKTEST", (
        f"Se esperaba BACKTEST como safe default pero se obtuvo {result['execution_mode']}."
    )


def test_ensure_signal_ranking_is_idempotent(storage):
    """
    Llamar múltiples veces no debe sobrescribir execution_mode si ya existe.
    """
    _set_strategy_mode(storage, "BRK_OPEN_0001", "BACKTEST")

    storage.ensure_signal_ranking_for_strategy("BRK_OPEN_0001")
    # Cambiar el modo manualmente (simula una promoción hecha por el ranker)
    storage.update_strategy_execution_mode("BRK_OPEN_0001", "LIVE")

    # Segunda llamada no debe revertir a BACKTEST
    result = storage.ensure_signal_ranking_for_strategy("BRK_OPEN_0001")

    assert result["execution_mode"] == "LIVE", (
        "ensure_signal_ranking_for_strategy no debe sobrescribir una entrada existente."
    )
