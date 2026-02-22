"""
Test Suite for StrategyRanker - Shadow Ranking & Evolution System
Testing: Promotion (SHADOW -> LIVE), Degradation (LIVE -> QUARANTINE)
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import json

from core_brain.strategy_ranker import StrategyRanker
from data_vault.storage import StorageManager


@pytest.fixture
def mock_storage():
    """Mock StorageManager for testing."""
    mock = MagicMock(spec=StorageManager)
    mock.get_system_state.return_value = {}
    return mock


@pytest.fixture
def strategy_ranker(mock_storage):
    """Create StrategyRanker instance with mocked storage."""
    return StrategyRanker(storage=mock_storage)


class TestStrategyRankerPromotion:
    """Test strategy promotion from SHADOW to LIVE."""

    def test_promote_shadow_to_live_with_high_profit_factor_and_win_rate(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in SHADOW mode with:
            - Profit Factor: 1.6 (> 1.5 threshold)
            - Win Rate: 52% (> 50% threshold)
            - Last 50 trades all completed
        WHEN: StrategyRanker evaluates the strategy
        THEN: Strategy should be promoted to LIVE with trace_id logged
        """
        strategy_id = "strat_golden_eagle_v2"
        
        # Mock strategy data from DB
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.6,
            'win_rate': 0.52,
            'drawdown_max': 1.2,  # Below 3% threshold
            'consecutive_losses': 0,
            'execution_mode': 'SHADOW',
            'total_trades': 150,
            'completed_last_50': 50
        }
        
        # Mock update_strategy_execution_mode to return a valid trace_id
        mock_storage.update_strategy_execution_mode.return_value = "RANK-promo0001"
        
        # Execute promotion
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        # Assertions
        assert result['action'] == 'promoted'
        assert result['from_mode'] == 'SHADOW'
        assert result['to_mode'] == 'LIVE'
        assert result['trace_id'].startswith('RANK-')
        
        # Verify update was called
        mock_storage.update_strategy_execution_mode.assert_called_once()
        args = mock_storage.update_strategy_execution_mode.call_args[0]
        assert args[0] == strategy_id
        assert args[1] == 'LIVE'

    def test_shadow_stays_shadow_with_insufficient_metrics(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in SHADOW with:
            - Profit Factor: 1.3 (< 1.5 threshold)
            - Win Rate: 48% (< 50% threshold)
            - Sufficient trades (50)
        WHEN: StrategyRanker evaluates
        THEN: Strategy remains in SHADOW, no action taken
        """
        strategy_id = "strat_learner_v1"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.3,
            'win_rate': 0.48,
            'drawdown_max': 1.8,
            'consecutive_losses': 2,
            'execution_mode': 'SHADOW',
            'total_trades': 50,
            'completed_last_50': 50
        }
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'no_change'
        assert result['current_mode'] == 'SHADOW'
        mock_storage.update_strategy_execution_mode.assert_not_called()

    def test_promote_only_with_minimum_50_completed_trades(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy with perfect metrics (PF=1.8, WR=60%)
            but only 40 completed trades out of last 50
        WHEN: StrategyRanker evaluates
        THEN: Strategy NOT promoted (needs at least 50 trades)
        """
        strategy_id = "strat_new_idea"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.8,
            'win_rate': 0.60,
            'drawdown_max': 1.0,
            'consecutive_losses': 0,
            'execution_mode': 'SHADOW',
            'total_trades': 45,
            'completed_last_50': 40  # Insufficient
        }
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'insufficient_trades'
        assert result['current_mode'] == 'SHADOW'
        mock_storage.update_strategy_execution_mode.assert_not_called()


