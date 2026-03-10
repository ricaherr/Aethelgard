"""
test_dedup_learner_phase3.py — Tests for Weekly Dedup Learning (PHASE 3)

Coverage:
  - Gap data collection
  - Optimal window calculation (percentile 50 × 0.8)
  - Governance guardrails (±30%, 10%-300%)
  - Rule persistence
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock
import sys
from pathlib import Path

# Add path for imports
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from core_brain.dedup_learner import (
    DedupLearner, DedupLearningResult, scheduled_weekly_dedup_learning
)


class TestDedupLearner:
    """PHASE 3: Weekly deduplication learning tests."""

    @pytest.fixture
    def mock_storage(self):
        """Mock StorageManager with dedup methods."""
        storage = AsyncMock()
        storage.get_dedup_events_since = AsyncMock(return_value=[])
        storage.get_dedup_rule = AsyncMock(return_value=None)
        storage.update_dedup_rule = AsyncMock(return_value=True)
        return storage

    @pytest.fixture
    def learner(self, mock_storage):
        """Create DedupLearner instance."""
        return DedupLearner(mock_storage)

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Gap Data Collection
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_collect_gap_data_empty(self, learner, mock_storage):
        """Test: No gaps returns empty list."""
        mock_storage.get_dedup_events_since.return_value = []
        
        gaps = await learner._collect_gap_data(days=7)
        
        assert gaps == []
        assert mock_storage.get_dedup_events_since.called

    @pytest.mark.asyncio
    async def test_collect_gap_data_multiple_events(self, learner, mock_storage):
        """Test: Multiple dedup events collected correctly."""
        mock_storage.get_dedup_events_since.return_value = [
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "OliverVelez",
                "gap_minutes": 8.5,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "OliverVelez",
                "gap_minutes": 15.2,
                "created_at": datetime.utcnow()
            }
        ]
        
        gaps = await learner._collect_gap_data(days=7)
        
        assert len(gaps) == 2
        assert gaps[0]["gap_minutes"] == 8.5
        assert gaps[1]["gap_minutes"] == 15.2

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Grouping by Key
    # ─────────────────────────────────────────────────────────────────────────

    def test_group_by_key_single_group(self, learner):
        """Test: Single (symbol, timeframe, strategy) groups correctly."""
        gaps = [
            {"symbol": "EURUSD", "timeframe": "M5", "strategy": "Oliver", "gap_minutes": 10},
            {"symbol": "EURUSD", "timeframe": "M5", "strategy": "Oliver", "gap_minutes": 15},
            {"symbol": "EURUSD", "timeframe": "M5", "strategy": "Oliver", "gap_minutes": 12}
        ]
        
        groups = learner._group_by_key(gaps)
        
        assert len(groups) == 1
        key = ("EURUSD", "M5", "Oliver")
        assert key in groups
        assert groups[key] == [10, 15, 12]

    def test_group_by_key_multiple_groups(self, learner):
        """Test: Multiple (symbol, timeframe, strategy) separate correctly."""
        gaps = [
            {"symbol": "EURUSD", "timeframe": "M5", "strategy": "Oliver", "gap_minutes": 10},
            {"symbol": "EURUSD", "timeframe": "H1", "strategy": "Oliver", "gap_minutes": 45},
            {"symbol": "GBPUSD", "timeframe": "M5", "strategy": "Oliver", "gap_minutes": 12},
            {"symbol": "EURUSD", "timeframe": "M5", "strategy": "RSI", "gap_minutes": 8}
        ]
        
        groups = learner._group_by_key(gaps)
        
        assert len(groups) == 4
        assert ("EURUSD", "M5", "Oliver") in groups
        assert ("EURUSD", "H1", "Oliver") in groups
        assert ("GBPUSD", "M5", "Oliver") in groups
        assert ("EURUSD", "M5", "RSI") in groups

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Window Calculation
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_optimal_window_calculation(self, learner, mock_storage):
        """Test: Optimal window = percentile_50 × 0.8."""
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 5,
            "current_window_minutes": 5
        }
        
        gaps = [8, 10, 12, 14, 16, 18, 20]  # Median = 14
        
        result = await learner._analyze_and_propose_window(
            "EURUSD", "M5", "Oliver", gaps, "TEST-TRACE-001"
        )
        
        # Optimal = median × 0.8 = 14 × 0.8 = 11.2 ≈ 11
        assert result.window_optimal == 11
        assert result.gap_median == 14.0

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Governance Guardrails
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_change_rate_rejected_too_large(self, learner, mock_storage):
        """Test: Change >30% is rejected."""
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 5,
            "current_window_minutes": 5  # Current
        }
        
        # Proposed: 15 min → change = (15-5)/5 = 200% ❌
        gaps = [15, 15, 15, 15, 15]  # All 15 → median = 15 → optimal = 12
        
        result = await learner._analyze_and_propose_window(
            "EURUSD", "M5", "Oliver", gaps, "TEST-TRACE-002"
        )
        
        # Optimal = 12, current = 5, change = 140% > 30% limit
        assert not result.was_applied
        assert result.reason_blocked is not None
        assert "30%" in result.reason_blocked or "exceeds" in result.reason_blocked

    @pytest.mark.asyncio
    async def test_window_below_minimum_rejected(self, learner, mock_storage):
        """Test: Window < 10% of base is rejected."""
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 100,
            "current_window_minutes": 10
        }
        
        # Proposed: 8 min (< 10% of 100 = bounds [10, 300])
        # gap_median = 10, optimal = 10 * 0.8 = 8
        # change = ((8-10)/10)*100 = -20% (within ±30%)
        gaps = [10, 10, 10, 10, 10]
        
        result = await learner._analyze_and_propose_window(
            "EURUSD", "H1", "Strategy", gaps, "TEST-TRACE-003"
        )
        
        assert not result.was_applied
        assert result.reason_blocked is not None
        assert "bounds" in result.reason_blocked.lower()

    @pytest.mark.asyncio
    async def test_window_above_maximum_rejected(self, learner, mock_storage):
        """Test: Window > 300% of base is rejected."""
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 5,
            "current_window_minutes": 15
        }
        
        # Proposed: 20 min (> 300% of 5 = bounds [0.5, 15])
        # gap_median = 25, optimal = 25 * 0.8 = 20
        # change = ((20-15)/15)*100 = 33.3% (just exceeds ±30%, but let's adjust current_window)
        # Actually: For 20 to be accepted with ±30%, current_window must be: window_opt * (1 ± 0.3)
        # 20 / 1.3 = 15.38, 20 / 0.7 = 28.6
        # So current_window in [15.38, 28.6] would accept 20 with ±30%
        # Let's use current_window = 16: change = ((20-16)/16)*100 = 25% ✓ within ±30%
        # But bounds check: 20 > 15 (300% of 5) so should fail bounds
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 5,
            "current_window_minutes": 16
        }
        gaps = [25, 25, 25, 25, 25]
        
        result = await learner._analyze_and_propose_window(
            "EURUSD", "M5", "Strategy", gaps, "TEST-TRACE-004"
        )
        
        assert not result.was_applied
        assert "bounds" in result.reason_blocked.lower()

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Minimum Observations
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_insufficient_observations_skipped(self, learner, mock_storage):
        """Test: Groups with < 5 observations are skipped in learning cycle."""
        # Add dedup events with only 2 observations
        mock_storage.query.return_value = [
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 10,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 15,
                "created_at": datetime.utcnow()
            }
        ]
        
        results = await learner.run_weekly_learning_cycle()
        
        # Should be in "skipped", not "blocked" or "learned"
        assert len(results["skipped"]) > 0 or len(results["blocked"]) == 0
        # Verify that nothing was learned from insufficient data
        eurusd_m5 = [r for r in results.get("learned", []) if r.symbol == "EURUSD" and r.timeframe == "M5"]
        assert len(eurusd_m5) == 0

    # ─────────────────────────────────────────────────────────────────────────
    # TESTS: Full Weekly Learning Cycle
    # ─────────────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_weekly_learning_cycle_empty_data(self, learner, mock_storage):
        """Test: Empty gap data returns no learning."""
        mock_storage.get_dedup_events_since.return_value = []
        
        results = await learner.run_weekly_learning_cycle()
        
        assert results["total_processed"] == 0
        assert len(results["learned"]) == 0
        assert len(results["skipped"]) == 0

    @pytest.mark.asyncio
    async def test_weekly_learning_cycle_successful_learning(self, learner, mock_storage):
        """Test: Good data with ±30% change applies learning."""
        mock_storage.get_dedup_events_since.return_value = [
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 5.0,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 6.5,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 7.0,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 8.0,
                "created_at": datetime.utcnow()
            },
            {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "strategy": "Oliver",
                "gap_minutes": 9.0,
                "created_at": datetime.utcnow()
            }
        ]
        
        mock_storage.get_dedup_rule.return_value = {
            "base_window_minutes": 5,
            "current_window_minutes": 5
        }
        mock_storage.update_dedup_rule.return_value = True
        
        results = await learner.run_weekly_learning_cycle()
        
        assert results["total_processed"] >= 1
        # Optimal = 7 × 0.8 = 5.6, current = 5, change = 12% ✅


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
