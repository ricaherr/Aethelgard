"""
TDD Tests for StrategyMonitorService
Ensures real-time monitoring of strategy metrics (DD%, CL, status, etc.)

§ 1.4: SSOT - All test data centralized in conftest_test_data.py
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from core_brain.services.strategy_monitor_service import StrategyMonitorService
from tests.conftest_test_data import (
    TEST_STRATEGIES,
    TEST_STRATEGIES_BY_ID,
    get_test_strategy_statuses,
    get_test_strategy_blocked_statuses,
    get_test_status_priority
)


@pytest.fixture
def mock_storage():
    """
    Mock StorageManager with strategy data (SSOT).
    uses conftest_test_data.py as single source of truth.
    """
    storage = Mock()
    
    # Mock strategy summary list (uses TEST_STRATEGIES)
    storage.get_all_sys_strategies = Mock(
        return_value=[
            {k: v for k, v in s.items() if k in ['strategy_id', 'execution_mode']}
            for s in TEST_STRATEGIES
        ]
    )
    
    # Mock getting single strategy (lookup from TEST_STRATEGIES_BY_ID)
    def get_signal_ranking_impl(sid):
        strategy = TEST_STRATEGIES_BY_ID.get(sid)
        if strategy:
            return {
                'strategy_id': strategy['strategy_id'],
                'win_rate': strategy['win_rate'],
                'profit_factor': strategy['profit_factor'],
                'drawdown_max': strategy['dd_pct'],
                'consecutive_losses': strategy['consecutive_losses'],
                'total_usr_trades': strategy['usr_trades_count'],
                'last_update_utc': strategy['updated_at']
            }
        return None
    
    storage.get_signal_ranking = Mock(side_effect=get_signal_ranking_impl)
    
    return storage


@pytest.fixture
def mock_circuit_breaker():
    """
    Mock CircuitBreaker (SSOT).
    Uses conftest_test_data.py for status mappings.
    """
    cb = Mock()
    status_map = get_test_strategy_statuses()
    blocked_map = get_test_strategy_blocked_statuses()
    
    cb.get_strategy_status = Mock(side_effect=lambda sid: status_map.get(sid, 'UNKNOWN'))
    cb.is_strategy_blocked_for_trading = Mock(side_effect=lambda sid: blocked_map.get(sid, False))
    
    return cb


@pytest.fixture
def monitor_service(mock_storage, mock_circuit_breaker):
    """Initialize StrategyMonitorService with mocks"""
    return StrategyMonitorService(
        storage=mock_storage,
        circuit_breaker=mock_circuit_breaker
    )


class TestStrategyMonitorServiceInitialization:
    """Test service initialization and DI"""
    
    def test_service_initializes_with_dependencies(self, mock_storage, mock_circuit_breaker):
        """Service should accept storage and circuit_breaker via DI"""
        service = StrategyMonitorService(
            storage=mock_storage,
            circuit_breaker=mock_circuit_breaker
        )
        assert service.storage is mock_storage
        assert service.circuit_breaker is mock_circuit_breaker
    
    def test_service_has_required_methods(self, monitor_service):
        """Service should have core methods"""
        assert hasattr(monitor_service, 'get_strategy_metrics')
        assert hasattr(monitor_service, 'get_all_usr_strategies_metrics')
        assert callable(monitor_service.get_strategy_metrics)
        assert callable(monitor_service.get_all_usr_strategies_metrics)


class TestGetSingleStrategyMetrics:
    """Test getting metrics for single strategy"""
    
    def test_get_metrics_live_strategy(self, monitor_service):
        """Should return LIVE status with positive metrics"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        
        assert metrics is not None
        assert metrics['strategy_id'] == 'BRK_OPEN_0001'
        assert metrics['status'] == 'LIVE'
        assert metrics['dd_pct'] == 2.3
        assert metrics['consecutive_losses'] == 1
        assert metrics['win_rate'] == 0.58
        assert metrics['profit_factor'] == 1.45
        assert 'updated_at' in metrics
    
    def test_get_metrics_quarantine_strategy(self, monitor_service):
        """Should return QUARANTINE status with degraded metrics"""
        metrics = monitor_service.get_strategy_metrics('institutional_footprint')
        
        assert metrics is not None
        assert metrics['strategy_id'] == 'institutional_footprint'
        assert metrics['status'] == 'QUARANTINE'
        assert metrics['dd_pct'] == 4.8
        assert metrics['consecutive_losses'] == 5
        assert metrics['blocked_for_trading'] is True
    
    def test_get_metrics_shadow_strategy(self, monitor_service):
        """Should return SHADOW status (non-trading)"""
        metrics = monitor_service.get_strategy_metrics('MOM_BIAS_0001')
        
        assert metrics is not None
        assert metrics['strategy_id'] == 'MOM_BIAS_0001'
        assert metrics['status'] == 'SHADOW'
        assert metrics['blocked_for_trading'] is False
    
    def test_get_metrics_unknown_strategy(self, monitor_service):
        """Should return UNKNOWN for non-existent strategy"""
        metrics = monitor_service.get_strategy_metrics('UNKNOWN_STRATEGY_9999')
        
        assert metrics is not None
        assert metrics['status'] == 'UNKNOWN'
        assert metrics['strategy_id'] == 'UNKNOWN_STRATEGY_9999'
    
    def test_metrics_include_online_status(self, monitor_service):
        """Should include online/updated_at indicator"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        
        assert 'updated_at' in metrics
        # Should be recent (within last hour)
        updated = datetime.fromisoformat(metrics['updated_at'])
        now = datetime.now()
        assert (now - updated).seconds < 3600


class TestGetAllStrategiesMetrics:
    """Test getting metrics for all usr_strategies"""
    
    def test_get_all_returns_list(self, monitor_service):
        """Should return list of all strategy metrics"""
        metrics_list = monitor_service.get_all_usr_strategies_metrics()
        
        assert isinstance(metrics_list, list)
        assert len(metrics_list) >= 3
    
    def test_all_metrics_have_required_fields(self, monitor_service):
        """Each metric dict should have required fields"""
        metrics_list = monitor_service.get_all_usr_strategies_metrics()
        
        required_fields = [
            'strategy_id', 'status', 'dd_pct', 'consecutive_losses',
            'win_rate', 'profit_factor', 'blocked_for_trading', 'updated_at'
        ]
        
        for metric in metrics_list:
            for field in required_fields:
                assert field in metric, f"Missing field: {field}"
    
    def test_metrics_sorted_by_status_priority(self, monitor_service):
        """Metrics should be sorted: LIVE > SHADOW > QUARANTINE > UNKNOWN"""
        metrics_list = monitor_service.get_all_usr_strategies_metrics()
        
        status_order = get_test_status_priority()
        statuses = [m['status'] for m in metrics_list]
        
        # Verify sorting
        for i in range(len(statuses) - 1):
            assert status_order[statuses[i]] <= status_order[statuses[i + 1]]
    
    def test_all_usr_strategies_included(self, monitor_service):
        """All usr_strategies from storage should be included"""
        metrics_list = monitor_service.get_all_usr_strategies_metrics()
        strategy_ids = [m['strategy_id'] for m in metrics_list]
        
        assert 'BRK_OPEN_0001' in strategy_ids
        assert 'institutional_footprint' in strategy_ids
        assert 'MOM_BIAS_0001' in strategy_ids


class TestMetricsCalculations:
    """Test metric calculations and transformations"""
    
    def test_dd_pct_format(self, monitor_service):
        """DD% should be float between 0-100"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        
        assert isinstance(metrics['dd_pct'], (int, float))
        assert 0 <= metrics['dd_pct'] <= 100
    
    def test_consecutive_losses_is_integer(self, monitor_service):
        """Consecutive losses should be non-negative integer"""
        metrics = monitor_service.get_strategy_metrics('institutional_footprint')
        
        assert isinstance(metrics['consecutive_losses'], int)
        assert metrics['consecutive_losses'] >= 0
    
    def test_win_rate_between_0_and_1(self, monitor_service):
        """Win rate should be float between 0.0 and 1.0"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        
        assert isinstance(metrics['win_rate'], (int, float))
        assert 0 <= metrics['win_rate'] <= 1.0
    
    def test_profit_factor_positive(self, monitor_service):
        """Profit factor should be positive number"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        
        assert isinstance(metrics['profit_factor'], (int, float))
        assert metrics['profit_factor'] > 0


