"""
Test Suite: StrategyGatekeeper — In-Memory Asset Efficiency Filter
Testing: Asset Score Validation, Pre-Tick Filtering, Performance Logging

TRACE_ID: EXEC-EFFICIENCY-SCORE-001
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import json
import time

from core_brain.strategy_gatekeeper import StrategyGatekeeper
from data_vault.storage import StorageManager


@pytest.fixture
def mock_storage():
    """Mock StorageManager for testing."""
    mock = MagicMock(spec=StorageManager)
    mock.get_sys_config.return_value = {}
    mock.save_strategy_performance_log.return_value = True
    mock.get_strategy_affinity_scores.return_value = {
        'EUR/USD': 0.92,
        'GBP/USD': 0.85,
        'JPY/USD': 0.78
    }
    return mock


@pytest.fixture
def gatekeeper(mock_storage):
    """Create StrategyGatekeeper instance with mocked storage."""
    return StrategyGatekeeper(storage=mock_storage)


class TestStrategyGatekeeperInitialization:
    """Test StrategyGatekeeper initialization and configuration."""

    def test_gatekeeper_initializes_with_storage(self, gatekeeper, mock_storage):
        """
        GIVEN: StrategyGatekeeper is instantiated
        WHEN: Constructor is called with StorageManager dependency
        THEN: Gatekeeper stores reference and is ready for operations
        """
        assert gatekeeper.storage == mock_storage
        assert gatekeeper.asset_scores is not None
        assert isinstance(gatekeeper.asset_scores, dict)

    def test_gatekeeper_loads_affinity_scores_on_init(self, mock_storage):
        """
        GIVEN: StorageManager contains affinity_scores for EUR/USD, GBP/USD, JPY/USD
        WHEN: StrategyGatekeeper initializes
        THEN: Scores are loaded into memory (in-memory cache)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {
            'EUR/USD': 0.92,
            'GBP/USD': 0.85,
            'JPY/USD': 0.78
        }
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        assert gatekeeper.asset_scores['EUR/USD'] == 0.92
        assert gatekeeper.asset_scores['GBP/USD'] == 0.85
        assert gatekeeper.asset_scores['JPY/USD'] == 0.78


