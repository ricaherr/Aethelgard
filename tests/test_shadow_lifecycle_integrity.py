"""
Tests TDD: Integridad del ciclo de vida SHADOW.

P2 — OEM repair debe resetear last_backtest_at en DB (tier-2 cooldown).
P3 — mark_orphan_shadow_instances_dead() limpia instancias huérfanas.

RED state: falla porque StorageManager no tiene:
  - reset_backtest_cooldown_for_pending()
  - mark_orphan_shadow_instances_dead()
"""
import pytest
from data_vault.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test_lifecycle.db")
    return StorageManager(db_path=db_path)


def _seed_strategy(storage: StorageManager, class_id: str, mode: str, last_backtest_at=None):
    """Insert a strategy row directly via SQL for test setup."""
    conn = storage._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO sys_strategies
            (class_id, mnemonic, mode, score_backtest, score_shadow, score_live,
             score, last_backtest_at, updated_at)
        VALUES (?, ?, ?, 0.0, 0.0, 0.0, 0.0, ?, CURRENT_TIMESTAMP)
        """,
        (class_id, class_id[:8], mode, last_backtest_at),
    )
    conn.commit()
    storage._close_conn(conn)


def _seed_shadow_instance(storage: StorageManager, instance_id: str, strategy_id: str, status: str = "INCUBATING"):
    """Insert a shadow instance row for test setup."""
    conn = storage._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO sys_shadow_instances
            (instance_id, strategy_id, status, account_id, account_type,
             parameter_overrides, regime_filters, created_at, updated_at)
        VALUES (?, ?, ?, 'TEST_ACC', 'DEMO', '{}', '[]',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (instance_id, strategy_id, status),
    )
    conn.commit()
    storage._close_conn(conn)


def _get_strategy_backtest_at(storage: StorageManager, class_id: str):
    conn = storage._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT last_backtest_at FROM sys_strategies WHERE class_id = ?", (class_id,))
    row = cursor.fetchone()
    storage._close_conn(conn)
    return row[0] if row else None


def _get_shadow_instance_status(storage: StorageManager, instance_id: str) -> str:
    conn = storage._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM sys_shadow_instances WHERE instance_id = ?", (instance_id,))
    row = cursor.fetchone()
    storage._close_conn(conn)
    return row[0] if row else None


# ── P2: reset_backtest_cooldown_for_pending ───────────────────────────────────

class TestResetBacktestCooldownForPending:
    def test_clears_last_backtest_at_for_backtest_strategies(self, storage):
        """last_backtest_at debe quedar NULL para todas las estrategias en BACKTEST mode."""
        _seed_strategy(storage, "STRAT_A", "BACKTEST", last_backtest_at="2026-03-28T21:20:00")
        _seed_strategy(storage, "STRAT_B", "BACKTEST", last_backtest_at="2026-03-27T10:00:00")

        storage.reset_backtest_cooldown_for_pending()

        assert _get_strategy_backtest_at(storage, "STRAT_A") is None
        assert _get_strategy_backtest_at(storage, "STRAT_B") is None

    def test_does_not_touch_shadow_or_real_strategies(self, storage):
        """Estrategias en SHADOW o REAL NO deben ser modificadas."""
        _seed_strategy(storage, "STRAT_SHADOW", "SHADOW",  last_backtest_at="2026-03-28T21:20:00")
        _seed_strategy(storage, "STRAT_REAL",   "LIVE",    last_backtest_at="2026-03-28T21:20:00")
        _seed_strategy(storage, "STRAT_BACK",   "BACKTEST", last_backtest_at="2026-03-28T21:20:00")

        storage.reset_backtest_cooldown_for_pending()

        assert _get_strategy_backtest_at(storage, "STRAT_SHADOW") == "2026-03-28T21:20:00"
        assert _get_strategy_backtest_at(storage, "STRAT_REAL")   == "2026-03-28T21:20:00"  # mode=LIVE
        assert _get_strategy_backtest_at(storage, "STRAT_BACK")   is None

    def test_idempotent_when_already_null(self, storage):
        """Si ya es NULL, no debe lanzar error."""
        _seed_strategy(storage, "STRAT_C", "BACKTEST", last_backtest_at=None)
        storage.reset_backtest_cooldown_for_pending()  # Must not raise
        assert _get_strategy_backtest_at(storage, "STRAT_C") is None


# ── P3: mark_orphan_shadow_instances_dead ────────────────────────────────────

class TestMarkOrphanShadowInstancesDead:
    def test_marks_incubating_instances_of_backtest_strategies_as_dead(self, storage):
        """Instancias INCUBATING de estrategias en BACKTEST → DEAD."""
        _seed_strategy(storage, "STRAT_BACK", "BACKTEST")
        _seed_shadow_instance(storage, "SHADOW_BACK_V0", "STRAT_BACK", "INCUBATING")
        _seed_shadow_instance(storage, "SHADOW_BACK_V1", "STRAT_BACK", "INCUBATING")

        storage.mark_orphan_shadow_instances_dead()

        assert _get_shadow_instance_status(storage, "SHADOW_BACK_V0") == "DEAD"
        assert _get_shadow_instance_status(storage, "SHADOW_BACK_V1") == "DEAD"

    def test_does_not_touch_instances_of_shadow_strategies(self, storage):
        """Instancias de estrategias en SHADOW mode NO deben ser marcadas DEAD."""
        _seed_strategy(storage, "STRAT_SHAD", "SHADOW")
        _seed_shadow_instance(storage, "SHADOW_SHAD_V0", "STRAT_SHAD", "INCUBATING")

        storage.mark_orphan_shadow_instances_dead()

        assert _get_shadow_instance_status(storage, "SHADOW_SHAD_V0") == "INCUBATING"

    def test_does_not_touch_already_dead_instances(self, storage):
        """Instancias ya DEAD no deben ser alteradas."""
        _seed_strategy(storage, "STRAT_BACK2", "BACKTEST")
        _seed_shadow_instance(storage, "SHADOW_DEAD", "STRAT_BACK2", "DEAD")

        storage.mark_orphan_shadow_instances_dead()

        assert _get_shadow_instance_status(storage, "SHADOW_DEAD") == "DEAD"

    def test_idempotent_when_no_orphans(self, storage):
        """Sin huérfanos no debe lanzar error."""
        storage.mark_orphan_shadow_instances_dead()  # No rows → must not raise

    def test_returns_count_of_marked_instances(self, storage):
        """Debe retornar el número de instancias marcadas."""
        _seed_strategy(storage, "STRAT_X", "BACKTEST")
        _seed_shadow_instance(storage, "SHADOW_X_V0", "STRAT_X", "INCUBATING")
        _seed_shadow_instance(storage, "SHADOW_X_V1", "STRAT_X", "INCUBATING")

        count = storage.mark_orphan_shadow_instances_dead()

        assert count == 2
