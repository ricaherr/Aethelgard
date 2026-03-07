"""
CENTRALIZED TEST DATA - FIXTURE REFERENCE (SSOT)
Implements § 1.4 (Explorar antes de Crear) and .ai_rules § 1 (SSOT)

All test data for usr_strategies, metrics, and mock objects should be
referenced from THIS file, not hardcoded in individual test files.
"""

from datetime import datetime, timedelta

# ============================================================================
# TEST STRATEGY DEFINITIONS (Single Source of Truth)
# ============================================================================

TEST_STRATEGY_LIVE = {
    'strategy_id': 'BRK_OPEN_0001',
    'execution_mode': 'LIVE',
    'status': 'LIVE',
    'win_rate': 0.58,
    'profit_factor': 1.45,
    'dd_pct': 2.3,
    'consecutive_losses': 1,
    'usr_trades_count': 50,
    'updated_at': datetime.now().isoformat(),
    'blocked_for_trading': False
}

TEST_STRATEGY_QUARANTINE = {
    'strategy_id': 'institutional_footprint',
    'execution_mode': 'QUARANTINE',
    'status': 'QUARANTINE',
    'win_rate': 0.52,
    'profit_factor': 1.12,
    'dd_pct': 4.8,
    'consecutive_losses': 5,
    'usr_trades_count': 35,
    'updated_at': (datetime.now() - timedelta(hours=1)).isoformat(),
    'blocked_for_trading': True
}

TEST_STRATEGY_SHADOW = {
    'strategy_id': 'MOM_BIAS_0001',
    'execution_mode': 'SHADOW',
    'status': 'SHADOW',
    'win_rate': 0.55,
    'profit_factor': 1.38,
    'dd_pct': 1.9,
    'consecutive_losses': 0,
    'usr_trades_count': 42,
    'updated_at': datetime.now().isoformat(),
    'blocked_for_trading': False
}

# List of all test usr_strategies (for get_all_usr_strategies mock)
TEST_STRATEGIES = [
    TEST_STRATEGY_LIVE,
    TEST_STRATEGY_QUARANTINE,
    TEST_STRATEGY_SHADOW
]

# Mapping by strategy_id for easy lookup
TEST_STRATEGIES_BY_ID = {
    s['strategy_id']: s for s in TEST_STRATEGIES
}

# Status mappings for CircuitBreaker mock
TEST_STRATEGY_STATUS_MAP = {
    'BRK_OPEN_0001': 'LIVE',
    'institutional_footprint': 'QUARANTINE',
    'MOM_BIAS_0001': 'SHADOW'
}

TEST_STRATEGY_BLOCKED_MAP = {
    'BRK_OPEN_0001': False,
    'institutional_footprint': True,
    'MOM_BIAS_0001': False
}

# Status priority for sorting (LIVE > SHADOW > QUARANTINE > UNKNOWN)
# Used in: StrategyMonitorService.get_all_usr_strategies_metrics()
TEST_STATUS_PRIORITY_MAP = {
    'LIVE': 0,
    'SHADOW': 1,
    'QUARANTINE': 2,
    'UNKNOWN': 3
}

# ============================================================================
# HELPER FUNCTIONS FOR MOCK SETUP
# ============================================================================

def get_test_strategy(strategy_id: str) -> dict | None:
    """
    Get test strategy data by ID (replaces hardcoded lookups).
    
    Args:
        strategy_id: The strategy identifier
    
    Returns:
        Strategy data dict or None if not found
    """
    return TEST_STRATEGIES_BY_ID.get(strategy_id)


def get_test_strategy_ids() -> list[str]:
    """Get list of all test strategy IDs."""
    return list(TEST_STRATEGIES_BY_ID.keys())


def get_test_strategy_statuses() -> dict:
    """Get status mapping for all test usr_strategies."""
    return TEST_STRATEGY_STATUS_MAP.copy()


def get_test_strategy_blocked_statuses() -> dict:
    """Get blocked/trading status mapping for all test usr_strategies."""
    return TEST_STRATEGY_BLOCKED_MAP.copy()


def get_test_status_priority() -> dict:
    """
    Get status priority mapping for sorting.
    LIVE (0) > SHADOW (1) > QUARANTINE (2) > UNKNOWN (3)
    
    Used by: StrategyMonitorService.get_all_usr_strategies_metrics()
    """
    return TEST_STATUS_PRIORITY_MAP.copy()
