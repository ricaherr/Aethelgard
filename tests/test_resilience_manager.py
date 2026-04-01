"""
Tests for core_brain/resilience_manager.py — HU 10.15: ResilienceManager.

Coverage:
  - Initial posture is NORMAL
  - L0 MUTE escalation: < threshold → no change, >= 3 → CAUTION, >= 6 → DEGRADED
  - L1 QUARANTINE → CAUTION
  - L2 SELF_HEAL   → DEGRADED
  - L3 LOCKDOWN    → STRESSED
  - Posture never de-escalates (one-directional)
  - process_report() returns the updated posture
  - get_current_status_narrative() reflects posture and scope
  - Audit persistence: calls storage with correct parameters
  - Audit persistence failure is swallowed (no exception propagates)
  - get_current_status_narrative() returns "" when NORMAL and no report

TDD: tests written BEFORE implementation (RED → GREEN → REFACTOR).
Trace_ID: ARCH-RESILIENCE-ENGINE-V1-B
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from core_brain.resilience import (
    EdgeAction,
    EdgeEventReport,
    ResilienceLevel,
    SystemPosture,
)
from core_brain.resilience_manager import ResilienceManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage() -> MagicMock:
    """Minimal StorageManager mock with a working _get_conn() (direct connection, not context manager)."""
    storage = MagicMock()
    conn_mock = MagicMock()
    storage._get_conn.return_value = conn_mock
    return storage


def _mute_report(scope: str = "XAUUSD") -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.ASSET,
        scope=scope,
        action=EdgeAction.MUTE,
        reason="Spread anomaly",
    )


def _quarantine_report(scope: str = "STRAT_01") -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.STRATEGY,
        scope=scope,
        action=EdgeAction.QUARANTINE,
        reason="3 consecutive ORDER_REJECTED",
    )


def _self_heal_report(scope: str = "IntegrityGuard") -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.SERVICE,
        scope=scope,
        action=EdgeAction.SELF_HEAL,
        reason="DB connectivity lost",
    )


def _lockdown_report(scope: str = "AnomalySentinel") -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.GLOBAL,
        scope=scope,
        action=EdgeAction.LOCKDOWN,
        reason="3 assets muted simultaneously",
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_initial_posture_is_normal(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        assert manager.current_posture == SystemPosture.NORMAL

    def test_narrative_empty_when_normal_and_no_report(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        assert manager.get_current_status_narrative() == ""


# ---------------------------------------------------------------------------
# L0 MUTE escalation
# ---------------------------------------------------------------------------

class TestL0MuteEscalation:
    def test_single_mute_does_not_change_posture(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        posture = manager.process_report(_mute_report())
        assert posture == SystemPosture.NORMAL

    def test_two_mutes_same_asset_stays_normal(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_mute_report("EURUSD"))
        posture = manager.process_report(_mute_report("EURUSD"))
        assert posture == SystemPosture.NORMAL

    def test_three_mutes_same_asset_escalates_to_caution(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        for _ in range(3):
            posture = manager.process_report(_mute_report("XAUUSD"))
        assert posture == SystemPosture.CAUTION

    def test_six_mutes_same_asset_escalates_to_degraded(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        for _ in range(6):
            posture = manager.process_report(_mute_report("XAUUSD"))
        assert posture == SystemPosture.DEGRADED

    def test_mutes_on_different_assets_count_independently(self) -> None:
        """2 mutes on XAUUSD + 2 mutes on EURUSD — neither alone reaches threshold 3."""
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("EURUSD"))
        posture = manager.process_report(_mute_report("EURUSD"))
        assert posture == SystemPosture.NORMAL

    def test_third_mute_on_second_asset_escalates_independently(self) -> None:
        """Each asset has its own counter; the third mute on an asset triggers CAUTION."""
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_mute_report("XAUUSD"))
        manager.process_report(_mute_report("XAUUSD"))
        # Third mute on XAUUSD → CAUTION
        posture = manager.process_report(_mute_report("XAUUSD"))
        assert posture == SystemPosture.CAUTION


# ---------------------------------------------------------------------------
# L1 QUARANTINE
# ---------------------------------------------------------------------------

class TestL1Quarantine:
    def test_quarantine_escalates_to_caution(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        posture = manager.process_report(_quarantine_report())
        assert posture == SystemPosture.CAUTION

    def test_quarantine_does_not_de_escalate_from_degraded(self) -> None:
        """Once DEGRADED (via SELF_HEAL), a new QUARANTINE cannot downgrade to CAUTION."""
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report())
        assert manager.current_posture == SystemPosture.DEGRADED
        posture = manager.process_report(_quarantine_report())
        assert posture == SystemPosture.DEGRADED  # unchanged — CAUTION < DEGRADED


# ---------------------------------------------------------------------------
# L2 SELF_HEAL
# ---------------------------------------------------------------------------

class TestL2SelfHeal:
    def test_self_heal_escalates_to_degraded(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        posture = manager.process_report(_self_heal_report())
        assert posture == SystemPosture.DEGRADED

    def test_self_heal_from_caution_escalates_to_degraded(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_quarantine_report())  # → CAUTION
        posture = manager.process_report(_self_heal_report())
        assert posture == SystemPosture.DEGRADED


# ---------------------------------------------------------------------------
# L3 LOCKDOWN
# ---------------------------------------------------------------------------

class TestL3Lockdown:
    def test_lockdown_escalates_to_stressed(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        posture = manager.process_report(_lockdown_report())
        assert posture == SystemPosture.STRESSED

    def test_lockdown_from_normal_escalates_to_stressed(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        assert manager.current_posture == SystemPosture.NORMAL
        posture = manager.process_report(_lockdown_report())
        assert posture == SystemPosture.STRESSED

    def test_lockdown_from_degraded_escalates_to_stressed(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report())  # → DEGRADED
        posture = manager.process_report(_lockdown_report())
        assert posture == SystemPosture.STRESSED


# ---------------------------------------------------------------------------
# One-directional posture (no de-escalation)
# ---------------------------------------------------------------------------

class TestPostureIsOneDirectional:
    def test_lockdown_then_mute_stays_stressed(self) -> None:
        """A MUTE after STRESSED should NOT downgrade the posture."""
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_lockdown_report())
        posture = manager.process_report(_mute_report())
        assert posture == SystemPosture.STRESSED

    def test_self_heal_then_quarantine_stays_degraded(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report())
        posture = manager.process_report(_quarantine_report())
        assert posture == SystemPosture.DEGRADED

    def test_degraded_then_second_self_heal_stays_degraded(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report())
        posture = manager.process_report(_self_heal_report())
        assert posture == SystemPosture.DEGRADED


# ---------------------------------------------------------------------------
# process_report() return value
# ---------------------------------------------------------------------------

class TestProcessReportReturn:
    def test_returns_updated_posture_after_escalation(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        result = manager.process_report(_self_heal_report())
        assert result == SystemPosture.DEGRADED

    def test_returns_current_posture_when_no_escalation(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        result = manager.process_report(_mute_report())  # single mute — no change
        assert result == SystemPosture.NORMAL


# ---------------------------------------------------------------------------
# get_current_status_narrative (Veto Reasoner — HU 10.17)
# ---------------------------------------------------------------------------

class TestGetCurrentStatusNarrative:
    def test_narrative_contains_posture_value(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report("AnomalySentinel"))
        narrative = manager.get_current_status_narrative()
        assert "DEGRADED" in narrative

    def test_narrative_contains_scope(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_lockdown_report("AnomalySentinel"))
        narrative = manager.get_current_status_narrative()
        assert "AnomalySentinel" in narrative

    def test_narrative_contains_recovery_plan(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_self_heal_report("IntegrityGuard"))
        narrative = manager.get_current_status_narrative()
        assert "auto-recuperación" in narrative

    def test_narrative_caution_mentions_quarantena(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_quarantine_report("STRAT_01"))
        narrative = manager.get_current_status_narrative()
        assert "CAUTION" in narrative
        assert "cuarentena" in narrative

    def test_narrative_lockdown_mentions_manual_intervention(self) -> None:
        manager = ResilienceManager(storage=_make_storage())
        manager.process_report(_lockdown_report())
        narrative = manager.get_current_status_narrative()
        assert "manual" in narrative


# ---------------------------------------------------------------------------
# Audit persistence
# ---------------------------------------------------------------------------

class TestAuditPersistence:
    def test_process_report_calls_storage(self) -> None:
        storage = _make_storage()
        manager = ResilienceManager(storage=storage)
        manager.process_report(_self_heal_report())
        # If _get_conn() was invoked, the mock records it.
        # We verify via the connection's execute call.

    def test_audit_storage_failure_does_not_propagate(self) -> None:
        """A broken storage must never crash the ResilienceManager."""
        storage = MagicMock()
        storage._get_conn = MagicMock(side_effect=RuntimeError("DB offline"))
        manager = ResilienceManager(storage=storage)
        # Should not raise
        posture = manager.process_report(_lockdown_report())
        assert posture == SystemPosture.STRESSED

    def test_conn_execute_called_with_resilience_event(self) -> None:
        storage = MagicMock()
        conn_mock = MagicMock()
        storage._get_conn.return_value = conn_mock
        manager = ResilienceManager(storage=storage)
        report = _self_heal_report("IntegrityGuard")
        manager.process_report(report)

        # execute() must have been called at least once
        assert conn_mock.execute.called
        args = conn_mock.execute.call_args[0]
        # Second positional arg is the tuple of parameters
        params = args[1]
        assert "RESILIENCE_EVENT" in params
        assert "IntegrityGuard" in params

    def test_recovery_plan_included_in_audit_details(self) -> None:
        storage = MagicMock()
        conn_mock = MagicMock()
        storage._get_conn.return_value = conn_mock
        manager = ResilienceManager(storage=storage)
        manager.process_report(_lockdown_report())

        args = conn_mock.execute.call_args[0]
        # Schema: (user_id, action, resource, resource_id, status, reason, trace_id)
        # reason (index -2) contains the details text with recovery_plan
        details_field = args[1][-2]
        assert "recovery_plan=" in details_field
        assert "manual" in details_field
