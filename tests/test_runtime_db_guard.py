from data_vault.runtime_db_guard import _is_allowed_caller


def test_guard_allows_manager_and_legacy_callers() -> None:
    legacy_allowed = {"core_brain/legacy_runtime.py"}

    assert _is_allowed_caller("data_vault/database_manager.py", legacy_allowed)
    assert _is_allowed_caller("core_brain/legacy_runtime.py", legacy_allowed)


def test_guard_blocks_new_runtime_callers() -> None:
    legacy_allowed = {"core_brain/legacy_runtime.py"}

    assert not _is_allowed_caller("core_brain/new_hot_path.py", legacy_allowed)
