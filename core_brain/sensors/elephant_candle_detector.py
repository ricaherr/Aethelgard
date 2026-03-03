"""
Elephant Candle Detector - Validación de Ubicación Geométrica para MOM_BIAS_0001
==================================================================================

Responsabilidades:
1. Detectar "Elephant Candles" (velas con cuerpo grande, impulso fuerte)
2. Validar ubicación relativa a SMA20 (ignición alcista/bajista)
3. Validar compresión SMA20/SMA200 (< 15 pips)
4. Confirmar impulso de volumen

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage + moving_average_sensor

TRACE_ID: SENSOR-ELEPHANT-CANDLE-001
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime

logger = logging.getLogger(__name__)


class ElephantCandleDetector:
    """
    Detector de velas elefante con validación de ubicación.
    
    Propósito: Identificar puntos de ignición para MOM_BIAS_0001
    (Ruptura de zona de compresión SMA20/SMA200).
    """
    
    def __init__(
        self,
        storage: Any,
        moving_average_sensor: Any,
        trace_id: str = None
    ):
        """
        Args:
            storage: StorageManager (SSOT para configuración)
            moving_average_sensor: Sensor para acceder a SMA20/SMA200
            trace_id: Request trace ID para auditoría
        """
        self.storage = storage
        self.moving_average_sensor = moving_average_sensor
        self.trace_id = trace_id or "ELEPHANT-CANDLE-001"
        
        # Parámetros de detección
        self._load_config()
        
        logger.info(
            f"[{self.trace_id}] ElephantCandleDetector initialized. "
            f"Min_body_pips={self.min_body_pips}, "
            f"SMA_compression_max_pips={self.sma_compression_max_pips}"
        )
    
    
    def _load_config(self) -> None:
        """Carga configuración desde DB (SSOT)."""
        try:
            params = self.storage.get_dynamic_params()
            # Parámetros de vela elefante
            self.min_body_pips = params.get('elephant_min_body_pips', 50)  # Min 50 pips de cuerpo
            self.min_body_ratio = params.get('elephant_min_body_ratio', 0.6)  # Min 60% del rango
            self.sma_compression_max_pips = params.get('mom_bias_sma_compression_pips', 15)  # Max 15 pips
            self.closure_threshold_pct = params.get('mom_bias_closure_threshold', 0.02)  # 2%
            
        except Exception as e:
            logger.warning(f"Failed to load config from storage: {e}. Using defaults.")
            self.min_body_pips = 50
            self.min_body_ratio = 0.6
            self.sma_compression_max_pips = 15
            self.closure_threshold_pct = 0.02
    
    
    def calculate_body_size(self, candle: Dict[str, float]) -> float:
        """
        Calcula tamaño del cuerpo de vela (OHLC).
        
        Body Size = |close - open|
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            Tamaño del cuerpo en pips
        """
        body = abs(candle['close'] - candle['open'])
        return body * 10000  # Convertir a pips
    
    
    def calculate_candle_range(self, candle: Dict[str, float]) -> float:
        """
        Calcula rango total de vela.
        
        Range = high - low
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            Rango en pips
        """
        return (candle['high'] - candle['low']) * 10000  # En pips
    
    
    def is_elephant_candle(
        self,
        candle: Dict[str, float]
    ) -> bool:
        """
        Valida si una vela es "Elephant" (cuerpo grande, impulso fuerte).
        
        Criterios:
        1. Cuerpo >= 50 pips
        2. Cuerpo >= 60% del rango total
        
        Args:
            candle: Dict con OHLC
            
        Returns:
            True si es elephant candle
        """
        try:
            body_pips = self.calculate_body_size(candle)
            range_pips = self.calculate_candle_range(candle)
            
            if range_pips == 0:
                return False
            
            body_ratio = body_pips / range_pips
            
            is_elephant = (
                body_pips >= self.min_body_pips and
                body_ratio >= self.min_body_ratio
            )
            
            if is_elephant:
                logger.debug(
                    f"[{self.trace_id}] Elephant candle detected. "
                    f"Body: {body_pips:.1f} pips ({body_ratio:.1%} del rango)"
                )
            
            return is_elephant
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error validating elephant candle: {e}", exc_info=True)
            return False
    
    
    def check_bullish_ignition(
        self,
        current_candle: Dict[str, float],
        sma20: float,
        sma200: float,
        previous_candles: List[Dict[str, float]] = None,
        symbol: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Valida condiciones para IGNICIÓN ALCISTA (BUY).
        
        Requisitos:
        1. Es vela elefante
        2. Cierra >= 2% por encima de SMA20
        3. SMA20 y SMA200 están en compresión (<= 15 pips)
        4. Cierre bullish (close > open)
        
        Args:
            current_candle: Dict con OHLC de vela actual
            sma20: Valor actual de SMA20
            sma200: Valor actual de SMA200
            previous_candles: Velas previas (optional)
            symbol: Símbolo para logging
            
        Returns:
            Dict con detalles si ignición válida, None si no
        """
        try:
            symbol_tag = f" [{symbol}]" if symbol else ""
            
            # Step 1: Validar que es vela elefante
            if not self.is_elephant_candle(current_candle):
                logger.debug(f"[{self.trace_id}] {symbol_tag} BULLISH: No es vela elefante")
                return None
            
            # Step 2: Validar compresión SMA20/SMA200
            compression_pips = abs(sma20 - sma200) * 10000
            if compression_pips > self.sma_compression_max_pips:
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BULLISH: Compresión insuficiente. "
                    f"Dist: {compression_pips:.1f} pips (max: {self.sma_compression_max_pips})"
                )
                return None
            
            # Step 3: Validar cierre bullish
            if current_candle['close'] <= current_candle['open']:
                logger.debug(f"[{self.trace_id}] {symbol_tag} BULLISH: Cierre no bullish")
                return None
            
            # Step 4: Validar cierre 2% arriba de SMA20
            closure_threshold_pips = sma20 * self.closure_threshold_pct * 10000
            distance_above_sma20 = (current_candle['close'] - sma20) * 10000
            
            if distance_above_sma20 < closure_threshold_pips:
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BULLISH: Cierre insuficiente. "
                    f"Dist: {distance_above_sma20:.1f} pips (min: {closure_threshold_pips:.1f})"
                )
                return None
            
            # ✅ BULLISH IGNITION VÁLIDA
            result = {
                'detected': True,
                'direction': 'BUY',
                'symbol': symbol,
                'current_price': current_candle['close'],
                'sma20': sma20,
                'sma200': sma200,
                'compression_pips': compression_pips,
                'closure_distance_pips': distance_above_sma20,
                'open_price': current_candle['open'],  # SL para MOM_BIAS_0001
                'high_price': current_candle['high'],
                'candle_body_pips': self.calculate_body_size(current_candle),
                'timestamp': current_candle.get('timestamp', datetime.now().isoformat()),
            }
            
            logger.info(
                f"[{self.trace_id}] {symbol_tag} 🚀 BULLISH IGNITION! "
                f"Price={current_candle['close']:.5f}, SL={current_candle['open']:.5f}, "
                f"Compression={compression_pips:.1f} pips"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error in check_bullish_ignition: {e}", exc_info=True)
            return None
    
    
    def check_bearish_ignition(
        self,
        current_candle: Dict[str, float],
        sma20: float,
        sma200: float,
        previous_candles: List[Dict[str, float]] = None,
        symbol: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Valida condiciones para IGNICIÓN BAJISTA (SELL).
        
        Requisitos:
        1. Es vela elefante
        2. Cierra <= 2% por debajo de SMA20
        3. SMA20 y SMA200 están en compresión (<= 15 pips)
        4. Cierre bearish (close < open)
        
        Args:
            current_candle: Dict con OHLC de vela actual
            sma20: Valor actual de SMA20
            sma200: Valor actual de SMA200
            previous_candles: Velas previas (optional)
            symbol: Símbolo para logging
            
        Returns:
            Dict con detalles si ignición válida, None si no
        """
        try:
            symbol_tag = f" [{symbol}]" if symbol else ""
            
            # Step 1: Validar que es vela elefante
            if not self.is_elephant_candle(current_candle):
                logger.debug(f"[{self.trace_id}] {symbol_tag} BEARISH: No es vela elefante")
                return None
            
            # Step 2: Validar compresión SMA20/SMA200
            compression_pips = abs(sma20 - sma200) * 10000
            if compression_pips > self.sma_compression_max_pips:
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BEARISH: Compresión insuficiente. "
                    f"Dist: {compression_pips:.1f} pips (max: {self.sma_compression_max_pips})"
                )
                return None
            
            # Step 3: Validar cierre bearish
            if current_candle['close'] >= current_candle['open']:
                logger.debug(f"[{self.trace_id}] {symbol_tag} BEARISH: Cierre no bearish")
                return None
            
            # Step 4: Validar cierre 2% abajo de SMA20
            closure_threshold_pips = sma20 * self.closure_threshold_pct * 10000
            distance_below_sma20 = (sma20 - current_candle['close']) * 10000
            
            if distance_below_sma20 < closure_threshold_pips:
                logger.debug(
                    f"[{self.trace_id}] {symbol_tag} BEARISH: Cierre insuficiente. "
                    f"Dist: {distance_below_sma20:.1f} pips (min: {closure_threshold_pips:.1f})"
                )
                return None
            
            # ✅ BEARISH IGNITION VÁLIDA
            result = {
                'detected': True,
                'direction': 'SELL',
                'symbol': symbol,
                'current_price': current_candle['close'],
                'sma20': sma20,
                'sma200': sma200,
                'compression_pips': compression_pips,
                'closure_distance_pips': distance_below_sma20,
                'open_price': current_candle['open'],  # SL para MOM_BIAS_0001
                'low_price': current_candle['low'],
                'candle_body_pips': self.calculate_body_size(current_candle),
                'timestamp': current_candle.get('timestamp', datetime.now().isoformat()),
            }
            
            logger.info(
                f"[{self.trace_id}] {symbol_tag} 📉 BEARISH IGNITION! "
                f"Price={current_candle['close']:.5f}, SL={current_candle['open']:.5f}, "
                f"Compression={compression_pips:.1f} pips"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error in check_bearish_ignition: {e}", exc_info=True)
            return None
    
    
    def validate_ignition(
        self,
        current_candle: Dict[str, float],
        sma20: float,
        sma200: float,
        previous_candles: List[Dict[str, float]] = None,
        symbol: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Valida ignición alcista O bajista (método unificado).
        
        Retorna:
        - Dict con ignición si se detecta (BULLISH o BEARISH)
        - None si no hay ignición válida
        
        Args:
            current_candle: Dict con OHLC
            sma20: Valor actual de SMA20
            sma200: Valor actual de SMA200
            previous_candles: Velas previas (optional)
            symbol: Símbolo para logging
            
        Returns:
            Dict con detalles completos de ignición o None
        """
        # Intenta bullish primero
        bullish_result = self.check_bullish_ignition(
            current_candle, sma20, sma200, previous_candles, symbol
        )
        if bullish_result:
            return bullish_result
        
        # Intenta bearish
        bearish_result = self.check_bearish_ignition(
            current_candle, sma20, sma200, previous_candles, symbol
        )
        if bearish_result:
            return bearish_result
        
        # Sin ignición válida
        return None
