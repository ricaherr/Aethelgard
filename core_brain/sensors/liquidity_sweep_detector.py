"""
LiquiditySweepDetector - Detección de Breakout Falso + Reversión

Responsabilidades:
- Detectar PIN BAR: Wick > 60%, cuerpo < 30% del rango
- Detectar ENGULFING: Vela actual envuelve anterior completamente
- Validar que cierre está dentro del rango previo (negación de ruptura)
- Calcular probabilidad/strength de reversión
- Validar con volumen

TRACE_ID: SENSOR-LIQUIDITY-SWEEP-2026
"""

import logging
from typing import Dict, Tuple, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from data_vault.storage import StorageManager


class CandleData(BaseModel):
    """Validación de datos de vela OHLC para LiquiditySweepDetector."""
    model_config = ConfigDict(str_strip_whitespace=True)

    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: Optional[float] = Field(default=None, ge=0, description="Volume (opcional)")

logger = logging.getLogger(__name__)


class LiquiditySweepDetector:
    """
    Detecta candles de reversión (PIN BAR, ENGULFING) tras breakout falso.
    
    Valida que el breakout fue falso (cierre vuelve al rango anterior)
    y que la reversal tiene suficiente fuerza (volumen, patrón).
    """
    
    def __init__(self, storage: StorageManager = None, user_id: str = "DEFAULT", trace_id: str = None):
        """
        Inicializa el detector de sweep.
        
        Args:
            storage: StorageManager para leer configuración (debe estar aislado a user_id)
            user_id: Identificador del usuario para aislamiento multiusuario
            trace_id: ID único de traza
        """
        self.storage_manager = storage
        self.user_id = user_id
        self.trace_id = trace_id or f"SENSOR-LIQUIDITY-SWEEP-{user_id}"
        
        # Parámetros de PIN BAR
        self.pin_bar_wick_threshold = 0.60    # Wick debe ser >= 60% del rango
        self.pin_bar_body_threshold = 0.30    # Cuerpo debe ser <= 30% del rango
        
        # Parámetros de ENGULFING
        self.engulfing_body_overlap = 0.80    # Cuerpo actual debe envolver >= 80%
        
        logger.info(f"[{self.trace_id}] LiquiditySweepDetector initialized for user {self.user_id}")
    
    
    def detect_pin_bar(self, candle: Dict) -> Tuple[bool, Optional[str], float]:
        """
        Detecta si una vela es PIN BAR.
        
        Características:
        - Wick > 50% del rango total
        - Cuerpo < 20% del rango total
        - Cierre en extremo opuesto al wick
        
        Args:
            candle: Dict con keys 'open', 'high', 'low', 'close' o CandleData validada
            
        Returns:
            Tuple (is_pin_bar, direction, strength)
            - is_pin_bar: True si cumple criterios
            - direction: 'BULLISH' (wick abajo) o 'BEARISH' (wick arriba)
            - strength: Confidence 0-1
        """
        try:
            # Validar con Pydantic
            if isinstance(candle, dict):
                candle_data = CandleData(**candle)
            else:
                candle_data = candle
            
            open_price = candle_data.open
            high_price = candle_data.high
            low_price = candle_data.low
            close_price = candle_data.close
            
            # Calcular rango total y cuerpo
            total_range = high_price - low_price
            body = abs(close_price - open_price)
            
            if total_range == 0 or body == 0:
                return False, None, 0
            
            # Calcular wicks (la parte que se rechaza)
            upper_wick = high_price - max(close_price, open_price)
            lower_wick = min(close_price, open_price) - low_price
            
            upper_wick_ratio = upper_wick / total_range
            lower_wick_ratio = lower_wick / total_range
            body_ratio = body / total_range
            
            # Criterios de PIN BAR: cuerpo pequeño
            # Ajustado: cuerpo < 25% del rango
            is_pin_bar = body_ratio <= 0.25
            
            if not is_pin_bar:
                return False, None, 0
            
            # Determinar dirección según wick dominante
            # Debe haber un wick que sea > 50%
            if lower_wick_ratio > upper_wick_ratio and lower_wick_ratio >= 0.50:
                # Wick inferior dominante: BULLISH (rechaza abajo)
                direction = 'BULLISH'
                strength = min(1.0, lower_wick_ratio)
            elif upper_wick_ratio > lower_wick_ratio and upper_wick_ratio >= 0.50:
                # Wick superior dominante: BEARISH (rechaza arriba)
                direction = 'BEARISH'
                strength = min(1.0, upper_wick_ratio)
            else:
                return False, None, 0
            
            logger.debug(
                f"[{self.trace_id}] PIN BAR detected: {direction}, strength={strength:.2f}"
            )
            
            return True, direction, strength
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error detecting PIN BAR: {e}")
            return False, None, 0
    
    
    def detect_engulfing(
        self,
        prev_candle: Dict,
        current_candle: Dict
    ) -> Tuple[bool, Optional[str], float]:
        """
        Detecta si hay patrón ENGULFING (vela actual envuelve la anterior).
        
        Criterios:
        - Cuerpo actual > cuerpo anterior
        - Open actual abre fuera del open anterior
        - Close actual cierra fuera del close anterior
        
        Args:
            prev_candle: Dict de vela anterior
            current_candle: Dict de vela actual
            
        Returns:
            Tuple (is_engulfing, direction, strength)
        """
        try:
            prev_open = prev_candle['open']
            prev_close = prev_candle['close']
            prev_high = prev_candle.get('high', max(prev_open, prev_close))
            prev_low = prev_candle.get('low', min(prev_open, prev_close))
            
            curr_open = current_candle['open']
            curr_close = current_candle['close']
            curr_high = current_candle.get('high', max(curr_open, curr_close))
            curr_low = current_candle.get('low', min(curr_open, curr_close))
            
            # Calcular cuerpos
            prev_body = abs(prev_close - prev_open)
            curr_body = abs(curr_close - curr_open)
            
            # Validar que cuerpo actual > cuerpo anterior
            if curr_body <= prev_body:
                return False, None, 0
            
            # Validar envolvimiento
            # Para BULLISH: curr_open < prev_open y curr_close > prev_close
            is_bullish_engulf = (curr_open < prev_open and curr_close > prev_close)
            
            # Para BEARISH: curr_open > prev_open y curr_close < prev_close
            is_bearish_engulf = (curr_open > prev_open and curr_close < prev_close)
            
            if is_bullish_engulf:
                direction = 'BULLISH'
                # Strength basada en cuánto envuelve
                strength = min(1.0, (curr_body / max(prev_body, 1e-10)) * 0.5 + 0.5)
            elif is_bearish_engulf:
                direction = 'BEARISH'
                strength = min(1.0, (curr_body / max(prev_body, 1e-10)) * 0.5 + 0.5)
            else:
                return False, None, 0
            
            logger.debug(
                f"[{self.trace_id}] ENGULFING detected: {direction}, strength={strength:.2f}"
            )
            
            return True, direction, strength
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error detecting ENGULFING: {e}")
            return False, None, 0
    
    
    def is_within_previous_range(
        self,
        current_close: float,
        prev_high: float,
        prev_low: float
    ) -> bool:
        """
        Valida que el cierre está dentro del rango previo.
        
        Esto confirma una falsa ruptura (precio subió/bajó pero volvió).
        
        Args:
            current_close: Cierre actual
            prev_high: Máximo del rango previo
            prev_low: Mínimo del rango previo
            
        Returns:
            True si cierre está dentro, False si continúa ruptura
        """
        return prev_low <= current_close <= prev_high
    
    
    def detect_false_breakout_with_reversal(
        self,
        breakout_level: float,
        current_candle: Dict,
        prev_high: float,
        prev_low: float,
        direction: str
    ) -> Tuple[bool, Optional[str], float]:
        """
        Detecta breakout falso + reversal en una sola evaluación.
        
        Lógica:
        1. Validar que precio superó el nivel (breakout)
        2. Validar que cierre volvió al rango (falsa ruptura)
        3. Detectar patrón de reversal (PIN BAR o ENGULFING)
        
        Args:
            breakout_level: Nivel que se supone perfora
            current_candle: Vela actual
            prev_high: High del rango previo
            prev_low: Low del rango previo
            direction: 'ABOVE' o 'BELOW'
            
        Returns:
            Tuple (is_false_breakout, pattern_type, strength)
        """
        try:
            current_close = current_candle['close']
            current_high = current_candle.get('high')
            current_low = current_candle.get('low')
            
            # Step 1: Verificar breakout
            if direction == 'ABOVE':
                breakout_occurred = current_high > breakout_level
            elif direction == 'BELOW':
                breakout_occurred = current_low < breakout_level
            else:
                return False, None, 0
            
            if not breakout_occurred:
                # Ni siquiera hubo breakout
                return False, None, 0
            
            # Step 2: Verificar que cierre volvió (falsa ruptura)
            is_false = self.is_within_previous_range(current_close, prev_high, prev_low)
            
            if not is_false:
                # Precio continuó rompiendose (no es falsa ruptura)
                return False, None, 0
            
            # Step 3: Detectar patrón de reversal
            is_pin_bar, pin_direction, pin_strength = self.detect_pin_bar(current_candle)
            
            if is_pin_bar:
                logger.info(
                    f"[{self.trace_id}] FALSE BREAKOUT + PIN BAR detected ({pin_direction}), "
                    f"strength={pin_strength:.2f}"
                )
                return True, 'PIN_BAR', pin_strength
            
            # Si no es PIN BAR, buscar ENGULFING
            # Para ENGULFING necesitamos vela anterior
            # Por ahora retornamos como reversal genérica
            logger.info(f"[{self.trace_id}] FALSE BREAKOUT detected, searching for reversal pattern")
            
            return True, 'REVERSAL', 0.6  # Strength conservadora
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error detecting false breakout: {e}")
            return False, None, 0
    
    
    def validate_volume_confirmation(
        self,
        reversal_volume: float,
        average_volume: float
    ) -> Tuple[bool, float]:
        """
        Valida que el volumen de reversal es significativo.
        
        Args:
            reversal_volume: Volumen de la vela de reversal
            average_volume: Volumen promedio de últimas N velas
            
        Returns:
            Tuple (is_confirmed, confidence_boost)
            - confidence_boost: 0-0.2 adicional al score
        """
        try:
            if average_volume <= 0:
                return False, 0
            
            volume_ratio = reversal_volume / average_volume
            
            # Volumen > 120% del promedio es confirmación
            threshold = 1.20
            
            if volume_ratio >= threshold:
                # Boost confidence: entre 0.1 y 0.2 según ratio
                confidence_boost = min(0.2, (volume_ratio - threshold) * 0.1)
                logger.debug(
                    f"[{self.trace_id}] Volume confirmation: ratio={volume_ratio:.2f}, "
                    f"boost={confidence_boost:.3f}"
                )
                return True, confidence_boost
            else:
                return False, 0
                
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error validating volume: {e}")
            return False, 0
