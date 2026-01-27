"""
Alpha Vantage Data Provider
Free tier: 25 requests/day, 5 requests/minute
Requiere API key gratuita de https://www.alphavantage.co/support/#api-key
"""
import logging
from typing import Optional
import pandas as pd
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class AlphaVantageProvider:
    """
    Data provider using Alpha Vantage API
    Free tier available with limitations
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    # Timeframe mapping
    TIMEFRAME_MAPPING = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "60min",
        "D1": "daily",
        "W1": "weekly",
        "MN1": "monthly",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Alpha Vantage provider
        
        Args:
            api_key: Alpha Vantage API key (required)
        """
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise ValueError("Alpha Vantage requires a valid API key")
        
        self.api_key = api_key
        logger.info("AlphaVantageProvider initialized")
    
    def _map_timeframe(self, timeframe: str) -> str:
        """Map Aethelgard timeframe to Alpha Vantage format"""
        return self.TIMEFRAME_MAPPING.get(timeframe, "5min")
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from Alpha Vantage
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe
            count: Number of candles (max 100 for free tier intraday)
        
        Returns:
            DataFrame with OHLC data
        """
        try:
            av_timeframe = self._map_timeframe(timeframe)
            
            # Determine function based on timeframe
            if av_timeframe in ["1min", "5min", "15min", "30min", "60min"]:
                function = "TIME_SERIES_INTRADAY"
                params = {
                    "function": function,
                    "symbol": symbol,
                    "interval": av_timeframe,
                    "apikey": self.api_key,
                    "outputsize": "compact" if count <= 100 else "full"
                }
                time_series_key = f"Time Series ({av_timeframe})"
            elif av_timeframe == "daily":
                function = "TIME_SERIES_DAILY"
                params = {
                    "function": function,
                    "symbol": symbol,
                    "apikey": self.api_key,
                    "outputsize": "compact" if count <= 100 else "full"
                }
                time_series_key = "Time Series (Daily)"
            else:
                logger.warning(f"Timeframe {timeframe} not supported by Alpha Vantage")
                return None
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Alpha Vantage API error: {response.status_code}")
                return None
            
            data = response.json()
            
            # Check for error messages
            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                return None
            
            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                return None
            
            if time_series_key not in data:
                logger.error(f"Unexpected response format from Alpha Vantage")
                return None
            
            # Parse time series data
            time_series = data[time_series_key]
            
            rows = []
            for timestamp, values in time_series.items():
                rows.append({
                    'time': pd.to_datetime(timestamp),
                    'open': float(values['1. open']),
                    'high': float(values['2. high']),
                    'low': float(values['3. low']),
                    'close': float(values['4. close']),
                    'volume': int(values['5. volume'])
                })
            
            df = pd.DataFrame(rows)
            df = df.sort_values('time').reset_index(drop=True)
            
            # Limit to requested count
            if len(df) > count:
                df = df.tail(count).reset_index(drop=True)
            
            logger.info(f"Fetched {len(df)} candles from Alpha Vantage for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from Alpha Vantage: {e}")
            return None
