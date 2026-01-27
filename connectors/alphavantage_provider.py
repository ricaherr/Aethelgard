"""
Alpha Vantage Data Provider - Free tier with API key
Proveedor gratuito con límite de 500 requests/día
API Key gratuita en: https://www.alphavantage.co/support/#api-key
"""
import logging
from typing import Optional
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class AlphaVantageProvider:
    """
    Alpha Vantage data provider
    
    Features:
    - Free tier: 500 requests/day
    - Stocks, Forex, Crypto support
    - No credit card required
    
    Get free API key at: https://www.alphavantage.co/support/#api-key
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    # Timeframe mapping
    TIMEFRAME_MAP = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "60min",
        "D1": "daily",
        "W1": "weekly",
        "MN1": "monthly"
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Alpha Vantage provider
        
        Args:
            api_key: Alpha Vantage API key (get free at alphavantage.co)
        """
        if requests is None:
            raise ImportError("requests library required. Install: pip install requests")
        
        self.api_key = api_key
        
        if not self.api_key:
            logger.warning("Alpha Vantage API key not provided. Provider will not work.")
        
        logger.info("AlphaVantageProvider initialized")
    
    def is_available(self) -> bool:
        """Check if provider is available"""
        return bool(self.api_key and requests)
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from Alpha Vantage
        
        Args:
            symbol: Symbol to fetch (e.g., 'AAPL', 'EUR/USD')
            timeframe: Timeframe (M1, M5, H1, D1, etc.)
            count: Number of candles (max 5000)
        
        Returns:
            DataFrame with OHLC data or None
        """
        if not self.is_available():
            logger.error("Alpha Vantage not available (missing API key)")
            return None
        
        try:
            # Detect symbol type
            if "/" in symbol or len(symbol) == 6:
                # Forex
                return self._fetch_forex(symbol, timeframe, count)
            elif "-" in symbol or "BTC" in symbol.upper() or "ETH" in symbol.upper():
                # Crypto
                return self._fetch_crypto(symbol, timeframe, count)
            else:
                # Stock
                return self._fetch_stock(symbol, timeframe, count)
        
        except Exception as e:
            logger.error(f"Error fetching data from Alpha Vantage: {e}")
            return None
    
    def _fetch_stock(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        """Fetch stock data"""
        interval = self.TIMEFRAME_MAP.get(timeframe, "5min")
        
        # For intraday
        if interval in ["1min", "5min", "15min", "30min", "60min"]:
            function = "TIME_SERIES_INTRADAY"
            params = {
                "function": function,
                "symbol": symbol,
                "interval": interval,
                "apikey": self.api_key,
                "outputsize": "full" if count > 100 else "compact"
            }
        else:
            # Daily, weekly, monthly
            function_map = {
                "daily": "TIME_SERIES_DAILY",
                "weekly": "TIME_SERIES_WEEKLY",
                "monthly": "TIME_SERIES_MONTHLY"
            }
            function = function_map.get(interval, "TIME_SERIES_DAILY")
            params = {
                "function": function,
                "symbol": symbol,
                "apikey": self.api_key,
                "outputsize": "full" if count > 100 else "compact"
            }
        
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for errors
        if "Error Message" in data:
            logger.error(f"Alpha Vantage error: {data['Error Message']}")
            return None
        
        if "Note" in data:
            logger.warning(f"Alpha Vantage limit reached: {data['Note']}")
            return None
        
        # Parse response
        time_series_key = [k for k in data.keys() if "Time Series" in k]
        if not time_series_key:
            logger.error("No time series data in response")
            return None
        
        time_series = data[time_series_key[0]]
        
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Rename columns
        df.columns = ["open", "high", "low", "close", "volume"]
        df = df.astype(float)
        
        # Limit to requested count
        df = df.tail(count)
        
        logger.info(f"Fetched {len(df)} candles for {symbol} from Alpha Vantage")
        return df
    
    def _fetch_forex(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        """Fetch forex data"""
        # Convert EURUSD to EUR/USD format if needed
        if "/" not in symbol:
            from_currency = symbol[:3]
            to_currency = symbol[3:]
        else:
            from_currency, to_currency = symbol.split("/")
        
        interval = self.TIMEFRAME_MAP.get(timeframe, "5min")
        
        if interval in ["1min", "5min", "15min", "30min", "60min"]:
            params = {
                "function": "FX_INTRADAY",
                "from_symbol": from_currency,
                "to_symbol": to_currency,
                "interval": interval,
                "apikey": self.api_key,
                "outputsize": "full" if count > 100 else "compact"
            }
        else:
            function_map = {
                "daily": "FX_DAILY",
                "weekly": "FX_WEEKLY",
                "monthly": "FX_MONTHLY"
            }
            function = function_map.get(interval, "FX_DAILY")
            params = {
                "function": function,
                "from_symbol": from_currency,
                "to_symbol": to_currency,
                "apikey": self.api_key,
                "outputsize": "full" if count > 100 else "compact"
            }
        
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for errors
        if "Error Message" in data:
            logger.error(f"Alpha Vantage error: {data['Error Message']}")
            return None
        
        # Parse response
        time_series_key = [k for k in data.keys() if "Time Series" in k]
        if not time_series_key:
            logger.error("No time series data in response")
            return None
        
        time_series = data[time_series_key[0]]
        
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Rename columns
        df.columns = ["open", "high", "low", "close"]
        df["volume"] = 0  # Forex doesn't have volume
        df = df.astype(float)
        
        # Limit to requested count
        df = df.tail(count)
        
        logger.info(f"Fetched {len(df)} candles for {symbol} from Alpha Vantage")
        return df
    
    def _fetch_crypto(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        """Fetch crypto data"""
        # Parse symbol (e.g., BTC-USD, BTCUSD)
        if "-" in symbol:
            base, quote = symbol.split("-")
        else:
            base = symbol[:3]
            quote = symbol[3:]
        
        interval = self.TIMEFRAME_MAP.get(timeframe, "5min")
        
        if interval in ["1min", "5min", "15min", "30min", "60min"]:
            params = {
                "function": "CRYPTO_INTRADAY",
                "symbol": base,
                "market": quote,
                "interval": interval,
                "apikey": self.api_key,
                "outputsize": "full" if count > 100 else "compact"
            }
        else:
            params = {
                "function": "DIGITAL_CURRENCY_DAILY",
                "symbol": base,
                "market": quote,
                "apikey": self.api_key
            }
        
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for errors
        if "Error Message" in data:
            logger.error(f"Alpha Vantage error: {data['Error Message']}")
            return None
        
        # Parse response
        time_series_key = [k for k in data.keys() if "Time Series" in k]
        if not time_series_key:
            logger.error("No time series data in response")
            return None
        
        time_series = data[time_series_key[0]]
        
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Rename columns (crypto has different naming)
        if "1. open" in df.columns:
            df = df.rename(columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume"
            })
        
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        
        # Limit to requested count
        df = df.tail(count)
        
        logger.info(f"Fetched {len(df)} candles for {symbol} from Alpha Vantage")
        return df