class TestStrategyGatekeeperAssetValidation:
    """Test asset score validation against thresholds."""

    def test_validate_asset_passes_with_score_above_threshold(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset EUR/USD with affinity_score 0.92
        WHEN: validate_asset_score() is called with min_threshold=0.80
        THEN: Validation passes and returns True
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'EUR/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        result = gatekeeper.validate_asset_score(
            asset='EUR/USD',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert result is True

    def test_validate_asset_fails_with_score_below_threshold(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset GBP/USD with affinity_score 0.75
        WHEN: validate_asset_score() is called with min_threshold=0.80
        THEN: Validation fails and returns False (triggers abort)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'GBP/USD': 0.75}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        result = gatekeeper.validate_asset_score(
            asset='GBP/USD',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert result is False

    def test_validate_asset_with_missing_asset_defaults_to_fail(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset UNKNOWN/USD not in affinity_scores
        WHEN: validate_asset_score() is called
        THEN: Defaults to failure (conservative: block unknown assets)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'EUR/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        result = gatekeeper.validate_asset_score(
            asset='UNKNOWN/USD',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert result is False

    def test_validate_asset_uses_exact_threshold_comparison(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset with score exactly equal to threshold (0.80)
        WHEN: validate_asset_score() is called with min_threshold=0.80
        THEN: Passes (>= comparison, not strictly greater)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'ASSET': 0.80}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        result = gatekeeper.validate_asset_score(
            asset='ASSET',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert result is True


class TestStrategyGatekeeperPreTickFiltering:
    """Test pre-tick execution filtering and abort."""

    def test_can_execute_on_tick_passes_validation(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset EUR/USD with score 0.92, min_threshold=0.80
        WHEN: can_execute_on_tick() is called before strategy processing
        THEN: Returns True, signal can proceed
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'EUR/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        can_exec = gatekeeper.can_execute_on_tick(
            asset='EUR/USD',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert can_exec is True

    def test_can_execute_on_tick_blocks_below_threshold(self, gatekeeper, mock_storage):
        """
        GIVEN: Asset with score 0.70, min_threshold=0.80
        WHEN: can_execute_on_tick() is called
        THEN: Returns False, execution aborted (no processing)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'POOR/ASSET': 0.70}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        can_exec = gatekeeper.can_execute_on_tick(
            asset='POOR/ASSET',
            min_threshold=0.80,
            strategy_id='STRAT_0001'
        )
        
        assert can_exec is False

    def test_can_execute_on_tick_completes_in_less_than_1ms(self, gatekeeper, mock_storage):
        """
        GIVEN: StrategyGatekeeper with loaded affinity scores
        WHEN: can_execute_on_tick() is called repeatedly
        THEN: Each call completes in < 1ms (fast in-memory lookup)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {
            'EUR/USD': 0.92,
            'GBP/USD': 0.85,
            'JPY/USD': 0.78
        }
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        start_time = time.perf_counter()
        for i in range(1000):
            gatekeeper.can_execute_on_tick(
                asset='EUR/USD',
                min_threshold=0.80,
                strategy_id='STRAT_0001'
            )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Average time per call should be < 1ms (even at 1000 calls)
        avg_time_per_call = elapsed_ms / 1000
        assert avg_time_per_call < 1.0, f"Expected < 1ms per call, got {avg_time_per_call:.4f}ms"


class TestStrategyGatekeeperPerformanceLogging:
    """Test performance logging for affinity score learning."""

    def test_log_asset_performance_saves_to_database(self, gatekeeper, mock_storage):
        """
        GIVEN: Strategy execution result (win/loss) for EUR/USD
        WHEN: log_asset_performance() is called
        THEN: Performance is logged to usr_strategy_logs table
        """
        mock_storage.save_strategy_performance_log.return_value = True
        
        result = gatekeeper.log_asset_performance(
            strategy_id='STRAT_0001',
            asset='EUR/USD',
            pnl=150.00,
            usr_trades_count=5,
            win_rate=0.80,
            profit_factor=1.5
        )
        
        assert result is True
        mock_storage.save_strategy_performance_log.assert_called_once()

    def test_log_asset_performance_persists_metadata(self, gatekeeper, mock_storage):
        """
        GIVEN: Performance log call with pnl, win_rate, profit_factor
        WHEN: log_asset_performance() is called
        THEN: All metadata is passed to storage layer
        """
        mock_storage.save_strategy_performance_log.return_value = True
        
        gatekeeper.log_asset_performance(
            strategy_id='STRAT_0001',
            asset='EUR/USD',
            pnl=250.00,
            usr_trades_count=10,
            win_rate=0.75,
            profit_factor=1.8
        )
        
        call_args = mock_storage.save_strategy_performance_log.call_args
        assert call_args[1]['asset'] == 'EUR/USD'
        assert call_args[1]['pnl'] == 250.00
        assert call_args[1]['win_rate'] == 0.75


class TestStrategyGatekeeperAffiniScoreUpdate:
    """Test dynamic affinity score updates."""

    def test_refresh_affinity_scores_reloads_from_storage(self, gatekeeper, mock_storage):
        """
        GIVEN: Affinity scores updated in database
        WHEN: refresh_affinity_scores() is called
        THEN: In-memory cache is refreshed with latest values
        """
        # Initial scores
        mock_storage.get_strategy_affinity_scores.return_value = {
            'EUR/USD': 0.92,
            'GBP/USD': 0.85
        }
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        assert gatekeeper.asset_scores['EUR/USD'] == 0.92
        
        # Updated scores
        mock_storage.get_strategy_affinity_scores.return_value = {
            'EUR/USD': 0.95,
            'GBP/USD': 0.88,
            'JPY/USD': 0.80
        }
        
        gatekeeper.refresh_affinity_scores()
        
        assert gatekeeper.asset_scores['EUR/USD'] == 0.95
        assert gatekeeper.asset_scores['GBP/USD'] == 0.88
        assert gatekeeper.asset_scores['JPY/USD'] == 0.80

    def test_refresh_affinity_scores_is_idempotent(self, gatekeeper, mock_storage):
        """
        GIVEN: Multiple calls to refresh_affinity_scores()
        WHEN: Called repeatedly
        THEN: Cache remains consistent (idempotent)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {
            'EUR/USD': 0.92
        }
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        initial_score = gatekeeper.asset_scores['EUR/USD']
        gatekeeper.refresh_affinity_scores()
        gatekeeper.refresh_affinity_scores()
        
        assert gatekeeper.asset_scores['EUR/USD'] == initial_score


class TestStrategyGatekeeperIntegrationWithUniversalEngine:
    """Test integration between Gatekeeper and UniversalStrategyEngine."""

    def test_gatekeeper_validates_before_signal_generation(self, gatekeeper, mock_storage):
        """
        GIVEN: UniversalStrategyEngine is about to generate signal for EUR/USD
        WHEN: Gatekeeper validates asset before signal creation
        THEN: Signal is only generated if score >= threshold
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'EUR/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        # Simulate pre-signal validation
        can_generate_signal = gatekeeper.can_execute_on_tick(
            asset='EUR/USD',
            min_threshold=0.85,
            strategy_id='BRK_OPEN_0001'
        )
        
        assert can_generate_signal is True

    def test_gatekeeper_veto_prevents_poor_asset_execution(self, gatekeeper, mock_storage):
        """
        GIVEN: Strategy requests execution on asset with low efficiency score
        WHEN: Gatekeeper evaluates (min_threshold=0.90)
        THEN: Veto is issued, no execution proceeds
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'POOR/ASSET': 0.65}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        
        veto = not gatekeeper.can_execute_on_tick(
            asset='POOR/ASSET',
            min_threshold=0.90,
            strategy_id='BRK_OPEN_0001'
        )
        
        assert veto is True  # Veto issued


class TestStrategyGatekeeperMarketWhitelist:
    """Test market whitelist enforcement (optional filter)."""

    def test_gatekeeper_respects_market_whitelist(self, gatekeeper, mock_storage):
        """
        GIVEN: Strategy BRK_OPEN_0001 has market_whitelist = ['EUR/USD', 'GBP/USD']
        WHEN: can_execute_on_tick() is called for EUR/USD
        THEN: Execution is allowed (asset in whitelist AND score passes)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'EUR/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        gatekeeper.set_market_whitelist(
            strategy_id='BRK_OPEN_0001',
            whitelist=['EUR/USD', 'GBP/USD']
        )
        
        can_exec = gatekeeper.can_execute_on_tick(
            asset='EUR/USD',
            min_threshold=0.80,
            strategy_id='BRK_OPEN_0001'
        )
        
        assert can_exec is True

    def test_gatekeeper_blocks_asset_not_in_whitelist(self, gatekeeper, mock_storage):
        """
        GIVEN: Strategy whitelist = ['EUR/USD', 'GBP/USD']
        WHEN: Execution requested for JPY/USD (not in whitelist)
        THEN: Execution blocked (whitelist veto)
        """
        mock_storage.get_strategy_affinity_scores.return_value = {'JPY/USD': 0.92}
        gatekeeper = StrategyGatekeeper(storage=mock_storage)
        gatekeeper.set_market_whitelist(
            strategy_id='BRK_OPEN_0001',
            whitelist=['EUR/USD', 'GBP/USD']
        )
        
        can_exec = gatekeeper.can_execute_on_tick(
            asset='JPY/USD',
            min_threshold=0.80,
            strategy_id='BRK_OPEN_0001'
        )
        
        assert can_exec is False
