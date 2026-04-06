from unittest.mock import MagicMock

from start import _ensure_exec_capable_account


def test_exec_seed_skips_when_exec_account_exists() -> None:
    storage = MagicMock()
    storage.get_sys_broker_accounts.return_value = [
        {"account_id": "ACC1", "supports_exec": 1, "enabled": 1}
    ]

    created = _ensure_exec_capable_account(storage)

    assert created is False
    storage.save_broker_account.assert_not_called()
    storage.execute_update.assert_not_called()


def test_exec_seed_creates_fallback_when_no_exec_account_exists() -> None:
    storage = MagicMock()
    storage.get_sys_broker_accounts.return_value = [
        {"account_id": "ACC_DATA", "supports_exec": 0, "enabled": 1}
    ]

    created = _ensure_exec_capable_account(storage)

    assert created is True
    storage.save_broker_account.assert_called_once()
    save_kwargs = storage.save_broker_account.call_args.kwargs
    assert save_kwargs["id"] == "SYS_EXEC_DEMO_AUTO"
    assert save_kwargs["platform_id"] == "mt5"
    assert save_kwargs["enabled"] is True

    storage.execute_update.assert_called_once()
    sql = storage.execute_update.call_args.args[0]
    assert "supports_exec = 1" in sql


def test_exec_seed_handles_storage_error_gracefully() -> None:
    storage = MagicMock()
    storage.get_sys_broker_accounts.side_effect = RuntimeError("db down")

    created = _ensure_exec_capable_account(storage)

    assert created is False