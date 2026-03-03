"""
Candlestick Pattern Detector - Rejection Tails & Hammer Patterns
==================================================================

Responsabilidades:
1. Detectar "Rejection Tails" (Cola de Piso: tail >= 50% del rango)
2. Detectar "Hammer" patterns (Vela Elefante - reversión bullish)
3. Validar proporción cuerpo/mecha
4. Generar señales de reversión basadas en patterns

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage por constructor

TRACE_ID: SENSOR-CANDLESTICK-001
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime

logger = logging.getLogger(__name__)


class CandlestickPatternDetector:
    """
    Detector de patrones candlestick para estrategia Trifecta.
    
    Enfoque:
    1. Colas de rechazo (Rejection Tails): Defensa en SMA 20
    2. Velas Elefante (Hammer): Estructura de reversión clave
    """
    
    def __init__(
        self,
        storage: Any,
        trace_id: str = None
    ):
        """
        Args:
            storage: StorageManager (SSOT para configuración)
            trace_id: Request trace ID para auditoría
        """
        self.storage = storage
        self.trace_id = trace_id
        
        # Parámetros de detección
        self._load_config()
        
        logger.info(
            f"[{self.trace_id}] CandlestickPatternDetector initialized. "
            f"Rejection_tail_threshold={self.rejection_tail_threshold}"
        )
    
    
    def _load_config(self) -> None:
        """Carga configuración desde DB (SSOT)."""
        try:
            params = self.storage.get_dynamic_params()
            self.rejection_tail_threshold = params.get('rejection_tail_threshold', 0.5)
            self.hammer_body_max_pct = params.get('hammer_body_max_pct', 0.3)
            self.min_tail_pips = params.get('min_tail_pips', 5)
        except Exception as e:
            logger.warning(f"Failed to load config from storage: {e}. Using defaults.")
            self.rejection_tail_threshold = 0.5  # 50% del rango
            self.hammer_body_max_pct = 0.3  # Máx 30% del rango
            self.min_tail_pips = 5
    
    
    def calculate_body_size(self, candle: Dict[str, float]) -> float:
        """
        Calcula el tamaño del cuerpo de la vela.
        
        Body Size = |close - open|
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            Tamaño del cuerpo en pips
        """
        return abs(candle['close'] - candle['open'])
    
    
    def calculate_tail_length(
        self,
        candle: Dict[str, float],
        direction: Literal['upper', 'lower'] = 'lower'
    ) -> float:
        """
        Calcula la longitud de una mecha (tail/shadow).
        
        Args:
            candle: Dict con OHLC
            direction: 'upper' o 'lower'
            
        Returns:
            Longitud de la mecha en pips
        """
        body_top = max(candle['open'], candle['close'])
        body_bottom = min(candle['open'], candle['close'])
        
        if direction == 'lower':
            return body_bottom - candle['low']
        else:  # upper
            return candle['high'] - body_top
    
    
    def calculate_candle_range(self, candle: Dict[str, float]) -> float:
        """
        Calcula el rango total de la vela.
        
        Range = high - low
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            Rango en pips
        """
        return candle['high'] - candle['low']
    
    
    def detect_rejection_tail(
        self,
        candle: Dict[str, float],
        threshold: Optional[float] = None
    ) -> bool:
        """
        Detecta si una vela tiene una "Cola de Rechazo" (Rejection Tail).
        
        Rejection Tail = Mecha >= 50% del rango total
        
        Interpretación:
        - Precio intenta ir a nivel bajo/alto
        - Market rejaza ese nivel y cierra lejos
        - Indica defensa institucional
        
        Args:
            candle: Dict con OHLC
            threshold: % del rango (default: self.rejection_tail_threshold)
            
        Returns:
            True si detecta rejection tail
        """
        if threshold is None:
            threshold = self.rejection_tail_threshold
        
        try:
            candle_range = self.calculate_candle_range(candle)
            
            if candle_range == 0:
                return False
            
            # Calcular proporciones de mechas
            lower_tail = self.calculate_tail_length(candle, 'lower')
            upper_tail = self.calculate_tail_length(candle, 'upper')
            
            # Una mecha debe ser >= threshold del rango
            lower_tail_ratio = lower_tail / candle_range
            upper_tail_ratio = upper_tail / candle_range
            
            is_rejection = (lower_tail_ratio >= threshold) or (upper_tail_ratio >= threshold)
            
            if is_rejection:
                logger.debug(
                    f"[{self.trace_id}] Rejection tail detected. "
                    f"Lower tail ratio: {lower_tail_ratio:.2%}, "
                    f"Upper tail ratio: {upper_tail_ratio:.2%}"
                )
            
            return is_rejection
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error detecting rejection tail: {e}",
                exc_info=True
            )
            return False
    
    
    def detect_hammer(
        self,
        candle: Dict[str, float]
    ) -> bool:
        """
        Detecta patrón de Hammer (Vela Elefante).
        
        Características:
        - Abre cerca del máximo
        - Tiene larga mecha inferior (rechazo)
        - Cuerpo pequeño
        - Cierra positivo (impulso alcista)
        
        Interpretación: Reversión bullish potencial
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            True si es Hammer
        """
        try:
            candle_range = self.calculate_candle_range(candle)
            body_size = self.calculate_body_size(candle)
            lower_tail = self.calculate_tail_length(candle, 'lower')
            upper_tail = self.calculate_tail_length(candle, 'upper')
            
            if candle_range == 0 or candle_range < self.min_tail_pips:
                return False
            
            # Condiciones para Hammer
            body_ratio = body_size / candle_range
            lower_tail_ratio = lower_tail / candle_range
            upper_tail_ratio = upper_tail / candle_range
            
            # 1. Cuerpo pequeño (< 30% del rango)
            has_small_body = body_ratio <= self.hammer_body_max_pct
            
            # 2. Mecha inferior larga (>= 50% del rango)
            has_long_lower_tail = lower_tail_ratio >= self.rejection_tail_threshold
            
            # 3. Mecha superior corta o no existe (< 10% del rango)
            has_short_upper_tail = upper_tail_ratio < 0.1
            
            # 4. Cierra positivo (close > open para bullish)
            is_bullish = candle['close'] > candle['open']
            
            is_hammer = (
                has_small_body and
                has_long_lower_tail and
                has_short_upper_tail and
                is_bullish
            )
            
            if is_hammer:
                logger.debug(
                    f"[{self.trace_id}] Hammer pattern detected. "
                    f"Body ratio: {body_ratio:.2%}, "
                    f"Lower tail ratio: {lower_tail_ratio:.2%}"
                )
            
            return is_hammer
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error detecting hammer: {e}",
                exc_info=True
            )
            return False
    
    
    def scan_for_rejections(
        self,
        df: pd.DataFrame
    ) -> List[int]:
        """
        Escanea un DataFrame buscando velas con Rejection Tails.
        
        Args:
            df: DataFrame con columnas OHLC
            
        Returns:
            Lista de índices donde se detectaron rejection tails
        """
        rejection_indices = []
        
        try:
            for idx in range(len(df)):
                row = df.iloc[idx]
                candle = {
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row.get('volume', 0)
                }
                
                if self.detect_rejection_tail(candle):
                    rejection_indices.append(idx)
            
            logger.debug(
                f"[{self.trace_id}] Found {len(rejection_indices)} rejection tails "
                f"in {len(df)} candles"
            )
            
            return rejection_indices
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error scanning for rejections: {e}",
                exc_info=True
            )
            return []
    
    
    def detect_consecutive_pattern(
        self,
        df: pd.DataFrame,
        min_length: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Detecta secuencias de patrones (ej: rejection + hammer).
        
        Caso de uso: Confirmación de reversal después de toque de SMA
        
        Args:
            df: DataFrame de velas consecutivas
            min_length: Longitud mínima de patrón
            
        Returns:
            Dict con descripción de patrón si existe, None si no hay
        """
        try:
            rejections = self.scan_for_rejections(df)
            
            if len(rejections) < min_length:
                return None
            
            # Analizar secuencia
            pattern_description = {
                'type': 'consecutive_rejections',
                'count': len(rejections),
                'indices': rejections,
                'strength': len(rejections) / len(df),  # % de velas con patrón
            }
            
            # Si hay hammer al final
            last_row = df.iloc[-1]
            last_candle = {
                'open': last_row['open'],
                'high': last_row['high'],
                'low': last_row['low'],
                'close': last_row['close'],
            }
            
            if self.detect_hammer(last_candle):
                pattern_description['final_pattern'] = 'hammer'
                pattern_description['bullish_confirmation'] = True
            
            logger.debug(
                f"[{self.trace_id}] Consecutive pattern detected: {pattern_description}"
            )
            
            return pattern_description
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error detecting consecutive pattern: {e}",
                exc_info=True
            )
            return None
    
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        symbol: str,
        direction: Literal['BUY', 'SELL']
    ) -> Optional[Dict[str, Any]]:
        """
        Genera señal de entrada/salida basada en patrón detectado.
        
        Implementa Pilar Multi-tenant: riesgo 1% del capital
        
        Args:
            candle: Vela que generó el patrón
            symbol: Símbolo del activo
            direction: BUY o SELL
            
        Returns:
            Dict con detalles de entrada/stop/tp
        """
        try:
            if direction == 'BUY':
                # Entry: Por encima del máximo + 1 pip
                entry_price = candle['high'] + 0.0001
                # Stop Loss: Por debajo del mínimo - 1 pip
                stop_loss = candle['low'] - 0.0001
                tp_ratio = 2.5  # Risk/Reward de 1:2.5
                
            else:  # SELL
                # Entry: Por debajo del mínimo - 1 pip
                entry_price = candle['low'] - 0.0001
                # Stop Loss: Por encima del máximo + 1 pip
                stop_loss = candle['high'] + 0.0001
                tp_ratio = 2.5
            
            risk = abs(entry_price - stop_loss)
            take_profit = entry_price + (risk * tp_ratio) if direction == 'BUY' else entry_price - (risk * tp_ratio)
            
            signal = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': round(entry_price, 5),
                'stop_loss': round(stop_loss, 5),
                'take_profit': round(take_profit, 5),
                'risk_pips': round(risk * 10000, 2),
                'reward_pips': round(abs(take_profit - entry_price) * 10000, 2),
                'ratio': tp_ratio,
                'timestamp': datetime.now().isoformat(),
            }
            
            logger.debug(
                f"[{self.trace_id}] Signal generated for {symbol} {direction}: "
                f"Entry={signal['entry_price']}, SL={signal['stop_loss']}, TP={signal['take_profit']}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error generating signal: {e}",
                exc_info=True
            )
            return None
