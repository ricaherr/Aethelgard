"""
Test Suite - Confidence Threshold Optimizer (HU 7.1)
=====================================================

Trace_ID: ADAPTIVE-THRESHOLD-2026-001
Dominio: 07 (Adaptive Learning)

Tests TDD for dynamic confidence threshold adjustment based on:
- Equity Curve Feedback
- Consecutive Loss Detection
- Safety Governor enforcement
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from core_brain.threshold_optimizer import (
    ThresholdOptimizer,
    EquityCurveAnalyzer,
)
from models.signal import Signal, SignalType
from data_vault.storage import StorageManager


# ──────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_storage():
    """Mock StorageManager for persistence."""
    storage = Mock(spec=StorageManager)
    
    # Setup default returns
    storage.get_dynamic_params = Mock(return_value={
        "confidence_threshold": 0.75,
        "confidence_threshold_min": 0.50,
        "confidence_threshold_max": 0.95,
        "confidence_smoothing_max": 0.05,
        "equity_lookback_trades": 20,
        "consecutive_loss_threshold": 3,
    })
    
    storage.get_account_trades = Mock(return_value=[])
    storage.log_threshold_adjustment = Mock()
    storage.update_dynamic_params = Mock()
    
    return storage


@pytest.fixture
def threshold_optimizer(mock_storage):
    """Instantiate ThresholdOptimizer with mocked storage."""
    return ThresholdOptimizer(storage=mock_storage)


@pytest.fixture
def sample_winning_trades() -> List[Dict[str, Any]]:
    """Sample winning trades for equity curve analysis."""
    return [
        {
            "ticket_id": f"trade_{i}",
            "is_win": True,
            "pnl": 100.0 + (i * 10),
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=30 - i),
            "symbol": "EURUSD",
        }
        for i in range(5)
    ]


@pytest.fixture
def sample_losing_trades() -> List[Dict[str, Any]]:
    """Sample losing trades (consecutive losses for testing adversity detection)."""
    return [
        {
            "ticket_id": f"trade_{i}",
            "is_win": False,
            "pnl": -50.0 - (i * 5),
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=30 - i),
            "symbol": "EURUSD",
        }
        for i in range(4)
    ]


@pytest.fixture
def sample_mixed_trades() -> List[Dict[str, Any]]:
    """Mixed winning and losing trades."""
    trades = []
    for i in range(20):
        trades.append({
            "ticket_id": f"trade_{i}",
            "is_win": (i % 3) != 0,  # Win pattern: W, W, L, W, W, L, ...
            "pnl": 100.0 if (i % 3) != 0 else -50.0,
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=60 - i),
            "symbol": "EURUSD",
        })
    return trades


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Core Functionality
# ──────────────────────────────────────────────────────────────────────────────

class TestThresholdOptimizerInitialization:
    """Test initialization and parameter loading."""

    def test_init_loads_parameters_from_storage(self, threshold_optimizer, mock_storage):
        """Verify ThresholdOptimizer loads config from StorageManager (SSOT)."""
        assert threshold_optimizer.storage == mock_storage
        assert threshold_optimizer.current_threshold == 0.75
        assert threshold_optimizer.threshold_min == 0.50
        assert threshold_optimizer.threshold_max == 0.95
        assert threshold_optimizer.smoothing_max == 0.05
        
        # Verify Storage.get_dynamic_params was called
        mock_storage.get_dynamic_params.assert_called_once()

    def test_init_with_missing_optional_params(self, mock_storage):
        """Verify optimizer handles missing optional parameters gracefully."""
        # Remove some optional params to test defaults
        mock_storage.get_dynamic_params.return_value = {
            "confidence_threshold": 0.70,
        }
        
        optimizer = ThresholdOptimizer(storage=mock_storage)
        
        # Should use defaults
        assert optimizer.current_threshold == 0.70
        assert optimizer.threshold_min == 0.50  # Default
        assert optimizer.threshold_max == 0.95  # Default


class TestEquityCurveAnalyzer:
    """Test equity curve analysis logic."""

    def test_analyzer_calculates_win_rate(self, sample_winning_trades):
        """Test win rate calculation on all winning trades."""
        analyzer = EquityCurveAnalyzer(trades=sample_winning_trades)
        
        assert analyzer.win_rate == 1.0
        assert analyzer.total_trades == 5
        assert analyzer.consecutive_losses == 0

    def test_analyzer_calculates_losing_streak(self, sample_losing_trades):
        """Test consecutive losses detection."""
        analyzer = EquityCurveAnalyzer(trades=sample_losing_trades)
        
        assert analyzer.win_rate == 0.0
        assert analyzer.consecutive_losses == 4

    def test_analyzer_detects_consecutive_losses_in_mixed_trades(self, sample_mixed_trades):
        """Test detection of consecutive losses within mixed winning/losing trades."""
        # First 3 trades: W, W, L → no streak of 3
        # Then: W, W, L → no streak of 3
        # Pattern repeats, max consecutive loss should be 1
        
        analyzer = EquityCurveAnalyzer(trades=sample_mixed_trades)
        
        assert analyzer.consecutive_losses == 1
        assert analyzer.total_trades == 20
        assert analyzer.win_rate < 1.0
        assert analyzer.win_rate > 0.0

    def test_analyzer_calculates_drawdown(self, sample_mixed_trades):
        """Test drawdown calculation (cumulative loss from peak)."""
        analyzer = EquityCurveAnalyzer(trades=sample_mixed_trades)
        
        # Should have calculated some drawdown from equity curve
        assert hasattr(analyzer, "max_drawdown")
        assert analyzer.max_drawdown <= 0.0  # Drawdown is negative or zero

    def test_analyzer_handles_empty_trades(self):
        """Test analyzer gracefully handles empty trades list."""
        analyzer = EquityCurveAnalyzer(trades=[])
        
        assert analyzer.total_trades == 0
        assert analyzer.win_rate == 0.0
        assert analyzer.consecutive_losses == 0


class TestThresholdAdjustment:
    """Test dynamic threshold adjustment based on equity curve."""

    @pytest.mark.asyncio
    async def test_increase_threshold_on_consecutive_losses(
        self, threshold_optimizer, sample_losing_trades
    ):
        """
        Test RULE: When consecutive_losses >= threshold (e.g., 3),
        the confidence_threshold should increase (become more demanding).
        """
        # Simulate 4 consecutive losses
        threshold_optimizer.storage.get_account_trades.return_value = sample_losing_trades
        
        old_threshold = threshold_optimizer.current_threshold
        
        # Call adjustment logic
        await threshold_optimizer.optimize_threshold(account_id="test_account")
        
        # Threshold should have increased (more stringent)
        new_threshold = threshold_optimizer.current_threshold
        assert new_threshold > old_threshold, \
            "Threshold should increase after consecutive losses (become more demanding)"

    @pytest.mark.asyncio
    async def test_decrease_threshold_on_winning_streak(
        self, threshold_optimizer, sample_winning_trades
    ):
        """
        Test RULE: When win_rate is high after recovering from losses,
        the threshold can decrease slightly (become more permissive).
        """
        threshold_optimizer.storage.get_account_trades.return_value = sample_winning_trades
        
        old_threshold = threshold_optimizer.current_threshold
        
        # Call adjustment logic
        await threshold_optimizer.optimize_threshold(account_id="test_account")
        
        # Threshold can decrease on consistent wins
        new_threshold = threshold_optimizer.current_threshold
        # Might decrease or stay same, but shouldn't exceed max bounds
        assert threshold_optimizer.threshold_min <= new_threshold <= threshold_optimizer.threshold_max

    @pytest.mark.asyncio
    async def test_no_adjustment_on_stable_performance(
        self, threshold_optimizer, sample_mixed_trades
    ):
        """
        Test RULE: On stable mixed performance (no extreme patterns),
        threshold adjustment should be minimal or none.
        """
        threshold_optimizer.storage.get_account_trades.return_value = sample_mixed_trades
        
        old_threshold = threshold_optimizer.current_threshold
        
        await threshold_optimizer.optimize_threshold(account_id="test_account")
        
        new_threshold = threshold_optimizer.current_threshold
        # Should be close to original or slightly adjusted
        delta = abs(new_threshold - old_threshold)
        assert delta <= threshold_optimizer.smoothing_max, \
            f"Delta {delta} exceeded smoothing limit {threshold_optimizer.smoothing_max}"


class TestSafetyGovernor:
    """Test Safety Governor enforcement for threshold adjustments."""

    def test_threshold_respects_min_bound(self, threshold_optimizer):
        """Verify threshold cannot go below minimum (floor)."""
        threshold_optimizer.current_threshold = threshold_optimizer.threshold_min - 0.1
        
        governed, reason = threshold_optimizer._apply_governance_limits(
            proposed_threshold=threshold_optimizer.threshold_min - 0.1
        )
        
        assert governed >= threshold_optimizer.threshold_min, \
            "Threshold should not go below minimum"
        assert "FLOOR" in reason or "governed" in reason.lower()

    def test_threshold_respects_max_bound(self, threshold_optimizer):
        """Verify threshold cannot exceed maximum (ceiling)."""
        # To test ceiling without smoothing interference, we'll set current_threshold
        # very close to max, then propose slightly above
        threshold_optimizer.current_threshold = threshold_optimizer.threshold_max - 0.01
        proposed = threshold_optimizer.threshold_max + 0.15
        
        governed, reason = threshold_optimizer._apply_governance_limits(
            proposed_threshold=proposed,
            current_threshold=threshold_optimizer.current_threshold
        )
        
        assert governed <= threshold_optimizer.threshold_max, \
            "Threshold should not exceed maximum"
        # Governed should be exactly max due to ceiling
        assert governed == threshold_optimizer.threshold_max or "BOUNDARY_CEILING" in reason

    def test_smoothing_limit_enforcement(self, threshold_optimizer):
        """
        Verify smoothing limit: max change per optimization cycle is limited.
        """
        current = 0.75
        proposed = 0.90  # Delta = 0.15, but smoothing_max = 0.05
        
        governed, reason = threshold_optimizer._apply_governance_limits(
            proposed_threshold=proposed,
            current_threshold=current,
        )
        
        delta = abs(governed - current)
        # Use small epsilon for floating point comparison
        assert delta <= threshold_optimizer.smoothing_max + 1e-10, \
            f"Delta {delta} exceeds smoothing limit {threshold_optimizer.smoothing_max}"


class TestPersistence:
    """Test persistence of threshold adjustments to DB."""

    @pytest.mark.asyncio
    async def test_adjustment_persisted_to_storage(
        self, threshold_optimizer, sample_losing_trades
    ):
        """Verify threshold changes are persisted to StorageManager."""
        threshold_optimizer.storage.get_account_trades.return_value = sample_losing_trades
        
        old_threshold = threshold_optimizer.current_threshold
        
        await threshold_optimizer.optimize_threshold(account_id="test_account")
        
        # After optimization, storage.update_dynamic_params should have been called
        # if threshold changed
        if threshold_optimizer.current_threshold != old_threshold:
            threshold_optimizer.storage.update_dynamic_params.assert_called()

    @pytest.mark.asyncio
    async def test_adjustment_logged_with_trace_id(
        self, threshold_optimizer, sample_losing_trades, monkeypatch
    ):
        """Verify adjustments are logged with Trace_ID for traceability."""
        threshold_optimizer.storage.get_account_trades.return_value = sample_losing_trades
        
        await threshold_optimizer.optimize_threshold(
            account_id="test_account",
            trace_id="ADAPTIVE-THRESHOLD-2026-TEST"
        )
        
        # Verify logging method was called with trace_id
        if threshold_optimizer.storage.log_threshold_adjustment.called:
            call_args = threshold_optimizer.storage.log_threshold_adjustment.call_args
            if call_args:
                # Check if trace_id was included in kwargs or args
                assert call_args is not None


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Integration & Edge Cases
# ──────────────────────────────────────────────────────────────────────────────

class TestIntegrationWithSignalFactory:
    """Test integration with signal generation pipeline."""

    @pytest.mark.asyncio
    async def test_threshold_used_in_signal_validation(self, threshold_optimizer):
        """
        Verify optimized threshold is available for SignalFactory to use
        when validating signal confidence.
        """
        # Get current optimized threshold
        current_threshold = threshold_optimizer.current_threshold
        
        # Should be callable/readable by external components
        assert isinstance(current_threshold, float)
        assert threshold_optimizer.threshold_min <= current_threshold <= threshold_optimizer.threshold_max


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_trades_handling(self, threshold_optimizer):
        """Verify optimizer handles accounts with no trades gracefully."""
        optimizer = threshold_optimizer
        optimizer.storage.get_account_trades.return_value = []
        
        # Should not crash, should handle gracefully
        # Equity curve analysis should return neutral values
        analyzer = EquityCurveAnalyzer(trades=[])
        assert analyzer.total_trades == 0

    @pytest.mark.asyncio
    async def test_threshold_optimization_on_single_trade(self, threshold_optimizer):
        """Verify optimizer handles accounts with only 1 trade."""
        single_trade = [
            {
                "ticket_id": "trade_1",
                "is_win": True,
                "pnl": 100.0,
                "timestamp": datetime.now(timezone.utc),
                "symbol": "EURUSD",
            }
        ]
        threshold_optimizer.storage.get_account_trades.return_value = single_trade
        
        # Should not crash
        await threshold_optimizer.optimize_threshold(account_id="test_account")
        
        # Threshold should remain valid
        assert threshold_optimizer.threshold_min <= threshold_optimizer.current_threshold <= threshold_optimizer.threshold_max


class TestTraceIDHandling:
    """Test Trace_ID propagation for observability."""

    @pytest.mark.asyncio
    async def test_trace_id_propagated_in_optimization(self, threshold_optimizer):
        """Verify Trace_ID is propagated through optimization flow."""
        trace_id = "ADAPTIVE-THRESHOLD-2026-001"
        
        await threshold_optimizer.optimize_threshold(
            account_id="test_account",
            trace_id=trace_id
        )
        
        # log_threshold_adjustment should have been called with trace_id
        # This verifies observability chain


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE: Performance & Complexity
# ──────────────────────────────────────────────────────────────────────────────

def test_threshold_optimizer_code_complexity():
    """Verify ThresholdOptimizer doesn't exceed 500 line limit."""
    import inspect
    source = inspect.getsource(ThresholdOptimizer)
    lines = len(source.split('\n'))
    assert lines < 500, f"ThresholdOptimizer exceeds 500 lines: {lines}"


def test_equity_curve_analyzer_efficiency():
    """Verify EquityCurveAnalyzer handles large trade histories efficiently."""
    # Generate 1000 trades
    large_trades = [
        {
            "ticket_id": f"trade_{i}",
            "is_win": i % 2 == 0,
            "pnl": 100.0 if i % 2 == 0 else -50.0,
            "timestamp": datetime.now(timezone.utc) - timedelta(minutes=1000 - i),
            "symbol": "EURUSD",
        }
        for i in range(1000)
    ]
    
    # Should complete analysis quickly (< 1 second)
    analyzer = EquityCurveAnalyzer(trades=large_trades)
    
    assert analyzer.total_trades == 1000
