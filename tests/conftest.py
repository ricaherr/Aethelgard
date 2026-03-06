"""
Pytest configuration file.
Ensures the project root is in sys.path for imports.
Provides shared fixtures for all tests.
"""
import sys
from pathlib import Path
import pytest
from data_vault.storage import StorageManager

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class MockSymbolInfo:
    """
    Shared mock symbol info for multi-asset testing.
    
    Used by:
    - test_risk_calculator_universal.py: MockSymbolInfo(contract_size)
    - test_breakeven_spread_cost.py: MockSymbolInfo(symbol='EURUSD', contract_size=100000, ...)
    
    Supports both usage patterns:
    1. Positional: MockSymbolInfo(100000) → contract_size=100000
    2. Keyword: MockSymbolInfo(symbol='EURUSD', contract_size=100, point=0.01, ...)
    
    Configurable contract_size for different asset classes:
    - Forex (EURUSD): contract_size=100,000
    - Metals (XAUUSD): contract_size=100
    - Crypto (BTCUSD): contract_size=1
    - Indices (US30): contract_size=10
    """
    def __init__(self, contract_size_or_symbol=None, contract_size=None, point=0.00001, 
                 ask=None, bid=None, trade_mode=None, symbol=None, 
                 v_min=0.01, v_max=100.0, v_step=0.01, digits=5):
        # Handle positional usage: MockSymbolInfo(100000)
        if contract_size_or_symbol is not None and isinstance(contract_size_or_symbol, (int, float)):
            self.trade_contract_size = contract_size_or_symbol
            self.name = symbol or 'UNKNOWN'
        # Handle keyword usage: MockSymbolInfo(symbol='EURUSD', contract_size=100000)
        else:
            self.name = contract_size_or_symbol or symbol or 'UNKNOWN'
            self.trade_contract_size = contract_size or 100000
        
        self.point = point
        self.ask = ask or 1.10000
        self.bid = bid or 1.09990
        self.digits = digits
        self.trade_mode = trade_mode or 4  # TRADE_MODE_FULL
        
        # Volume/Lot limits (for normalize_volume)
        self.volume_min = v_min
        self.volume_max = v_max
        self.volume_step = v_step


@pytest.fixture
def storage(tmp_path):
    """
    Create temporary in-memory database for testing.
    
    Ensures test isolation - each test gets fresh database.
    """
    db_path = tmp_path / "test_db.db"
    return StorageManager(db_path=str(db_path))


# ============================================================================
# PHASE D: EXECUTION MODE TEST CONSTANTS (SSOT - Single Source of Truth)
# ============================================================================
# Centralized constants for execution mode, provider, and account type tests.
# These are imported from models.execution_mode for runtime use.

from models.execution_mode import ExecutionMode, Provider, AccountType

# SSOT constant definitions for tests (use these instead of hardcoded strings)
TEST_EXECUTION_MODE_LIVE = ExecutionMode.LIVE.value
TEST_EXECUTION_MODE_SHADOW = ExecutionMode.SHADOW.value
TEST_EXECUTION_MODE_QUARANTINE = ExecutionMode.QUARANTINE.value

TEST_PROVIDER_MT5 = Provider.MT5.value
TEST_PROVIDER_NT = Provider.NT.value
TEST_PROVIDER_FIX = Provider.FIX.value
TEST_PROVIDER_INTERNAL = Provider.INTERNAL.value

TEST_ACCOUNT_TYPE_REAL = AccountType.REAL.value
TEST_ACCOUNT_TYPE_DEMO = AccountType.DEMO.value


# ============================================================================
# NEWSSANITIZER TEST CONSTANTS (SSOT - Single Source of Truth)
# ============================================================================

# Provider sources (economic calendar data providers)
TEST_PROVIDER_SOURCE = "INVESTING"
VALID_PROVIDER_SOURCES = ["INVESTING", "BLOOMBERG", "FOREXFACTORY"]

# Import country codes from source of truth
from core_brain.news_sanitizer import VALID_COUNTRY_CODES

