import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from core_brain.orchestrators._lifecycle import is_strategy_authorized_for_execution
from core_brain.strategy_gatekeeper import StrategyGatekeeper


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


# ── HU 5.5: Gatekeeper reason codes ──────────────────────────────────────────


@pytest.mark.parametrize(
    "asset, whitelist, scores, min_threshold, strategy_id, expected_allowed, expected_reason",
    [
        # Score above threshold, no whitelist → approved
        ("EURUSD", None, {"EURUSD": 0.85}, 0.5, "STRAT_A", True, "gk_approved"),
        # Score below threshold → rejected with specific code
        ("GBPUSD", None, {"GBPUSD": 0.30}, 0.5, "STRAT_A", False, "gk_score_below_threshold"),
        # Asset not in whitelist → rejected with specific code
        ("AUDUSD", ["EURUSD", "GBPUSD"], {"AUDUSD": 0.90}, 0.5, "STRAT_B", False, "gk_whitelist_reject"),
        # In whitelist, score above threshold → approved
        ("EURUSD", ["EURUSD"], {"EURUSD": 0.70}, 0.5, "STRAT_B", True, "gk_approved"),
        # Unknown asset (no score) → score=0.0 < threshold → rejected
        ("XAUUSD", None, {}, 0.1, "STRAT_C", False, "gk_score_below_threshold"),
    ],
)
def test_strategy_gatekeeper_rejections_keep_deterministic_codes(
    asset: str,
    whitelist,
    scores: dict,
    min_threshold: float,
    strategy_id: str,
    expected_allowed: bool,
    expected_reason: str,
) -> None:
    """
    TDD HU5.5: StrategyGatekeeper.can_execute_on_tick_with_reason() debe emitir
    reason codes determinísticos: gk_approved | gk_whitelist_reject | gk_score_below_threshold.
    """
    storage_mock = MagicMock()
    storage_mock.get_strategy_affinity_scores.return_value = scores

    gk = StrategyGatekeeper(storage=storage_mock)

    if whitelist is not None:
        gk.set_market_whitelist(strategy_id, whitelist)

    allowed, reason = gk.can_execute_on_tick_with_reason(
        asset=asset, min_threshold=min_threshold, strategy_id=strategy_id
    )

    assert allowed is expected_allowed
    assert reason == expected_reason
