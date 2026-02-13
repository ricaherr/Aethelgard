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
    def calculate_volatility(df: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        Calcula la volatilidad basada en la desviación estándar de retornos logarítmicos.
        """
        if len(df) < window + 1:
            return pd.Series(0.0, index=df.index)
            
        returns = np.log(df['close'] / df['close'].shift(1))
        return returns.rolling(window=window).std()

    @staticmethod
    def calculate_sma_slope(df: pd.DataFrame, period: int, lookback: int = 5, column: str = 'close') -> pd.Series:
        """
        Calcula la pendiente (slope) de una SMA como porcentaje de cambio.
        
        Args:
            df: DataFrame con datos OHLC
            period: Período de la SMA (ej. 20, 200)
            lookback: Velas hacia atrás para calcular pendiente (default: 5)
            column: Columna a usar para el cálculo (default: 'close')
        
        Returns:
            Serie con pendiente en porcentaje (valores positivos = alcista, negativos = bajista)
            
        Ejemplo:
            slope = 0.15  → SMA subiendo 0.15% en últimas 5 velas (tendencia alcista moderada)
            slope = -0.08 → SMA bajando 0.08% en últimas 5 velas (tendencia bajista débil)
        """
        if len(df) < period + lookback:
            return pd.Series(0.0, index=df.index)
        
        sma = df[column].rolling(window=period).mean()
        sma_prev = sma.shift(lookback)
        
        # Calcular cambio porcentual
        slope = ((sma - sma_prev) / sma_prev.replace(0, np.nan)) * 100
        return slope.fillna(0.0)

    @staticmethod
    def calculate_trend_strength(df: pd.DataFrame, 
                                  fast_period: int = 20, 
                                  slow_period: int = 200,
                                  lookback: int = 5) -> dict:
        """
        Calcula la fuerza de la tendencia combinando múltiples factores.
        
        Args:
            df: DataFrame con datos OHLC
            fast_period: Período SMA rápida (default: 20)
            slow_period: Período SMA lenta (default: 200)
            lookback: Velas para calcular pendiente (default: 5)
        
        Returns:
            Dict con:
                - slope_fast: Pendiente SMA rápida (%)
                - slope_slow: Pendiente SMA lenta (%)
                - separation_pct: Separación entre SMAs (%)
                - price_position: Posición del precio respecto a SMAs ('above_both', 'below_both', 'between')
                - strength_score: Score 0-100 (100 = tendencia muy fuerte)
        """
        if len(df) < slow_period + lookback:
            return {
                "slope_fast": 0.0,
                "slope_slow": 0.0,
                "separation_pct": 0.0,
                "price_position": "unknown",
                "strength_score": 0.0
            }
        
        # Calcular SMAs
        sma_fast = df['close'].rolling(window=fast_period).mean().iloc[-1]
        sma_slow = df['close'].rolling(window=slow_period).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        
        # Calcular pendientes
        slope_fast = TechnicalAnalyzer.calculate_sma_slope(df, fast_period, lookback).iloc[-1]
        slope_slow = TechnicalAnalyzer.calculate_sma_slope(df, slow_period, lookback).iloc[-1]
        
        # Separación entre SMAs
        separation_pct = abs(sma_fast - sma_slow) / sma_slow * 100 if sma_slow > 0 else 0.0
        
        # Posición del precio
        if current_price > sma_fast and sma_fast > sma_slow:
            price_position = "above_both"
        elif current_price < sma_fast and sma_fast < sma_slow:
            price_position = "below_both"
        else:
            price_position = "between"
        
        # Calcular strength score (0-100)
        # Componentes:
        # - Pendiente slow (40 puntos): |slope_slow| > 0.15% = 40, lineal hasta 0
        # - Separación (40 puntos): separation > 3% = 40, lineal hasta 0
        # - Alineación (20 puntos): above_both o below_both = 20, between = 0
        
        slope_score = min(40, abs(slope_slow) / 0.15 * 40) if abs(slope_slow) < 0.15 else 40
        separation_score = min(40, separation_pct / 3.0 * 40) if separation_pct < 3.0 else 40
        alignment_score = 20 if price_position in ["above_both", "below_both"] else 0
        
        strength_score = slope_score + separation_score + alignment_score
        
        return {
            "slope_fast": float(slope_fast),
            "slope_slow": float(slope_slow),
            "separation_pct": float(separation_pct),
            "price_position": price_position,
            "strength_score": float(strength_score)
        }

    @staticmethod
    def classify_trend(df: pd.DataFrame, 
                      fast_period: int = 20, 
                      slow_period: int = 200,
                      lookback: int = 5) -> str:
        """
        Clasifica la tendencia en 5 niveles basándose en jerarquía de precios, 
        pendiente de SMA200 y separación entre SMAs.
        
        Args:
            df: DataFrame con datos OHLC
            fast_period: Período SMA rápida (default: 20)
            slow_period: Período SMA lenta (default: 200)
            lookback: Velas para calcular pendiente (default: 5)
        
        Returns:
            String con clasificación:
                - "DOWNTREND_STRONG": Bajista fuerte (slope200 < -0.1%, sep > 2%)
                - "DOWNTREND_WEAK": Bajista débil (slope200 < -0.05%, sep > 1%)
                - "SIDEWAYS": Lateral/sin tendencia (slope200 entre -0.05% y 0.05%)
                - "UPTREND_WEAK": Alcista débil (slope200 > 0.05%, sep > 1%)
                - "UPTREND_STRONG": Alcista fuerte (slope200 > 0.1%, sep > 2%)
        """
        if len(df) < slow_period + lookback:
            return "SIDEWAYS"
        
        # Obtener datos de fuerza de tendencia
        strength = TechnicalAnalyzer.calculate_trend_strength(df, fast_period, slow_period, lookback)
        
        slope_slow = strength["slope_slow"]
        separation_pct = strength["separation_pct"]
        price_position = strength["price_position"]
        
        # Clasificación jerárquica
        # 1. Validar jerarquía de precios (requisito básico)
        if price_position == "above_both":
            # Tendencia alcista (precio > SMA20 > SMA200)
            if slope_slow > 0.1 and separation_pct > 2.0:
                return "UPTREND_STRONG"
            elif slope_slow > 0.05 and separation_pct > 1.0:
                return "UPTREND_WEAK"
            else:
                return "SIDEWAYS"  # Jerarquía alcista pero sin momentum
                
        elif price_position == "below_both":
            # Tendencia bajista (precio < SMA20 < SMA200)
            if slope_slow < -0.1 and separation_pct > 2.0:
                return "DOWNTREND_STRONG"
            elif slope_slow < -0.05 and separation_pct > 1.0:
                return "DOWNTREND_WEAK"
            else:
                return "SIDEWAYS"  # Jerarquía bajista pero sin momentum
        
        else:
            # Precio entre SMAs = sin tendencia definida
            return "SIDEWAYS"

    @staticmethod
    def enrich_dataframe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
        """
        Enriquece el DataFrame con indicadores comunes usados en Aethelgard.
        """
        if df is None or df.empty:
            return df
            
        # ATR para volatilidad
        df['atr'] = TechnicalAnalyzer.calculate_atr(df, config.get('atr_period', 14))
        
        # Volatilidad estadística
        df['volatility'] = TechnicalAnalyzer.calculate_volatility(df, config.get('volatility_window', 20))
        
        # SMAs
        for p in config.get('sma_periods', [20, 50, 200]):
            df[f'sma_{p}'] = TechnicalAnalyzer.calculate_sma(df, p)
            
        # ADX
        df['adx'] = TechnicalAnalyzer.calculate_adx(df, config.get('adx_period', 14))
        
        return df