# Import impact normalizer
from core_brain.news_sanitizer import IMPACT_NORMALIZER

# ============================================================================
# ECONOMIC VETO INTERFACE TEST CONSTANTS (SSOT - Single Source of Truth)
# ============================================================================
from datetime import datetime, timedelta

# Economic calendar parameters (SSOT for all tests)
ECON_CACHE_TTL_SECONDS = 60
ECON_MAX_LATENCY_MS = 50
ECON_BUFFER_HIGH_PRE_MINUTES = 15
ECON_BUFFER_HIGH_POST_MINUTES = 10
ECON_BUFFER_MEDIUM_PRE_MINUTES = 5
ECON_BUFFER_MEDIUM_POST_MINUTES = 3
ECON_BUFFER_LOW_PRE_MINUTES = 0
ECON_BUFFER_LOW_POST_MINUTES = 0

# Default event symbol mapping (NOT imported from economic_integration to avoid circular imports)
# This is test-specific SSOT for default events used in testing
DEFAULT_EVENT_SYMBOL_MAPPING = {
    # NFP (Non-Farm Payroll) - USA
    "NFP": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    "UNEMPLOYMENT": ["USD", "EURUSD", "GBPUSD"],
    "INITIAL_CLAIMS": ["USD", "EURUSD"],
    "RETAIL_SALES": ["USD", "EURUSD", "GBPUSD"],
    "CPI": ["USD", "EURUSD", "GBPUSD"],
    "PPI": ["USD", "EURUSD"],
    "FOMC": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    "FED_RATE": ["USD", "EURUSD", "GBPUSD", "USDCAD", "AUDUSD"],
    
    # ECB (European Central Bank)
    "ECB": ["EUR", "EURUSD", "EURGBP", "EURJPY", "EURCHF"],
    "ECB_RATE": ["EUR", "EURUSD", "EURGBP", "EURJPY"],
    "EUROZONE_CPI": ["EUR", "EURUSD", "EURGBP"],
    
    # BOE (Bank of England)
    "BOE": ["GBP", "GBPUSD", "EURGBP", "GBPJPY", "GBPCHF"],
    "BOE_RATE": ["GBP", "GBPUSD", "EURGBP", "GBPJPY"],
    "UK_CPI": ["GBP", "GBPUSD", "EURGBP"],
    
    # RBA (Reserve Bank of Australia)
    "RBA": ["AUD", "AUDUSD", "EURAUD", "AUDJPY", "GBPAUD"],
    "RBA_RATE": ["AUD", "AUDUSD", "EURAUD", "AUDJPY"],
    "AUSTRALIA_CPI": ["AUD", "AUDUSD"],
    
    # BOJ (Bank of Japan)
    "BOJ": ["JPY", "USDJPY", "EURJPY", "GBPJPY", "AUDJPY"],
    "BOJ_RATE": ["JPY", "USDJPY", "EURJPY", "GBPJPY"],
    "JAPAN_CPI": ["JPY", "USDJPY", "EURJPY"],
}


@pytest.fixture
def econ_test_now():
    """Fixture providing current test time. Ensures consistent datetime."""
    return datetime(2026, 3, 5, 10, 0, 0)


@pytest.fixture
def econ_test_event_high_impact(econ_test_now):
    """Fixture providing HIGH impact economic event (NFP)."""
    return {
        "event_id": "evt_nfp_20260305",
        "event_name": "NFP",
        "country": "USA",
        "impact": "HIGH",
        "event_time_utc": econ_test_now,
        "currency": "USD",
        "forecast": "100K",
        "previous": "85K",
    }


@pytest.fixture
def econ_test_event_medium_impact(econ_test_now):
    """Fixture providing MEDIUM impact economic event (PMI)."""
    return {
        "event_id": "evt_pmi_20260305",
        "event_name": "PMI Manufacturing",
        "country": "Eurozone",
        "impact": "MEDIUM",
        "event_time_utc": econ_test_now + timedelta(hours=2),
        "currency": "EUR",
        "forecast": "52.5",
        "previous": "51.8",
    }