class TestExceptionHandling:
    """Test fail-safe exception handling (RULE 4.3)"""
    
    def test_storage_error_handled_gracefully(self, mock_circuit_breaker):
        """Should handle storage errors gracefully"""
        mock_storage = Mock()
        mock_storage.get_usr_performance = Mock(side_effect=Exception("DB error"))
        
        service = StrategyMonitorService(
            storage=mock_storage,
            circuit_breaker=mock_circuit_breaker
        )
        
        # Should not raise, should return safe default
        metrics = service.get_strategy_metrics('ANY_ID')
        assert metrics is not None
        assert 'error' in metrics or metrics['status'] == 'UNKNOWN'
    
    def test_circuit_breaker_error_handled_gracefully(self, mock_storage):
        """Should handle circuit breaker errors gracefully"""
        mock_cb = Mock()
        mock_cb.get_strategy_status = Mock(side_effect=Exception("CB error"))
        
        service = StrategyMonitorService(
            storage=mock_storage,
            circuit_breaker=mock_cb
        )
        
        # Should not raise
        metrics = service.get_strategy_metrics('BRK_OPEN_0001')
        assert metrics is not None
    
    def test_all_metrics_call_wrapped_in_try_except(self, monitor_service):
        """All storage/CB calls should be protected"""
        # This test verifies implementation by checking that no exceptions
        # escape from public methods
        
        # None of these should raise
        monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        monitor_service.get_all_usr_strategies_metrics()
        monitor_service.get_strategy_metrics('NONEXISTENT')


class TestStatusCombinations:
    """Test status determination logic"""
    
    def test_live_strategy_not_blocked(self, monitor_service):
        """LIVE strategy should have blocked_for_trading = False"""
        metrics = monitor_service.get_strategy_metrics('BRK_OPEN_0001')
        assert metrics['blocked_for_trading'] is False
    
    def test_quarantine_strategy_blocked(self, monitor_service):
        """QUARANTINE strategy should have blocked_for_trading = True"""
        metrics = monitor_service.get_strategy_metrics('institutional_footprint')
        assert metrics['blocked_for_trading'] is True
    
    def test_shadow_strategy_not_blocked(self, monitor_service):
        """SHADOW strategy should have blocked_for_trading = False (not trading anyway)"""
        metrics = monitor_service.get_strategy_metrics('MOM_BIAS_0001')
        assert metrics['blocked_for_trading'] is False
