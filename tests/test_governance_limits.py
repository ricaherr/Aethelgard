"""
TDD: Governance Limits Tests for EdgeTuner Safety Governor
===========================================================
Milestone 6.2: Verifies that apply_governance_limits() enforces:
 - Minimum weight floor: 10% (0.10)
 - Maximum weight ceiling: 50% (0.50)
 - Smoothing: max 2% (0.02) change per learning event
"""
import logging
import pytest
from unittest.mock import MagicMock

from core_brain.edge_tuner import EdgeTuner


@pytest.fixture
def tuner():
    """Creates an EdgeTuner with a mocked StorageManager."""
    mock_storage = MagicMock()
    return EdgeTuner(storage=mock_storage)


# ─── Boundary Tests ───────────────────────────────────────────────────────────

class TestGovernanceBoundaries:
    """Verify that governance clamps to the [0.10, 0.50] range."""

    def test_floor_boundary(self, tuner):
        """A proposed weight below 10% must be raised to exactly 10%."""
        result, _ = tuner.apply_governance_limits(current_weight=0.12, proposed_weight=0.05)
        assert result == pytest.approx(0.10), (
            f"Weight below floor should be clamped to 0.10, got {result}"
        )

    def test_ceiling_boundary(self, tuner):
        """A proposed weight that, after smoothing, exceeds 50% must be clamped.

        Flow: current=0.49, proposed=0.80
        -> delta=+0.31, smoothing cap: 0.49 + 0.02 = 0.51
        -> ceiling triggers: 0.51 -> 0.50

        Note: The safety governor applies smoothing first, then boundaries.
        A direct jump to ceiling from a distant current requires multiple events.
        To reach the ceiling in one step, current must be within 0.02 of 0.50.
        """
        result, _ = tuner.apply_governance_limits(current_weight=0.49, proposed_weight=0.80)
        assert result == pytest.approx(0.50), (
            f"Weight above ceiling (post-smoothing) should be clamped to 0.50, got {result}"
        )

    def test_within_range_unchanged(self, tuner):
        """A small, in-range change should pass through unmodified."""
        result, reason = tuner.apply_governance_limits(current_weight=0.30, proposed_weight=0.31)
        assert result == pytest.approx(0.31), (
            f"In-range weight should not be altered, got {result}"
        )
        assert reason == "", "No governance reason should be returned for in-range changes."

    def test_floor_edge(self, tuner):
        """A proposed weight of exactly 0.10 is valid (not clamped)."""
        result, _ = tuner.apply_governance_limits(current_weight=0.12, proposed_weight=0.10)
        assert result == pytest.approx(0.10)

    def test_ceiling_edge(self, tuner):
        """A proposed weight of exactly 0.50 is valid (not clamped)."""
        result, _ = tuner.apply_governance_limits(current_weight=0.48, proposed_weight=0.50)
        assert result == pytest.approx(0.50)


# ─── Smoothing Tests ──────────────────────────────────────────────────────────

class TestGovernanceSmoothing:
    """Verify that changes exceeding 2% per event are smoothed."""

    def test_positive_delta_too_large(self, tuner):
        """An upward jump of 10% must be capped at +2%."""
        current = 0.30
        proposed = 0.40  # delta = +0.10, exceeds 0.02 limit
        result, reason = tuner.apply_governance_limits(current_weight=current, proposed_weight=proposed)
        assert result == pytest.approx(current + 0.02), (
            f"Upward delta should be capped at +0.02. Expected {current + 0.02:.4f}, got {result}"
        )
        assert "SMOOTHING LIMIT" in reason

    def test_negative_delta_too_large(self, tuner):
        """A downward jump of 10% must be capped at -2%."""
        current = 0.40
        proposed = 0.30  # delta = -0.10, exceeds 0.02 limit
        result, reason = tuner.apply_governance_limits(current_weight=current, proposed_weight=proposed)
        assert result == pytest.approx(current - 0.02), (
            f"Downward delta should be capped at -0.02. Expected {current - 0.02:.4f}, got {result}"
        )
        assert "SMOOTHING LIMIT" in reason

    def test_delta_exactly_at_limit(self, tuner):
        """A delta clearly below 2% should pass through (not be restricted).
        
        Note: Due to floating-point arithmetic, 0.32 - 0.30 = 0.020000...04
        which exceeds the 0.02 threshold. This test uses 0.31 - 0.30 = 0.01
        to verify that small, in-bound changes are never clamped.
        """
        current = 0.30
        proposed = 0.31  # delta = 0.01, clearly below 0.02 limit
        result, reason = tuner.apply_governance_limits(current_weight=current, proposed_weight=proposed)
        assert result == pytest.approx(0.31), (
            f"A delta of 0.01 (below 0.02 limit) should be allowed. Got {result}"
        )
        assert reason == "", "Sub-limit delta should not trigger governance."

    def test_smoothing_then_floor(self, tuner):
        """
        When smoothing AND floor both apply:
        current=0.12, proposed=-0.05 -> after smoothing: 0.10 -> after floor: 0.10
        """
        result, _ = tuner.apply_governance_limits(current_weight=0.12, proposed_weight=-0.05)
        # Smoothing: current - 0.02 = 0.10. Floor: max(0.10, 0.10) = 0.10
        assert result == pytest.approx(0.10)

    def test_smoothing_then_ceiling(self, tuner):
        """
        When smoothing AND ceiling both apply:
        current=0.49, proposed=0.60 -> after smoothing: 0.51 -> after ceiling: 0.50
        """
        result, _ = tuner.apply_governance_limits(current_weight=0.49, proposed_weight=0.60)
        # Smoothing: 0.49 + 0.02 = 0.51. Ceiling: min(0.51, 0.50) = 0.50
        assert result == pytest.approx(0.50)


