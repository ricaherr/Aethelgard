"""
Twelve Data Provider - Free tier with API key
800 requests/day en tier gratuito
Soporta stocks, forex, crypto, commodities
API Key gratuita en: https://twelvedata.com/pricing
"""
import logging
from typing import Optional
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class TwelveDataProvider:
    """
    Twelve Data API provider
    
    Features:
    - Free tier: 800 requests/day
    - Stocks, Forex, Crypto, Commodities
    - Real-time and historical data
    - No credit card required for free tier
    
    Get free API key at: https://twelvedata.com/pricing
    """
    
    BASE_URL = "https://api.twelvedata.com"
    
    # Timeframe mapping
    TIMEFRAME_MAP = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "1h",
        "H2": "2h",
        "H4": "4h",
        "D1": "1day",
        "W1": "1week",
        "MN1": "1month"
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Twelve Data provider
        
        Args:
            api_key: Twelve Data API key (get free at twelvedata.com)
        """
        if requests is None:
            raise ImportError("requests library required. Install: pip install requests")
        
        self.api_key = api_key
        
        if not self.api_key:
            logger.warning("Twelve Data API key not provided. Provider will not work.")
        
        logger.info("TwelveDataProvider initialized")
    
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
        Fetch OHLC data from Twelve Data
        
        Args:
            symbol: Symbol to fetch (e.g., 'AAPL', 'EUR/USD', 'BTC/USD')
            timeframe: Timeframe (M1, M5, H1, D1, etc.)
            count: Number of candles (max 5000)
        
        Returns:
            DataFrame with OHLC data or None
        """
        if not self.is_available():
            logger.error("Twelve Data not available (missing API key)")
            return None
        
        try:
            # Format symbol
            formatted_symbol = self._format_symbol(symbol)
            
            # Map timeframe
            interval = self.TIMEFRAME_MAP.get(timeframe, "5min")
            
            # Build request
            params = {
                "symbol": formatted_symbol,
                "interval": interval,
                "apikey": self.api_key,
                "outputsize": min(count, 5000),  # Max 5000
                "format": "JSON"
            }
            
            url = f"{self.BASE_URL}/time_series"
            
            logger.info(f"Fetching {count} candles of {formatted_symbol} {interval} from Twelve Data")
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for errors
            if "code" in data or "status" in data:
                error_msg = data.get("message", data.get("status", "Unknown error"))
                logger.error(f"Twelve Data error: {error_msg}")
                return None
            
            if "values" not in data:
                logger.error("No values in Twelve Data response")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(data["values"])
            
            # Convert datetime column
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            df = df.sort_index()
            
            # Rename and select columns
            df = df.rename(columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume"
            })
            
            # Ensure we have all required columns
            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    logger.error(f"Missing column: {col}")
                    return None
            
            # Add volume if missing (forex doesn't have volume)
            if "volume" not in df.columns:
                df["volume"] = 0
            
            # Convert to numeric
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            
            # Limit to requested count
            df = df.tail(count)
            
            logger.info(f"Fetched {len(df)} candles for {formatted_symbol} from Twelve Data")
            return df
        
        except Exception as e:
            logger.error(f"Error fetching data from Twelve Data: {e}")
            return None
    
    def _format_symbol(self, symbol: str) -> str:
        """
        Format symbol for Twelve Data API
        
        Args:
            symbol: Symbol in various formats
        
        Returns:
            Symbol in Twelve Data format
        """
        # Remove common suffixes
        symbol = symbol.replace("=X", "").replace(".US", "")
        
        # Forex: EUR/USD format
        if "/" in symbol:
            return symbol.upper()
        
        # Forex without slash: EURUSD -> EUR/USD
        if len(symbol) == 6 and symbol.isalpha():
            return f"{symbol[:3]}/{symbol[3:]}".upper()
        
        # Crypto: BTC/USD format
        crypto_bases = ["BTC", "ETH", "XRP", "LTC", "ADA", "SOL", "DOT", "DOGE", "AVAX", "MATIC"]
        for base in crypto_bases:
            if symbol.upper().startswith(base):
                quote = symbol[len(base):] or "USD"
                return f"{base}/{quote}".upper()
        
        # Default: return as-is (stocks)
        return symbol.upper()
    
    def get_supported_symbols(self, symbol_type: str = "stock") -> list:
        """
        Get list of supported symbols
        
        Args:
            symbol_type: Type of symbols (stock, forex, crypto, etf, index)
        
        Returns:
            List of supported symbols
        """
        if not self.is_available():
            return []
        
        try:
            url = f"{self.BASE_URL}/{symbol_type}"
            params = {"apikey": self.api_key}
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if "data" in data:
                return [item["symbol"] for item in data["data"]]
            
            return []
        
        except Exception as e:
            logger.error(f"Error getting supported symbols: {e}")
            return []
