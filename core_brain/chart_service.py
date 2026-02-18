"""
Servicio para obtener datos de gráficas (OHLC + indicadores) para Aethelgard.
"""
from core_brain.data_provider_manager import DataProviderManager
import pandas as pd
from typing import Dict, Any

class ChartService:
    def __init__(self, storage=None):
        # Allow optional storage injection, fallback to internal if None (for now) but recommend DI
        self.provider_manager = DataProviderManager(storage=storage)
        self.data_provider = self.provider_manager.get_best_provider()

    def get_chart_data(self, symbol: str, timeframe: str = "M5", count: int = 500) -> Dict[str, Any]:
        # 1. Obtener datos OHLC
        df = self.data_provider.fetch_ohlc(symbol, timeframe, count)
        if df is None or len(df) == 0:
            return {"symbol": symbol, "timeframe": timeframe, "data": [], "indicators": {}}

        # 2. Calcular indicadores
        df = df.copy()
        
        # Ensure 'time' is Unix timestamp (seconds) for lightweight-charts
        if pd.api.types.is_datetime64_any_dtype(df['time']):
            # Convert to int seconds
            df['time'] = df['time'].astype(int) // 10**9
        
        df["sma20"] = df["close"].rolling(window=20).mean()
        df["sma200"] = df["close"].rolling(window=200).mean()
        df["adx"] = self._calculate_adx(df)

        # 3. Formatear para frontend
        candles = df.tail(count).to_dict(orient="records")
        indicators = {
            "sma20": df["sma20"].dropna().tolist(),
            "sma200": df["sma200"].dropna().tolist(),
            "adx": df["adx"].dropna().tolist()
        }
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "indicators": indicators,
            # Metadatos para marcadores (Placeholders por ahora)
            "entryPrice": None,
            "stopLoss": None,
            "takeProfit": None,
            "isBuy": None
        }

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        # Implementación simple de ADX
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
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).sum() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).sum() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(window=period).mean()
        return adx
