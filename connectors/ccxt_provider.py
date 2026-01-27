"""
CCXT Data Provider - Free crypto data from 100+ exchanges
No API key needed for public data
Ideal para trading de criptomonedas
"""
import logging
from typing import Optional
import pandas as pd

try:
    import ccxt
except ImportError:
    ccxt = None

logger = logging.getLogger(__name__)


class CCXTProvider:
    """
    CCXT (CryptoCurrency eXchange Trading) data provider
    
    Features:
    - 100% gratuito para datos públicos
    - 100+ exchanges soportados
    - No requiere API key para datos de mercado
    - Ideal para crypto trading
    
    Install: pip install ccxt
    """
    
    # Timeframe mapping
    TIMEFRAME_MAP = {
        "M1": "1m",
        "M5": "5m",
        "M15": "15m",
        "M30": "30m",
        "H1": "1h",
        "H4": "4h",
        "D1": "1d",
        "W1": "1w"
    }
    
    def __init__(self, exchange_id: str = "binance"):
        """
        Initialize CCXT provider
        
        Args:
            exchange_id: Exchange to use (binance, coinbase, kraken, etc.)
        """
        if ccxt is None:
            raise ImportError("ccxt library required. Install: pip install ccxt")
        
        self.exchange_id = exchange_id
        
        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class({
                'enableRateLimit': True,  # Respetar rate limits
            })
            
            logger.info(f"CCXTProvider initialized with {exchange_id}")
        except Exception as e:
            logger.error(f"Error initializing CCXT exchange {exchange_id}: {e}")
            self.exchange = None
    
    def is_available(self) -> bool:
        """Check if provider is available"""
        return bool(ccxt and self.exchange)
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data from crypto exchange
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
            timeframe: Timeframe (M1, M5, H1, D1, etc.)
            count: Number of candles
        
        Returns:
            DataFrame with OHLC data or None
        """
        if not self.is_available():
            logger.error("CCXT not available")
            return None
        
        try:
            # Convert symbol format
            # BTCUSD -> BTC/USDT
            # BTC-USD -> BTC/USD
            formatted_symbol = self._format_symbol(symbol)
            
            # Map timeframe
            interval = self.TIMEFRAME_MAP.get(timeframe, "5m")
            
            # Check if exchange supports this timeframe
            if not self.exchange.has['fetchOHLCV']:
                logger.error(f"Exchange {self.exchange_id} doesn't support OHLCV")
                return None
            
            # Fetch OHLCV data
            logger.info(f"Fetching {count} candles of {formatted_symbol} {interval} from {self.exchange_id}")
            
            ohlcv = self.exchange.fetch_ohlcv(
                formatted_symbol,
                timeframe=interval,
                limit=count
            )
            
            if not ohlcv:
                logger.warning(f"No data returned for {formatted_symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Ensure numeric types
            df = df.astype(float)
            
            logger.info(f"Fetched {len(df)} candles for {formatted_symbol} from {self.exchange_id}")
            return df
        
        except ccxt.NetworkError as e:
            logger.error(f"Network error fetching from {self.exchange_id}: {e}")
            return None
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error from {self.exchange_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching data from CCXT: {e}")
            return None
    
    def _format_symbol(self, symbol: str) -> str:
        """
        Format symbol for CCXT (e.g., BTCUSD -> BTC/USDT)
        
        Args:
            symbol: Symbol in various formats
        
        Returns:
            Symbol in CCXT format (BASE/QUOTE)
        """
        # Already in correct format
        if "/" in symbol:
            return symbol.upper()
        
        # Handle BTC-USD format
        if "-" in symbol:
            return symbol.replace("-", "/").upper()
        
        # Common crypto symbols
        symbol_map = {
            "BTCUSD": "BTC/USDT",
            "ETHUSD": "ETH/USDT",
            "BNBUSD": "BNB/USDT",
            "ADAUSD": "ADA/USDT",
            "XRPUSD": "XRP/USDT",
            "SOLUSD": "SOL/USDT",
            "DOTUSD": "DOT/USDT",
            "DOGEUSD": "DOGE/USDT",
            "AVAXUSD": "AVAX/USDT",
            "MATICUSD": "MATIC/USDT"
        }
        
        if symbol.upper() in symbol_map:
            return symbol_map[symbol.upper()]
        
        # Try to parse as BASEUSD
        if symbol.upper().endswith("USD"):
            base = symbol[:-3]
            return f"{base}/USDT"
        
        # Default: assume it's BTC/USDT format
        logger.warning(f"Could not parse symbol {symbol}, using as-is")
        return symbol.upper()
    
    def get_supported_exchanges(self) -> list:
        """Get list of supported exchanges"""
        if not ccxt:
            return []
        
        return ccxt.exchanges
    
    def get_exchange_info(self) -> dict:
        """Get information about current exchange"""
        if not self.is_available():
            return {}
        
        return {
            "id": self.exchange.id,
            "name": self.exchange.name,
            "countries": getattr(self.exchange, 'countries', []),
            "has_fetchOHLCV": self.exchange.has.get('fetchOHLCV', False),
            "timeframes": list(self.exchange.timeframes.keys()) if hasattr(self.exchange, 'timeframes') else []
        }
