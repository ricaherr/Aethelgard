"""
Servicio para obtener datos de gráficas (OHLC + indicadores) para Aethelgard.
Implementa resiliencia mediante graceful degradation - nunca lanza excepciones, retorna datos parciales.
"""
import logging
from core_brain.data_provider_manager import DataProviderManager
import pandas as pd
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChartService:
    def __init__(self, storage=None, user_id: str = "default"):
        """
        Inicializa ChartService.
        
        Args:
            storage: StorageManager inyectado (DI pattern)
            user_id: ID del usuario (para isolación multi-usuario)
        """
        self.user_id = user_id
        try:
            self.provider_manager = DataProviderManager(storage=storage)
            self.data_provider = self.provider_manager.get_best_provider()
        except Exception as e:
            logger.warning(f"[ChartService] Failed to initialize provider: {e}")
            self.data_provider = None

    def get_chart_data(self, symbol: str, timeframe: str = "M5", count: int = 500) -> Dict[str, Any]:
        """
        Retorna datos de OHLC + indicadores para un símbolo y timeframe.
        Implementa graceful degradation: nunca lanza excepciones (500).
        
        Returns:
            Dict con estructura: {symbol, timeframe, candles, indicators, metadata}
        """
        try:
            # Validar inputs
            if not symbol or not isinstance(symbol, str):
                return self._empty_response(symbol or "UNKNOWN", timeframe)
            
            if not self.data_provider:
                logger.warning(f"[ChartService] No data provider available for {symbol}")
                return self._empty_response(symbol, timeframe, reason="No data provider")
            
            # Obtener datos OHLC
            try:
                df = self.data_provider.fetch_ohlc(symbol, timeframe, count)
            except Exception as e:
                logger.warning(f"[ChartService] Failed to fetch OHLC for {symbol}/{timeframe}: {e}")
                return self._empty_response(symbol, timeframe, reason="Data fetch failed")
            
            if df is None or len(df) == 0:
                logger.debug(f"[ChartService] No data available for {symbol}/{timeframe}")
                return self._empty_response(symbol, timeframe, reason="No data")
            
            # Calcular indicadores (con try-catch per indicador)
            try:
                df = df.copy()
                
                # Normalizar 'time' a Unix timestamp (segundos)
                if 'time' in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df['time']):
                        df['time'] = df['time'].astype(int) // 10**9
                else:
                    df['time'] = range(len(df))
                
                # SMA20 y SMA200
                df["sma20"] = df["close"].rolling(window=20, min_periods=1).mean()
                df["sma200"] = df["close"].rolling(window=200, min_periods=1).mean()
                
                # ADX (con try-catch interno)
                try:
                    df["adx"] = self._calculate_adx(df)
                except Exception as e:
                    logger.debug(f"[ChartService] ADX calculation failed: {e}")
                    df["adx"] = None
                
            except Exception as e:
                logger.warning(f"[ChartService] Indicator calculation failed: {e}")
                # Continue with raw data if indicators fail
            
            # Formatear para frontend
            candles = df.tail(count).to_dict(orient="records")
            indicators = {
                "sma20": df["sma20"].dropna().tolist() if "sma20" in df else [],
                "sma200": df["sma200"].dropna().tolist() if "sma200" in df else [],
                "adx": df["adx"].dropna().tolist() if "adx" in df and df["adx"] is not None else []
            }
            
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": candles,
                "indicators": indicators,
                "entryPrice": None,
                "stopLoss": None,
                "takeProfit": None,
                "isBuy": None,
                "metadata": {
                    "candle_count": len(candles),
                    "freshness": "real-time",
                    "source": "data_provider"
                }
            }
        
        except Exception as e:
            logger.error(f"[ChartService] Unexpected error in get_chart_data: {e}", exc_info=True)
            return self._empty_response(symbol, timeframe, reason="Internal error")

    def _empty_response(self, symbol: str, timeframe: str, reason: str = "No data") -> Dict[str, Any]:
        """Retorna respuesta vacía pero válida cuando no hay datos."""
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": [],
            "indicators": {"sma20": [], "sma200": [], "adx": []},
            "entryPrice": None,
            "stopLoss": None,
            "takeProfit": None,
            "isBuy": None,
            "metadata": {
                "candle_count": 0,
                "freshness": "stale",
                "source": "empty",
                "reason": reason
            }
        }

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
        """
        Calcula ADX (Average Directional Index) de forma resiliente.
        
        Returns:
            pd.Series con ADX o None si falla
        """
        try:
            if len(df) < period:
                return None
            
            high = df["high"]
            low = df["low"]
            close = df["close"]
            
            plus_dm = high.diff()
            minus_dm = low.diff()
            
            plus_dm[plus_dm < 0] = 0
            minus_dm = -minus_dm
            minus_dm[minus_dm < 0] = 0
            
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)
            
            atr = tr.rolling(window=period, min_periods=1).mean()
            atr = atr.replace(0, 1)  # Evitar división por cero
            
            plus_di = 100 * (plus_dm.rolling(window=period, min_periods=1).sum() / atr)
            minus_di = 100 * (minus_dm.rolling(window=period, min_periods=1).sum() / atr)
            
            di_sum = plus_di + minus_di
            di_sum = di_sum.replace(0, 1)  # Evitar división por cero
            
            dx = (abs(plus_di - minus_di) / di_sum) * 100
            adx = dx.rolling(window=period, min_periods=1).mean()
            
            return adx
        except Exception as e:
            logger.debug(f"[ChartService] ADX calculation error: {e}")
            return None