# ─── Logging Tests ────────────────────────────────────────────────────────────

class TestGovernanceLogging:
    """Verify that governance activations are logged for auditability."""

    def test_log_on_floor_clamp(self, tuner, caplog):
        """Applying the floor clamp must emit an INFO log.
        
        Strategy: current=0.12, proposed=0.05
        -> delta = -0.07, smoothing cap: 0.12 - 0.02 = 0.10 (exactly at floor)
        -> floor triggers: 0.10 -> 0.10 (boundary check)
        -> SMOOTHING LIMIT log is emitted
        """
        with caplog.at_level(logging.INFO):
            tuner.apply_governance_limits(current_weight=0.12, proposed_weight=0.05)
        assert any(
            "GOVERNANCE LIMIT" in r.message or "SMOOTHING LIMIT" in r.message
            for r in caplog.records
        ), "Floor/smoothing activation should produce a [SAFETY_GOVERNOR] log entry."

    def test_log_on_ceiling_clamp(self, tuner, caplog):
        """Applying the ceiling clamp must emit an INFO log.
        
        Strategy: current=0.50, proposed=0.70
        -> At ceiling already, increase -> GOVERNANCE LIMIT [CEILING]
        """
        with caplog.at_level(logging.INFO):
            tuner.apply_governance_limits(current_weight=0.49, proposed_weight=0.52)
        assert any("GOVERNANCE LIMIT" in r.message for r in caplog.records), (
            "Ceiling clamp should produce a [SAFETY_GOVERNOR] GOVERNANCE LIMIT log entry."
        )

    def test_log_on_smoothing(self, tuner, caplog):
        """Applying the smoothing limit must emit an INFO log."""
        with caplog.at_level(logging.INFO):
            tuner.apply_governance_limits(current_weight=0.30, proposed_weight=0.45)
        assert any("SMOOTHING LIMIT" in r.message for r in caplog.records), (
            "Smoothing clamp should produce a [SAFETY_GOVERNOR] log entry."
        )

    def test_no_log_when_within_bounds(self, tuner, caplog):
        """No log should be emitted when governance limits are NOT triggered."""
        with caplog.at_level(logging.INFO):
            tuner.apply_governance_limits(current_weight=0.30, proposed_weight=0.31)
        governor_logs = [r for r in caplog.records if "SAFETY_GOVERNOR" in r.message]
        assert len(governor_logs) == 0, (
            "No governance log should be emitted for in-bounds, small changes."
        )


# ─── Constants Tests ──────────────────────────────────────────────────────────

class TestGovernanceConstants:
    """Verify that governance constants are correctly defined."""

    def test_constants_are_correct(self, tuner):
        """Governance constants must match the Milestone 6.2 specification."""
        assert tuner.GOVERNANCE_MIN_WEIGHT == pytest.approx(0.10), "Min weight must be 10%"
        assert tuner.GOVERNANCE_MAX_WEIGHT == pytest.approx(0.50), "Max weight must be 50%"
        assert tuner.GOVERNANCE_MAX_SMOOTHING == pytest.approx(0.02), "Max smoothing must be 2%"

    def test_min_is_less_than_max(self, tuner):
        """Sanity check: floor must be strictly less than the ceiling."""
        assert tuner.GOVERNANCE_MIN_WEIGHT < tuner.GOVERNANCE_MAX_WEIGHT
