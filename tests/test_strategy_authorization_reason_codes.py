import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from core_brain.orchestrators._lifecycle import is_strategy_authorized_for_execution


@pytest.mark.parametrize(
    "execution_mode, expected_allowed, expected_reason",
    [
        ("SHADOW", True, "auth_shadow_demo"),
        ("LIVE", True, "auth_live"),
        ("QUARANTINE", False, "strategy_not_authorized"),
        ("BACKTEST", False, "strategy_not_authorized"),
    ],
)
def test_strategy_authorization_emits_reason_code(
    execution_mode: str,
    expected_allowed: bool,
    expected_reason: str,
) -> None:
    orch = SimpleNamespace(storage=MagicMock())
    orch.storage.get_signal_ranking.return_value = {"execution_mode": execution_mode}
    signal = SimpleNamespace(strategy="STRAT_X")

    allowed, reason = is_strategy_authorized_for_execution(orch, signal, with_reason=True)

    assert allowed is expected_allowed
    assert reason == expected_reason


def test_strategy_authorization_emits_error_reason_code() -> None:
    orch = SimpleNamespace(storage=MagicMock())
    orch.storage.get_signal_ranking.side_effect = RuntimeError("db error")
    signal = SimpleNamespace(strategy="STRAT_ERR")

    allowed, reason = is_strategy_authorized_for_execution(orch, signal, with_reason=True)

    assert allowed is False
    assert reason == "strategy_auth_error"
