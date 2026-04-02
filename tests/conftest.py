"""
Pytest configuration file.
Ensures the project root is in sys.path for imports.
Provides shared fixtures for all tests.
"""

import sys
from pathlib import Path
import pytest

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_vault.storage import StorageManager


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
    Create isolated database for testing using temporary files.

    Each test gets a unique database in a temporary directory.
    This ensures complete test isolation without file system locks.

    Args:
        tmp_path: Pytest's built-in temporary directory fixture

    Returns:
        StorageManager instance with isolated database
    """
    import uuid
    # Create unique DB file per test in temp directory
    db_file = tmp_path / f"test_db_{uuid.uuid4().hex[:8]}.db"
    unique_db_path = str(db_file)

    storage_mgr = StorageManager(db_path=unique_db_path)

    yield storage_mgr

    # Cleanup: Close the unique connection after test
    from data_vault.database_manager import get_database_manager
    db_manager = get_database_manager()
    db_manager.close_connection(unique_db_path)


@pytest.fixture(autouse=True)
def cleanup_database_manager():
    """
    Auto-cleanup fixture: Ensures ALL test database connections are properly closed.

    This is CRITICAL for Windows to allow tmp path cleanup:
    Without this, PermissionError: [WinError 32] prevents pytest from deleting tmp files.

    The global database connection stays alive for the full test session.
    """
    yield

    # After test completes, close ALL non-global DB connections immediately
    # This allows pytest to clean up tmp_path directories on Windows
    from data_vault.database_manager import get_database_manager
    db_manager = get_database_manager()

    # Get the expected global DB path
    from pathlib import Path
    global_db_path = str(Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db")

    # Close ALL non-global connections (including :memory: and tmp files)
    # We iterate over a copy of keys to avoid RuntimeError during iteration
    db_paths_to_close = list(db_manager._connection_pool.keys())

    for db_path in db_paths_to_close:
        # Keep ONLY the global database alive
        if db_path != global_db_path:
            try:
                # Explicit checkpoint before closing to ensure WAL is merged
                conn = db_manager._connection_pool.get(db_path)
                if conn:
                    try:
                        conn.execute("PRAGMA wal_checkpoint(RESTART)")
                    except Exception:
                        pass  # Connection might be in bad state

                db_manager.close_connection(db_path)
            except Exception:
                pass  # Connection might already be closed


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

# ========================================================================================
# NEWS SANITIZER CONSTANTS (Imported with lazy fallback)
# Try to import from source to satisfy interface validation, fallback to local definition
# ========================================================================================

try:
    # Try to import from news_sanitizer (will fail on first load due to server init)
    from core_brain.news_sanitizer import VALID_COUNTRY_CODES, IMPACT_NORMALIZER
except ImportError:
    # Fallback: Define locally (copied from source) to avoid server initialization
    # If these change in core_brain/news_sanitizer.py, they MUST be updated here too
    VALID_COUNTRY_CODES = {
        "US", "EU", "GB", "JP", "CH", "CA", "AU", "NZ", "CN", "IN", "BR", "MX",
        "ZA", "SG", "HK", "KR", "RU", "SE", "NO", "DK", "NL", "BE", "FR", "DE",
        "IT", "ES", "PT", "GR", "CZ", "PL", "TR", "SA", "AE", "IL", "TH", "ID"
    }

    IMPACT_NORMALIZER = {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "UNKNOWN": 0
    }

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
