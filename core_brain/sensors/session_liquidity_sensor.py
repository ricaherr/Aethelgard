"""
SessionLiquiditySensor - Detector de Niveles de Sesión de Liquidez

Responsabilidades:
- Calcular Session High/Low de Londres (08:00-17:00 GMT)
- Calcular máximo/mínimo del día anterior
- Detectar breakouts por encima/debajo de estos niveles
- Proporcionar mapeo de zonas de liquidez críticas

TRACE_ID: SENSOR-SESSION-LIQUIDITY-2026
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, List
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from data_vault.storage import StorageManager


class CandleData(BaseModel):
    """Validación de datos de vela OHLC para SessionLiquiditySensor."""
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: Optional[float] = Field(default=None, ge=0, description="Volume (opcional)")
    
    class Config:
        str_strip_whitespace = True

logger = logging.getLogger(__name__)


class SessionLiquiditySensor:
    """
    Sensor de niveles de sesión y liquidez institucional.
    
    Detecta máximos/mínimos de sesión Londres y día anterior,
    identifica breakouts falsos y zonas de alta densidad de stops.
    """
    
    def __init__(self, storage: StorageManager, user_id: str = "DEFAULT", trace_id: str = None):
        """
        Inicializa el sensor con inyección de dependencias.
        
        Args:
            storage: StorageManager para lectura de configuración (debe estar aislado a user_id)
            user_id: Identificador del usuario para aislamiento multiusuario
            trace_id: Identificador único de traza
        """
        self.storage_manager = storage
        self.user_id = user_id
        self.trace_id = trace_id or f"SENSOR-SESSION-LIQUIDITY-{user_id}"
        
        # Configuración de sesión Londres
        self.london_session_start = 8   # 08:00 GMT
        self.london_session_end = 17    # 17:00 GMT
        self.london_timezone = "GMT"
        
        logger.info(f"[{self.trace_id}] SessionLiquiditySensor initialized for user {self.user_id}")
    
    
    def get_london_session_high_low(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calcula el High/Low de la sesión de Londres (08:00-17:00 GMT).
        
        Args:
            df: DataFrame OHLC con índice datetime (timezone-aware)
            
        Returns:
            Tuple (session_high, session_low) o (None, None) si no hay datos
        """
        if df is None or df.empty:
            logger.debug(f"[{self.trace_id}] Empty DataFrame provided")
            return None, None
        
        # Filtrar velas dentro de horario Londres
        try:
            # Asegurar que el índice tiene timezone
            if not hasattr(df.index, 'tz') or df.index.tz is None:
                logger.warning(f"[{self.trace_id}] DataFrame index is not timezone-aware, assuming UTC")
                df.index = df.index.tz_localize('UTC')
            
            # Filtrar por hora (08:00-17:00)
            london_mask = (df.index.hour >= self.london_session_start) & \
                          (df.index.hour < self.london_session_end)
            london_df = df[london_mask]
            
            if london_df.empty:
                logger.debug(f"[{self.trace_id}] No data in London session hours")
                return None, None
            
            session_high = float(london_df['high'].max())
            session_low = float(london_df['low'].min())
            
            logger.debug(
                f"[{self.trace_id}] London session High: {session_high:.5f}, Low: {session_low:.5f}"
            )
            
            return session_high, session_low
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error calculating session high/low: {e}")
            return None, None
    
    
    def get_previous_day_high_low(
        self,
        df: pd.DataFrame,
        current_date: Optional[datetime] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calcula el High/Low del día anterior (H-1).
        
        Args:
            df: DataFrame OHLC con índice datetime
            current_date: Fecha actual para comparación (default: hoy)
            
        Returns:
            Tuple (prev_day_high, prev_day_low)
        """
        if df is None or df.empty:
            logger.debug(f"[{self.trace_id}] Empty DataFrame provided")
            return None, None
        
        if current_date is None:
            current_date = datetime.now(timezone.utc)
        
        try:
            # Asegurar timezone
            if not hasattr(df.index, 'tz') or df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            
            # Filtrar por día anterior
            prev_date = pd.Timestamp(current_date.date()) - pd.Timedelta(days=1)
            prev_date_mask = df.index.date == prev_date.date()
            
            prev_df = df[prev_date_mask]
            
            if prev_df.empty:
                # Si no hay día anterior, usar último día disponible
                logger.debug(f"[{self.trace_id}] No previous day data, using last available day")
                prev_df = df.iloc[:-24] if len(df) >= 24 else df
            
            if prev_df.empty:
                return None, None
            
            prev_high = float(prev_df['high'].max())
            prev_low = float(prev_df['low'].min())
            
            logger.debug(
                f"[{self.trace_id}] Previous day High: {prev_high:.5f}, Low: {prev_low:.5f}"
            )
            
            return prev_high, prev_low
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error calculating previous day high/low: {e}")
            return None, None
    
    
    def detect_breakout(
        self,
        current_price: float,
        breakout_level: float,
        direction: str
    ) -> Tuple[bool, Optional[str], float]:
        """
        Detecta si el precio ha perforado un nivel (breakout).
        
        Args:
            current_price: Precio actual (cierre de vela)
            breakout_level: Nivel a perforar (ej. Session High)
            direction: 'ABOVE' o 'BELOW'
            
        Returns:
            Tuple (is_breakout, signal_direction, distance)
            - is_breakout: True si perforó
            - signal_direction: 'BULLISH' o 'BEARISH'
            - distance: Distancia en pips (positiva)
        """
        try:
            if direction == 'ABOVE':
                is_breakout = current_price > breakout_level
                signal = 'BULLISH' if is_breakout else None
            elif direction == 'BELOW':
                is_breakout = current_price < breakout_level
                signal = 'BEARISH' if is_breakout else None
            else:
                return False, None, 0
            
            distance = abs(current_price - breakout_level)
            
            if is_breakout:
                logger.debug(
                    f"[{self.trace_id}] Breakout detected: {signal} by {distance:.5f}"
                )
            
            return is_breakout, signal, distance
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error detecting breakout: {e}")
            return False, None, 0
    
    
    def get_liquidity_zones(
        self,
        london_high: Optional[float],
        london_low: Optional[float],
        prev_day_high: Optional[float],
        prev_day_low: Optional[float]
    ) -> Dict[str, float]:
        """
        Mapea todas las zonas de liquidez críticas.
        
        Args:
            london_high: Máximo de sesión Londres
            london_low: Mínimo de sesión Londres
            prev_day_high: Máximo del día anterior
            prev_day_low: Mínimo del día anterior
            
        Returns:
            Dict con niveles críticos y densidad
        """
        zones = {
            'london_session_high': london_high,
            'london_session_low': london_low,
            'previous_day_high': prev_day_high,
            'previous_day_low': prev_day_low,
        }
        
        # Calcular indicador de densidad (cuántos niveles están cercanos)
        valid_zones = [z for z in [london_high, london_low, prev_day_high, prev_day_low] if z is not None]
        zones['density_indicator'] = len(valid_zones) / 4.0  # 0-1
        
        logger.debug(f"[{self.trace_id}] Liquidity zones mapped: {zones}")
        
        return zones
    
    
    def analyze_session_liquidity(
        self,
        df: pd.DataFrame
    ) -> Dict:
        """
        Ejecuta análisis completo de liquidez de sesión.
        
        Args:
            df: DataFrame OHLC con histórico
            
        Returns:
            Dict con resultado del análisis
        """
        try:
            london_high, london_low = self.get_london_session_high_low(df)
            prev_high, prev_low = self.get_previous_day_high_low(df)
            
            # Detectar breakout si hay vela actual
            has_breakout = False
            breakout_info = None
            
            if not df.empty and london_high is not None:
                current_close = float(df.iloc[-1]['close'])
                
                # Chequear si hay breakout hacia arriba o abajo
                if current_close > london_high:
                    is_break, direction, distance = self.detect_breakout(
                        current_close, london_high, 'ABOVE'
                    )
                    has_breakout = is_break
                    breakout_info = {
                        'type': 'ABOVE_SESSION_HIGH',
                        'direction': direction,
                        'distance': distance
                    }
                elif current_close < london_low:
                    is_break, direction, distance = self.detect_breakout(
                        current_close, london_low, 'BELOW'
                    )
                    has_breakout = is_break
                    breakout_info = {
                        'type': 'BELOW_SESSION_LOW',
                        'direction': direction,
                        'distance': distance
                    }
            
            result = {
                'london_high': london_high,
                'london_low': london_low,
                'previous_day_high': prev_high,
                'previous_day_low': prev_low,
                'has_breakout': has_breakout,
                'breakout_info': breakout_info,
                'liquidity_zones': self.get_liquidity_zones(london_high, london_low, prev_high, prev_low),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error in session liquidity analysis: {e}")
            return {
                'error': str(e),
                'london_high': None,
                'london_low': None,
                'has_breakout': False,
            }
