"""TDD for stale SHADOW instance expiration at startup."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from data_vault.storage import StorageManager
from core_brain.orchestrators._discovery import initialize_shadow_pool_impl
from start import _expire_stale_shadow_instances_before_pool_bootstrap


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _seed_strategy(storage: StorageManager, class_id: str, mode: str) -> None:
    storage.execute_update(
        "INSERT INTO sys_strategies (class_id, mnemonic, mode) VALUES (?, ?, ?)",
        (class_id, class_id[:8], mode),
    )


def _seed_shadow_instance(
    storage: StorageManager,
    instance_id: str,
    strategy_id: str,
    status: str,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    storage.execute_update(
        """
        INSERT INTO sys_shadow_instances (
            instance_id, strategy_id, account_id, account_type,
            parameter_overrides, regime_filters, status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            instance_id,
            strategy_id,
            "DEMO_ACC_001",
            "DEMO",
            "{}",
            "[]",
            status,
            _fmt(created_at),
            _fmt(updated_at),
        ),
    )


def _get_shadow_row(storage: StorageManager, instance_id: str) -> dict:
    rows = storage.execute_query(
        "SELECT status, created_at, updated_at FROM sys_shadow_instances WHERE instance_id = ?",
        (instance_id,),
    )
    return rows[0]


def test_expire_stale_shadow_instances_marks_incubating_as_dead(tmp_path) -> None:
    """Old INCUBATING rows must be marked DEAD and refresh updated_at."""
    storage = StorageManager(db_path=str(tmp_path / "stale_expire.db"))
    _seed_strategy(storage, "STRAT_SHADOW_A", "SHADOW")

    old_created = datetime.now(UTC) - timedelta(hours=72)
    old_updated = old_created
    _seed_shadow_instance(
        storage,
        instance_id="SHADOW_STALE_001",
        strategy_id="STRAT_SHADOW_A",
        status="INCUBATING",
        created_at=old_created,
        updated_at=old_updated,
    )

    affected = storage.expire_stale_shadow_instances(max_age_hours=48)

    row = _get_shadow_row(storage, "SHADOW_STALE_001")
    assert affected == 1
    assert row["status"] == "DEAD"
    assert row["updated_at"] != _fmt(old_updated)


def test_expire_stale_shadow_instances_keeps_recent_rows_untouched(tmp_path) -> None:
    """Recent INCUBATING rows (< max_age) must stay active."""
    storage = StorageManager(db_path=str(tmp_path / "stale_keep_recent.db"))
    _seed_strategy(storage, "STRAT_SHADOW_B", "SHADOW")

    recent_created = datetime.now(UTC) - timedelta(hours=6)
    recent_updated = recent_created
    _seed_shadow_instance(
        storage,
        instance_id="SHADOW_RECENT_001",
        strategy_id="STRAT_SHADOW_B",
        status="INCUBATING",
        created_at=recent_created,
        updated_at=recent_updated,
    )

    affected = storage.expire_stale_shadow_instances(max_age_hours=48)

    row = _get_shadow_row(storage, "SHADOW_RECENT_001")
    assert affected == 0
    assert row["status"] == "INCUBATING"
    assert row["updated_at"] == _fmt(recent_updated)


def test_expiration_unblocks_shadow_pool_bootstrap_capacity(tmp_path) -> None:
    """After expiring stale rows, SHADOW bootstrap must create fresh pool instances."""
    storage = StorageManager(db_path=str(tmp_path / "stale_unblock_pool.db"))

    strategy_ids = ["STRAT_SHADOW_1", "STRAT_SHADOW_2", "STRAT_SHADOW_3"]
    for strategy_id in strategy_ids:
        _seed_strategy(storage, strategy_id, "SHADOW")

    stale_created = datetime.now(UTC) - timedelta(hours=120)
    stale_updated = stale_created
    for strategy_id in strategy_ids:
        _seed_shadow_instance(
            storage,
            instance_id=f"{strategy_id}_V0_STALE",
            strategy_id=strategy_id,
            status="INCUBATING",
            created_at=stale_created,
            updated_at=stale_updated,
        )
        _seed_shadow_instance(
            storage,
            instance_id=f"{strategy_id}_V1_STALE",
            strategy_id=strategy_id,
            status="INCUBATING",
            created_at=stale_created,
            updated_at=stale_updated,
        )

    affected = storage.expire_stale_shadow_instances(max_age_hours=48)
    assert affected == 6

    shadow_storage = MagicMock()
    shadow_storage.list_active_instances.return_value = []
    shadow_storage.create_shadow_instance = MagicMock()

    orch = SimpleNamespace()
    orch.storage = storage
    orch.shadow_manager = SimpleNamespace(storage=shadow_storage)

    engines = {strategy_id: MagicMock() for strategy_id in strategy_ids}
    result = asyncio.run(
        initialize_shadow_pool_impl(
            orch,
            engines,
            account_id="DEMO_MT5_001",
            variations_per_strategy=2,
        )
    )

    assert result["created"] == 6
    assert result["skipped_at_capacity"] == 0
    assert result["failed"] == 0
    assert shadow_storage.create_shadow_instance.call_count == 6


def test_pre_bootstrap_expiration_uses_sys_config_threshold() -> None:
    """Startup stale cleanup must honor sys_config threshold before pool bootstrap."""
    storage = MagicMock()
    storage.get_sys_config.return_value = {"shadow_stale_max_age_hours": "72"}
    storage.expire_stale_shadow_instances.return_value = 4

    expired = _expire_stale_shadow_instances_before_pool_bootstrap(storage)

    assert expired == 4
    storage.expire_stale_shadow_instances.assert_called_once_with(72)


def test_pre_bootstrap_expiration_runs_before_pool_capacity_check() -> None:
    """In single boot flow, stale expiration must execute before pool active-count check."""
    call_order: list[str] = []

    storage = MagicMock()
    storage.get_sys_config.return_value = {"shadow_stale_max_age_hours": 48}

    def _expire(max_age_hours: int) -> int:
        call_order.append(f"expire:{max_age_hours}")
        return 1

    storage.expire_stale_shadow_instances.side_effect = _expire
    storage.get_shadow_mode_strategy_ids.return_value = {"STRAT_SHADOW_1"}

    shadow_storage = MagicMock()

    def _list_active_instances():
        call_order.append("list_active_instances")
        return []

    shadow_storage.list_active_instances.side_effect = _list_active_instances
    shadow_storage.create_shadow_instance = MagicMock()

    orch = SimpleNamespace()
    orch.storage = storage
    orch.shadow_manager = SimpleNamespace(storage=shadow_storage)

    _expire_stale_shadow_instances_before_pool_bootstrap(storage)
    result = asyncio.run(
        initialize_shadow_pool_impl(
            orch,
            {"STRAT_SHADOW_1": MagicMock()},
            account_id="DEMO_MT5_001",
            variations_per_strategy=2,
        )
    )

    assert call_order[0] == "expire:48"
    assert call_order[1] == "list_active_instances"
    assert result["created"] == 2
    assert result["skipped_at_capacity"] == 0
