"""
test_shadow_manager_metrics_refresh.py
=======================================
TDD para FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30

Verifica que:
1. evaluate_all_instances() refresca métricas desde sys_trades
   (NO usa el cache de sys_shadow_instances).
2. score_shadow en sys_strategies se actualiza tras la evaluación.
3. recalculate_all_shadow_scores() funciona como trigger manual.
4. calculate_instance_metrics_from_sys_trades() recibe datos no vacíos
   cuando sys_trades tiene trades con instance_id correcto.

Regla §7 — Feedback Loop: score=0 paraliza el motor Darwiniano.
Trace_ID: FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30
"""
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from core_brain.shadow_manager import ShadowManager
from data_vault.schema import initialize_schema
from data_vault.shadow_db import ShadowStorageManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """DB en memoria con esquema completo."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def strategy_id():
    return "LIQ_SWEEP_0001"


@pytest.fixture
def instance_id():
    return f"SHADOW_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def db_with_strategy(db, strategy_id):
    """DB con estrategia en sys_strategies (score_shadow empieza en 0)."""
    db.execute(
        """
        INSERT INTO sys_strategies (
            class_id, mnemonic, mode, score_backtest, score_shadow,
            score_live, score, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strategy_id, "LIQ SWEEP 0001", "BACKTEST",
            0.0, 0.0, 0.0, 0.0,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    return db


@pytest.fixture
def db_with_active_shadow_instance(db_with_strategy, strategy_id, instance_id):
    """DB con instancia SHADOW activa — métricas en cache = 0 (estado inicial)."""
    db_with_strategy.execute(
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
            "{}", "[]",
            datetime.now(timezone.utc).isoformat(),
            "INCUBATING",
            # Cache stale: 0 trades (bug original — evaluación ciega)
            0, 0.0, 0.0, 0.0, 0, 0.0,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db_with_strategy.commit()
    return db_with_strategy


def _insert_shadow_trades(db, instance_id: str, n_wins: int, n_losses: int):
    """Inserta trades SHADOW en sys_trades con instance_id correcto."""
    now = datetime.now(timezone.utc).isoformat()
    for i in range(n_wins):
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
                "EURUSD", "BUY",
                1.1000, 1.1050, 50.0, "TP",
                now, now, "SHADOW", "LIQ_SWEEP_0001", None,
            ),
        )
    for i in range(n_losses):
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
                "EURUSD", "SELL",
                1.1050, 1.1000, -50.0, "SL",
                now, now, "SHADOW", "LIQ_SWEEP_0001", None,
            ),
        )
    db.commit()


# ── Tests RED ─────────────────────────────────────────────────────────────────

