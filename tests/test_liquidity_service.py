import pytest
from core_brain.services.liquidity_service import LiquidityService


from unittest.mock import MagicMock

@pytest.fixture
def service():
    mock_storage = MagicMock()
    mock_storage.get_dynamic_params.return_value = {
        "liquidity_thresholds": {
            "fvg_min_size_pips": 5.0,
            "ob_volume_multiplier": 1.5,
            "max_lookback_candles": 20
        }
    }
    return LiquidityService(storage=mock_storage)


def test_detect_bullish_fvg(service):
    # Setup data where Candle 1 High < Candle 3 Low
    # Velas alcistas agresivas
    ohlcv = [
        {"high": 1.1000, "low": 1.0950, "open": 1.0960, "close": 1.0990, "volume": 100}, # Candle 1
        {"high": 1.1100, "low": 1.1005, "open": 1.1005, "close": 1.1090, "volume": 200}, # Candle 2 (Expansión)
        {"high": 1.1150, "low": 1.1050, "open": 1.1100, "close": 1.1140, "volume": 150}  # Candle 3
    ]
    # Gap is 1.1050 (low 3) - 1.1000 (high 1) = 0.0050 = 50 pips
    pip_size = 0.0001
    
    fvgs = service.detect_fvg(ohlcv, pip_size)
    
    assert len(fvgs) == 1
    assert fvgs[0]["type"] == "bullish_fvg"
    assert fvgs[0]["bottom"] == 1.1000
    assert fvgs[0]["top"] == 1.1050
    assert fvgs[0]["size_pips"] == pytest.approx(50.0)

def test_detect_bearish_fvg(service):
    # Setup data where Candle 1 Low > Candle 3 High
    ohlcv = [
        {"high": 1.1000, "low": 1.0950, "open": 1.0990, "close": 1.0960, "volume": 100}, # Candle 1
        {"high": 1.0950, "low": 1.0850, "open": 1.0940, "close": 1.0860, "volume": 200}, # Candle 2 (Expansión bajista)
        {"high": 1.0900, "low": 1.0800, "open": 1.0850, "close": 1.0810, "volume": 150}  # Candle 3
    ]
    # Gap is 1.0950 (low 1) - 1.0900 (high 3) = 0.0050 = 50 pips
    pip_size = 0.0001
    
    fvgs = service.detect_fvg(ohlcv, pip_size)
    assert len(fvgs) == 1
    assert fvgs[0]["type"] == "bearish_fvg"
    assert fvgs[0]["top"] == 1.0950
    assert fvgs[0]["bottom"] == 1.0900
    assert fvgs[0]["size_pips"] == pytest.approx(50.0)

def test_fvg_too_small(service):
    ohlcv = [
        {"high": 1.1000, "low": 1.0950, "open": 1.0960, "close": 1.0990, "volume": 100},
        {"high": 1.1100, "low": 1.0995, "open": 1.1005, "close": 1.1090, "volume": 200},
        {"high": 1.1150, "low": 1.1002, "open": 1.1100, "close": 1.1140, "volume": 150} 
    ]
    # Gap is 1.1002 (low 3) - 1.1000 (high 1) = 0.0002 = 2 pips
    # Threshold is 5.0 pips
    pip_size = 0.0001
    fvgs = service.detect_fvg(ohlcv, pip_size)
    assert len(fvgs) == 0

def test_detect_bullish_ob(service):
    # Require High volume after a bearish candle
    ohlcv = [
        {"high": 1.1000, "low": 1.0900, "open": 1.0990, "close": 1.0910, "volume": 100}, # Prev (Bearish)
        {"high": 1.1100, "low": 1.0890, "open": 1.0920, "close": 1.1090, "volume": 350}, # Curr (Bullish, high vol > 1.5 * 225)
        {"high": 1.1150, "low": 1.1050, "open": 1.1100, "close": 1.1140, "volume": 150}  # Next
    ]
    obs = service.detect_order_blocks(ohlcv)
    assert len(obs) == 1
    assert obs[0]["type"] == "bullish_ob"
    assert obs[0]["top"] == 1.1000  # High of the previous bearish candle
    assert obs[0]["bottom"] == 1.0900 # Low of the previous bearish candle

def test_is_in_high_probability_zone(service):
    ohlcv = [
        {"high": 1.1000, "low": 1.0950, "open": 1.0960, "close": 1.0990, "volume": 100}, 
        {"high": 1.1100, "low": 1.1005, "open": 1.1005, "close": 1.1090, "volume": 200}, 
        {"high": 1.1150, "low": 1.1050, "open": 1.1100, "close": 1.1140, "volume": 150}  
    ]
    pip_size = 0.0001
    
    # Target buy inside FVG (1.1000 to 1.1050)
    is_high, msg = service.is_in_high_probability_zone("EURUSD", 1.1020, "BUY", ohlcv, pip_size)
    assert is_high is True
    assert "Bullish FVG" in msg
    
    # Target buy outside FVG
    is_high, msg = service.is_in_high_probability_zone("EURUSD", 1.1100, "BUY", ohlcv, pip_size)
    assert is_high is False
    assert "Unknown" not in msg
