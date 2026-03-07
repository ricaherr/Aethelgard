"""
Signal Converter - Conversión de StrategySignal a Signal
=========================================================

Responsabilidad única: Convertir resultados de estrategias (StrategySignal)
a objetos Signal normalizados para persistencia y ejecución.

Soporta dos tipos de engines:
1. JSON_SCHEMA usr_strategies (UniversalStrategyEngine.execute_from_registry)
2. PYTHON_CLASS usr_strategies (.analyze method)
"""
import logging
from typing import Optional, Any
from datetime import datetime

import pandas as pd

from models.signal import Signal, SignalType, ConnectorType

logger = logging.getLogger(__name__)


class StrategySignalConverter:
    """
    Convierte StrategySignal (output de UniversalStrategyEngine) a Signal (modelo canónico).
    
    Responsabilidades:
    1. Validar estructura de StrategySignal
    2. Mapear fields StrategySignal → Signal
    3. Manejar tipos de datos (strings vs enums)
    4. Registrar errores de compatibilidad
    """
    
    @staticmethod
    def convert_from_universal_engine(
        result: Any,
        symbol: str,
        strategy_id: str,
        timeframe: Optional[str] = None,
        trace_id: Optional[str] = None,
        provider_source: Optional[str] = None
    ) -> Optional[Signal]:
        """
        Convierte resultado de UniversalStrategyEngine.execute_from_registry() a Signal.
        
        Args:
            result: StrategySignal object con fields: signal, confidence, ...
            symbol: Símbolo del activo
            strategy_id: ID de la estrategia (para trazabilidad)
            timeframe: Timeframe (ej: "M5")
            trace_id: ID de trazabilidad único
            provider_source: Fuente de datos (ej: "UniversalStrategyEngine")
        
        Returns:
            Signal object o None si result no es válido
        
        Raises:
            Exception: Log de error, no re-lanza
        """
        try:
            if not result or not result.signal:
                return None
            
            # Convertir signal string ("BUY"/"SELL") a enum SignalType
            signal_type_enum = SignalType.BUY if result.signal == "BUY" else SignalType.SELL
            
            # Crear Signal con campos mínimos requeridos
            signal = Signal(
                symbol=symbol,
                signal_type=signal_type_enum,
                confidence=float(result.confidence) if hasattr(result, 'confidence') else 0.5,
                connector_type=ConnectorType.GENERIC,
                strategy_id=strategy_id,
                timeframe=timeframe or "M5",
                trace_id=trace_id,
                provider_source=provider_source or "UniversalStrategyEngine",
                timestamp=datetime.utcnow()
            )
            
            # Copiar campos opcionales si existen
            if hasattr(result, 'entry_price'):
                signal.entry_price = float(result.entry_price)
            if hasattr(result, 'stop_loss'):
                signal.stop_loss = float(result.stop_loss)
            if hasattr(result, 'take_profit'):
                signal.take_profit = float(result.take_profit)
            if hasattr(result, 'volume'):
                signal.volume = float(result.volume)
            
            logger.debug(
                f"[{symbol}] Converted StrategySignal from {strategy_id}: "
                f"{signal_type_enum} @ confidence={signal.confidence:.2f}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(
                f"[{symbol}] DataIncompatibilityError converting StrategySignal from {strategy_id}: {e}",
                exc_info=True
            )
            return None
    
    @staticmethod
    def convert_from_python_class(
        signal: Optional[Signal],
        symbol: str,
        strategy_id: str,
        timeframe: Optional[str] = None,
        trace_id: Optional[str] = None,
        provider_source: Optional[str] = None
    ) -> Optional[Signal]:
        """
        Procesa Signal directamente de estrategias PYTHON_CLASS (.analyze method).
        
        Las estrategias Python ya retornan Signal objects, solo se enriquecen metadatos.
        
        Args:
            signal: Signal object directo de strategy.analyze()
            symbol: Símbolo del activo
            strategy_id: ID de la estrategia
            timeframe: Timeframe (puede sobrescribir el del signal)
            trace_id: ID de trazabilidad
            provider_source: Fuente de datos
        
        Returns:
            Signal enriquecida o None si signal es None
        """
        if not signal:
            return None
        
        try:
            # Enriquecer metadatos si se proporciona información adicional
            if timeframe:
                signal.timeframe = timeframe
            if trace_id:
                signal.trace_id = trace_id
            if provider_source:
                signal.provider_source = provider_source
            
            # Asegurar que strategy_id está registrado
            if not signal.metadata.get("strategy_id"):
                signal.metadata["strategy_id"] = strategy_id
            
            logger.debug(
                f"[{symbol}] Processed PYTHON_CLASS signal from {strategy_id}: "
                f"{signal.signal_type} @ confidence={signal.confidence:.2f}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(
                f"[{symbol}] Error processing PYTHON_CLASS signal from {strategy_id}: {e}",
                exc_info=True
            )
            return None
