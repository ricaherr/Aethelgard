"""
Tests for core_brain/resilience.py — HU 10.14: Resilience Playbook & Interface Definition

Coverage:
  - All enum values match the canonical spec (docs/10_INFRA_RESILIENCY.md §E14)
  - EdgeEventReport instantiation and auto trace_id generation
  - ResilienceInterface enforces ABC contract
  - check_health() returns None when healthy (concrete subclass)
  - check_health() returns EdgeEventReport when a problem is detected

TDD order: tests written BEFORE final code adjustment.
Trace_ID: ARCH-RESILIENCE-ENGINE-V1-A
"""

import pytest
from typing import Optional

from core_brain.resilience import (
    ResilienceLevel,
    EdgeAction,
    SystemPosture,
    EdgeEventReport,
    ResilienceInterface,
)


# ---------------------------------------------------------------------------
# ResilienceLevel
# ---------------------------------------------------------------------------

class TestResilienceLevel:
    def test_asset_value(self) -> None:
        assert ResilienceLevel.ASSET.value == "L0"

    def test_strategy_value(self) -> None:
        assert ResilienceLevel.STRATEGY.value == "L1"

    def test_service_value(self) -> None:
        assert ResilienceLevel.SERVICE.value == "L2"

    def test_global_value(self) -> None:
        assert ResilienceLevel.GLOBAL.value == "L3"

    def test_exactly_four_levels(self) -> None:
        assert len(ResilienceLevel) == 4


# ---------------------------------------------------------------------------
# EdgeAction
# ---------------------------------------------------------------------------

class TestEdgeAction:
    def test_mute_value(self) -> None:
        assert EdgeAction.MUTE.value == "MUTE"

    def test_quarantine_value(self) -> None:
        assert EdgeAction.QUARANTINE.value == "QUARANTINE"

    def test_self_heal_value(self) -> None:
        assert EdgeAction.SELF_HEAL.value == "SELF_HEAL"

    def test_lockdown_value(self) -> None:
        assert EdgeAction.LOCKDOWN.value == "LOCKDOWN"

    def test_exactly_four_actions(self) -> None:
        assert len(EdgeAction) == 4

    def test_no_none_action(self) -> None:
        """NONE is not part of the canonical spec — absence is expressed by returning None from check_health()."""
        with pytest.raises(AttributeError):
            _ = EdgeAction.NONE  # type: ignore[attr-defined]

    def test_no_degrade_action(self) -> None:
        """DEGRADE is not part of the canonical spec — replaced by SELF_HEAL at L2."""
        with pytest.raises(AttributeError):
            _ = EdgeAction.DEGRADE  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# SystemPosture
# ---------------------------------------------------------------------------

class TestSystemPosture:
    def test_exactly_four_postures(self) -> None:
        assert len(SystemPosture) == 4

    def test_normal_value(self) -> None:
        assert SystemPosture.NORMAL.value == "NORMAL"

    def test_caution_value(self) -> None:
        assert SystemPosture.CAUTION.value == "CAUTION"

    def test_degraded_value(self) -> None:
        assert SystemPosture.DEGRADED.value == "DEGRADED"

    def test_stressed_value(self) -> None:
        assert SystemPosture.STRESSED.value == "STRESSED"


# ---------------------------------------------------------------------------
# EdgeEventReport
# ---------------------------------------------------------------------------

