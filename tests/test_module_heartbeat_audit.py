from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from data_vault.system_db import SystemMixin


class _DummySystem(SystemMixin):
    """Minimal dummy to exercise SystemMixin heartbeat logic with mocks."""


def test_update_module_heartbeat_logs_audit_when_interval_elapsed() -> None:
    dummy = _DummySystem.__new__(_DummySystem)
    dummy.update_sys_config = MagicMock()
    dummy.get_sys_config = MagicMock(return_value={"heartbeat_audit_interval_s": 120})
    dummy.log_audit_event = MagicMock()

    SystemMixin.update_module_heartbeat(dummy, "orchestrator")

    # heartbeat key always written
    first_update_payload = dummy.update_sys_config.call_args_list[0].args[0]
    assert "heartbeat_orchestrator" in first_update_payload

    # throttled audit marker should also be written
    all_payloads = [c.args[0] for c in dummy.update_sys_config.call_args_list]
    assert any("heartbeat_audit_last_orchestrator" in p for p in all_payloads)

    dummy.log_audit_event.assert_called_once()
    kwargs = dummy.log_audit_event.call_args.kwargs
    assert kwargs["action"] == "HEARTBEAT"
    assert kwargs["resource"] == "orchestrator"


def test_update_module_heartbeat_skips_audit_when_recently_logged() -> None:
    recent = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()

    dummy = _DummySystem.__new__(_DummySystem)
    dummy.update_sys_config = MagicMock()
    dummy.get_sys_config = MagicMock(
        return_value={
            "heartbeat_audit_interval_s": 120,
            "heartbeat_audit_last_orchestrator": recent,
        }
    )
    dummy.log_audit_event = MagicMock()
    dummy._heartbeat_audit_bootstrap_written = {"orchestrator"}

    SystemMixin.update_module_heartbeat(dummy, "orchestrator")

    dummy.log_audit_event.assert_not_called()
