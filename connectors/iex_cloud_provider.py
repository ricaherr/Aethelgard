"""
IEX Cloud Data Provider
Free tier: 50,000 requests/month
Requiere API key de https://iexcloud.io/
"""
import logging
from typing import Optional
import pandas as pd
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IEXCloudProvider:
    """
    Data provider using IEX Cloud API
    Free tier available with limitations
    """
    
    BASE_URL = "https://cloud.iexapis.com/stable"
    
    # Timeframe mapping
    TIMEFRAME_MAPPING = {
        "M1": "1m",
        "M5": "5m",
        "M15": "15m",
        "M30": "30m",
        "H1": "1h",
        "D1": "1d",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize IEX Cloud provider
        
        Args:
            api_key: IEX Cloud API key (required)
        """
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise ValueError("IEX Cloud requires a valid API key")
        
        self.api_key = api_key
        logger.info("IEXCloudProvider initialized")
    
    def _map_timeframe(self, timeframe: str) -> str:
        """Map Aethelgard timeframe to IEX Cloud format"""
        return self.TIMEFRAME_MAPPING.get(timeframe, "5m")
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from IEX Cloud
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe
            count: Number of candles
        
        Returns:
            DataFrame with OHLC data
        """
        try:
            iex_timeframe = self._map_timeframe(timeframe)
            
            # For intraday data
            if iex_timeframe.endswith('m') or iex_timeframe.endswith('h'):
                url = f"{self.BASE_URL}/stock/{symbol}/intraday-prices"
                params = {
                    "token": self.api_key,
                    "chartInterval": iex_timeframe.replace('m', '').replace('h', ''),
                }
            else:
                # For daily data
                url = f"{self.BASE_URL}/stock/{symbol}/chart/1m"
                params = {
                    "token": self.api_key,
                }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"IEX Cloud API error: {response.status_code}")
                return None
            
            data = response.json()
            
            if not data:
                logger.warning(f"No data returned from IEX Cloud for {symbol}")
                return None
            
            # Parse data
            rows = []
            for item in data:
                # Skip items without required fields
                if not all(key in item for key in ['date', 'open', 'high', 'low', 'close']):
                    continue
                
                # Build timestamp
                date_str = item['date']
                minute_str = item.get('minute', '00:00')
                timestamp = pd.to_datetime(f"{date_str} {minute_str}")
                
                rows.append({
                    'time': timestamp,
                    'open': float(item['open']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'close': float(item['close']),
                    'volume': int(item.get('volume', 0))
                })
            
            if not rows:
                logger.warning(f"No valid data parsed from IEX Cloud for {symbol}")
                return None
            
            df = pd.DataFrame(rows)
            df = df.sort_values('time').reset_index(drop=True)
            
            # Limit to requested count
            if len(df) > count:
                df = df.tail(count).reset_index(drop=True)
            
            logger.info(f"Fetched {len(df)} candles from IEX Cloud for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data from IEX Cloud: {e}")
            return None
