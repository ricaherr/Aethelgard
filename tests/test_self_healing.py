"""
tests/test_self_healing.py — HU 10.16: Self-Healing Playbook & Correlation Engine.

Coverage:
  CorrelationEngine
    - ≥3 distinct L0 assets muted in 60s → L3/STRESSED (cascade)
    - Same asset repeated 3× does NOT trigger cascade (only 1 distinct)
    - Only 2 distinct assets → no cascade
    - Events outside 60s window are pruned and do not count

  RootCauseDiagnosis
    - 2 L1/QUARANTINE failures on same DataProvider → upgrade to L2/DEGRADED
    - Single L1 failure with provider → stays CAUTION
    - L1 failure without provider → no upgrade

  SelfHealingPlaybook — Check_Data_Coherence
    - reconnect_provider called on each attempt
    - reconnect called EXACTLY 3 times before giving up (core contract)
    - STRESSED only after 3rd failure, NOT before
    - Successful reconnect resets the attempt counter

  SelfHealingPlaybook — Check_Database
    - clear_db_cache called before reconnect
    - call order: clear_cache → reconnect
    - STRESSED after 3 failures

  SelfHealingPlaybook — Spread_Anomaly
    - Cooldown registered after report
    - is_in_cooldown True during active cooldown
    - is_in_cooldown False for unknown scope
    - is_in_cooldown False after expiry

  is_healing property
    - False initially
    - False after healing completes (sync resets)

TDD: RED → GREEN | Trace_ID: ARCH-RESILIENCE-ENGINE-V1-C
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from core_brain.resilience import (
    EdgeAction,
    EdgeEventReport,
    ResilienceLevel,
    SystemPosture,
)
from core_brain.resilience_manager import (
    ISSUE_DATA_COHERENCE,
    ISSUE_DATABASE,
    ISSUE_SPREAD_ANOMALY,
    ResilienceManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage() -> MagicMock:
    storage = MagicMock()
    conn_mock = MagicMock()
    storage._get_conn.return_value = conn_mock
    return storage


def _make_manager(
    reconnect_fn=None,
    clear_cache_fn=None,
) -> ResilienceManager:
    return ResilienceManager(
        storage=_make_storage(),
        reconnect_provider_fn=reconnect_fn,
        clear_db_cache_fn=clear_cache_fn,
    )


def _mute_report(scope: str, issue_type: str | None = None) -> EdgeEventReport:
    meta = {"issue_type": issue_type} if issue_type else {}
    return EdgeEventReport(
        level=ResilienceLevel.ASSET,
        scope=scope,
        action=EdgeAction.MUTE,
        reason="Test mute",
        metadata=meta,
    )


def _quarantine_report(scope: str, provider: str | None = None) -> EdgeEventReport:
    meta = {"data_provider": provider} if provider else {}
    return EdgeEventReport(
        level=ResilienceLevel.STRATEGY,
        scope=scope,
        action=EdgeAction.QUARANTINE,
        reason="Test quarantine",
        metadata=meta,
    )


def _self_heal_report(scope: str, issue_type: str) -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.SERVICE,
        scope=scope,
        action=EdgeAction.SELF_HEAL,
        reason="Test self-heal",
        metadata={"issue_type": issue_type},
    )


# ---------------------------------------------------------------------------
# Correlation Engine
# ---------------------------------------------------------------------------

class TestCorrelationEngine:

    def test_three_distinct_assets_escalates_to_stressed(self) -> None:
        """≥3 distinct L0 assets muted in window → STRESSED (systemic cascade)."""
        manager = _make_manager()
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("EURUSD"))
        manager.process_report(_mute_report("GBPUSD"))
        assert manager.current_posture == SystemPosture.STRESSED

    def test_two_distinct_assets_does_not_escalate_to_stressed(self) -> None:
        manager = _make_manager()
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("EURUSD"))
        assert manager.current_posture != SystemPosture.STRESSED

    def test_same_asset_three_times_does_not_trigger_cascade(self) -> None:
        """3 MUTEs on the same asset = 1 distinct → no cascade; standard CAUTION."""
        manager = _make_manager()
        for _ in range(3):
            manager.process_report(_mute_report("XAUUSD"))
        assert manager.current_posture == SystemPosture.CAUTION

    def test_events_outside_window_are_pruned(self) -> None:
        """Two stale events (>60s ago) must not count toward the cascade threshold."""
        manager = _make_manager()
        now = time.monotonic()
        manager._l0_mute_window = [
            (now - 70.0, "XAUUSD"),
            (now - 65.0, "EURUSD"),
        ]
        manager.process_report(_mute_report("GBPUSD"))
        # Only GBPUSD is within the fresh window → 1 distinct, no cascade
        assert manager.current_posture != SystemPosture.STRESSED

    def test_cascade_clears_window_to_avoid_re_trigger(self) -> None:
        """After cascade fires, the window is cleared."""
        manager = _make_manager()
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("EURUSD"))
        manager.process_report(_mute_report("GBPUSD"))
        assert len(manager._l0_mute_window) == 0


# ---------------------------------------------------------------------------
# Root Cause Diagnosis
# ---------------------------------------------------------------------------

class TestRootCauseDiagnosis:

    def test_two_l1_quarantines_same_provider_upgrades_to_degraded(self) -> None:
        """Shared DataProvider on 2nd quarantine → L2 upgrade → DEGRADED."""
        manager = _make_manager()
        manager.process_report(_quarantine_report("STRAT_01", provider="MT5_FEED"))
        posture = manager.process_report(_quarantine_report("STRAT_02", provider="MT5_FEED"))
        assert posture == SystemPosture.DEGRADED

    def test_single_l1_quarantine_with_provider_stays_caution(self) -> None:
        manager = _make_manager()
        posture = manager.process_report(_quarantine_report("STRAT_01", provider="MT5_FEED"))
        assert posture == SystemPosture.CAUTION

    def test_quarantine_without_provider_not_upgraded(self) -> None:
        manager = _make_manager()
        posture = manager.process_report(_quarantine_report("STRAT_01"))
        assert posture == SystemPosture.CAUTION

    def test_different_providers_do_not_cross_trigger(self) -> None:
        """Two L1 failures with different providers should NOT trigger L2 upgrade."""
        manager = _make_manager()
        manager.process_report(_quarantine_report("STRAT_01", provider="FEED_A"))
        posture = manager.process_report(_quarantine_report("STRAT_02", provider="FEED_B"))
        assert posture == SystemPosture.CAUTION


# ---------------------------------------------------------------------------
# Self-Healing — Check_Data_Coherence
# ---------------------------------------------------------------------------

class TestHealDataCoherence:

    def test_reconnect_called_on_first_attempt(self) -> None:
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect)
        manager.process_report(_self_heal_report("DP", ISSUE_DATA_COHERENCE))
        reconnect.assert_called_once()

    def test_reconnect_called_exactly_3_times_before_giving_up(self) -> None:
        """Core contract: manager retries exactly 3 times before escalating."""
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect)
        report = _self_heal_report("DP", ISSUE_DATA_COHERENCE)
        for _ in range(3):
            manager.process_report(report)
        assert reconnect.call_count == 3
        assert manager.current_posture == SystemPosture.STRESSED

    def test_no_stressed_before_third_attempt(self) -> None:
        """STRESSED must NOT be reached before the 3rd retry is exhausted."""
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect)
        report = _self_heal_report("DP", ISSUE_DATA_COHERENCE)
        manager.process_report(report)   # attempt 1
        manager.process_report(report)   # attempt 2
        assert manager.current_posture == SystemPosture.DEGRADED

    def test_third_failure_escalates_to_stressed(self) -> None:
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect)
        report = _self_heal_report("DP", ISSUE_DATA_COHERENCE)
        for _ in range(3):
            manager.process_report(report)
        assert manager.current_posture == SystemPosture.STRESSED

    def test_success_resets_attempt_counter(self) -> None:
        """A successful reconnect must reset the counter for that scope."""
        reconnect = MagicMock(return_value=True)
        manager = _make_manager(reconnect_fn=reconnect)
        manager.process_report(_self_heal_report("DP", ISSUE_DATA_COHERENCE))
        assert manager._healing_attempts["data_coherence:DP"] == 0

    def test_success_does_not_escalate_to_stressed(self) -> None:
        reconnect = MagicMock(return_value=True)
        manager = _make_manager(reconnect_fn=reconnect)
        manager.process_report(_self_heal_report("DP", ISSUE_DATA_COHERENCE))
        assert manager.current_posture != SystemPosture.STRESSED

    def test_exception_in_reconnect_counts_as_failure(self) -> None:
        """An exception from reconnect_provider is treated as a failed attempt."""
        reconnect = MagicMock(side_effect=RuntimeError("connection refused"))
        manager = _make_manager(reconnect_fn=reconnect)
        report = _self_heal_report("DP", ISSUE_DATA_COHERENCE)
        for _ in range(3):
            manager.process_report(report)
        assert manager.current_posture == SystemPosture.STRESSED


# ---------------------------------------------------------------------------
# Self-Healing — Check_Database
# ---------------------------------------------------------------------------

class TestHealDatabase:

    def test_clear_cache_called_on_db_heal(self) -> None:
        clear_cache = MagicMock()
        reconnect = MagicMock(return_value=True)
        manager = _make_manager(reconnect_fn=reconnect, clear_cache_fn=clear_cache)
        manager.process_report(_self_heal_report("DB", ISSUE_DATABASE))
        clear_cache.assert_called_once()

    def test_reconnect_called_after_clear_cache(self) -> None:
        """clear_db_cache must execute before reconnect_provider."""
        call_order: list[str] = []
        clear_cache = MagicMock(side_effect=lambda: call_order.append("clear"))
        reconnect = MagicMock(
            side_effect=lambda: call_order.append("reconnect") or True
        )
        manager = _make_manager(reconnect_fn=reconnect, clear_cache_fn=clear_cache)
        manager.process_report(_self_heal_report("DB", ISSUE_DATABASE))
        assert call_order == ["clear", "reconnect"]

    def test_db_heal_exhaustion_escalates_to_stressed(self) -> None:
        clear_cache = MagicMock()
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect, clear_cache_fn=clear_cache)
        report = _self_heal_report("DB", ISSUE_DATABASE)
        for _ in range(3):
            manager.process_report(report)
        assert manager.current_posture == SystemPosture.STRESSED

    def test_db_heal_success_resets_counter(self) -> None:
        clear_cache = MagicMock()
        reconnect = MagicMock(return_value=True)
        manager = _make_manager(reconnect_fn=reconnect, clear_cache_fn=clear_cache)
        manager.process_report(_self_heal_report("DB", ISSUE_DATABASE))
        assert manager._healing_attempts["database:DB"] == 0


# ---------------------------------------------------------------------------
# Self-Healing — Spread_Anomaly cooldown
# ---------------------------------------------------------------------------

class TestSpreadAnomalyCooldown:

    def test_spread_anomaly_registers_cooldown(self) -> None:
        manager = _make_manager()
        manager.process_report(_mute_report("XAUUSD", issue_type=ISSUE_SPREAD_ANOMALY))
        assert manager.is_in_cooldown("XAUUSD")

    def test_asset_without_cooldown_not_in_cooldown(self) -> None:
        manager = _make_manager()
        assert not manager.is_in_cooldown("EURUSD")

    def test_expired_cooldown_is_not_active(self) -> None:
        """A cooldown whose end_time is in the past must return False."""
        manager = _make_manager()
        manager._cooldowns["XAUUSD"] = time.monotonic() - 1.0
        assert not manager.is_in_cooldown("XAUUSD")

    def test_spread_cooldown_does_not_escalate_posture(self) -> None:
        """Spread_Anomaly cooldown is informational; normal MUTE escalation applies."""
        manager = _make_manager()
        # One MUTE with spread issue → still only 1 mute for XAUUSD → NORMAL
        manager.process_report(_mute_report("XAUUSD", issue_type=ISSUE_SPREAD_ANOMALY))
        assert manager.current_posture == SystemPosture.NORMAL


# ---------------------------------------------------------------------------
# is_healing property
# ---------------------------------------------------------------------------

class TestIsHealingProperty:

    def test_is_healing_false_initially(self) -> None:
        manager = _make_manager()
        assert manager.is_healing is False

    def test_is_healing_false_after_successful_reconnect(self) -> None:
        reconnect = MagicMock(return_value=True)
        manager = _make_manager(reconnect_fn=reconnect)
        manager.process_report(_self_heal_report("DP", ISSUE_DATA_COHERENCE))
        assert manager.is_healing is False

    def test_is_healing_false_after_failed_reconnect(self) -> None:
        reconnect = MagicMock(return_value=False)
        manager = _make_manager(reconnect_fn=reconnect)
        manager.process_report(_self_heal_report("DP", ISSUE_DATA_COHERENCE))
        assert manager.is_healing is False
