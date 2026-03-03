"""
Candlestick Pattern Detector - Rejection Tails, Hammer & Momentum Strike
==========================================================================

Responsabilidades:
1. Detectar "Rejection Tails" (Cola de Piso: tail >= 50% del rango)
2. Detectar "Hammer" patterns (Vela Elefante - reversión bullish)
3. Detectar "Momentum Strike" (MOM_BIAS_0001): Vela elefante + ubicación geométrica
4. Validar proporción cuerpo/mecha y confluencia de medias
5. Generar señales de entrada con SL = OPEN (para Momentum)

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage + moving_average_sensor por constructor

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
    Detector de patrones candlestick para estrategias Trifecta y Momentum.
    
    Enfoque:
    1. Colas de rechazo (Rejection Tails): Defensa en SMA 20
    2. Velas Elefante (Hammer): Estructura de reversión clave
    3. Momentum Strike (MOM_BIAS_0001): Ruptura de compresión SMA20/SMA200
    """
    
    def __init__(
        self,
        storage: Any,
        moving_average_sensor: Any = None,
        trace_id: str = None
    ):
        """
        Args:
            storage: StorageManager (SSOT para configuración)
            moving_average_sensor: MovingAverageSensor (para SMA20/SMA200 en Momentum)
            trace_id: Request trace ID para auditoría
        """
        self.storage = storage
        self.moving_average_sensor = moving_average_sensor
        self.trace_id = trace_id or "CANDLESTICK-001"
        
        # Parámetros de detección
        self._load_config()
        
        logger.info(
            f"[{self.trace_id}] CandlestickPatternDetector initialized. "
            f"Rejection_tail_threshold={self.rejection_tail_threshold}, "
            f"MOM_BIAS_closure_threshold={self.mom_bias_closure_threshold}"
        )
    
    
    def _load_config(self) -> None:
        """Carga configuración desde DB (SSOT) para ambas estrategias."""
        try:
            params = self.storage.get_dynamic_params()
            # Parámetros Trifecta (Rejection Tails & Hammer)
            self.rejection_tail_threshold = params.get('rejection_tail_threshold', 0.5)
            self.hammer_body_max_pct = params.get('hammer_body_max_pct', 0.3)
            self.min_tail_pips = params.get('min_tail_pips', 5)
            
            # Parámetros MOM_BIAS_0001 (Momentum Strike)
            self.mom_bias_closure_threshold = params.get('mom_bias_closure_threshold', 0.02)  # 2%
            self.mom_bias_sma_compression_pips = params.get('mom_bias_sma_compression_pips', 15)  # pips
            self.mom_bias_volume_multiplier = params.get('mom_bias_volume_multiplier', 1.0)  # >= promedio
            
        except Exception as e:
            logger.warning(f"Failed to load config from storage: {e}. Using defaults.")
            # Defaults Trifecta
            self.rejection_tail_threshold = 0.5
            self.hammer_body_max_pct = 0.3
            self.min_tail_pips = 5
            # Defaults MOM_BIAS
            self.mom_bias_closure_threshold = 0.02
            self.mom_bias_sma_compression_pips = 15
            self.mom_bias_volume_multiplier = 1.0
    
    
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
    
    
    def detect_momentum_strike(
        self,
        current_candle: Dict[str, float],
        previous_candles: List[Dict[str, float]],
        sma20: float,
        sma200: float,
        symbol: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detecta patrón de Momentum Strike (MOM_BIAS_0001).
        
        Lógica de Ubicación (Filtro de Ignición):
        1. Vela cierra 2%+ por encima/debajo de máximo previo O SMA20
        2. SMA20 y SMA200 están en compresión (≤15 pips)
        3. Confluencia: SMA20 cruzando O comprimida
        
        Args:
            current_candle: Dict con OHLC de vela actual
            previous_candles: Lista de dicts OHLC previos (últimas 5)
            sma20: Valor actual de SMA20
            sma200: Valor actual de SMA200
            symbol: Símbolo del activo (para logging)
            
        Returns:
            Dict con detalles si momentum strike detectado, None si no
        """
        try:
            if not self.moving_average_sensor:
                logger.warning(f"[{self.trace_id}] moving_average_sensor no inyectado. Skipping MOM_BIAS_0001")
                return None
            
            # Validar inputs
            if not previous_candles or len(previous_candles) < 2:
                logger.debug(f"[{self.trace_id}] No hay velas previas suficientes")
                return None
            
            symbol_tag = f" [{symbol}]" if symbol else ""
            
            # ========================
            # PASO 1: Validar Compresión SMA20/SMA200
            # ========================
            compression_pips = abs(sma20 - sma200)
            is_compressed = compression_pips <= self.mom_bias_sma_compression_pips
            
            if not is_compressed:
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} SMA20/200 no en compresión. "
                    f"Dist: {compression_pips:.1f} pips (max: {self.mom_bias_sma_compression_pips})"
                )
                return None
            
            logger.debug(
                f"[{self.trace_id}] {symbol_tag} SMA20/200 EN COMPRESIÓN: {compression_pips:.1f} pips"
            )
            
            # ========================
            # PASO 2: Validar Dirección y Cierre 2%+ Lejos
            # ========================
            is_bullish_close = current_candle['close'] > current_candle['open']
            candle_range = self.calculate_candle_range(current_candle)
            
            # Máximo de consolidación previa (últimas 5 velas)
            prev_high = max([c.get('high', 0) for c in previous_candles])
            prev_low = min([c.get('low', float('inf')) for c in previous_candles])
            
            # Calcular threshold 2% en pips (ej: para EUR/USD 1.0700 -> 214 pips)
            avg_price = (sma20 + sma200) / 2
            closure_threshold_pips = avg_price * self.mom_bias_closure_threshold * 10000  # Convertir a pips
            
            # Caso BULLISH: Cierre debe estar 2% por encima
            if is_bullish_close:
                distance_above_sma20 = (current_candle['close'] - sma20) * 10000  # En pips
                distance_above_prev_high = (current_candle['close'] - prev_high) * 10000
                
                bullish_ignition = (
                    distance_above_sma20 >= closure_threshold_pips or
                    distance_above_prev_high >= closure_threshold_pips
                )
                
                if not bullish_ignition:
                    logger.debug(
                        f"[{self.trace_id}] {symbol_tag} BULLISH no cumple 2% cierre. "
                        f"Dist SMA20: {distance_above_sma20:.1f} pips (min: {closure_threshold_pips:.1f})"
                    )
                    return None
                
                direction = 'BUY'
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BULLISH IGNITION! Cierre {distance_above_sma20:.1f} pips arriba de SMA20"
                )
            
            # Caso BEARISH: Cierre debe estar 2% por debajo
            else:
                distance_below_sma20 = (sma20 - current_candle['close']) * 10000  # En pips
                distance_below_prev_low = (prev_low - current_candle['close']) * 10000
                
                bearish_ignition = (
                    distance_below_sma20 >= closure_threshold_pips or
                    distance_below_prev_low >= closure_threshold_pips
                )
                
                if not bearish_ignition:
                    logger.debug(
                        f"[{self.trace_id}] {symbol_tag} BEARISH no cumple 2% cierre. "
                        f"Dist SMA20: {distance_below_sma20:.1f} pips (min: {closure_threshold_pips:.1f})"
                    )
                    return None
                
                direction = 'SELL'
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BEARISH IGNITION! Cierre {distance_below_sma20:.1f} pips bajo de SMA20"
                )
            
            # ========================
            # PASO 3: Validar Volumen (Confirmación)
            # ========================
            current_vol = current_candle.get('volume', 0)
            prev_volumes = [c.get('volume', 0) for c in previous_candles[-20:] if c.get('volume', 0) > 0]
            
            if prev_volumes:
                avg_volume = np.mean(prev_volumes)
                vol_ratio = current_vol / avg_volume if avg_volume > 0 else 0
                
                if vol_ratio < self.mom_bias_volume_multiplier:
                    logger.debug(
                        f"[{self.trace_id}] {symbol_tag} Volumen bajo: {vol_ratio:.2f}x "
                        f"(min: {self.mom_bias_volume_multiplier}x)"
                    )
                    # Nota: No es requisito hard, solo confirmación
            else:
                vol_ratio = 1.0
            
            # ========================
            # PASO 4: Construir respuesta
            # ========================
            momentum_strike = {
                'detected': True,
                'direction': direction,
                'symbol': symbol,
                'current_price': current_candle['close'],
                'sma20': sma20,
                'sma200': sma200,
                'compression_pips': compression_pips,
                'open_price': current_candle['open'],  # SL para MOM_BIAS_0001
                'volume_ratio': vol_ratio,
                'candle_range': candle_range,
                'timestamp': current_candle.get('timestamp', datetime.now().isoformat()),
            }
            
            logger.info(
                f"[{self.trace_id}] {symbol_tag} 🚀 MOMENTUM STRIKE DETECTED! "
                f"Dir={direction}, Price={current_candle['close']:.5f}, SL={current_candle['open']:.5f}"
            )
            
            return momentum_strike
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error detecting momentum strike: {e}",
                exc_info=True
            )
            return None
    
    
    def generate_signal(
        self,
        candle: Dict[str, float],
        symbol: str,
        direction: Literal['BUY', 'SELL'],
        strategy_type: Literal['TRIFECTA', 'MOMENTUM'] = 'TRIFECTA'
    ) -> Optional[Dict[str, Any]]:
        """
        Genera señal de entrada/salida basada en patrón detectado.
        
        Soporta dos estrategias:
        1. TRIFECTA: SL = LOW/HIGH (máximo riesgo, máxima confirmación)
        2. MOMENTUM: SL = OPEN (menor riesgo, mayor lotaje)
        
        Args:
            candle: Vela que generó el patrón
            symbol: Símbolo del activo
            direction: BUY o SELL
            strategy_type: TRIFECTA (default) o MOMENTUM
            
        Returns:
            Dict con detalles de entrada/stop/tp/risk/reward
        """
        try:
            if strategy_type == 'MOMENTUM':
                # MOM_BIAS_0001: SL = OPEN de la vela
                if direction == 'BUY':
                    entry_price = candle['high'] + 0.0001  # Entry encima del máximo
                    stop_loss = candle['open']  # SL en OPEN (regla de ORO)
                    tp_ratio = 2.0  # Risk/Reward 1:2 (conservador)
                else:  # SELL
                    entry_price = candle['low'] - 0.0001  # Entry bajo del mínimo
                    stop_loss = candle['open']  # SL en OPEN
                    tp_ratio = 2.0
                    
            else:  # TRIFECTA (default)
                # Estrategia Trifecta: SL = LOW/HIGH
                if direction == 'BUY':
                    entry_price = candle['high'] + 0.0001
                    stop_loss = candle['low'] - 0.0001  # Por debajo del mínimo
                    tp_ratio = 2.5  # Risk/Reward 1:2.5
                else:  # SELL
                    entry_price = candle['low'] - 0.0001
                    stop_loss = candle['high'] + 0.0001  # Por encima del máximo
                    tp_ratio = 2.5
            
            risk = abs(entry_price - stop_loss)
            take_profit = entry_price + (risk * tp_ratio) if direction == 'BUY' else entry_price - (risk * tp_ratio)
            
            signal = {
                'symbol': symbol,
                'direction': direction,
                'strategy_type': strategy_type,
                'entry_price': round(entry_price, 5),
                'stop_loss': round(stop_loss, 5),
                'take_profit': round(take_profit, 5),
                'risk_pips': round(risk * 10000, 2),
                'reward_pips': round(abs(take_profit - entry_price) * 10000, 2),
                'ratio': tp_ratio,
                'timestamp': datetime.now().isoformat(),
            }
            
            logger.debug(
                f"[{self.trace_id}] Signal generated [{strategy_type}] {symbol} {direction}: "
                f"Entry={signal['entry_price']}, SL={signal['stop_loss']}, TP={signal['take_profit']}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error generating signal: {e}",
                exc_info=True
            )
            return None
