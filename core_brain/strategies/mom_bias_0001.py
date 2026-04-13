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

from typing import List
from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from models.trade_result import TradeResult
from data_vault.storage import StorageManager
from core_brain.strategies.base_strategy import BaseStrategy
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
        "GBPJPY": 0.85,
        "EURUSD": 0.65,
        "GBPUSD": 0.72,
        "USDJPY": 0.60,
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

        # Snapshot DB-backed de metadata estratégica (SSOT).
        # Inicializa con constantes de clase como fallback para compatibilidad regresiva.
        # Se sobreescribe con apply_metadata_snapshot() al cargar desde factory.
        self._affinity_scores: Dict[str, float] = dict(self.AFFINITY_SCORES)
        self._market_whitelist: List[str] = []
        self._execution_params: Dict[str, Any] = {}

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
    
    
    def apply_metadata_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Inyecta snapshot DB-backed de metadata estratégica desde sys_strategies (SSOT).

        Reemplaza los valores operativos de filtro (affinity_scores, market_whitelist)
        con los persistidos en DB. analyze() usará estos valores en lugar de las
        constantes de clase hardcodeadas.

        Args:
            snapshot: Dict con claves affinity_scores, market_whitelist, execution_params.

        Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13
        """
        if snapshot.get("affinity_scores"):
            self._affinity_scores = dict(snapshot["affinity_scores"])
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
            # Step 1: Filtrar por affinity score (snapshot DB-backed; fallback a constante de clase)
            if symbol not in self._affinity_scores:
                logger.debug(
                    f"[{self.trace_id}] {symbol} no en affinity scores (snapshot). "
                    f"Skipping MOM_BIAS_0001. Razón: symbol_not_in_affinity"
                )
                return None

            affinity_score = self._resolve_affinity_score(symbol)
            
            # Validaciones de datos
            if df is None or len(df) < 20:
                logger.debug(f"[{self.trace_id}] {symbol}: Datos insuficientes")
                return None
            
            if 'close' not in df.columns or 'open' not in df.columns:
                logger.warning(f"[{self.trace_id}] {symbol}: Columnas OHLC faltantes")
                return None
            
            # Step 2: Calcular SMA20 y SMA200
            try:
                sma20_series = self.moving_average_sensor.calculate_sma(df, 20, 'close')
                sma200_series = self.moving_average_sensor.calculate_sma(df, 200, 'close')
                sma20 = float(sma20_series.iloc[-1]) if not pd.isna(sma20_series.iloc[-1]) else None
                sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None
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

    def evaluate_on_history(self, df: pd.DataFrame, params: Dict) -> List[TradeResult]:
        """
        Backtesting de MOM_BIAS_0001: ruptura de compresión SMA20/SMA200 con vela elefante.

        Condiciones de entrada:
        - SMA20 y SMA200 en compresión (|SMA20 - SMA200| < compression_ratio × precio)
        - Vela elefante: cuerpo >= min_body_ratio del rango total
        - Cierre alejado de SMA20 (breakout confirmado)
        - Dirección: LONG si close > SMA200, SHORT si close < SMA200
        SL = open de la vela, TP = entry ± sl_distance × rr
        """
        if df.empty or len(df) < 202:
            return []
        try:
            rr               = float(params.get("risk_reward", 2.0))
            min_body_ratio   = float(params.get("min_body_ratio", 0.60))
            compression_pct  = float(params.get("compression_pct", 0.015))
            away_pct         = float(params.get("away_from_sma20_pct", 0.0015))
            max_hold         = int(params.get("max_bars_hold", 50))

            close = df["close"].values
            open_ = df["open"].values
            high  = df["high"].values
            low   = df["low"].values
            sma20  = pd.Series(close).rolling(20).mean().values
            sma200 = pd.Series(close).rolling(200).mean().values

            trades: List[TradeResult] = []
            for i in range(200, len(close) - 1):
                if np.isnan(sma20[i]) or np.isnan(sma200[i]):
                    continue
                mid = (sma20[i] + sma200[i]) / 2
                if mid <= 0:
                    continue
                if abs(sma20[i] - sma200[i]) / mid > compression_pct:
                    continue  # sin compresión
                candle_range = high[i] - low[i]
                if candle_range <= 0:
                    continue
                if abs(close[i] - open_[i]) / candle_range < min_body_ratio:
                    continue  # no es vela elefante
                if abs(close[i] - sma20[i]) / close[i] < away_pct:
                    continue  # no suficientemente alejado de SMA20
                direction = 1 if close[i] > sma200[i] else -1
                sl       = open_[i]
                sl_dist  = abs(close[i] - sl)
                if sl_dist <= 0:
                    continue
                tp = close[i] + direction * sl_dist * rr
                exit_px, bars = self._exit_by_sl_tp(df, i, sl, tp, direction, max_hold)
                regime = "TREND" if direction == 1 else "RANGE"
                trades.append(TradeResult(
                    entry_price=float(close[i]),
                    exit_price=float(exit_px),
                    pnl=float(direction * (exit_px - close[i])),
                    direction=direction,
                    bars_held=bars,
                    regime_at_entry=regime,
                    sl_distance=float(sl_dist),
                    tp_distance=float(abs(tp - close[i])),
                ))
            return trades
        except Exception as exc:
            logger.warning("[MOM_BIAS_0001] evaluate_on_history error: %s", exc)
            return []