class TestEdgeEventReport:
    def test_instantiation_with_required_fields(self) -> None:
        report = EdgeEventReport(
            level=ResilienceLevel.ASSET,
            scope="XAUUSD",
            action=EdgeAction.MUTE,
            reason="Spread anomaly detected",
        )
        assert report.level == ResilienceLevel.ASSET
        assert report.scope == "XAUUSD"
        assert report.action == EdgeAction.MUTE
        assert report.reason == "Spread anomaly detected"

    def test_trace_id_auto_generated(self) -> None:
        report = EdgeEventReport(
            level=ResilienceLevel.STRATEGY,
            scope="STRAT_01",
            action=EdgeAction.QUARANTINE,
            reason="Profit factor drift > 30%",
        )
        assert report.trace_id.startswith("EDGE-")
        assert len(report.trace_id) == 13  # "EDGE-" (5) + 8 hex chars

    def test_trace_id_unique_per_instance(self) -> None:
        r1 = EdgeEventReport(
            level=ResilienceLevel.SERVICE,
            scope="AnomalySentinel",
            action=EdgeAction.SELF_HEAL,
            reason="Socket timeout",
        )
        r2 = EdgeEventReport(
            level=ResilienceLevel.SERVICE,
            scope="AnomalySentinel",
            action=EdgeAction.SELF_HEAL,
            reason="Socket timeout",
        )
        assert r1.trace_id != r2.trace_id

    def test_custom_trace_id_accepted(self) -> None:
        report = EdgeEventReport(
            level=ResilienceLevel.GLOBAL,
            scope="GLOBAL",
            action=EdgeAction.LOCKDOWN,
            reason="3 assets muted simultaneously",
            trace_id="EDGE-CUSTOM01",
        )
        assert report.trace_id == "EDGE-CUSTOM01"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        report = EdgeEventReport(
            level=ResilienceLevel.ASSET,
            scope="EURUSD",
            action=EdgeAction.MUTE,
            reason="Stale tick",
        )
        assert report.metadata == {}

    def test_metadata_accepts_free_form_data(self) -> None:
        report = EdgeEventReport(
            level=ResilienceLevel.ASSET,
            scope="EURUSD",
            action=EdgeAction.MUTE,
            reason="Stale tick",
            metadata={"staleness_seconds": 320, "threshold": 300},
        )
        assert report.metadata["staleness_seconds"] == 320

    def test_not_frozen(self) -> None:
        """EdgeEventReport is NOT frozen — ResilienceManager may annotate it."""
        report = EdgeEventReport(
            level=ResilienceLevel.ASSET,
            scope="XAUUSD",
            action=EdgeAction.MUTE,
            reason="Test",
        )
        report.metadata["annotated_by"] = "ResilienceManager"
        assert report.metadata["annotated_by"] == "ResilienceManager"


# ---------------------------------------------------------------------------
# ResilienceInterface
# ---------------------------------------------------------------------------

class TestResilienceInterface:
    def test_cannot_instantiate_abstract_class(self) -> None:
        with pytest.raises(TypeError):
            ResilienceInterface()  # type: ignore[abstract]

    def test_concrete_subclass_healthy_returns_none(self) -> None:
        class HealthyComponent(ResilienceInterface):
            def check_health(self) -> Optional[EdgeEventReport]:
                return None

        component = HealthyComponent()
        assert component.check_health() is None

    def test_concrete_subclass_unhealthy_returns_report(self) -> None:
        class UnhealthyComponent(ResilienceInterface):
            def check_health(self) -> Optional[EdgeEventReport]:
                return EdgeEventReport(
                    level=ResilienceLevel.SERVICE,
                    scope="UnhealthyComponent",
                    action=EdgeAction.SELF_HEAL,
                    reason="Internal buffer overflow",
                )

        component = UnhealthyComponent()
        report = component.check_health()
        assert report is not None
        assert report.action == EdgeAction.SELF_HEAL
        assert report.level == ResilienceLevel.SERVICE

    def test_subclass_missing_check_health_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            class IncompleteComponent(ResilienceInterface):
                pass  # Does not implement check_health

            IncompleteComponent()  # type: ignore[abstract]

    def test_check_health_signature_returns_optional(self) -> None:
        """check_health() returning None must be treated as 'all healthy'."""
        class SilentComponent(ResilienceInterface):
            def check_health(self) -> Optional[EdgeEventReport]:
                return None

        assert SilentComponent().check_health() is None
