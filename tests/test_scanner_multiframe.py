"""
Test: Scanner Multi-Timeframe Support
======================================

Validates that ScannerEngine correctly scans multiple timeframes
for each symbol and generates independent regime classifications.
"""
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import time

from core_brain.scanner import ScannerEngine
from models.signal import MarketRegime


class MockDataProvider:
    """Mock data provider for testing"""
    
    def fetch_ohlc(self, symbol: str, timeframe: str = "M5", count: int = 500, only_system: bool = False):
        """Return mock OHLC data"""
        # Create different data patterns based on timeframe for variety
        if timeframe == "M5":
            trend_strength = 0.8
        elif timeframe == "H1":
            trend_strength = 0.6
        else:  # H4, D1, etc
            trend_strength = 0.4
        
        return pd.DataFrame({
            'time': pd.date_range('2024-01-01', periods=count, freq='1h'),
            'open': [100.0 + i * trend_strength for i in range(count)],
            'high': [100.5 + i * trend_strength for i in range(count)],
            'low': [99.5 + i * trend_strength for i in range(count)],
            'close': [100.2 + i * trend_strength for i in range(count)],
        })


@pytest.fixture
def mock_provider():
    """Provide mock data provider"""
    return MockDataProvider()


def test_scanner_loads_active_timeframes_from_config(tmp_path):
    """Scanner should load active timeframes from config.json"""
    import json
    
    # Create temporary config with 3 active timeframes
    config_path = tmp_path / "config.json"
    config_data = {
        "scanner": {
            "timeframes": [
                {"timeframe": "M1", "enabled": False},
                {"timeframe": "M5", "enabled": True},
                {"timeframe": "H1", "enabled": True},
                {"timeframe": "H4", "enabled": True},
                {"timeframe": "D1", "enabled": False}
            ],
            "cpu_limit_pct": 80.0,
            "mt5_bars_count": 100
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(config_data, f)
    
    scanner = ScannerEngine(
        assets=["EURUSD"],
        data_provider=MockDataProvider(),
        config_path=str(config_path)
    )
    
    # Should have loaded 3 active timeframes
    assert len(scanner.active_timeframes) == 3
    assert "M5" in scanner.active_timeframes
    assert "H1" in scanner.active_timeframes
    assert "H4" in scanner.active_timeframes
    assert "M1" not in scanner.active_timeframes  # disabled
    assert "D1" not in scanner.active_timeframes  # disabled


def test_scanner_creates_classifier_per_symbol_timeframe_combination(mock_provider):
    """Scanner should create one classifier per (symbol, timeframe) combination"""
    import json
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "scanner": {
                "timeframes": [
                    {"timeframe": "M5", "enabled": True},
                    {"timeframe": "H1", "enabled": True}
                ],
                "cpu_limit_pct": 80.0,
                "mt5_bars_count": 100
            }
        }
        json.dump(config_data, f)
        config_path = f.name
    
    scanner = ScannerEngine(
        assets=["EURUSD", "GBPUSD"],
        data_provider=mock_provider,
        config_path=config_path
    )
    
    # 2 symbols × 2 timeframes = 4 classifiers
    assert len(scanner.classifiers) == 4
    
    # Verify keys
    assert "EURUSD|M5" in scanner.classifiers
    assert "EURUSD|H1" in scanner.classifiers
    assert "GBPUSD|M5" in scanner.classifiers
    assert "GBPUSD|H1" in scanner.classifiers


def test_scanner_processes_all_timeframes_independently(mock_provider):
    """Scanner should process each timeframe independently"""
    import json
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "scanner": {
                "timeframes": [
                    {"timeframe": "M5", "enabled": True},
                    {"timeframe": "H1", "enabled": True},
                    {"timeframe": "H4", "enabled": True}
                ],
                "cpu_limit_pct": 80.0,
                "mt5_bars_count": 100,
                "base_sleep_seconds": 0.1  # Fast for testing
            }
        }
        json.dump(config_data, f)
        config_path = f.name
    
    scanner = ScannerEngine(
        assets=["EURUSD"],
        data_provider=mock_provider,
        config_path=config_path
    )
    
    # Run one scan cycle
    scanner._run_cycle()
    
    # Should have results for all 3 timeframes
    results = scanner.get_scan_results_with_data()
    
    assert len(results) == 3
    assert "EURUSD|M5" in results
    assert "EURUSD|H1" in results
    assert "EURUSD|H4" in results
    
    # Each should have regime and dataframe
    for key, data in results.items():
        assert "regime" in data
        assert "df" in data
        assert "symbol" in data
        assert "timeframe" in data
        assert data["symbol"] == "EURUSD"
        assert isinstance(data["regime"], MarketRegime)


def test_scan_results_include_symbol_and_timeframe_metadata(mock_provider):
    """Scan results should include symbol and timeframe in metadata"""
    import json
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "scanner": {
                "timeframes": [
                    {"timeframe": "M5", "enabled": True},
                    {"timeframe": "H4", "enabled": True}
                ],
                "cpu_limit_pct": 80.0,
                "mt5_bars_count": 100
            }
        }
        json.dump(config_data, f)
        config_path = f.name
    
    scanner = ScannerEngine(
        assets=["BTCUSD"],
        data_provider=mock_provider,
        config_path=config_path
    )
    
    scanner._run_cycle()
    results = scanner.get_scan_results_with_data()
    
    # Verify M5 result
    m5_result = results.get("BTCUSD|M5")
    assert m5_result is not None
    assert m5_result["symbol"] == "BTCUSD"
    assert m5_result["timeframe"] == "M5"
    
    # Verify H4 result
    h4_result = results.get("BTCUSD|H4")
    assert h4_result is not None
    assert h4_result["symbol"] == "BTCUSD"
    assert h4_result["timeframe"] == "H4"


def test_scanner_fallback_to_legacy_single_timeframe(mock_provider):
    """Scanner should fallback to mt5_timeframe if timeframes array not configured"""
    import json
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "scanner": {
                # No timeframes array - legacy config
                "mt5_timeframe": "M15",
                "cpu_limit_pct": 80.0,
                "mt5_bars_count": 100
            }
        }
        json.dump(config_data, f)
        config_path = f.name
    
    scanner = ScannerEngine(
        assets=["EURUSD"],
        data_provider=mock_provider,
        config_path=config_path
    )
    
    # Should fallback to single timeframe
    assert len(scanner.active_timeframes) == 1
    assert scanner.active_timeframes[0] == "M15"


def test_different_regimes_per_timeframe(mock_provider):
    """Different timeframes can have different regimes for same symbol"""
    import json
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "scanner": {
                "timeframes": [
                    {"timeframe": "M5", "enabled": True},
                    {"timeframe": "H1", "enabled": True}
                ],
                "cpu_limit_pct": 80.0,
                "mt5_bars_count": 100
            }
        }
        json.dump(config_data, f)
        config_path = f.name
    
    scanner = ScannerEngine(
        assets=["EURUSD"],
        data_provider=mock_provider,
        config_path=config_path
    )
    
    scanner._run_cycle()
    results = scanner.get_scan_results_with_data()
    
    # Both timeframes should be scanned
    assert "EURUSD|M5" in results
    assert "EURUSD|H1" in results
    
    # Regimes can differ (though with mock data they might be same)
    # Just verify both have valid regimes
    assert isinstance(results["EURUSD|M5"]["regime"], MarketRegime)
    assert isinstance(results["EURUSD|H1"]["regime"], MarketRegime)
