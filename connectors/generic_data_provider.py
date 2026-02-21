"""
Generic Data Provider - Proveedor de datos agnóstico de plataforma
Utiliza Yahoo Finance (yfinance) para obtener datos OHLC sin requerir MT5
100% autónomo, sin instalaciones externas más allá de pip
"""
import logging
import threading
from typing import Optional
import pandas as pd
import time

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

# Silenciar logs ruidosos de yfinance que corrompen la consola
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

YFINANCE_LOCK = threading.Lock()


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
        "GOLD": "XAUUSD=X",  # Gold Spot
        "XAUUSD": "XAUUSD=X",
        "SILVER": "XAGUSD=X", # Silver Spot
        "XAGUSD": "XAGUSD=X",
        "OIL": "CL=F",     # Crude Oil
        "BRENT": "BZ=F",   # Brent Oil
        
        # Crypto
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "SOLUSD": "SOL-USD",
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
    
    def __init__(self, **kwargs) -> None:
        """Inicializa el proveedor de datos genérico"""
        if yf is None:
            raise ImportError(
                "yfinance no está instalado. "
                "Instala con: pip install yfinance"
            )
        
        # Store storage if passed (optional, for future use)
        self.storage = kwargs.get('storage')
        self.last_request_time = 0  # Initialize rate limiter
        self.min_interval = 2.0     # Default rate limit (2 seconds)
        
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
    
    def _enforce_rate_limit(self) -> None:
        """Asegura que no se exceda el límite de peticiones (2s entre llamadas)"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            # Solo loguear si el sleep es significativo (>0.5s)
            if sleep_time > 0.5:
                # logger.debug(f"[RATE-LIMIT] Sleeping {sleep_time:.2f}s before next Yahoo request")
                pass
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def fetch_ohlc(self, symbol: str, timeframe: str = "M5", count: int = 500) -> Optional[Any]:
        """
        Obtiene OHLCV de Yahoo Finance con Rate Limiting.
        
        Args:
            symbol: Símbolo (ej. "EURUSD")
            timeframe: Timeframe (ej. "M5")
            count: Número de velas
            
        Returns:
            DataFrame con [time, open, high, low, close, volume] o None
        """
        # Apply Rate Limit before Request
        self._enforce_rate_limit()
        
        try:
            # Mapear símbolo (EURUSD -> EURUSD=X)
            if symbol in self.SYMBOL_MAPPING:
                yf_symbol = self.SYMBOL_MAPPING[symbol]
            else:
                yf_symbol = self._map_symbol(symbol)
            
            yf_interval = self._map_timeframe(timeframe)
            period = self._calculate_period(timeframe, count)
            
            logger.debug(
                f"Descargando {symbol} ({yf_symbol}) - "
                f"Timeframe: {timeframe} ({yf_interval}) - "
                f"Período: {period}"
            )
            
            # Descargar datos (history con fallback a download)
            df = None
            try:
                with YFINANCE_LOCK:
                    ticker = yf.Ticker(yf_symbol)
                    df = ticker.history(
                        period=period,
                        interval=yf_interval,
                        auto_adjust=False,
                        actions=False,
                    )
                # Remover columnas duplicadas (puede ocurrir con yfinance)
                df = df.loc[:,~df.columns.duplicated()]
                # Normalizar índice de tiempo (evitar tz-naive/tz-aware conflict)
                try:
                    if hasattr(df.index, 'tz') and df.index.tz is not None:
                        df.index = df.index.tz_convert(None)
                except Exception:
                    df.index = pd.to_datetime(df.index, errors='coerce')
                df = df.reset_index()
                # Si hay error de dictionary changed size, forzar copia segura
                try:
                    df = df.copy()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(
                    f"history() falló para {symbol} ({yf_symbol}): {e}. "
                    "Intentando yf.download()"
                )

            if df is None or df.empty:
                try:
                    with YFINANCE_LOCK:
                        df = yf.download(
                            yf_symbol,
                            period=period,
                            interval=yf_interval,
                            progress=False,
                            auto_adjust=False,
                            group_by='column',
                            threads=False,
                        )
                except Exception as e:
                    logger.error(
                        f"Error descargando datos para {symbol} ({yf_symbol}): {e}",
                        exc_info=True,
                    )
                    return None

            if df is None or df.empty:
                logger.warning(f"No se obtuvieron datos para {symbol}")
                return None
            
            # Robustez: yfinance puede devolver MultiIndex si hay problemas o cambios de versión
            if isinstance(df.columns, pd.MultiIndex):
                logger.debug(f"Aplanando MultiIndex para {symbol}")
                df.columns = df.columns.get_level_values(0)
            
            # Renombrar columnas al formato Aethelgard
            df = df.reset_index()
            # Asegurar que columns.str existe y funciona
            df.columns = [str(col).lower() for col in df.columns]
            # Remover columnas duplicadas (puede ocurrir con yfinance)
            if df.columns.duplicated().any():
                df = df.loc[:, ~df.columns.duplicated()]
            
            # Mapear nombres de columnas
            column_mapping = {
                'datetime': 'time',
                'date': 'time',
            }
            df = df.rename(columns=column_mapping)
            
            # Asegurar que tenemos las columnas requeridas
            required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
            
            # Verificar si existe volume antes de subscriptar
            if 'volume' in df.columns:
                volume_cols = [col for col in df.columns if str(col).lower().startswith('volume')]
                if volume_cols:
                    volume_data = df[volume_cols]
                else:
                    volume_data = df['volume']

                if isinstance(volume_data, pd.DataFrame):
                    volume_data = volume_data.iloc[:, 0]

                df['tick_volume'] = volume_data
            else:
                df['tick_volume'] = 0
            
            # Verificar columnas faltantes
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logger.error(f"Columnas faltantes para {symbol}: {missing_cols}")
                return None
            
            # Seleccionar solo las columnas necesarias (uso de .get para evitar NoneType subscripting if df was somehow lost)
            df = df[required_cols + ['tick_volume']]
            
            # Limitar a count velas (las más recientes)
            if len(df) > count:
                df = df.tail(count)
            
            logger.info(
                f"[OK] {symbol}: {len(df)} velas obtenidas "
                f"(timeframe: {timeframe}, período: {period})"
            )
            
            return df
        
        except Exception as e:
            logger.error(f"Error obteniendo datos para {symbol}: {str(e)}", exc_info=True)
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