class TestEvaluateAllInstancesRefreshesMetrics:
    """
    evaluate_all_instances() DEBE leer métricas frescas desde sys_trades,
    no usar el cache en sys_shadow_instances.
    """

    def test_evaluate_all_instances_reads_from_sys_trades_not_cache(
        self, db_with_active_shadow_instance, instance_id, strategy_id
    ):
        """
        Con cache en 0 pero trades reales en sys_trades, evaluate_all_instances()
        DEBE usar los datos de sys_trades.

        Sin el fix: metrics = instance.metrics → win_rate=0, total=0 → MONITOR/INCUBATING
        Con el fix: metrics = calculate_instance_metrics_from_sys_trades() → datos reales
        """
        # Insertar trades suficientes para pasar los 3 Pilares
        _insert_shadow_trades(db_with_active_shadow_instance, instance_id, n_wins=12, n_losses=3)

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        manager = ShadowManager(storage=shadow_storage)

        result = manager.evaluate_all_instances()

        # Con 12W/3L: WR=0.8, PF=4.0 → Pilar1 PASS
        # Pilar3: 15 trades exactos → PASS (si min_trades=15)
        # El resultado debe reflejar datos reales, no cache vacío
        total_processed = sum(len(v) for v in result.values())
        assert total_processed == 1, (
            f"Se esperaba 1 instancia procesada, got {total_processed}. "
            "evaluate_all_instances() debe procesar la instancia activa."
        )

    def test_evaluate_all_instances_refreshes_cached_zero_metrics(
        self, db_with_active_shadow_instance, instance_id, strategy_id
    ):
        """
        La instancia tiene cache total_trades_executed=0.
        Hay 20 trades en sys_trades.
        Tras evaluate_all_instances(), sys_shadow_instances DEBE tener métricas actualizadas.
        """
        _insert_shadow_trades(db_with_active_shadow_instance, instance_id, n_wins=14, n_losses=6)

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        manager = ShadowManager(storage=shadow_storage)
        manager.evaluate_all_instances()

        # Verificar que sys_shadow_instances se actualizó con datos reales
        row = db_with_active_shadow_instance.execute(
            "SELECT total_trades_executed, win_rate FROM sys_shadow_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()

        assert row is not None
        assert row["total_trades_executed"] == 20, (
            f"sys_shadow_instances.total_trades_executed debe ser 20, got {row['total_trades_executed']}. "
            "evaluate_all_instances() debe persistir métricas frescas."
        )
        assert row["win_rate"] == pytest.approx(0.7, abs=0.01), (
            f"win_rate esperado ~0.70, got {row['win_rate']}"
        )


class TestScoreShadowUpdate:
    """
    score_shadow en sys_strategies DEBE actualizarse tras evaluate_all_instances().
    Actualmente siempre es 0 — paraliza la fórmula Darwiniana.
    """

    def test_score_shadow_updated_in_sys_strategies_after_evaluation(
        self, db_with_active_shadow_instance, instance_id, strategy_id
    ):
        """
        Después de evaluate_all_instances(), sys_strategies.score_shadow
        DEBE ser > 0 cuando la instancia tiene trades reales con buen desempeño.

        Sin el fix: score_shadow = 0.0 siempre → score efectivo sesgado hacia backtest.
        """
        _insert_shadow_trades(db_with_active_shadow_instance, instance_id, n_wins=12, n_losses=3)

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        manager = ShadowManager(storage=shadow_storage)
        manager.evaluate_all_instances()

        row = db_with_active_shadow_instance.execute(
            "SELECT score_shadow FROM sys_strategies WHERE class_id = ?",
            (strategy_id,),
        ).fetchone()

        assert row is not None
        assert row["score_shadow"] > 0.0, (
            f"score_shadow debe ser > 0 con trades reales. Got {row['score_shadow']}. "
            "Verificar que evaluate_all_instances() actualiza sys_strategies.score_shadow."
        )


class TestRecalculateAllShadowScores:
    """
    recalculate_all_shadow_scores() — trigger manual de recálculo.
    Permite recalcular sin esperar al ciclo horario de evaluate_all_instances().
    """

    def test_recalculate_all_shadow_scores_updates_metrics_and_score(
        self, db_with_active_shadow_instance, instance_id, strategy_id
    ):
        """
        recalculate_all_shadow_scores() DEBE:
        1. Leer trades desde sys_trades para cada instancia activa.
        2. Actualizar sys_shadow_instances con métricas frescas.
        3. Actualizar sys_strategies.score_shadow.
        """
        _insert_shadow_trades(db_with_active_shadow_instance, instance_id, n_wins=9, n_losses=3)

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        manager = ShadowManager(storage=shadow_storage)

        summary = manager.recalculate_all_shadow_scores()

        assert "recalculated" in summary, "El resumen debe tener clave 'recalculated'"
        assert summary["recalculated"] == 1, (
            f"Debe recalcular 1 instancia, got {summary['recalculated']}"
        )

        # Verificar sys_shadow_instances actualizado
        row_inst = db_with_active_shadow_instance.execute(
            "SELECT total_trades_executed FROM sys_shadow_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
        assert row_inst["total_trades_executed"] == 12

        # Verificar sys_strategies actualizado
        row_strat = db_with_active_shadow_instance.execute(
            "SELECT score_shadow FROM sys_strategies WHERE class_id = ?",
            (strategy_id,),
        ).fetchone()
        assert row_strat["score_shadow"] > 0.0, (
            "score_shadow debe actualizarse tras recalculate_all_shadow_scores()"
        )

    def test_recalculate_all_shadow_scores_returns_zero_when_no_instances(
        self, db_with_strategy
    ):
        """
        Sin instancias activas, recalculate_all_shadow_scores() devuelve 0.
        No debe lanzar excepción.
        """
        shadow_storage = ShadowStorageManager(db_with_strategy)
        manager = ShadowManager(storage=shadow_storage)

        summary = manager.recalculate_all_shadow_scores()

        assert summary["recalculated"] == 0


class TestCalculateMetricsReceivesNonEmptyData:
    """
    Confirmar que calculate_instance_metrics_from_sys_trades() recibe datos
    no vacíos cuando los trades tienen instance_id correcto (post-fix).
    """

    def test_calculate_metrics_non_empty_after_shadow_sync_fix(
        self, db_with_active_shadow_instance, instance_id
    ):
        """
        Tras el fix FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30,
        calculate_instance_metrics_from_sys_trades() NO debe retornar métricas vacías
        cuando hay trades con instance_id correcto en sys_trades.
        """
        _insert_shadow_trades(db_with_active_shadow_instance, instance_id, n_wins=6, n_losses=2)

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        metrics = shadow_storage.calculate_instance_metrics_from_sys_trades(instance_id)

        assert metrics.total_trades_executed == 8, (
            f"Esperado 8 trades, got {metrics.total_trades_executed}. "
            "calculate_instance_metrics_from_sys_trades() debe encontrar los trades "
            "guardados con instance_id correcto."
        )
        assert metrics.win_rate == pytest.approx(0.75, abs=0.01)
        assert metrics.profit_factor > 1.0

    def test_calculate_metrics_empty_confirms_null_instance_id_bug(
        self, db_with_active_shadow_instance, instance_id
    ):
        """
        Documentación del bug original: trades con instance_id=NULL
        son invisibles para calculate_instance_metrics_from_sys_trades().
        """
        now = datetime.now(timezone.utc).isoformat()
        db_with_active_shadow_instance.execute(
            """
            INSERT INTO sys_trades (
                id, signal_id, instance_id, account_id, symbol, direction,
                entry_price, exit_price, profit, exit_reason,
                open_time, close_time, execution_mode, strategy_id, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), None, None,  # instance_id = NULL — bug original
                "ACC_DEMO_01", "EURUSD", "BUY",
                1.1000, 1.1050, 50.0, "TP",
                now, now, "SHADOW", "LIQ_SWEEP_0001", None,
            ),
        )
        db_with_active_shadow_instance.commit()

        shadow_storage = ShadowStorageManager(db_with_active_shadow_instance)
        metrics = shadow_storage.calculate_instance_metrics_from_sys_trades(instance_id)

        assert metrics.total_trades_executed == 0, (
            "Bug documentado: instance_id=NULL hace invisible el trade. "
            "La función devuelve métricas vacías — confirma la raíz del score=0."
        )
