"""
Clasificador de Régimen de Mercado Optimizado
Analiza volatilidad y tendencia para determinar el modo de operación
Usa pandas para cálculos vectorizados eficientes
"""
from typing import List, Optional, Dict
from datetime import datetime
from models.signal import MarketRegime
import pandas as pd
import numpy as np


class RegimeClassifier:
    """
    Clasifica el régimen de mercado basándose en:
    - Volatilidad (desviación estándar de retornos)
    - Tendencia (ADX correctamente calculado)
    - Movimientos extremos (detección de crash/shock: +300% volatilidad en 3 velas)
    - Sesgo a largo plazo (distancia a SMA 200)
    """
    
    def __init__(self, 
                 adx_period: int = 14,
                 sma_period: int = 200,
                 adx_trend_threshold: float = 25.0,
                 adx_range_threshold: float = 20.0,
                 volatility_shock_multiplier: float = 3.0,
                 shock_lookback: int = 3):
        """
        Args:
            adx_period: Período para cálculo de ADX (default: 14)
            sma_period: Período para SMA de largo plazo (default: 200)
            adx_trend_threshold: ADX > este valor indica TREND (default: 25.0)
            adx_range_threshold: ADX < este valor indica RANGE (default: 20.0)
            volatility_shock_multiplier: Multiplicador para detectar shock (default: 3.0 = 300%)
            shock_lookback: Número de velas para comparar volatilidad (default: 3)
        """
        self.adx_period = adx_period
        self.sma_period = sma_period
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold
        self.volatility_shock_multiplier = volatility_shock_multiplier
        self.shock_lookback = shock_lookback
        
        # DataFrame para almacenar datos OHLC
        self.df: Optional[pd.DataFrame] = None
        self.max_history = 300  # Mantener suficientes datos para SMA 200
    
    def add_candle(self, 
                   close: float,
                   high: Optional[float] = None,
                   low: Optional[float] = None,
                   open_price: Optional[float] = None,
                   timestamp: Optional[datetime] = None):
        """
        Añade una vela al historial para análisis
        
        Args:
            close: Precio de cierre (requerido)
            high: Precio máximo (opcional, se usa close si no se proporciona)
            low: Precio mínimo (opcional, se usa close si no se proporciona)
            open_price: Precio de apertura (opcional, se usa close si no se proporciona)
            timestamp: Timestamp de la vela (opcional)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Si no se proporcionan high/low/open, usar close como aproximación
        high = high if high is not None else close
        low = low if low is not None else close
        open_price = open_price if open_price is not None else close
        
        new_row = pd.DataFrame({
            'timestamp': [timestamp],
            'open': [open_price],
            'high': [high],
            'low': [low],
            'close': [close]
        })
        
        if self.df is None:
            self.df = new_row
        else:
            self.df = pd.concat([self.df, new_row], ignore_index=True)
        
        # Mantener solo el historial reciente
        if len(self.df) > self.max_history:
            self.df = self.df.tail(self.max_history).reset_index(drop=True)
    
    def add_price(self, price: float, timestamp: Optional[datetime] = None):
        """
        Método de compatibilidad: añade solo precio (se usa como close)
        Para mejor precisión, usar add_candle() con datos OHLC completos
        """
        self.add_candle(close=price, timestamp=timestamp)
    
    def _calculate_adx(self) -> float:
        """
        Calcula el ADX (Average Directional Index) correctamente usando pandas
        Implementa el método de suavizado de Wilder para ATR, +DI, -DI y ADX
        
        Returns:
            Valor de ADX entre 0-100, o 0.0 si no hay suficientes datos
        """
        if self.df is None or len(self.df) < self.adx_period * 2:
            return 0.0
        
        df = self.df.copy()
        period = self.adx_period
        
        # Calcular True Range (TR)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # Calcular Directional Movement
        df['plus_dm'] = df['high'].diff()
        df['minus_dm'] = -df['low'].diff()
        
        # Filtrar movimientos direccionales según reglas de ADX
        # +DM solo cuenta si es mayor que -DM y positivo
        # -DM solo cuenta si es mayor que +DM y positivo
        df.loc[(df['plus_dm'] <= df['minus_dm']) | (df['plus_dm'] < 0), 'plus_dm'] = 0
        df.loc[(df['minus_dm'] <= df['plus_dm']) | (df['minus_dm'] < 0), 'minus_dm'] = 0
        
        # Calcular ATR usando Wilder's Smoothing
        # Primera vez: suma simple de los primeros 'period' valores
        # Después: ATR = (ATR_previo * (period - 1) + TR_actual) / period
        atr = pd.Series(index=df.index, dtype=float)
        atr.iloc[period-1] = df['tr'].iloc[:period].sum() / period
        
        for i in range(period, len(df)):
            atr.iloc[i] = (atr.iloc[i-1] * (period - 1) + df['tr'].iloc[i]) / period
        
        # Calcular +DI y -DI usando Wilder's Smoothing
        plus_dm_smooth = pd.Series(index=df.index, dtype=float)
        minus_dm_smooth = pd.Series(index=df.index, dtype=float)
        
        plus_dm_smooth.iloc[period-1] = df['plus_dm'].iloc[:period].sum() / period
        minus_dm_smooth.iloc[period-1] = df['minus_dm'].iloc[:period].sum() / period
        
        for i in range(period, len(df)):
            plus_dm_smooth.iloc[i] = (plus_dm_smooth.iloc[i-1] * (period - 1) + df['plus_dm'].iloc[i]) / period
            minus_dm_smooth.iloc[i] = (minus_dm_smooth.iloc[i-1] * (period - 1) + df['minus_dm'].iloc[i]) / period
        
        # Calcular +DI y -DI como porcentaje del ATR
        plus_di = 100 * (plus_dm_smooth / atr)
        minus_di = 100 * (minus_dm_smooth / atr)
        
        # Calcular DX (Directional Index)
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        dx = 100 * (di_diff / di_sum.replace(0, np.nan))
        
        # Calcular ADX usando Wilder's Smoothing de DX
        adx = pd.Series(index=df.index, dtype=float)
        adx.iloc[period*2-2] = dx.iloc[period-1:period*2-1].mean()
        
        for i in range(period*2-1, len(df)):
            adx.iloc[i] = (adx.iloc[i-1] * (period - 1) + dx.iloc[i]) / period
        
        # Retornar el último valor de ADX
        return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    
    def _calculate_volatility(self, window: int = 20) -> float:
        """
        Calcula la volatilidad basada en desviación estándar de retornos usando pandas
        
        Args:
            window: Ventana de tiempo para el cálculo (default: 20)
        
        Returns:
            Volatilidad (desviación estándar de retornos)
        """
        if self.df is None or len(self.df) < window + 1:
            return 0.0
        
        df = self.df.copy()
        df['returns'] = df['close'].pct_change()
        
        # Calcular desviación estándar de retornos en la ventana
        volatility = df['returns'].tail(window).std()
        
        return float(volatility) if not pd.isna(volatility) else 0.0
    
    def _detect_volatility_shock(self) -> bool:
        """
        Detecta si la volatilidad ha aumentado un 300% (o el multiplicador configurado)
        en las últimas N velas (shock_lookback)
        
        Returns:
            True si se detecta un shock/crash
        """
        if self.df is None or len(self.df) < self.shock_lookback + 20:
            return False
        
        df = self.df.copy()
        df['returns'] = df['close'].pct_change()
        
        # Calcular volatilidad actual (últimas N velas)
        current_volatility = df['returns'].tail(self.shock_lookback).std()
        
        # Calcular volatilidad base (ventana anterior de mismo tamaño)
        base_volatility = df['returns'].iloc[-(self.shock_lookback * 2):-self.shock_lookback].std()
        
        # Evitar división por cero
        if base_volatility == 0 or pd.isna(base_volatility):
            return False
        
        # Verificar si la volatilidad aumentó más del multiplicador configurado
        volatility_increase = current_volatility / base_volatility
        
        return volatility_increase >= self.volatility_shock_multiplier
    
    def _calculate_sma_distance(self) -> Optional[float]:
        """
        Calcula la distancia porcentual del precio actual a la SMA 200
        
        Returns:
            Distancia porcentual (positiva = por encima, negativa = por debajo)
            None si no hay suficientes datos
        """
        if self.df is None or len(self.df) < self.sma_period:
            return None
        
        df = self.df.copy()
        df['sma'] = df['close'].rolling(window=self.sma_period).mean()
        
        current_price = df['close'].iloc[-1]
        sma_value = df['sma'].iloc[-1]
        
        if pd.isna(sma_value):
            return None
        
        # Calcular distancia porcentual
        distance = ((current_price - sma_value) / sma_value) * 100
        
        return float(distance)
    
    def get_bias(self) -> Optional[str]:
        """
        Determina el sesgo alcista o bajista basado en la distancia a SMA 200
        
        Returns:
            'BULLISH' si precio > SMA 200, 'BEARISH' si precio < SMA 200, None si no hay datos
        """
        distance = self._calculate_sma_distance()
        
        if distance is None:
            return None
        
        return 'BULLISH' if distance > 0 else 'BEARISH'
    
    def classify(self, 
                 current_price: Optional[float] = None,
                 high: Optional[float] = None,
                 low: Optional[float] = None,
                 open_price: Optional[float] = None) -> MarketRegime:
        """
        Clasifica el régimen de mercado actual
        
        Args:
            current_price: Precio actual (opcional, se añade al historial como close)
            high: Precio máximo (opcional)
            low: Precio mínimo (opcional)
            open_price: Precio de apertura (opcional)
        
        Returns:
            MarketRegime: Régimen detectado
        """
        if current_price is not None:
            self.add_candle(
                close=current_price,
                high=high,
                low=low,
                open_price=open_price
            )
        
        if self.df is None or len(self.df) < max(self.adx_period * 2, 20):
            return MarketRegime.NEUTRAL
        
        # 1. Detectar CRASH/SHOCK primero (prioridad alta)
        # Si la volatilidad aumenta un 300% en 3 velas -> CRASH/SHOCK
        if self._detect_volatility_shock():
            return MarketRegime.CRASH
        
        # 2. Calcular ADX
        adx = self._calculate_adx()
        
        # 3. Clasificar según umbrales de ADX
        if adx > self.adx_trend_threshold:
            # ADX > 25 -> TREND
            return MarketRegime.TREND
        elif adx < self.adx_range_threshold:
            # ADX < 20 -> RANGE
            return MarketRegime.RANGE
        else:
            # ADX entre 20 y 25 -> Zona de transición, considerar NEUTRAL
            return MarketRegime.NEUTRAL
    
    def get_metrics(self) -> Dict:
        """
        Retorna un diccionario con todas las métricas calculadas
        
        Returns:
            Diccionario con: adx, volatility, sma_distance, bias, regime
        """
        if self.df is None or len(self.df) < max(self.adx_period * 2, 20):
            return {
                'adx': 0.0,
                'volatility': 0.0,
                'sma_distance': None,
                'bias': None,
                'regime': MarketRegime.NEUTRAL.value
            }
        
        return {
            'adx': self._calculate_adx(),
            'volatility': self._calculate_volatility(),
            'sma_distance': self._calculate_sma_distance(),
            'bias': self.get_bias(),
            'regime': self.classify().value,
            'volatility_shock_detected': self._detect_volatility_shock()
        }
    
    def reset(self):
        """Resetea el historial del clasificador"""
        self.df = None
