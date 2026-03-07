"""
MOM_BIAS_0001 Strategy - Momentum Strike with Open-Based Stop Loss
====================================================================

Estrategia de ruptura de compresión SMA20/SMA200 con vela elefante.

Características:
1. Detecta velas elefante (50+ pips, 60%+ del rango)
2. Valida ubicación: 2% arriba/abajo de SMA20
3. Requiere compresión SMA20/SMA200 <= 15 pips
4. **Stop Loss = OPEN de la vela** (regla de ORO para mayor aprovechamiento)
5. Risk/Reward: 1:2 a 1:3

Arquitectura Agnóstica: Sin imports de broker
Inyección de Dependencias: storage, elephant_candle_detector, moving_average_sensor

TRACE_ID: STRAT-MOM-BIAS-0001
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

import pandas as pd
import numpy as np

from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from data_vault.storage import StorageManager
from core_brain.usr_strategies.base_strategy import BaseStrategy
from core_brain.sensors.elephant_candle_detector import ElephantCandleDetector
from core_brain.sensors.moving_average_sensor import MovingAverageSensor

logger = logging.getLogger(__name__)


class MomentumBias0001Strategy(BaseStrategy):
    """
    Estrategia MOM_BIAS_0001: Momentum Strike.
    
    Detecta rupturas de compresión SMA20/SMA200 con velas elefante.
    Utiliza OPEN de la vela como Stop Loss para maximizar el aprovechamiento.
    """
    
    STRATEGY_ID = "MOM_BIAS_0001"
    AFFINITY_SCORES = {
        "GBP/JPY": 0.85,
        "EUR/USD": 0.65,
        "GBP/USD": 0.72,
        "USD/JPY": 0.60,
    }
    
    def __init__(
        self,
        storage_manager: StorageManager,
        elephant_candle_detector: ElephantCandleDetector,
        moving_average_sensor: MovingAverageSensor,
        config: Dict[str, Any] = None,
        trace_id: str = None
    ):
        """
        Inicializa la estrategia MOM_BIAS_0001 con inyección de dependencias.
        
        Args:
            storage_manager: Gestor de persistencia
            elephant_candle_detector: Detector de velas elefante
            moving_average_sensor: Sensor de medias móviles
            config: Configuración adicional (opcional)
            trace_id: ID de traza para auditoría
        """
        super().__init__(config or {})
        
        self.storage_manager = storage_manager
        self.elephant_candle_detector = elephant_candle_detector
        self.moving_average_sensor = moving_average_sensor
        self.trace_id = trace_id or "STRAT-MOM-BIAS-0001"
        
        # Cargar parámetros dinámicos
        self._load_parameters()
        
        logger.info(
            f"[{self.trace_id}] MomentumBias0001Strategy initialized. "
            f"Min SL pips: {self.min_sl_pips}, Risk/Reward ratio: {self.risk_reward_ratio}"
        )
    
    
    def _load_parameters(self) -> None:
        """Carga parámetros desde storage (SSOT)."""
        try:
            params = self.storage_manager.get_dynamic_params()
            self.min_sl_pips = params.get('elephant_min_body_pips', 50)
            self.risk_reward_ratio = params.get('mom_bias_rr_ratio', 2.0)  # 1:2
            self.enabled_symbols = params.get('mom_bias_enabled_symbols', list(self.AFFINITY_SCORES.keys()))
        except Exception as e:
            logger.warning(f"[{self.trace_id}] Failed to load parameters: {e}. Using defaults.")
            self.min_sl_pips = 50
            self.risk_reward_ratio = 2.0
            self.enabled_symbols = list(self.AFFINITY_SCORES.keys())
    
    
    @property
    def strategy_id(self) -> str:
        """Retorna el identificador único de la estrategia."""
        return self.STRATEGY_ID
    
    
    async def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Analiza datos OHLC para detectar momentum strike al OPEN.
        
        Lógica:
        1. Filtrar por affinity score (si no está configurado, retornar None)
        2. Calcular SMA20 y SMA200
        3. Chequear compresión SMA20/SMA200
        4. Validar vela actual: ¿Es elephant? ¿Cierra 2% lejos de SMA20?
        5. Generar Signal con stop_loss = OPEN de la vela
        
        Args:
            symbol: Símbolo del activo
            df: DataFrame con OHLC + indicadores
            regime: Régimen de mercado actual
            
        Returns:
            Signal con stop_loss = OPEN, o None si no hay señal
        """
        try:
            # Step 1: Filtrar por símbolo habilitado (affinity score)
            if symbol not in self.AFFINITY_SCORES:
                logger.debug(
                    f"[{self.trace_id}] {symbol} no en affinity scores. Skipping MOM_BIAS_0001"
                )
                return None
            
            affinity_score = self.AFFINITY_SCORES[symbol]
            
            # Validaciones de datos
            if df is None or len(df) < 20:
                logger.debug(f"[{self.trace_id}] {symbol}: Datos insuficientes")
                return None
            
            if 'close' not in df.columns or 'open' not in df.columns:
                logger.warning(f"[{self.trace_id}] {symbol}: Columnas OHLC faltantes")
                return None
            
            # Step 2: Calcular SMA20 y SMA200
            try:
                sma20 = self.moving_average_sensor.get_sma(
                    df, period=20, source='close', trace_id=self.trace_id
                )
                sma200 = self.moving_average_sensor.get_sma(
                    df, period=200, source='close', trace_id=self.trace_id
                )
            except Exception as sma_err:
                logger.warning(f"[{self.trace_id}] {symbol}: Error calculando SMAs: {sma_err}")
                return None
            
            if sma20 is None or sma200 is None:
                logger.debug(f"[{self.trace_id}] {symbol}: SMAs no disponibles")
                return None
            
            # Step 3: Obtener vela actual y previas
            current_candle = {
                'open': float(df.iloc[-1]['open']),
                'high': float(df.iloc[-1]['high']),
                'low': float(df.iloc[-1]['low']),
                'close': float(df.iloc[-1]['close']),
                'volume': float(df.iloc[-1].get('volume', 0)),
                'timestamp': df.index[-1].isoformat() if hasattr(df.index[-1], 'isoformat') else str(df.index[-1]),
            }
            
            # Velas previas para contexto
            previous_candles = []
            if len(df) >= 6:
                for i in range(1, min(6, len(df))):
                    prev = {
                        'open': float(df.iloc[-(i+1)]['open']),
                        'high': float(df.iloc[-(i+1)]['high']),
                        'low': float(df.iloc[-(i+1)]['low']),
                        'close': float(df.iloc[-(i+1)]['close']),
                        'volume': float(df.iloc[-(i+1)].get('volume', 0)),
                    }
                    previous_candles.append(prev)
            
            # Step 4: Validar ignición (bullish o bearish)
            ignition_result = self.elephant_candle_detector.validate_ignition(
                current_candle=current_candle,
                sma20=sma20,
                sma200=sma200,
                previous_candles=previous_candles,
                symbol=symbol
            )
            
            if not ignition_result:
                logger.debug(f"[{self.trace_id}] {symbol}: No hay ignición de momentum válida")
                return None
            
            # Step 5: Generar Signal con SL = OPEN (regla de ORO MOM_BIAS_0001)
            signal = self._generate_momentum_signal(
                symbol=symbol,
                ignition_result=ignition_result,
                affinity_score=affinity_score,
                regime=regime
            )
            
            if signal:
                logger.info(
                    f"[{self.trace_id}] ✅ SIGNAL GENERATED: {symbol} {signal.signal_type.value}, "
                    f"Entry={signal.entry_price:.5f}, SL={signal.stop_loss:.5f}, "
                    f"Affinity={affinity_score:.2f}"
                )
            
            return signal
        
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error analyzing {symbol}: {e}",
                exc_info=True
            )
            return None
    
    
    def _generate_momentum_signal(
        self,
        symbol: str,
        ignition_result: Dict[str, Any],
        affinity_score: float,
        regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Genera Signal con stop_loss = OPEN de la vela de ignición.
        
        Args:
            symbol: Símbolo del activo
            ignition_result: Resultado de validate_ignition()
            affinity_score: Score de afinidad (0-1)
            regime: Régimen de mercado
            
        Returns:
            Signal configurada con regla MOM_BIAS_0001
        """
        try:
            direction = ignition_result['direction']  # 'BUY' o 'SELL'
            entry_price = ignition_result['current_price']
            stop_loss = ignition_result['open_price']  # 🎯 REGLA DE ORO: SL = OPEN
            
            # Calcular Risk/Reward
            risk_pips = abs(entry_price - stop_loss) * 10000
            reward_pips = risk_pips * self.risk_reward_ratio
            
            if direction == 'BUY':
                take_profit = entry_price + (reward_pips / 10000)
            else:  # SELL
                take_profit = entry_price - (reward_pips / 10000)
            
            # Crear Signal
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY if direction == 'BUY' else SignalType.SELL,
                confidence=affinity_score,  # Usar affinity como confidence
                connector_type=ConnectorType.GENERIC,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),  # 🎯 OPEN de la vela
                take_profit=round(take_profit, 5),
                volume=0.01,  # Default trading volume
                strategy_id=self.STRATEGY_ID,
                timestamp=datetime.now(),
                market_type="FOREX",
                metadata={
                    'regime': regime.value if regime else None,
                    'sma20': ignition_result['sma20'],
                    'sma200': ignition_result['sma200'],
                    'compression_pips': ignition_result['compression_pips'],
                    'candle_body_pips': ignition_result['candle_body_pips'],
                    'risk_pips': round(risk_pips, 2),
                    'reward_pips': round(reward_pips, 2),
                    'rr_ratio': self.risk_reward_ratio,
                    'affinity_score': affinity_score,
                    'momentum_strike_detected': True,
                }
            )
            
            return signal
        
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error generating momentum signal: {e}",
                exc_info=True
            )
            return None
