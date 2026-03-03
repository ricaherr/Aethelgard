"""
Moving Average Sensor - SMA 20/200 Detection
============================================

Responsabilidades:
1. Calcular SMA 20 (M5/M15 - línea de batalla)
2. Calcular SMA 200 (H1 - nivel macro)
3. Integración con StrategyGatekeeper (veto por spread, etc)
4. Caching de cálculos para optimización
5. Análisis de ubicación (price above/below SMA)

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage, gatekeeper por constructor

TRACE_ID: SENSOR-MA-20-200-001
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MovingAverageSensor:
    """
    Sensor para detección de medias móviles institucionales.
    
    Pilares Sensorial:
    - SMA 200 (H1): Define si estamos en mercado "Barato" o "Caro"
    - SMA 20 (M5/M15): Línea de batalla, soporte dinámico
    
    Optimización: Solo calcula si StrategyGatekeeper autoriza el instrumento
    """
    
    def __init__(
        self,
        storage: Any,
        gatekeeper: Optional[Any] = None,
        trace_id: str = None
    ):
        """
        Args:
            storage: StorageManager (SSOT para configuración)
            gatekeeper: StrategyGatekeeper para autorización de activos
            trace_id: Request trace ID para auditoría
        """
        self.storage = storage
        self.gatekeeper = gatekeeper
        self.trace_id = trace_id
        
        # Cache de cálculos para optimización
        self._sma_cache: Dict[str, pd.Series] = {}
        
        # Parámetros cargados de DB
        self._load_config()
        
        logger.info(
            f"[{self.trace_id}] MovingAverageSensor initialized. "
            f"SMA_FAST={self.sma_fast}, SMA_SLOW={self.sma_slow}"
        )
    
    
    def _load_config(self) -> None:
        """Carga configuración desde DB (SSOT)."""
        try:
            params = self.storage.get_dynamic_params()
            self.sma_fast = params.get('sma_fast_period', 20)
            self.sma_slow = params.get('sma_slow_period', 200)
            self.cache_enabled = params.get('cache_enabled', True)
        except Exception as e:
            logger.warning(f"Failed to load config from storage: {e}. Using defaults.")
            self.sma_fast = 20
            self.sma_slow = 200
            self.cache_enabled = True
    
    
    def calculate_sma(
        self,
        df: pd.DataFrame,
        period: int,
        column: str = 'close'
    ) -> pd.Series:
        """
        Calcula Media Móvil Simple (SMA).
        
        Args:
            df: DataFrame con OHLCV
            period: Período de la SMA (20 o 200)
            column: Columna a usar (default 'close')
            
        Returns:
            pd.Series con SMA calculada
        """
        # Generar cache key
        cache_key = f"sma_{period}_{column}"
        
        # Verificar cache
        if self.cache_enabled and cache_key in self._sma_cache:
            logger.debug(f"[{self.trace_id}] Using cached SMA {period}")
            return self._sma_cache[cache_key]
        
        try:
            if len(df) < period:
                logger.warning(
                    f"[{self.trace_id}] Insufficient data for SMA {period}: "
                    f"need {period}, have {len(df)}"
                )
                return pd.Series(np.nan, index=df.index)
            
            # Calcular SMA
            sma = df[column].rolling(window=period).mean()
            
            # Guardar en cache
            if self.cache_enabled:
                self._sma_cache[cache_key] = sma
            
            return sma
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error calculating SMA {period}: {e}",
                exc_info=True
            )
            return pd.Series(np.nan, index=df.index)
    
    
    def analyze_macro_level(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = 'H1'
    ) -> Dict[str, Any]:
        """
        Analiza nivel MACRO usando SMA 200.
        
        Determina si el precio está "Caro" (arriba) o "Barato" (abajo)
        de la ubicación macro.
        
        Args:
            df: DataFrame H1 con datos
            symbol: Símbolo del activo (ej: EUR/USD)
            timeframe: Timeframe confirmación (default H1)
            
        Returns:
            Dict con 'level', 'status', 'sma200_value'
        """
        try:
            sma200 = self.calculate_sma(df, self.sma_slow, 'close')
            
            if len(df) == 0 or sma200.isna().all():
                logger.warning(
                    f"[{self.trace_id}] {symbol} H1: Insufficient data for SMA 200"
                )
                return {'level': 'unknown', 'status': 'error', 'sma200_value': None}
            
            latest_close = df['close'].iloc[-1]
            latest_sma200 = sma200.iloc[-1]
            
            if pd.isna(latest_sma200):
                return {'level': 'unknown', 'status': 'calculating', 'sma200_value': None}
            
            # Determinar ubicación
            if latest_close > latest_sma200:
                status = 'above'
                level_description = "CARO (Bullish)"
            elif latest_close < latest_sma200:
                status = 'below'
                level_description = "BARATO (Bearish)"
            else:
                status = 'on_line'
                level_description = "En la línea"
            
            distance_pips = abs(latest_close - latest_sma200) * 10000  # Asumir 4 decimales
            
            return {
                'level': latest_sma200,
                'status': status,
                'description': level_description,
                'current_price': latest_close,
                'distance_pips': round(distance_pips, 2),
                'sma200_value': latest_sma200,
                'timeframe': timeframe
            }
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error analyzing macro level {symbol}: {e}",
                exc_info=True
            )
            return {'level': 'unknown', 'status': 'error'}
    
    
    def analyze_micro_level(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = 'M5'
    ) -> Dict[str, Any]:
        """
        Analiza nivel MICRO usando SMA 20.
        
        Representa la "línea de batalla" donde ocurren reversiones.
        
        Args:
            df: DataFrame M5/M15 con datos
            symbol: Símbolo del activo
            timeframe: Timeframe (M5 o M15)
            
        Returns:
            Dict con 'level', 'status', 'proximity'
        """
        try:
            sma20 = self.calculate_sma(df, self.sma_fast, 'close')
            
            if len(df) == 0 or sma20.isna().all():
                return {'level': 'unknown', 'status': 'error'}
            
            latest_close = df['close'].iloc[-1]
            latest_sma20 = sma20.iloc[-1]
            
            if pd.isna(latest_sma20):
                return {'level': 'unknown', 'status': 'calculating'}
            
            # Distancia a la SMA 20
            distance = latest_close - latest_sma20
            distance_pips = abs(distance) * 10000
            
            # Clasificar proximidad
            if distance_pips < 5:
                proximity = 'touching'
            elif distance_pips < 15:
                proximity = 'near'
            elif distance_pips < 30:
                proximity = 'moderate'
            else:
                proximity = 'far'
            
            return {
                'level': latest_sma20,
                'status': 'above' if distance > 0 else 'below',
                'current_price': latest_close,
                'distance_pips': round(distance_pips, 2),
                'proximity': proximity,
                'sma20_value': latest_sma20,
                'timeframe': timeframe
            }
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error analyzing micro level {symbol}: {e}",
                exc_info=True
            )
            return {'level': 'unknown', 'status': 'error'}
    
    
    def calculate_with_gatekeeper(
        self,
        symbol: str,
        df: pd.DataFrame,
        period: int,
        column: str = 'close'
    ) -> Optional[pd.Series]:
        """
        Calcula SMA solo si StrategyGatekeeper autoriza el activo.
        
        Implementa Pilar de Coherencia: evitar cálculos innecesarios
        en activos vetados (spread > 1.0 pip, bajo volumen, etc).
        
        Args:
            symbol: Símbolo a verificar
            df: DataFrame con datos
            period: Período SMA
            column: Columna a usar
            
        Returns:
            pd.Series si autorizado, None si vetado
        """
        # Verificar autorización con gatekeeper
        if self.gatekeeper and not self.gatekeeper.is_asset_authorized(symbol):
            logger.debug(
                f"[{self.trace_id}] {symbol} vetado por StrategyGatekeeper. "
                f"Saltando cálculo SMA {period}."
            )
            return None
        
        # Si autorizado, calcular normalmente
        return self.calculate_sma(df, period, column)
    
    
    def is_price_above_sma(
        self,
        df: pd.DataFrame,
        period: int = None
    ) -> bool:
        """
        Verifica si el precio actual está por encima de la SMA.
        
        Args:
            df: DataFrame con datos
            period: Período (default: self.sma_slow)
            
        Returns:
            True si price > SMA, False si price < SMA
        """
        if period is None:
            period = self.sma_slow
        
        sma = self.calculate_sma(df, period, 'close')
        
        if len(df) == 0 or sma.isna().all():
            return False
        
        latest_close = df['close'].iloc[-1]
        latest_sma = sma.iloc[-1]
        
        if pd.isna(latest_sma):
            return False
        
        return latest_close > latest_sma
    
    
    def is_price_below_sma(
        self,
        df: pd.DataFrame,
        period: int = None
    ) -> bool:
        """
        Verifica si el precio actual está por debajo de la SMA.
        
        Args:
            df: DataFrame con datos
            period: Período (default: self.sma_slow)
            
        Returns:
            True si price < SMA, False si price > SMA
        """
        return not self.is_price_above_sma(df, period)
    
    
    def clear_cache(self) -> None:
        """Limpia el cache de cálculos."""
        self._sma_cache.clear()
        logger.debug(f"[{self.trace_id}] Cache cleared")
    
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del cache."""
        return {
            'cache_enabled': self.cache_enabled,
            'cached_entries': len(self._sma_cache),
            'cached_keys': list(self._sma_cache.keys())
        }