class TestStrategyRankerDegradation:
    """Test strategy degradation from LIVE to QUARANTINE."""

    def test_degrade_live_to_quarantine_with_high_drawdown(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in LIVE mode with:
            - Drawdown: 3.2% (> 3% threshold)
        WHEN: StrategyRanker evaluates
        THEN: Strategy degraded to QUARANTINE with trace_id logged
        """
        strategy_id = "strat_old_reliable"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.5,
            'win_rate': 0.52,
            'drawdown_max': 3.2,  # EXCEEDS 3% threshold
            'consecutive_losses': 2,
            'execution_mode': 'LIVE',
            'total_trades': 200,
            'completed_last_50': 50
        }
        
        # Mock update to return a trace_id
        mock_storage.update_strategy_execution_mode.return_value = "RANK-degrade001"
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'degraded'
        assert result['from_mode'] == 'LIVE'
        assert result['to_mode'] == 'QUARANTINE'
        assert result['reason'] == 'drawdown_exceeded'
        assert result['trace_id'].startswith('RANK-')
        
        mock_storage.update_strategy_execution_mode.assert_called_once()
        args = mock_storage.update_strategy_execution_mode.call_args[0]
        assert args[1] == 'QUARANTINE'

    def test_degrade_live_to_quarantine_with_5_consecutive_losses(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in LIVE mode with:
            - Consecutive Losses: 5 (>= 5 threshold)
        WHEN: StrategyRanker evaluates
        THEN: Strategy degraded to QUARANTINE
        """
        strategy_id = "strat_unlucky_streak"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.5,
            'win_rate': 0.52,
            'drawdown_max': 2.1,  # Below threshold
            'consecutive_losses': 5,  # EQUALS threshold
            'execution_mode': 'LIVE',
            'total_trades': 150,
            'completed_last_50': 50
        }
        
        mock_storage.update_strategy_execution_mode.return_value = "RANK-ab12cd34"
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'degraded'
        assert result['from_mode'] == 'LIVE'
        assert result['to_mode'] == 'QUARANTINE'
        assert result['reason'] == 'consecutive_losses_exceeded'

    def test_live_remains_live_with_healthy_metrics(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in LIVE mode with:
            - Drawdown: 1.5% (< 3%)
            - Consecutive Losses: 2 (< 5)
        WHEN: StrategyRanker evaluates
        THEN: Strategy remains in LIVE, no action
        """
        strategy_id = "strat_stable_performer"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.8,
            'win_rate': 0.58,
            'drawdown_max': 1.5,
            'consecutive_losses': 2,
            'execution_mode': 'LIVE',
            'total_trades': 200,
            'completed_last_50': 50
        }
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'no_change'
        assert result['current_mode'] == 'LIVE'
        mock_storage.update_strategy_execution_mode.assert_not_called()


class TestStrategyRankerRecovery:
    """Test strategy recovery from QUARANTINE back to monitored states."""

    def test_recover_quarantine_to_shadow_with_improvement(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy in QUARANTINE with recovered metrics:
            - Drawdown: 1.5% (improved from 3.2%)
            - Consecutive Losses: 0 (recovered)
        WHEN: StrategyRanker evaluates
        THEN: Strategy recovered to SHADOW for re-evaluation
        """
        strategy_id = "strat_comeback_kid"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.6,
            'win_rate': 0.55,
            'drawdown_max': 1.5,  # Recovered!
            'consecutive_losses': 0,  # Recovered!
            'execution_mode': 'QUARANTINE',
            'total_trades': 300,
            'completed_last_50': 50
        }
        
        mock_storage.update_strategy_execution_mode.return_value = "RANK-rec0very0"
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        assert result['action'] == 'recovered'
        assert result['from_mode'] == 'QUARANTINE'
        assert result['to_mode'] == 'SHADOW'
        
        mock_storage.update_strategy_execution_mode.assert_called_once()


class TestStrategyRankerAudit:
    """Test audit trail and trace_id logging."""

    def test_trace_id_format_and_persistence(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy being promoted
        WHEN: Trace_ID is generated
        THEN: Should follow pattern 'RANK-XXXXXXXX' and be unique
        """
        strategy_id = "strat_audit_test"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.7,
            'win_rate': 0.53,
            'drawdown_max': 1.1,
            'consecutive_losses': 0,
            'execution_mode': 'SHADOW',
            'total_trades': 100,
            'completed_last_50': 50
        }
        
        # Mock update to return different trace_ids each time
        mock_storage.update_strategy_execution_mode.side_effect = [
            "RANK-trace0001",
            "RANK-trace0002"
        ]
        
        # Run first evaluation
        result1 = strategy_ranker.evaluate_and_rank(strategy_id)
        
        # Verify first promotion has correct trace_id format
        assert result1['action'] == 'promoted'
        assert result1['trace_id'].startswith('RANK-')
        assert result1['trace_id'] == "RANK-trace0001"

    def test_state_change_logging(self, strategy_ranker, mock_storage):
        """
        GIVEN: Strategy transition event
        WHEN: State changes
        THEN: log_strategy_state_change should be called with all context
        """
        strategy_id = "strat_log_test"
        
        mock_storage.get_strategy_ranking.return_value = {
            'strategy_id': strategy_id,
            'profit_factor': 1.75,
            'win_rate': 0.54,
            'drawdown_max': 0.9,
            'consecutive_losses': 0,
            'execution_mode': 'SHADOW',
            'total_trades': 95,
            'completed_last_50': 50
        }
        
        mock_storage.update_strategy_execution_mode.return_value = "RANK-logtest1"
        
        result = strategy_ranker.evaluate_and_rank(strategy_id)
        
        # Verify logging method was called
        mock_storage.log_strategy_state_change.assert_called()
        
        # Get the call arguments (can be positional or keyword)
        call_kwargs = mock_storage.log_strategy_state_change.call_args[1]
        
        assert call_kwargs.get('strategy_id') == strategy_id
        assert call_kwargs.get('old_mode') == 'SHADOW'
        assert call_kwargs.get('new_mode') == 'LIVE'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
