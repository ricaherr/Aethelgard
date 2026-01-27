"""
Finnhub Data Provider
Free tier: 60 requests/minute
Requiere API key gratuita de https://finnhub.io/
"""
import logging
from typing import Optional
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


class FinnhubProvider:
    """
    Data provider using Finnhub API
    Free tier available with limitations
    """
    
    BASE_URL = "https://finnhub.io/api/v1"
    
    # Finnhub uses resolution in minutes
    TIMEFRAME_MAPPING = {
        "M1": "1",
        "M5": "5",
        "M15": "15",
        "M30": "30",
        "H1": "60",
        "D1": "D",
        "W1": "W",
        "MN1": "M",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Finnhub provider
        
        Args:
            api_key: Finnhub API key (required)
        """
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise ValueError("Finnhub requires a valid API key")
        
        self.api_key = api_key
        logger.info("FinnhubProvider initialized")
    
    def _map_timeframe(self, timeframe: str) -> str:
        """Map Aethelgard timeframe to Finnhub resolution"""
        return self.TIMEFRAME_MAPPING.get(timeframe, "5")
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from Finnhub
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe
            count: Number of candles
        
        Returns:
            DataFrame with OHLC data
        """
        try:
            resolution = self._map_timeframe(timeframe)
            
            # Calculate time range
            end_time = int(time.time())
            
            # Estimate seconds needed based on timeframe
            if resolution in ["1", "5", "15", "30", "60"]:
                minutes_per_candle = int(resolution)
                seconds_needed = count * minutes_per_candle * 60
            elif resolution == "D":
                seconds_needed = count * 86400  # days
            elif resolution == "W":
                seconds_needed = count * 604800  # weeks
            elif resolution == "M":
                seconds_needed = count * 2592000  # months (approximate)
            else:
                seconds_needed = count * 300  # default 5 minutes
            
            start_time = end_time - int(seconds_needed * 1.5)  # Add buffer
            
            url = f"{self.BASE_URL}/stock/candle"
            
            params = {
                "symbol": symbol,
                "resolution": resolution,
                "from": start_time,
                "to": end_time,
                "token": self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Finnhub API error: {response.status_code}")
                return None
            
            data = response.json()
            
            # Check for errors
            if data.get("s") == "no_data":
                logger.warning(f"No data returned from Finnhub for {symbol}")
                return None
            
            if "t" not in data or not data["t"]:
                logger.warning(f"Invalid response from Finnhub for {symbol}")
                return None
            
            # Parse candles
            timestamps = data["t"]
            opens = data["o"]
            highs = data["h"]
            lows = data["l"]
            closes = data["c"]
            volumes = data["v"]
            
            rows = []
            for i in range(len(timestamps)):
                rows.append({
                    'time': pd.to_datetime(timestamps[i], unit='s'),
                    'open': float(opens[i]),
                    'high': float(highs[i]),
                    'low': float(lows[i]),
                    'close': float(closes[i]),
                    'volume': int(volumes[i])
                })
            
            df = pd.DataFrame(rows)
            df = df.sort_values('time').reset_index(drop=True)
            
            # Limit to requested count
            if len(df) > count:
                df = df.tail(count).reset_index(drop=True)
            
            logger.info(f"Fetched {len(df)} candles from Finnhub for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from Finnhub: {e}")
            return None
