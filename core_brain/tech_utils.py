"""
Technical Utils - Analizador Técnico Unificado
==============================================

Centraliza el cálculo de indicadores técnicos para evitar redundancia y asegurar 
consistencia en todo el sistema Aethelgard.

Principios:
- Precisión: Implementa Wilder's Smoothing según estandares de industria.
- Eficiencia: Cálculos vectorizados con pandas.
- Reutilización: Una sola fuente de verdad para indicadores.
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalyzer:
    """
    Provee métodos estáticos para cálculos técnicos optimizados.
    """

    @staticmethod
    def calculate_sma(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
        """Calcula la Media Móvil Simple (SMA)."""
        return df[column].rolling(window=period).mean()

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calcula el Average True Range (ATR)."""
        if len(df) < 2:
            return pd.Series(0.0, index=df.index)
            
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - prev_close),
            abs(df['low'] - prev_close)
        ], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calcula el ADX usando el suavizado de Wilder.
        """
        if len(df) < period * 2:
            return pd.Series(0.0, index=df.index)

        df_calc = df.copy()
        
        # True Range
        prev_close = df_calc['close'].shift(1)
        tr = pd.concat([
            df_calc['high'] - df_calc['low'],
            abs(df_calc['high'] - prev_close),
            abs(df_calc['low'] - prev_close)
        ], axis=1).max(axis=1)

        # Directional Movement
        plus_dm = df_calc['high'].diff()
        minus_dm = -df_calc['low'].diff()
        
        plus_dm.loc[(plus_dm <= minus_dm) | (plus_dm < 0)] = 0
        minus_dm.loc[(minus_dm <= plus_dm) | (minus_dm < 0)] = 0
        
        # Wilder's Smoothing
        def wilders_smooth(series: pd.Series, p: int) -> pd.Series:
            smoothed = pd.Series(index=series.index, dtype=float)
            if len(series) < p:
                return smoothed
            smoothed.iloc[p-1] = series.iloc[:p].sum() / p
            for i in range(p, len(series)):
                smoothed.iloc[i] = (smoothed.iloc[i-1] * (p - 1) + series.iloc[i]) / p
            return smoothed

        atr = wilders_smooth(tr, period)
        plus_dm_s = wilders_smooth(plus_dm, period)
        minus_dm_s = wilders_smooth(minus_dm, period)
        
        plus_di = 100 * (plus_dm_s / atr)
        minus_di = 100 * (minus_dm_s / atr)
        
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        dx = 100 * (di_diff / di_sum.replace(0, np.nan))
        
        adx = wilders_smooth(dx.fillna(0), period)
        return adx

    @staticmethod
    def enrich_dataframe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
        """
        Enriquece el DataFrame con indicadores comunes usados en Aethelgard.
        """
        if df is None or df.empty:
            return df
            
        # ATR para volatilidad
        df['atr'] = TechnicalAnalyzer.calculate_atr(df, config.get('atr_period', 14))
        
        # SMAs
        for p in config.get('sma_periods', [20, 50, 200]):
            df[f'sma_{p}'] = TechnicalAnalyzer.calculate_sma(df, p)
            
        # ADX
        df['adx'] = TechnicalAnalyzer.calculate_adx(df, config.get('adx_period', 14))
        
        return df
