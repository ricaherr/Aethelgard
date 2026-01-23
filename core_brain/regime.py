"""
Clasificador de Régimen de Mercado
Analiza volatilidad y tendencia para determinar el modo de operación
"""
from typing import List, Optional
from datetime import datetime, timedelta
from models.signal import MarketRegime
import numpy as np


class RegimeClassifier:
    """
    Clasifica el régimen de mercado basándose en:
    - Volatilidad (ATR, desviación estándar)
    - Tendencia (ADX, media móvil)
    - Movimientos extremos (detección de crash)
    """
    
    def __init__(self, 
                 volatility_threshold: float = 0.02,
                 trend_strength_threshold: float = 25.0,
                 crash_threshold: float = 0.05):
        """
        Args:
            volatility_threshold: Umbral de volatilidad (2% por defecto)
            trend_strength_threshold: Umbral de fuerza de tendencia (ADX)
            crash_threshold: Umbral para detectar movimientos extremos (5%)
        """
        self.volatility_threshold = volatility_threshold
        self.trend_strength_threshold = trend_strength_threshold
        self.crash_threshold = crash_threshold
        self.price_history: List[float] = []
        self.timestamps: List[datetime] = []
        self.max_history = 100  # Mantener últimas 100 muestras
    
    def add_price(self, price: float, timestamp: Optional[datetime] = None):
        """Añade un precio al historial para análisis"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.price_history.append(price)
        self.timestamps.append(timestamp)
        
        # Mantener solo el historial reciente
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)
            self.timestamps.pop(0)
    
    def calculate_volatility(self) -> float:
        """Calcula la volatilidad basada en desviación estándar de retornos"""
        if len(self.price_history) < 10:
            return 0.0
        
        prices = np.array(self.price_history)
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns)
        
        return float(volatility)
    
    def calculate_trend_strength(self) -> float:
        """
        Calcula la fuerza de la tendencia usando una aproximación de ADX
        Retorna un valor entre 0-100
        """
        if len(self.price_history) < 20:
            return 0.0
        
        prices = np.array(self.price_history)
        
        # Calcular dirección de movimiento
        highs = prices
        lows = prices
        closes = prices
        
        # Aproximación simple de ADX
        # +DI y -DI simplificados
        up_moves = np.diff(highs)
        down_moves = -np.diff(lows)
        
        plus_di = np.mean(up_moves[up_moves > 0]) if np.any(up_moves > 0) else 0
        minus_di = np.mean(down_moves[down_moves > 0]) if np.any(down_moves > 0) else 0
        
        # Calcular fuerza de tendencia
        if plus_di + minus_di == 0:
            return 0.0
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        return float(dx)
    
    def detect_crash(self) -> bool:
        """Detecta movimientos extremos que indican un crash"""
        if len(self.price_history) < 5:
            return False
        
        prices = np.array(self.price_history)
        
        # Calcular cambio porcentual reciente
        recent_change = abs((prices[-1] - prices[-5]) / prices[-5])
        
        return recent_change >= self.crash_threshold
    
    def classify(self, current_price: Optional[float] = None) -> MarketRegime:
        """
        Clasifica el régimen de mercado actual
        
        Args:
            current_price: Precio actual (opcional, se añade al historial)
        
        Returns:
            MarketRegime: Régimen detectado
        """
        if current_price is not None:
            self.add_price(current_price)
        
        if len(self.price_history) < 10:
            return MarketRegime.NEUTRAL
        
        # Detectar crash primero (prioridad alta)
        if self.detect_crash():
            return MarketRegime.CRASH
        
        # Calcular métricas
        volatility = self.calculate_volatility()
        trend_strength = self.calculate_trend_strength()
        
        # Clasificar según métricas
        if volatility < self.volatility_threshold:
            # Baja volatilidad
            if trend_strength > self.trend_strength_threshold:
                return MarketRegime.TREND
            else:
                return MarketRegime.RANGE
        else:
            # Alta volatilidad
            if trend_strength > self.trend_strength_threshold:
                return MarketRegime.TREND
            else:
                return MarketRegime.NEUTRAL
    
    def reset(self):
        """Resetea el historial del clasificador"""
        self.price_history.clear()
        self.timestamps.clear()
