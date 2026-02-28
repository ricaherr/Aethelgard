import logging
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from models.signal import Signal, SignalType
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class ConfluenceService:
    """
    Engine for Multi-Market Correlation & Confluence analysis.
    Detecs divergences (Symmetric/Asymmetric) and provides trade confirmation.
    """
    
    # Standard correlations for validation
    CORRELATION_MAP = {
        "EURUSD": {"inverse": ["DXY", "USDJPY", "USDCAD"], "direct": ["GBPUSD", "AUDUSD"]},
        "GBPUSD": {"inverse": ["DXY"], "direct": ["EURUSD"]},
        "BTCUSD": {"direct": ["ETHUSD", "NDX", "NAS100"]},
        "BTC": {"direct": ["ETH", "NAS100"]},
        "XAUUSD": {"inverse": ["DXY", "USDJPY"], "direct": ["XAGUSD"]},
        "GOLD": {"inverse": ["DXY"], "direct": ["SILVER"]},
    }

    def __init__(self, storage: StorageManager):
        self.storage = storage
        logger.info("ConfluenceService initialized.")

    def get_correlation_coefficient(self, data_a: pd.Series, data_b: pd.Series, window: int = 20) -> float:
        """Calculates Pearson correlation coefficient."""
        if len(data_a) < window or len(data_b) < window:
            return 0.0
        return data_a.corr(data_b)

    def detect_divergence(
        self, 
        base_data: pd.DataFrame, 
        correlated_data: pd.DataFrame, 
        inverse: bool = False
    ) -> Dict[str, Any]:
        """
        Detects SmT (Smart Money Tool) style divergence between two assets.
        
        Symmetric Divergence: Asset A makes new high, Asset B fails to make new high.
        Symmetric Divergence (Inverse): Asset A makes new high, Asset B fails to make new low.
        """
        if base_data.empty or correlated_data.empty:
            return {"divergence": False, "type": "NONE", "confidence": 0.0}

        # Simplified logic for recent peaks/troughs (last 5-10 bars)
        # In a real scenario, we'd use pivot points.
        
        last_high_a = base_data['high'].iloc[-10:].max()
        prev_high_a = base_data['high'].iloc[-20:-10].max()
        
        last_high_b = correlated_data['high'].iloc[-10:].max()
        prev_high_b = correlated_data['high'].iloc[-20:-10].max()
        
        last_low_a = base_data['low'].iloc[-10:].min()
        prev_low_a = base_data['low'].iloc[-20:-10].min()
        
        last_low_b = correlated_data['low'].iloc[-10:].min()
        prev_low_b = correlated_data['low'].iloc[-20:-10].min()

        divergence = False
        div_type = "NONE"
        confidence = 0.0

        # Bullish Divergence (Symmetric)
        # Base makes Lower Low, Correlated fails to make Lower Low (Symmetric)
        if last_low_a < prev_low_a and not (last_low_b < prev_low_b) and not inverse:
            divergence = True
            div_type = "BULLISH_SYMMETRIC"
            confidence = 0.8
        
        # Bullish Divergence (Inverse - e.g. DXY vs EURUSD)
        # EURUSD makes Lower Low, DXY fails to make Higher High
        elif last_low_a < prev_low_a and not (last_high_b > prev_high_b) and inverse:
            divergence = True
            div_type = "BULLISH_INVERSE"
            confidence = 0.85

        # Bearish Divergence (Symmetric)
        elif last_high_a > prev_high_a and not (last_high_b > prev_high_b) and not inverse:
            divergence = True
            div_type = "BEARISH_SYMMETRIC"
            confidence = 0.8

        # Bearish Divergence (Inverse)
        elif last_high_a > prev_high_a and not (last_low_b < prev_low_b) and inverse:
            divergence = True
            div_type = "BEARISH_INVERSE"
            confidence = 0.85

        return {
            "divergence": divergence, 
            "type": div_type, 
            "confidence": confidence,
            "metrics": {
                "base_ll": last_low_a < prev_low_a,
                "corr_ll": last_low_b < prev_low_b,
                "base_hh": last_high_a > prev_high_a,
                "corr_hh": last_high_b > prev_high_b
            }
        }

    def validate_confluence(
        self, 
        symbol: str, 
        side: str, 
        connector: Any, 
        timeframe: str = "M5"
    ) -> Tuple[bool, str, float]:
        """
        Main entry point for RiskManager to validate a trade.
        Returns (is_confirmed, reason, confidence_penalty)
        """
        symbol_clean = symbol.replace("=X", "").replace(".", "").upper()
        correlations = self.CORRELATION_MAP.get(symbol_clean)
        
        if not correlations:
            return True, "No correlation map for asset, skipping check.", 0.0

        # Fetch data for correlated assets
        # For brevity, we check the most representative one
        target_corr = correlations.get("inverse", correlations.get("direct", []))[0]
        
        try:
            # We assume connector has fetch_ohlc (standardized in Aethelgard)
            base_ohlcv = connector.fetch_ohlc(symbol, timeframe, count=50)
            corr_ohlcv = connector.fetch_ohlc(target_corr, timeframe, count=50)
            
            if base_ohlcv.empty or corr_ohlcv.empty:
                return True, "Insufficient data for correlation check", 0.0

            is_inverse = target_corr in correlations.get("inverse", [])
            div_data = self.detect_divergence(base_ohlcv, corr_ohlcv, inverse=is_inverse)
            
            if div_data["divergence"]:
                # Check if divergence is aligned with trade side
                is_bullish_div = "BULLISH" in div_data["type"]
                is_bearish_div = "BEARISH" in div_data["type"]
                
                if (side == "BUY" and is_bullish_div) or (side == "SELL" and is_bearish_div):
                    return True, f"CONFIRMED: {div_data['type']} divergence detected with {target_corr}", 0.0
                else:
                    return False, f"VETO: Divergence {div_data['type']} conflicts with {side} signal", 0.15

            # If no divergence, check basic alignment (Choppy State check)
            # e.g. if we want to BUY but DXY is also bullish (and is inverse), it's risky
            # This is "Choppy State" detection
            if is_inverse:
                # Basic trend check on last 10 candles
                base_trend = base_ohlcv['close'].iloc[-1] > base_ohlcv['close'].iloc[-10]
                corr_trend = corr_ohlcv['close'].iloc[-1] > corr_ohlcv['close'].iloc[-10]
                
                if base_trend == corr_trend: # Both up or both down in inverse assets = Choppy/Indecision
                    return False, f"CHOPPY: Alignment failure between {symbol} and {target_corr}", 0.20

            return True, f"Aligned with {target_corr}", 0.0

        except Exception as e:
            logger.error(f"Error in confluence validation for {symbol}: {e}")
            return True, f"Check failed: {e}", 0.0
