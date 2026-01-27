"""
Twelve Data Provider
Free tier: 800 requests/day, 8 requests/minute
Requiere API key gratuita de https://twelvedata.com/
"""
import logging
from typing import Optional
import pandas as pd
import requests

logger = logging.getLogger(__name__)


class TwelveDataProvider:
    """
    Data provider using Twelve Data API
    Free tier available with limitations
    """
    
    BASE_URL = "https://api.twelvedata.com/time_series"
    
    # Timeframe mapping
    TIMEFRAME_MAPPING = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "1h",
        "H4": "4h",
        "D1": "1day",
        "W1": "1week",
        "MN1": "1month",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Twelve Data provider
        
        Args:
            api_key: Twelve Data API key (required)
        """
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise ValueError("Twelve Data requires a valid API key")
        
        self.api_key = api_key
        logger.info("TwelveDataProvider initialized")
    
    def _map_timeframe(self, timeframe: str) -> str:
        """Map Aethelgard timeframe to Twelve Data format"""
        return self.TIMEFRAME_MAPPING.get(timeframe, "5min")
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from Twelve Data
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe
            count: Number of candles (max 5000)
        
        Returns:
            DataFrame with OHLC data
        """
        try:
            td_timeframe = self._map_timeframe(timeframe)
            
            params = {
                "symbol": symbol,
                "interval": td_timeframe,
                "outputsize": min(count, 5000),
                "apikey": self.api_key,
                "format": "JSON"
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Twelve Data API error: {response.status_code}")
                return None
            
            data = response.json()
            
            # Check for errors
            if "status" in data and data["status"] == "error":
                logger.error(f"Twelve Data error: {data.get('message', 'Unknown error')}")
                return None
            
            if "values" not in data:
                logger.error(f"Unexpected response format from Twelve Data")
                return None
            
            # Parse values
            values = data["values"]
            
            rows = []
            for item in values:
                rows.append({
                    'time': pd.to_datetime(item['datetime']),
                    'open': float(item['open']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'close': float(item['close']),
                    'volume': int(item.get('volume', 0))
                })
            
            df = pd.DataFrame(rows)
            df = df.sort_values('time').reset_index(drop=True)
            
            logger.info(f"Fetched {len(df)} candles from Twelve Data for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from Twelve Data: {e}")
            return None
