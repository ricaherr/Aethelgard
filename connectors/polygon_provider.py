"""
Polygon.io Data Provider - Free tier available
Stocks, Forex, Crypto support
API Key gratuita en: https://polygon.io/
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class PolygonProvider:
    """
    Polygon.io data provider
    
    Features:
    - Free tier disponible (limitado)
    - Stocks, Forex, Crypto, Options
    - Delayed data en tier gratuito
    - Real-time en tiers pagos
    
    Get free API key at: https://polygon.io/
    """
    
    BASE_URL = "https://api.polygon.io"
    
    # Timeframe mapping (for aggregates endpoint)
    TIMEFRAME_MAP = {
        "M1": {"multiplier": 1, "timespan": "minute"},
        "M5": {"multiplier": 5, "timespan": "minute"},
        "M15": {"multiplier": 15, "timespan": "minute"},
        "M30": {"multiplier": 30, "timespan": "minute"},
        "H1": {"multiplier": 1, "timespan": "hour"},
        "H4": {"multiplier": 4, "timespan": "hour"},
        "D1": {"multiplier": 1, "timespan": "day"},
        "W1": {"multiplier": 1, "timespan": "week"},
        "MN1": {"multiplier": 1, "timespan": "month"}
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Polygon provider
        
        Args:
            api_key: Polygon.io API key (get free at polygon.io)
        """
        if requests is None:
            raise ImportError("requests library required. Install: pip install requests")
        
        self.api_key = api_key
        
        if not self.api_key:
            logger.warning("Polygon.io API key not provided. Provider will not work.")
        
        logger.info("PolygonProvider initialized")
    
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
        Fetch OHLC data from Polygon.io
        
        Args:
            symbol: Symbol to fetch (e.g., 'AAPL', 'C:EURUSD', 'X:BTCUSD')
            timeframe: Timeframe (M1, M5, H1, D1, etc.)
            count: Number of candles
        
        Returns:
            DataFrame with OHLC data or None
        """
        if not self.is_available():
            logger.error("Polygon.io not available (missing API key)")
            return None
        
        try:
            # Format symbol
            formatted_symbol = self._format_symbol(symbol)
            
            # Get timeframe parameters
            tf_params = self.TIMEFRAME_MAP.get(timeframe, {"multiplier": 5, "timespan": "minute"})
            
            # Calculate date range
            end_date = datetime.now()
            
            # Estimate start date based on timeframe and count
            timespan = tf_params["timespan"]
            multiplier = tf_params["multiplier"]
            
            if timespan == "minute":
                start_date = end_date - timedelta(minutes=count * multiplier * 2)  # *2 for safety
            elif timespan == "hour":
                start_date = end_date - timedelta(hours=count * multiplier * 2)
            elif timespan == "day":
                start_date = end_date - timedelta(days=count * multiplier * 2)
            elif timespan == "week":
                start_date = end_date - timedelta(weeks=count * multiplier * 2)
            elif timespan == "month":
                start_date = end_date - timedelta(days=count * multiplier * 60)
            else:
                start_date = end_date - timedelta(days=30)
            
            # Format dates
            from_date = start_date.strftime("%Y-%m-%d")
            to_date = end_date.strftime("%Y-%m-%d")
            
            # Build URL
            url = (
                f"{self.BASE_URL}/v2/aggs/ticker/{formatted_symbol}/range/"
                f"{multiplier}/{timespan}/{from_date}/{to_date}"
            )
            
            params = {
                "apiKey": self.api_key,
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000  # Max limit
            }
            
            logger.info(f"Fetching {count} candles of {formatted_symbol} from Polygon.io")
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for errors
            if data.get("status") != "OK":
                error_msg = data.get("error", data.get("message", "Unknown error"))
                logger.error(f"Polygon.io error: {error_msg}")
                return None
            
            if "results" not in data or not data["results"]:
                logger.warning(f"No data returned for {formatted_symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(data["results"])
            
            # Rename columns
            df = df.rename(columns={
                "t": "timestamp",
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
                "n": "transactions"
            })
            
            # Convert timestamp to datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            
            # Select and order columns
            df = df[["open", "high", "low", "close", "volume"]]
            df = df.astype(float)
            
            # Limit to requested count
            df = df.tail(count)
            
            logger.info(f"Fetched {len(df)} candles for {formatted_symbol} from Polygon.io")
            return df
        
        except Exception as e:
            logger.error(f"Error fetching data from Polygon.io: {e}")
            return None
    
    def _format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Polygon.io API
        
        Args:
            symbol: Symbol in various formats
        
        Returns:
            Symbol in Polygon.io format
        """
        symbol_upper = symbol.upper()
        
        # Already formatted (has prefix)
        if ":" in symbol_upper:
            return symbol_upper
        
        # Detect type and add prefix
        # Forex
        if len(symbol_upper) == 6 and symbol_upper.isalpha():
            return f"C:{symbol_upper}"
        
        # Crypto
        crypto_bases = ["BTC", "ETH", "XRP", "LTC", "ADA", "SOL", "DOT", "DOGE", "AVAX", "MATIC"]
        for base in crypto_bases:
            if symbol_upper.startswith(base):
                quote = symbol_upper[len(base):] or "USD"
                return f"X:{base}{quote}"
        
        # Stocks (no prefix needed for newer API)
        return symbol_upper
    
    def get_ticker_details(self, symbol: str) -> Optional[dict]:
        """
        Get details about a ticker
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            Dictionary with ticker details or None
        """
        if not self.is_available():
            return None
        
        try:
            formatted_symbol = self._format_symbol(symbol)
            url = f"{self.BASE_URL}/v3/reference/tickers/{formatted_symbol}"
            
            params = {"apiKey": self.api_key}
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "OK" and "results" in data:
                return data["results"]
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting ticker details: {e}")
            return None
