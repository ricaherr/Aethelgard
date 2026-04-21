"""
HU 7.5 — Auditoría y Persistencia de Ajustes de Auto-Calibración
Epic: E12 — Auto-Calibración EDGE
Trace_ID: ETI-E12-TUNING-AUDIT-20260421

Criterios de aceptación:
  1. La tabla usr_tuning_adjustments acepta inserciones correctamente.
  2. get_tuning_history devuelve los N últimos ajustes ordenados por timestamp DESC.
  3. adjustment_data se serializa/deserializa como JSON sin pérdida de datos.
  4. El índice idx_usr_tuning_adjustments_timestamp existe en la DB migrada.

Orden de ejecución: pytest tests/test_usr_tuning_adjustments_hu7_5.py -v
"""
import json
import sqlite3
from typing import Any

import pytest

from data_vault.system_db import SystemMixin


# ─── Helper: repositorio mínimo self-contained ──────────────────────────────

class _TuningRepo(SystemMixin):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        return None

    def _execute_serialized(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        return func(self._conn, *args, **kwargs)

    def transaction(self):  # type: ignore[override]
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            yield self._conn

        return _ctx()


# ─── Fixture: DB en memoria con la tabla creada ──────────────────────────────

@pytest.fixture
def tuning_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE usr_tuning_adjustments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
            adjustment_data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX idx_usr_tuning_adjustments_timestamp
            ON usr_tuning_adjustments (timestamp DESC)
    """)
    conn.commit()
    return conn


# ─── AC-1: Inserción individual ──────────────────────────────────────────────

def test_save_tuning_adjustment_inserta_registro(tuning_db: sqlite3.Connection) -> None:
    """
    Dado un ajuste válido, cuando se llama save_tuning_adjustment,
    entonces la tabla contiene exactamente un registro con los datos correctos.
    """
    repo = _TuningRepo(tuning_db)
    adjustment = {
        "trigger": "EDGE_THRESHOLD_BREACH",
        "param_before": 0.75,
        "param_after": 0.65,
        "factor": 0.87,
        "trace_id": "ETI-TEST-001",
    }

    repo.save_tuning_adjustment(adjustment)

    cursor = tuning_db.cursor()
    cursor.execute("SELECT * FROM usr_tuning_adjustments")
    rows = cursor.fetchall()
    assert len(rows) == 1
    stored = json.loads(rows[0]["adjustment_data"])
    assert stored["trigger"] == "EDGE_THRESHOLD_BREACH"
    assert stored["trace_id"] == "ETI-TEST-001"


# ─── AC-2: get_tuning_history devuelve orden DESC y respeta limit ─────────────

def test_get_tuning_history_devuelve_ultimos_n_registros(tuning_db: sqlite3.Connection) -> None:
    """
    Dado 7 ajustes con timestamps distintos, cuando se pide get_tuning_history(limit=5),
    entonces se devuelven exactamente los 5 más recientes en orden DESC por timestamp.
    """
    repo = _TuningRepo(tuning_db)
    # Insertar con timestamps explícitos para garantizar orden determinista
    for i in range(7):
        ts = f"2026-04-21 10:00:{i:02d}"
        tuning_db.execute(
            "INSERT INTO usr_tuning_adjustments (timestamp, adjustment_data) VALUES (?, ?)",
            (ts, json.dumps({"seq": i, "trigger": f"TRIGGER_{i}"})),
        )
    tuning_db.commit()

    history = repo.get_tuning_history(limit=5)

    assert len(history) == 5
    seqs = [h["adjustment_data"]["seq"] for h in history]
    assert seqs == sorted(seqs, reverse=True), "Debe estar ordenado por timestamp DESC"
    # Los 5 más recientes son los de seq 6,5,4,3,2
    assert seqs == [6, 5, 4, 3, 2]


# ─── AC-3: Serialización JSON sin pérdida de datos ───────────────────────────

def test_save_tuning_adjustment_preserva_tipos_json(tuning_db: sqlite3.Connection) -> None:
    """
    Dado un ajuste con tipos mixtos (float, bool, list), cuando se persiste y
    se recupera, entonces los tipos se mantienen sin pérdida.
    """
    repo = _TuningRepo(tuning_db)
    adjustment = {
        "factor": 1.23456,
        "active": True,
        "symbols": ["EURUSD", "GBPUSD"],
        "nested": {"score": 99},
    }

    repo.save_tuning_adjustment(adjustment)
    history = repo.get_tuning_history(limit=1)

    data = history[0]["adjustment_data"]
    assert data["factor"] == pytest.approx(1.23456)
    assert data["active"] is True
    assert data["symbols"] == ["EURUSD", "GBPUSD"]
    assert data["nested"]["score"] == 99


# ─── AC-4: El índice existe en la DB migrada real ────────────────────────────

def test_indice_timestamp_existe_en_db_migrada() -> None:
    """
    Dado que se aplicó la migración 20260421_create_usr_tuning_adjustments.sql,
    entonces el índice idx_usr_tuning_adjustments_timestamp debe existir en la DB principal.
    """
    import os
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "data_vault", "global", "aethelgard.db"
    )
    if not os.path.exists(db_path):
        pytest.skip("DB principal no disponible en este entorno")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_usr_tuning_adjustments_timestamp'"
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None, "El índice idx_usr_tuning_adjustments_timestamp debe existir tras la migración"
