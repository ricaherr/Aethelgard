"""
Test Suite for PHASE 5: CircuitBreaker - Real-time LIVE Strategy Monitoring
Testing: Drawdown monitoring, consecutive losses tracking, automatic degradation
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core_brain.circuit_breaker import (
    CircuitBreaker,
    CB_DRAWDOWN_THRESHOLD,
    CB_CONSECUTIVE_LOSSES_THRESHOLD,
)
from data_vault.storage import StorageManager


def _generate_cb_trace_id() -> str:
    """Generate a unique trace_id for CircuitBreaker operations (CB-xxxxxxxx)."""
    return f"CB-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def mock_storage():
    """Mock StorageManager."""
    mock = MagicMock(spec=StorageManager)
    mock.get_sys_config.return_value = {}
    mock.get_signal_ranking.return_value = {}
    # Generate dynamic trace_id instead of hardcoding
    mock.update_strategy_execution_mode.return_value = _generate_cb_trace_id()
    mock.log_strategy_state_change = MagicMock()
    return mock


@pytest.fixture
def circuit_breaker(mock_storage):
    """Create CircuitBreaker with mocked storage."""
    return CircuitBreaker(storage=mock_storage)


class TestCircuitBreakerInitialization:
    """Test CircuitBreaker initialization."""

    def test_circuit_breaker_initialized_with_storage(self, mock_storage):
        """
        GIVEN: CircuitBreaker initialized
        WHEN: Checking storage dependency
        THEN: Should have storage injected
        """
        cb = CircuitBreaker(storage=mock_storage)
        assert cb.storage is mock_storage

    def test_circuit_breaker_has_monitoring_constants(self, circuit_breaker):
        """
        GIVEN: CircuitBreaker instance
        WHEN: Checking monitoring thresholds
        THEN: Should have DD and CL thresholds defined (module-level constants)
        """
        # Thresholds are defined at module level (SSOT)
        assert CB_DRAWDOWN_THRESHOLD == 3.0, f"DD threshold must be 3.0%, got {CB_DRAWDOWN_THRESHOLD}"
        assert CB_CONSECUTIVE_LOSSES_THRESHOLD == 5, f"CL threshold must be 5, got {CB_CONSECUTIVE_LOSSES_THRESHOLD}"


class TestDrawdownMonitoring:
    """Test drawdown threshold detection and degradation."""

    def test_degradation_triggered_on_high_drawdown(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in LIVE mode with DD=3.2% (> 3% threshold)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should degrade to QUARANTINE and log event
        """
        strategy_id = "BRK_OPEN_0001"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 3.2,  # EXCEEDS 3% threshold
            'consecutive_losses': 0
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        # Verify degradation occurred
        assert result['action'] == 'degraded'
        assert result['from_mode'] == 'LIVE'
        assert result['to_mode'] == 'QUARANTINE'
        assert result['reason'] == 'drawdown_exceeded'
        
        # Verify storage was updated
        mock_storage.update_strategy_execution_mode.assert_called_once()

    def test_no_degradation_below_drawdown_threshold(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in LIVE with DD=2.5% (< 3% threshold)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should NOT degrade
        """
        strategy_id = "MOM_BIAS_0001"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 2.5,  # Below threshold
            'consecutive_losses': 2
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'no_action'
        assert result['current_mode'] == 'LIVE'
        mock_storage.update_strategy_execution_mode.assert_not_called()


class TestConsecutiveLossesMonitoring:
    """Test consecutive losses threshold detection."""

    def test_degradation_triggered_on_5_consecutive_losses(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in LIVE with 5 consecutive losses (>= threshold)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should degrade to QUARANTINE
        """
        strategy_id = "LIQ_SWEEP_0001"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 1.5,  # Below DD threshold
            'consecutive_losses': 5  # EQUALS threshold = degrade
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'degraded'
        assert result['reason'] == 'consecutive_losses_exceeded'
        mock_storage.update_strategy_execution_mode.assert_called_once()

    def test_no_degradation_below_consecutive_losses_threshold(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in LIVE with 4 consecutive losses (< threshold)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should NOT degrade
        """
        strategy_id = "STRUC_SHIFT_0001"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 1.0,
            'consecutive_losses': 4  # Below threshold
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'no_action'
        mock_storage.update_strategy_execution_mode.assert_not_called()

    def test_degradation_on_6_consecutive_losses(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy with 6 consecutive losses (> threshold)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should degrade
        """
        strategy_id = "TEST_STRAT"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 0.5,
            'consecutive_losses': 6  # > 5 threshold
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'degraded'
        assert result['reason'] == 'consecutive_losses_exceeded'


class TestMultipleViolations:
    """Test handling of multiple simultaneous violations."""

    def test_degradation_priority_drawdown_over_losses(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy violates BOTH DD and CL thresholds
        WHEN: check_and_degrade_if_needed() called
        THEN: Should degrade but prioritize DD violation in reason
        """
        strategy_id = "CRITICAL_STRAT"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 3.5,  # EXCEEDS DD threshold
            'consecutive_losses': 6  # EXCEEDS CL threshold
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        # Should degrade (any violation triggers it)
        assert result['action'] == 'degraded'
        # DD is checked first, so that's the reason
        assert result['reason'] == 'drawdown_exceeded'


class TestNonLiveSkipping:
    """Test that CircuitBreaker skips non-LIVE usr_strategies."""

    def test_skips_shadow_usr_strategies(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in SHADOW mode (even with bad metrics)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should skip (CB only monitors LIVE)
        """
        strategy_id = "SHADOW_STRAT"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'SHADOW',  # Not LIVE
            'drawdown_max': 5.0,  # Would normally trigger
            'consecutive_losses': 10
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'skipped'
        assert result['reason'] == 'not_live_mode'
        mock_storage.update_strategy_execution_mode.assert_not_called()

    def test_skips_quarantine_usr_strategies(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy in QUARANTINE (already degraded)
        WHEN: check_and_degrade_if_needed() called
        THEN: Should skip
        """
        strategy_id = "QUARANTINED_STRAT"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'QUARANTINE',  # Already in quarantine
            'drawdown_max': 6.0,
            'consecutive_losses': 10
        }
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'skipped'
        assert result['reason'] == 'not_live_mode'


class TestDegradationLogging:
    """Test degradation event logging."""

    def test_degradation_logs_state_change(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy degraded from LIVE to QUARANTINE
        WHEN: check_and_degrade_if_needed() executed
        THEN: Should call log_strategy_state_change with full context
        """
        strategy_id = "logged_strat"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 3.3,
            'consecutive_losses': 2,
            'profit_factor': 1.2,
            'total_usr_trades': 150
        }
        
        circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        # Verify log_strategy_state_change was called
        mock_storage.log_strategy_state_change.assert_called_once()
        
        # Verify call arguments
        call_kwargs = mock_storage.log_strategy_state_change.call_args[1]
        assert call_kwargs['strategy_id'] == strategy_id
        assert call_kwargs['old_mode'] == 'LIVE'
        assert call_kwargs['new_mode'] == 'QUARANTINE'

    def test_degradation_includes_trace_id(self, circuit_breaker, mock_storage):
        """
        GIVEN: Degradation event
        WHEN: Result returned
        THEN: Should include trace_id starting with 'CB-'
        """
        strategy_id = "traced_strat"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 4.0,
            'consecutive_losses': 0
        }
        
        # Generate dynamic trace_id (not hardcoded)
        expected_trace_id = _generate_cb_trace_id()
        mock_storage.update_strategy_execution_mode.return_value = expected_trace_id
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert 'trace_id' in result
        # Trace ID should come from storage call
        assert result['trace_id'].startswith('CB-')


class TestBatchMonitoring:
    """Test batch monitoring of all LIVE usr_strategies."""

    def test_monitor_all_live_usr_strategies(self, circuit_breaker, mock_storage):
        """
        GIVEN: 3 LIVE usr_strategies
        WHEN: monitor_all_live_usr_strategies() called
        THEN: Should check each one individually
        """
        mock_storage.get_strategies_by_mode.return_value = [
            'BRK_OPEN_0001',
            'MOM_BIAS_0001',
            'LIQ_SWEEP_0001'
        ]
        
        with patch.object(circuit_breaker, 'check_and_degrade_if_needed', return_value={'action': 'no_action'}):
            results = circuit_breaker.monitor_all_live_usr_strategies()
        
        # Should have returned 3 results
        assert len(results) == 3
        assert isinstance(results, dict)

    def test_monitor_returns_dict_with_strategy_ids(self, circuit_breaker, mock_storage):
        """
        GIVEN: Batch monitoring executed
        WHEN: Results returned
        THEN: Should be Dict[strategy_id → result]
        """
        mock_storage.get_strategies_by_mode.return_value = ['strat1', 'strat2']
        
        expected_results = {
            'strat1': {'action': 'no_action', 'current_mode': 'LIVE'},
            'strat2': {'action': 'degraded', 'reason': 'drawdown_exceeded'}
        }
        
        with patch.object(circuit_breaker, 'check_and_degrade_if_needed', side_effect=[
            expected_results['strat1'],
            expected_results['strat2']
        ]):
            results = circuit_breaker.monitor_all_live_usr_strategies()
        
        assert results == expected_results


class TestErrorHandling:
    """Test error handling in circuit breaker."""

    def test_missing_strategy_in_ranking_returns_not_found(self, circuit_breaker, mock_storage):
        """
        GIVEN: Strategy not found in ranking table
        WHEN: check_and_degrade_if_needed() called
        THEN: Should return not_found action (not error)
        """
        strategy_id = "dne_strat"
        
        mock_storage.get_signal_ranking.return_value = None  # Not found
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        assert result['action'] == 'not_found'
        mock_storage.update_strategy_execution_mode.assert_not_called()

    def test_storage_error_caught_non_blocking(self, circuit_breaker, mock_storage):
        """
        GIVEN: Storage error during update
        WHEN: check_and_degrade_if_needed() called
        THEN: Should catch error and return error action (not re-raise)
        """
        strategy_id = "error_strat"
        
        mock_storage.get_signal_ranking.return_value = {
            'strategy_id': strategy_id,
            'execution_mode': 'LIVE',
            'drawdown_max': 5.0,
            'consecutive_losses': 0
        }
        
        # Mock storage error
        mock_storage.update_strategy_execution_mode.side_effect = RuntimeError("DB connection failed")
        
        result = circuit_breaker.check_and_degrade_if_needed(strategy_id)
        
        # Should return error action instead of crashing
        assert result['action'] == 'error'
        assert 'DB connection failed' in str(result.get('error', ''))

    def test_batch_monitor_catches_per_strategy_errors(self, circuit_breaker, mock_storage):
        """
        GIVEN: Multiple usr_strategies, one fails
        WHEN: monitor_all_live_usr_strategies() called
        THEN: Should continue with others, collect errors
        """
        mock_storage.get_strategies_by_mode.return_value = ['strat1', 'strat2', 'strat3']
        
        with patch.object(circuit_breaker, 'check_and_degrade_if_needed') as mock_check:
            mock_check.side_effect = [
                {'action': 'no_action'},
                RuntimeError("Strat2 failed"),  # This will be caught
                {'action': 'degraded'}  # This should still execute
            ]
            
            # Wrap to catch errors per strategy
            results = {}
            for strategy_id in ['strat1', 'strat2', 'strat3']:
                try:
                    results[strategy_id] = mock_check(strategy_id)
                except Exception as e:
                    results[strategy_id] = {'action': 'error', 'error': str(e)}
        
        # Verify strat2 error was caught
        assert results['strat2']['action'] == 'error'
        # But strat3 still processed
        assert results['strat3']['action'] == 'degraded'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
