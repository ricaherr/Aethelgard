"""
LiquiditySweep0001Strategy - Scalping de Breakout Falso

ESTRATEGIA: S-0004 (LIQUIDITY SWEEP)
TRACE_ID: STRAT-LIQ-SWEEP-0001
VERSIÓN: 1.0

Detecta breakouts falsos de Session High/Low con reversión mediante PIN BAR o ENGULFING.
Entrada al cierre de la vela de reversal, Stop Loss = High/Low de reversal + buffer.
Take Profit = 50% del rango de sesión (scalp agresivo).

Affinity Scores:
- EUR/USD: 0.92 (PRIME - Liquidez masiva en Londres)
- GBP/USD: 0.88 (Overlap Londres-NY)
- USD/JPY: 0.60 (Requiere umbral más alto, tiende tendencias)
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

import pandas as pd

from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from core_brain.strategies.base_strategy import BaseStrategy
from core_brain.sensors.session_liquidity_sensor import SessionLiquiditySensor
from core_brain.sensors.liquidity_sweep_detector import LiquiditySweepDetector
from core_brain.services.fundamental_guard import FundamentalGuardService
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class LiquiditySweep0001Strategy(BaseStrategy):
    """
    Estrategia de Scalping: Liquidity Sweep (Barrido de Liquidez).
    
    Detecta y opera breakouts falsos en niveles institucionales clave
    (Session High/Low de Londres) con validación de reversal candle.
    """
    
    STRATEGY_ID = "LIQ_SWEEP_0001"
    MNEMONIC = "LIQUIDITY_SWEEP_SCALPING"
    
    # Afinidad de activos (SSOT en DB)
    AFFINITY_SCORES = {
        "EUR/USD": 0.92,
        "GBP/USD": 0.88,
        "USD/JPY": 0.60,
        "GBP/JPY": 0.70,
        "USD/CAD": 0.65,
    }
    
    def __init__(
        self,
        storage_manager: StorageManager,
        session_liquidity_sensor: SessionLiquiditySensor,
        liquidity_sweep_detector: LiquiditySweepDetector,
        fundamental_guard: FundamentalGuardService,
        user_id: Optional[str] = None,
        config: Dict[str, Any] = None,
        trace_id: str = None
    ):
        """
        Inicializa la estrategia con inyección de dependencias.
        
        Args:
            storage_manager: Gestor de persistencia
            session_liquidity_sensor: Detector de Session High/Low
            liquidity_sweep_detector: Detector de breakout falso
            fundamental_guard: Servicio de veto por noticias
            user_id: ID del usuario/tenant para trazabilidad (multi-tenancy). Ver Dominio 01,08.
            config: Configuración adicional
            trace_id: ID único de traza
        """
        super().__init__(config or {})
        
        self.storage_manager = storage_manager
        self.session_liquidity_sensor = session_liquidity_sensor
        self.liquidity_sweep_detector = liquidity_sweep_detector
        self.fundamental_guard = fundamental_guard
        self.user_id = user_id
        self.trace_id = trace_id or f"STRAT-LIQ-SWEEP-0001-{user_id}"
        
        # Parámetros dinámicos
        self._load_parameters()
        
        logger.info(
            f"[{self.trace_id}] LiquiditySweep0001Strategy initialized for user {self.user_id}. "
            f"Max daily usr_trades: {self.max_daily_usr_trades}, "
            f"TP pips: {self.tp_pips}, SL buffer: {self.sl_buffer_pips}"
        )
    
    
    def _load_parameters(self) -> None:
        """Carga parámetros desde storage (SSOT)."""
        try:
            params = self.storage_manager.get_dynamic_params()
            self.max_daily_usr_trades = params.get('liq_sweep_max_daily_usr_trades', 3)
            self.tp_pips = params.get('liq_sweep_tp_pips', 30)
            self.sl_buffer_pips = params.get('liq_sweep_sl_buffer_pips', 2)
            self.min_affinity = params.get('liq_sweep_min_affinity', 0.75)
            self.allowed_sessions = params.get('liq_sweep_allowed_sessions', ['LONDON'])
        except Exception as e:
            logger.warning(f"[{self.trace_id}] Failed to load parameters: {e}. Using defaults.")
            self.max_daily_usr_trades = 3
            self.tp_pips = 30
            self.sl_buffer_pips = 2
            self.min_affinity = 0.75
            self.allowed_sessions = ['LONDON']
    
    
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
        Analiza datos OHLC para detectar liquidity sweep (breakout falso + reversal).
        
        Lógica:
        1. Validar símbolo en affinity scores
        2. Calcular Session High/Low de Londres
        3. Detectar breakout por encima/abajo
        4. Validar reversal candle (PIN BAR o ENGULFING)
        5. Validar que cierre está dentro del rango previo (falsa ruptura)
        6. Generar Signal con SL = reversal high/low + buffer
        
        Args:
            symbol: Símbolo del activo
            df: DataFrame con OHLC + indicadores
            regime: Régimen de mercado actual
            
        Returns:
            Signal con entrada, SL, TP, o None si no hay señal
        """
        try:
            # Step 1: Validar affinity score
            if symbol not in self.AFFINITY_SCORES:
                logger.debug(
                    f"[{self.trace_id}] {symbol} no en affinity scores. Skipping LIQ_SWEEP_0001"
                )
                return None
            
            affinity_score = self.AFFINITY_SCORES[symbol]
            if affinity_score < self.min_affinity:
                logger.debug(
                    f"[{self.trace_id}] {symbol} affinity {affinity_score:.2f} < {self.min_affinity:.2f}"
                )
                return None
            
            # Step 2: Validar datos
            if df is None or len(df) < 3:
                logger.debug(f"[{self.trace_id}] {symbol}: Datos insuficientes (< 3 velas)")
                return None
            
            if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
                logger.warning(f"[{self.trace_id}] {symbol}: Columnas OHLC faltantes")
                return None
            
            # Step 3: Consultar FundamentalGuardService
            is_market_safe, fundamental_reason = self.fundamental_guard.is_market_safe(symbol)
            if not is_market_safe:
                logger.debug(
                    f"[{self.trace_id}] {symbol}: Mercado no seguro - {fundamental_reason}"
                )
                return None
            
            # Step 4: Calcular Session High/Low de Londres
            session_result = self.session_liquidity_sensor.analyze_session_liquidity(df)
            london_high = session_result.get('london_high')
            london_low = session_result.get('london_low')
            
            if london_high is None or london_low is None:
                logger.debug(f"[{self.trace_id}] {symbol}: No hay datos de sesión Londres")
                return None
            
            # Step 5: Vela actual y previas
            current_candle = {
                'open': float(df.iloc[-1]['open']),
                'high': float(df.iloc[-1]['high']),
                'low': float(df.iloc[-1]['low']),
                'close': float(df.iloc[-1]['close']),
            }
            
            # Rango previo (vela anterior)
            prev_high = float(df.iloc[-2]['high'])
            prev_low = float(df.iloc[-2]['low'])
            
            # Step 6: Detectar breakout falso + reversal
            # Chequear ambas direcciones
            is_false_break_above, pattern_above, strength_above = self.liquidity_sweep_detector.detect_false_breakout_with_reversal(
                breakout_level=london_high,
                current_candle=current_candle,
                prev_high=prev_high,
                prev_low=prev_low,
                direction='ABOVE'
            )
            
            is_false_break_below, pattern_below, strength_below = self.liquidity_sweep_detector.detect_false_breakout_with_reversal(
                breakout_level=london_low,
                current_candle=current_candle,
                prev_high=prev_high,
                prev_low=prev_low,
                direction='BELOW'
            )
            
            # Si hay falsa ruptura y reversal
            if is_false_break_above and strength_above > 0:
                logger.info(
                    f"[{self.trace_id}] FALSE BREAKOUT ABOVE detected: {symbol}, "
                    f"Pattern: {pattern_above}, Strength: {strength_above:.2f}"
                )
                # Reversión bajista esperada
                signal = self._generate_sweep_signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    entry_price=current_candle['close'],
                    reversal_high=current_candle['high'],
                    reversal_low=current_candle['low'],
                    affinity_score=affinity_score,
                    pattern=pattern_above,
                    strength=strength_above,
                    regime=regime
                )
                return signal
            
            elif is_false_break_below and strength_below > 0:
                logger.info(
                    f"[{self.trace_id}] FALSE BREAKOUT BELOW detected: {symbol}, "
                    f"Pattern: {pattern_below}, Strength: {strength_below:.2f}"
                )
                # Reversión alcista esperada
                signal = self._generate_sweep_signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    entry_price=current_candle['close'],
                    reversal_high=current_candle['high'],
                    reversal_low=current_candle['low'],
                    affinity_score=affinity_score,
                    pattern=pattern_below,
                    strength=strength_below,
                    regime=regime
                )
                return signal
            
            # No hay breakout falso válido
            return None
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error analyzing {symbol}: {e}",
                exc_info=True
            )
            return None
    
    
    def _generate_sweep_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        entry_price: float,
        reversal_high: float,
        reversal_low: float,
        affinity_score: float,
        pattern: str,
        strength: float,
        regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Genera Signal con Stop Loss y Take Profit calculados.
        
        Args:
            symbol: Símbolo
            signal_type: BUY o SELL
            entry_price: Precio de entrada (cierre de vela)
            reversal_high: High de la vela de reversal
            reversal_low: Low de la vela de reversal
            affinity_score: Score de afinidad
            pattern: Tipo de patrón detectado
            strength: Fuerza de la reversal
            regime: Régimen de mercado
            
        Returns:
            Signal con parámetros configurados
        """
        try:
            # Stop Loss = High/Low de reversal + buffer
            if signal_type == SignalType.BUY:
                stop_loss = reversal_low - (self.sl_buffer_pips / 10000)  # Buffer en pips
                # Take Profit = entry + tp_pips
                take_profit = entry_price + (self.tp_pips / 10000)
            else:  # SELL
                stop_loss = reversal_high + (self.sl_buffer_pips / 10000)
                take_profit = entry_price - (self.tp_pips / 10000)
            
            # Calcular riesgo
            risk_pips = abs(entry_price - stop_loss) * 10000
            reward_pips = abs(take_profit - entry_price) * 10000
            rr_ratio = reward_pips / max(risk_pips, 1)
            
            # Confidence = affinity + strength boost
            confidence = min(1.0, affinity_score + (strength * 0.1))
            
            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                confidence=confidence,
                connector_type=ConnectorType.GENERIC,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),
                take_profit=round(take_profit, 5),
                volume=0.01,  # Default volume
                strategy_id=self.STRATEGY_ID,
                timestamp=datetime.now(),
                market_type="FOREX",
                metadata={
                    'regime': regime.value if regime else None,
                    'pattern': pattern,
                    'pattern_strength': strength,
                    'affinity_score': affinity_score,
                    'risk_pips': round(risk_pips, 2),
                    'reward_pips': round(reward_pips, 2),
                    'rr_ratio': round(rr_ratio, 2),
                    'liquidity_sweep_detected': True,
                }
            )
            
            logger.info(
                f"[{self.trace_id}] SIGNAL GENERATED: {symbol} {signal_type.value}, "
                f"Entry={signal.entry_price:.5f}, SL={signal.stop_loss:.5f}, "
                f"TP={signal.take_profit:.5f}, RR={rr_ratio:.1f}:1"
            )
            
            return signal
            
        except Exception as e:
            logger.error(
                f"[{self.trace_id}] Error generating sweep signal: {e}",
                exc_info=True
            )
            return None
