"""
Generic Data Provider - Proveedor de datos agnóstico de plataforma
Utiliza Yahoo Finance (yfinance) para obtener datos OHLC sin requerir MT5
100% autónomo, sin instalaciones externas más allá de pip
"""
import logging
from typing import Optional
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)


class GenericDataProvider:
    """
    Proveedor de datos genérico usando Yahoo Finance.
    Totalmente autónomo, no requiere MT5 ni software externo.
    """
    
    # Mapeo de símbolos Aethelgard -> Yahoo Finance
    SYMBOL_MAPPING = {
        # Forex (Yahoo usa formato XXX=X)
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X",
        "NZDUSD": "NZDUSD=X",
        
        # Acciones (símbolo directo)
        "AAPL": "AAPL",
        "TSLA": "TSLA",
        "MSFT": "MSFT",
        "GOOGL": "GOOGL",
        "AMZN": "AMZN",
        "NVDA": "NVDA",
        "META": "META",
        
        # Índices
        "SPX": "^GSPC",    # S&P 500
        "NDX": "^IXIC",    # NASDAQ
        "DJI": "^DJI",     # Dow Jones
        "US30": "^DJI",    # Dow Jones (alias)
        
        # Commodities
        "GOLD": "GC=F",    # Gold Futures
        "SILVER": "SI=F",  # Silver Futures
        "OIL": "CL=F",     # Crude Oil
        "BRENT": "BZ=F",   # Brent Oil
        
        # Crypto
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
    }
    
    # Mapeo de timeframes Aethelgard -> Yahoo Finance
    TIMEFRAME_MAPPING = {
        "M1": "1m",
        "M2": "2m",
        "M5": "5m",
        "M15": "15m",
        "M30": "30m",
        "H1": "1h",
        "H4": "4h",
        "D1": "1d",
        "W1": "1wk",
        "MN1": "1mo",
    }
    
    def __init__(self):
        """Inicializa el proveedor de datos genérico"""
        if yf is None:
            raise ImportError(
                "yfinance no está instalado. "
                "Instala con: pip install yfinance"
            )
        
        logger.info("GenericDataProvider inicializado (Yahoo Finance)")
    
    def _map_symbol(self, symbol: str) -> str:
        """
        Mapea símbolo de Aethelgard a Yahoo Finance
        
        Args:
            symbol: Símbolo en formato Aethelgard
        
        Returns:
            Símbolo en formato Yahoo Finance
        """
        return self.SYMBOL_MAPPING.get(symbol, symbol)
    
    def _map_timeframe(self, timeframe: str) -> str:
        """
        Mapea timeframe de Aethelgard a Yahoo Finance
        
        Args:
            timeframe: Timeframe en formato Aethelgard (M5, H1, etc.)
        
        Returns:
            Timeframe en formato Yahoo Finance
        """
        return self.TIMEFRAME_MAPPING.get(timeframe, "5m")
    
    def _calculate_period(self, timeframe: str, count: int) -> str:
        """
        Calcula el período de descarga basado en timeframe y count
        
        Args:
            timeframe: Timeframe (M5, H1, etc.)
            count: Número de velas deseadas
        
        Returns:
            Período en formato Yahoo Finance (1d, 5d, 1mo, etc.)
        """
        # Mapeo de timeframe a días aproximados por vela
        tf_to_days = {
            "M1": 1/1440,  # 1 minuto
            "M2": 2/1440,
            "M5": 5/1440,
            "M15": 15/1440,
            "M30": 30/1440,
            "H1": 1/24,
            "H4": 4/24,
            "D1": 1,
            "W1": 7,
            "MN1": 30,
        }
        
        days_per_candle = tf_to_days.get(timeframe, 5/1440)
        total_days = int(days_per_candle * count) + 1
        
        # Mapear a períodos de Yahoo Finance
        if total_days <= 1:
            return "1d"
        elif total_days <= 5:
            return "5d"
        elif total_days <= 30:
            return "1mo"
        elif total_days <= 90:
            return "3mo"
        elif total_days <= 180:
            return "6mo"
        elif total_days <= 365:
            return "1y"
        elif total_days <= 730:
            return "2y"
        else:
            return "5y"
    
    def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 500,
    ) -> Optional[pd.DataFrame]:
        """
        Obtiene datos OHLC de Yahoo Finance
        
        Args:
            symbol: Símbolo del instrumento
            timeframe: Timeframe (M1, M5, M15, H1, H4, D1, W1, MN1)
            count: Número de velas a obtener
        
        Returns:
            DataFrame con columnas: time, open, high, low, close, volume
            None si hay error
        """
        try:
            # Mapear símbolo y timeframe
            yf_symbol = self._map_symbol(symbol)
            yf_interval = self._map_timeframe(timeframe)
            period = self._calculate_period(timeframe, count)
            
            logger.debug(
                f"Descargando {symbol} ({yf_symbol}) - "
                f"Timeframe: {timeframe} ({yf_interval}) - "
                f"Período: {period}"
            )
            
            # Descargar datos
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=yf_interval)
            
            if df is None or df.empty:
                logger.warning(f"No se obtuvieron datos para {symbol}")
                return None
            
            # Renombrar columnas al formato Aethelgard
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            # Mapear nombres de columnas
            column_mapping = {
                'datetime': 'time',
                'date': 'time',
            }
            df = df.rename(columns=column_mapping)
            
            # Asegurar que tenemos las columnas requeridas
            required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
            
            # Agregar tick_volume (mismo que volume para Yahoo Finance)
            if 'volume' in df.columns:
                df['tick_volume'] = df['volume']
            
            # Verificar columnas
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logger.error(f"Columnas faltantes: {missing_cols}")
                return None
            
            # Seleccionar solo las columnas necesarias
            df = df[required_cols + ['tick_volume']]
            
            # Limitar a count velas (las más recientes)
            if len(df) > count:
                df = df.tail(count)
            
            logger.info(
                f"✓ {symbol}: {len(df)} velas obtenidas "
                f"(timeframe: {timeframe}, período: {period})"
            )
            
            return df
        
        except Exception as e:
            logger.error(f"Error obteniendo datos para {symbol}: {e}")
            return None
    
    def get_available_symbols(self) -> list[str]:
        """
        Retorna lista de símbolos disponibles
        
        Returns:
            Lista de símbolos en formato Aethelgard
        """
        return list(self.SYMBOL_MAPPING.keys())
    
    def is_symbol_supported(self, symbol: str) -> bool:
        """
        Verifica si un símbolo está soportado
        
        Args:
            symbol: Símbolo a verificar
        
        Returns:
            True si está soportado
        """
        return symbol in self.SYMBOL_MAPPING or symbol in self.get_available_symbols()


# Singleton para uso global
_provider_instance = None


def get_provider() -> GenericDataProvider:
    """
    Obtiene instancia singleton del provider
    
    Returns:
        GenericDataProvider instance
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = GenericDataProvider()
    return _provider_instance
