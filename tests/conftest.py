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
                 ask=None, bid=None, trade_mode=None, symbol=None):
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
        self.digits = 5
        self.trade_mode = trade_mode or 4  # TRADE_MODE_FULL


@pytest.fixture
def storage(tmp_path):
    """
    Create temporary in-memory database for testing.
    
    Ensures test isolation - each test gets fresh database.
    """
    db_path = tmp_path / "test_db.db"
    return StorageManager(db_path=str(db_path))
