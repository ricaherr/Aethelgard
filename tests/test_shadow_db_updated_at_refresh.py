"""
test_shadow_db_updated_at_refresh.py
=====================================
TDD para FIX-LIFECYCLE-COHERENCE-STALE-BACKTEST-2026-03-30

Regla §7 Feedback Loop: estrategias sin ciclo de vida activo no pueden ser
promovidas ni eliminadas. El campo updated_at de sys_shadow_instances DEBE
avanzar en cada ciclo de backtest para que el motor Darwiniano detecte
actividad de vida.

Bug: update_shadow_instance() persiste db_dict["updated_at"] (timestamp
original cargado desde DB), nunca lo refresca. El UPDATE escribe el mismo
valor que ya existía → updated_at se congela en la fecha de creación.

Fix esperado: UPDATE usa CURRENT_TIMESTAMP en lugar del valor serializado
del objeto.

Trace_ID: FIX-LIFECYCLE-COHERENCE-STALE-BACKTEST-2026-03-30
"""
import sqlite3
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from core_brain.shadow_manager import ShadowManager
from data_vault.schema import initialize_schema
from data_vault.shadow_db import ShadowStorageManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def strategy_id():
    return "BRK_OPEN_0001"


@pytest.fixture
def instance_id():
    return f"SHADOW_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def db_with_stale_instance(db, strategy_id, instance_id):
    """
    DB con estrategia e instancia SHADOW cuyo updated_at está en el pasado
    (simula las 5 estrategias con ciclo de vida congelado).
    """
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    db.execute(
        """
        INSERT INTO sys_strategies (
            class_id, mnemonic, mode, score_backtest, score_shadow,
            score_live, score, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strategy_id, "BRK OPEN 0001", "BACKTEST",
            0.0, 0.0, 0.0, 0.0, past, past,
        ),
    )
    db.execute(
        """
        INSERT INTO sys_shadow_instances (
            instance_id, strategy_id, account_id, account_type,
            parameter_overrides, regime_filters, birth_timestamp, status,
            total_trades_executed, profit_factor, win_rate,
            max_drawdown_pct, consecutive_losses_max, equity_curve_cv,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            instance_id, strategy_id, "ACC_DEMO_01", "DEMO",
            "{}", "[]", past, "INCUBATING",
            0, 0.0, 0.0, 0.0, 0, 0.0,
            past, past,  # updated_at congelado en el pasado
        ),
    )
    db.commit()
    return db, past


def _insert_shadow_trades(db, instance_id: str, n_wins: int, n_losses: int):
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(n_wins):
        db.execute(
            """
            INSERT INTO sys_trades (
                id, signal_id, instance_id, account_id, symbol, direction,
                entry_price, exit_price, profit, exit_reason,
                open_time, close_time, execution_mode, strategy_id, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), None, instance_id, "ACC_DEMO_01",
                "EURUSD", "BUY", 1.1000, 1.1050, 50.0, "TP",
                now, now, "SHADOW", "BRK_OPEN_0001", None,
            ),
        )
    for _ in range(n_losses):
        db.execute(
            """
            INSERT INTO sys_trades (
                id, signal_id, instance_id, account_id, symbol, direction,
                entry_price, exit_price, profit, exit_reason,
                open_time, close_time, execution_mode, strategy_id, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), None, instance_id, "ACC_DEMO_01",
                "EURUSD", "SELL", 1.1050, 1.1000, -50.0, "SL",
                now, now, "SHADOW", "BRK_OPEN_0001", None,
            ),
        )
    db.commit()


# ── Tests RED ─────────────────────────────────────────────────────────────────

class TestUpdatedAtRefreshesOnEvaluate:
    """
    evaluate_all_instances() DEBE actualizar updated_at en sys_shadow_instances.

    Sin el fix: UPDATE escribe el mismo updated_at que cargó → timestamp congelado.
    Con el fix: UPDATE usa CURRENT_TIMESTAMP → timestamp avanza en cada ciclo.
    """

    def test_evaluate_all_instances_advances_updated_at(
        self, db_with_stale_instance, instance_id
    ):
        """
        updated_at en sys_shadow_instances DEBE ser posterior al valor original
        después de que evaluate_all_instances() procese la instancia.
        """
        db, past_iso = db_with_stale_instance
        past_dt = datetime.fromisoformat(past_iso.replace("Z", "+00:00"))

        _insert_shadow_trades(db, instance_id, n_wins=10, n_losses=5)

        storage = ShadowStorageManager(db)
        manager = ShadowManager(storage=storage)

        # Pequeña pausa para garantizar que CURRENT_TIMESTAMP != past_dt
        time.sleep(0.05)

        manager.evaluate_all_instances()

        row = db.execute(
            "SELECT updated_at FROM sys_shadow_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()

        assert row is not None, "La instancia debe existir en sys_shadow_instances."

        updated_at_str = row["updated_at"]
        # SQLite CURRENT_TIMESTAMP produce 'YYYY-MM-DD HH:MM:SS' (sin zona)
        try:
            updated_at_dt = datetime.fromisoformat(updated_at_str)
        except ValueError:
            updated_at_dt = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")

        # Normalizar a naive si es necesario
        if updated_at_dt.tzinfo is not None:
            updated_at_dt = updated_at_dt.replace(tzinfo=None)
        past_naive = past_dt.replace(tzinfo=None)

        assert updated_at_dt > past_naive, (
            f"updated_at debe avanzar tras evaluate_all_instances(). "
            f"Original: {past_naive} | Actual: {updated_at_dt}. "
            "update_shadow_instance() debe usar CURRENT_TIMESTAMP, no el valor serializado."
        )

    def test_update_shadow_instance_directly_advances_updated_at(
        self, db_with_stale_instance, instance_id
    ):
        """
        update_shadow_instance() de forma directa DEBE actualizar updated_at.
        Verifica que el fix está en la capa de storage (no solo en ShadowManager).
        """
        db, past_iso = db_with_stale_instance
        past_dt = datetime.fromisoformat(past_iso.replace("Z", "+00:00"))

        storage = ShadowStorageManager(db)
        instances = storage.list_active_instances()
        assert len(instances) == 1, "Debe haber exactamente 1 instancia activa."

        instance = instances[0]

        time.sleep(0.05)

        # Llamada directa sin pasar por ShadowManager
        storage.update_shadow_instance(instance)

        row = db.execute(
            "SELECT updated_at FROM sys_shadow_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()

        updated_at_str = row["updated_at"]
        try:
            updated_at_dt = datetime.fromisoformat(updated_at_str)
        except ValueError:
            updated_at_dt = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")

        if updated_at_dt.tzinfo is not None:
            updated_at_dt = updated_at_dt.replace(tzinfo=None)
        past_naive = past_dt.replace(tzinfo=None)

        assert updated_at_dt > past_naive, (
            f"update_shadow_instance() DIRECTO debe actualizar updated_at. "
            f"Original: {past_naive} | Actual: {updated_at_dt}. "
            "Bug: la función serializa instance.updated_at (original) en vez de CURRENT_TIMESTAMP."
        )
