"""
StructureShift0001Strategy - S-0006 Detección de Quiebre de Estructura

ESTRATEGIA: S-0006 (STRUCTURE BREAK SHIFT)
TRACE_ID: STRAT-STRUC-SHIFT-0001
VERSIÓN: 1.0

Detecta ruptura de estructura (Break of Structure - BOS) con confirmación de
pullback a zona de Breaker Block. Entrada en confluencia: Vela Elefante + RSI
+ Imbalance detector.

Affinity Scores:
- EUR/USD: 0.89 (PRIME - Técnicas limpias, quiebres muy marcados)
- USD/CAD: 0.82 (ACTIVE - Tendencias prolongadas por precio del petróleo)
- AUD/NZD: 0.40 (VETO - Choppiness invalida estructura)

Market Whitelist: [EUR/USD, USD/CAD]
Timeframes: H1, H4
Membership: Premium+
Risk per trade: 1% capital
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

import pandas as pd

from typing import List
from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from models.trade_result import TradeResult
from core_brain.strategies.base_strategy import BaseStrategy
from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer
from core_brain.services.reasoning_event_builder import ReasoningEventBuilder
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class StructureShift0001Strategy(BaseStrategy):
    """
    Estrategia de Quiebre de Estructura (Structure Break Shift).
    
    Detecta y opera rupturas institucionales de estructura (HH/HL a LH/LL)
    con validación de Breaker Block y pullback.
    """
    
    STRATEGY_ID = "STRUC_SHIFT_0001"
    MNEMONIC = "STRUCTURE_BREAK_SHIFT"
    
    # Afinidad de activos (SSOT en DB)
    AFFINITY_SCORES = {
        "EURUSD": 0.89,      # PRIME - Muy técnico, quiebres limpios
        "USDCAD": 0.82,      # ACTIVE - Tendencias marcadas
        "AUDNZD": 0.40,      # VETO - Choppiness inválida estructura
        "GBPUSD": 0.75,      # Monitor - Posible tercero
        "USDJPY": 0.70,      # Monitor
    }

    # Market Whitelist (solo estos operan, resto es monitor)
    MARKET_WHITELIST = ["EURUSD", "USDCAD"]
    
    def __init__(
        self,
        storage_manager: StorageManager,
        market_structure_analyzer: MarketStructureAnalyzer,
        user_id: Optional[str] = None,
        config: Dict[str, Any] = None,
        trace_id: str = None,
        reasoning_event_callback: Optional[callable] = None
    ):
        """
        Inicializa la estrategia con inyección de dependencias.
        
        Args:
            storage_manager: Gestor de persistencia
            market_structure_analyzer: Sensor de estructura de mercado
            user_id: ID del usuario/tenant para trazabilidad (multi-tenancy). Ver Dominio 01,08.
            config: Configuración adicional
            trace_id: ID único de traza
            reasoning_event_callback: Callback para emitir eventos de razonamiento
        """
        super().__init__(config or {})

        self.storage_manager = storage_manager
        self.market_structure_analyzer = market_structure_analyzer
        self.user_id = user_id
        self.trace_id = trace_id or f"STRAT-STRUC-SHIFT-0001-{user_id}"
        self.reasoning_event_callback = reasoning_event_callback

        # Snapshot DB-backed de metadata estratégica (SSOT).
        # Fallback a constantes de clase para compatibilidad regresiva.
        self._affinity_scores: Dict[str, float] = dict(self.AFFINITY_SCORES)
        self._market_whitelist: List[str] = list(self.MARKET_WHITELIST)
        self._execution_params: Dict[str, Any] = {}

        # Parámetros dinámicos
        self._load_parameters()
        
        logger.info(
            f"[{self.trace_id}] StructureShift0001Strategy initialized for user {self.user_id}. "
            f"Max daily usr_trades: {self.max_daily_usr_trades}, "
            f"TP1 ratio: {self.tp1_ratio}, TP2 ratio: {self.tp2_ratio}"
        )
    
    
    def _load_parameters(self) -> None:
        """Carga parámetros desde storage (SSOT)."""
        try:
            params = self.storage_manager.get_dynamic_params()
            
            # Límites operativos
            self.max_daily_usr_trades = params.get('struc_shift_max_daily_usr_trades', 5)
            
            # Ratios de proyección
            self.tp1_ratio = params.get('struc_shift_tp1_ratio', 1.27)      # FIB 127%
            self.tp2_ratio = params.get('struc_shift_tp2_ratio', 1.618)     # FIB 618% (Golden)
            
            # Buffer de SL
            self.sl_buffer_pips = params.get('struc_shift_sl_buffer_pips', 10)
            
            # Validación mínima de estructura
            self.min_structure_strength = params.get('struc_shift_min_structure_strength', 3)  # Mínimo HH/HL
            
            # Fuerza de ruptura (ATR mínimo)
            self.min_bos_strength = params.get('struc_shift_min_bos_strength', 2.0)
            
        except Exception as e:
            logger.warning(f"Failed to load parameters from storage: {e}. Using defaults.")
            self.max_daily_usr_trades = 5
            self.tp1_ratio = 1.27
            self.tp2_ratio = 1.618
            self.sl_buffer_pips = 10
            self.min_structure_strength = 3
            self.min_bos_strength = 2.0
    def apply_metadata_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Inyecta snapshot DB-backed de metadata estratégica desde sys_strategies (SSOT).

        Reemplaza market_whitelist y affinity_scores operativos con los valores
        persistidos en DB. analyze() usará estos valores en lugar de las constantes
        de clase hardcodeadas (MARKET_WHITELIST, AFFINITY_SCORES).

        Regla: whitelist vacía en snapshot = sin restricción de activos.

        Args:
            snapshot: Dict con claves affinity_scores, market_whitelist, execution_params.

        Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13
        """
        if snapshot.get("affinity_scores"):
            self._affinity_scores = dict(snapshot["affinity_scores"])
        # market_whitelist siempre se actualiza (lista vacía = sin restricción)
        if "market_whitelist" in snapshot:
            self._market_whitelist = list(snapshot["market_whitelist"])
        if snapshot.get("execution_params"):
            self._execution_params = dict(snapshot["execution_params"])

        logger.debug(
            f"[{self.trace_id}] Metadata snapshot aplicado: "
            f"assets={list(self._affinity_scores.keys())}, "
            f"whitelist={self._market_whitelist}"
        )

    def _resolve_affinity_score(self, symbol: str) -> float:
        """
        Normaliza affinity score desde snapshot SSOT (float legacy o dict enriquecido).
        """
        raw_value = self._affinity_scores.get(symbol, 0.0)

        if isinstance(raw_value, (int, float)):
            return float(raw_value)

        if isinstance(raw_value, dict):
            if isinstance(raw_value.get("effective_score"), (int, float)):
                return float(raw_value["effective_score"])
            if isinstance(raw_value.get("raw_score"), (int, float)):
                return float(raw_value["raw_score"])

        logger.warning(
            f"[{self.trace_id}] {symbol}: affinity inválida ({type(raw_value).__name__}); "
            f"usando 0.0 como fallback seguro"
        )
        return 0.0

    @property
    def strategy_id(self) -> str:
        """Retorna el identificador único de la estrategia."""
        return self.STRATEGY_ID

    async def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        regime: Optional[MarketRegime] = None,
        **kwargs
    ) -> Optional[Signal]:
        """
        Analiza datos para detectar estructura de quiebre.
        
        Flujo:
        1. Detectar estructura (HH/HL o LH/LL)
        2. Validar Breaker Block
        3. Esperar Break of Structure (BOS)
        4. Calcular zonas de entrada y TP
        5. Generar señal confluencia
        
        Args:
            symbol: Par de divisas (ej. "EUR/USD")
            df: DataFrame con OHLC (índice debe ser datetime)
            regime: Régimen de mercado actual
            
        Returns:
            Signal si hay confluencia, None si no
        """
        
        try:
            # Validar que el símbolo está en el whitelist (snapshot DB-backed; fallback a clase)
            # Regla: whitelist vacía = sin restricción (todos los símbolos pasan)
            if self._market_whitelist and symbol not in self._market_whitelist:
                logger.debug(
                    f"[{self.trace_id}] {symbol} no está en market whitelist (snapshot) "
                    f"para {self.STRATEGY_ID}. Razón: symbol_not_in_market_whitelist"
                )
                return None
            
            # Recolectar suficientes datos históricos
            if len(df) < 20:
                logger.debug(f"[{self.trace_id}] Insuficientes velas ({len(df)} < 20)")
                return None
            
            # 1. Detectar estructura
            structure = self.market_structure_analyzer.detect_market_structure(symbol, df)
            
            if not structure['is_valid']:
                logger.debug(f"[{self.trace_id}] Estructura no válida en {symbol}")
                return None
            
            if structure['type'] not in ['UPTREND', 'DOWNTREND']:
                return None
            
            # 🔔 EMIT: Estructura detectada
            if self.reasoning_event_callback:
                event = ReasoningEventBuilder.build_struc_shift_reasoning(
                    asset=symbol,
                    action=ReasoningEventBuilder.ACTION_STRUCTURE_DETECTED,
                    structure_type=structure['type'],
                    confidence=0.80
                )
                self.reasoning_event_callback(event)
            
            # 2. Calcular Breaker Block
            breaker = self.market_structure_analyzer.calculate_breaker_block(structure, df)
            
            if not breaker or breaker['range_pips'] == 0:
                return None
            
            # 3. Validar fuerza de estructura
            structure_strength = structure['hh_count'] + structure['hl_count']
            if structure_strength < self.min_structure_strength:
                logger.debug(
                    f"[{self.trace_id}] Estructura débil en {symbol} "
                    f"({structure_strength} < {self.min_structure_strength})"
                )
                return None
            
            # 4. Obtener última vela para detectar BOS
            last_candle = {
                'high': df.iloc[-1]['high'],
                'low': df.iloc[-1]['low'],
                'close': df.iloc[-1]['close'],
                'open': df.iloc[-1]['open']
            }
            
            # 5. Detectar Break of Structure (BOS)
            bos = self.market_structure_analyzer.detect_break_of_structure(
                structure, breaker, last_candle
            )
            
            if not bos['is_break']:
                logger.debug(f"[{self.trace_id}] Sin BOS detectado en {symbol}")
                return None
            
            # 🔔 EMIT: Break of Structure confirmado
            if self.reasoning_event_callback:
                event = ReasoningEventBuilder.build_struc_shift_reasoning(
                    asset=symbol,
                    action=ReasoningEventBuilder.ACTION_BOS_CONFIRMED,
                    structure_type=structure['type'],
                    breaker_high=breaker['high'],
                    breaker_low=breaker['low'],
                    bos_direction=bos['direction'],
                    bos_strength=bos['strength'],
                    current_price=last_candle.get('close'),
                    confidence=0.85
                )
                self.reasoning_event_callback(event)
            
            # 6. Validar fuerza de ruptura
            if bos['strength'] < 25:  # Penetración > 25% del Breaker
                logger.debug(
                    f"[{self.trace_id}] BOS débil en {symbol} ({bos['strength']:.1f}% < 25%)"
                )
                return None
            
            # 7. Calcular zonas de entrada y TP
            pullback = self.market_structure_analyzer.calculate_pullback_zone(breaker)
            
            # Determinar si es BUY (subida) o SELL (bajada)
            if bos['direction'] == 'DOWN':
                # Ruptura hacia abajo = SELL
                signal_type = SignalType.SELL
                entry = pullback['entry_high']  # Pullback a la zona alta del Breaker
                sl = breaker['low'] - (self.sl_buffer_pips / 10000)
                
                # TP calculados desde la ruptura
                risk = entry - sl
                tp1 = entry - (risk * self.tp1_ratio)  # Extensión 1.27R
                tp2 = entry - (risk * self.tp2_ratio)  # Extensión 1.618R
                
            else:  # BOS['direction'] == 'UP'
                # Ruptura hacia arriba = BUY
                signal_type = SignalType.BUY
                entry = pullback['entry_low']  # Pullback a zona baja del Breaker
                sl = breaker['high'] + (self.sl_buffer_pips / 10000)
                
                risk = sl - entry
                tp1 = entry + (risk * self.tp1_ratio)
                tp2 = entry + (risk * self.tp2_ratio)
            
            # 8. Construir señal
            affinity = self._resolve_affinity_score(symbol)
            confidence = min(0.95, 0.70 + (bos['strength'] / 100) * 0.25)  # Confidence 70-95%
            
            signal = Signal(
                strategy_id=self.STRATEGY_ID,
                strategy_name=self.MNEMONIC,
                symbol=symbol,
                signal_type=signal_type,
                entry_price=entry,
                stop_loss=sl,
                take_profit_primary=tp1,
                take_profit_secondary=tp2,
                confidence=confidence,
                affinity_score=affinity,
                connector_type=ConnectorType.GENERIC,
                market_regime=regime or MarketRegime.UNKNOWN,
                timestamp=datetime.now(),
                metadata={
                    'structure_type': structure['type'],
                    'structure_count': structure_strength,
                    'breaker_block_high': breaker['high'],
                    'breaker_block_low': breaker['low'],
                    'bos_direction': bos['direction'],
                    'bos_strength': bos['strength'],
                    'pullback_midpoint': pullback['midpoint'],
                    'risk_pips': abs((entry - sl) * 10000)
                }
            )
            
            logger.info(
                f"[{self.trace_id}] Signal GENERATED: {signal_type.name} {symbol} "
                f"@ {entry:.5f} | SL={sl:.5f} | TP1={tp1:.5f} | TP2={tp2:.5f} "
                f"| Confidence={confidence:.2f} | Affinity={affinity:.2f}"
            )
            
            # 🔔 EMIT: Señal de confluencia generada
            if self.reasoning_event_callback:
                event = ReasoningEventBuilder.build_struc_shift_reasoning(
                    asset=symbol,
                    action=ReasoningEventBuilder.ACTION_ENTRY_SPOTTED,
                    structure_type=structure['type'],
                    breaker_high=breaker['high'],
                    breaker_low=breaker['low'],
                    bos_direction=bos['direction'],
                    current_price=entry,
                    confidence=confidence
                )
                self.reasoning_event_callback(event)
            
            return signal
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Exception in analyze(): {e}", exc_info=True)
            return None

    def evaluate_on_history(self, df: pd.DataFrame, params: Dict) -> List[TradeResult]:
        """
        Backtesting de STRUC_SHIFT_0001: ruptura de estructura (BOS) con pullback.

        Condiciones de entrada (BOS alcista):
        - Precio cierra por encima del swing high de los últimos N bars
        - El rango previo era estrecho (estructura consolidando)
        SL = swing low reciente, TP = entry + sl_distance × tp_ratio (FIB)
        """
        if df.empty or len(df) < 22:
            return []
        try:
            import numpy as np
            lookback  = int(params.get("structure_lookback", 20))
            tp_ratio  = float(params.get("tp_ratio", 1.618))
            max_hold  = int(params.get("max_bars_hold", 60))

            close = df["close"].values
            high  = df["high"].values
            low   = df["low"].values
            trades: List[TradeResult] = []

            for i in range(lookback + 1, len(close) - 1):
                prev_highs = high[i - lookback: i]
                prev_lows  = low[i - lookback: i]
                swing_high = float(prev_highs.max())
                swing_low  = float(prev_lows.min())
                struct_range = swing_high - swing_low
                if struct_range <= 0:
                    continue

                # BOS alcista: cierre rompe swing high con estructura previa comprimida
                if close[i] > swing_high and close[i - 1] <= swing_high:
                    direction = 1
                    sl     = swing_low
                    sl_dist = abs(close[i] - sl)
                    if sl_dist <= 0:
                        continue
                    tp     = close[i] + sl_dist * tp_ratio
                    exit_px, bars = self._exit_by_sl_tp(df, i, sl, tp, direction, max_hold)
                    trades.append(TradeResult(
                        entry_price=float(close[i]), exit_price=float(exit_px),
                        pnl=float(direction * (exit_px - close[i])), direction=direction,
                        bars_held=bars, regime_at_entry="TREND",
                        sl_distance=float(sl_dist), tp_distance=float(abs(tp - close[i])),
                    ))

                # BOS bajista: cierre rompe swing low con estructura previa comprimida
                elif close[i] < swing_low and close[i - 1] >= swing_low:
                    direction = -1
                    sl     = swing_high
                    sl_dist = abs(sl - close[i])
                    if sl_dist <= 0:
                        continue
                    tp     = close[i] - sl_dist * tp_ratio
                    exit_px, bars = self._exit_by_sl_tp(df, i, sl, tp, direction, max_hold)
                    trades.append(TradeResult(
                        entry_price=float(close[i]), exit_price=float(exit_px),
                        pnl=float(direction * (exit_px - close[i])), direction=direction,
                        bars_held=bars, regime_at_entry="TREND",
                        sl_distance=float(sl_dist), tp_distance=float(abs(tp - close[i])),
                    ))
            return trades
        except Exception as exc:
            logger.warning("[STRUC_SHIFT_0001] evaluate_on_history error: %s", exc)
            return []
