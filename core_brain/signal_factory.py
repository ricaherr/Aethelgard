"""
Signal Factory - Motor de Generación de Señales
Genera señales basadas en la estrategia de Oliver Vélez con sistema de scoring.

Estrategia Oliver Vélez (Swing Trading):
- Operar en tendencia (TREND es el mejor régimen)
- Buscar velas de momentum alto (Velas Elefante)
- Confirmar con volumen superior al promedio
- Entrar en zonas de soporte/resistencia (SMA 20 como referencia)
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from models.signal import (
    Signal, SignalType, ConnectorType, MarketRegime, 
    MembershipTier
)

logger = logging.getLogger(__name__)


class SignalFactory:
    """
    Motor que genera señales de trading basadas en análisis técnico
    y la estrategia de Oliver Vélez para swing trading.
    """
    
    def __init__(
        self,
        connector_type: ConnectorType = ConnectorType.METATRADER5,
        strategy_id: str = "oliver_velez_swing",
        # Parámetros de scoring
        score_regime_trend: float = 30.0,
        score_elephant_candle: float = 20.0,
        score_volume_high: float = 20.0,
        score_near_sma20: float = 30.0,
        # Umbral para membresía premium
        premium_threshold: float = 80.0,
        elite_threshold: float = 90.0,
        # Parámetros técnicos
        elephant_candle_threshold: float = 2.0,  # ATR multiplicador
        sma20_proximity_pct: float = 1.0,  # % de proximidad a SMA 20
        volume_avg_period: int = 20,
        sma_period: int = 20,
    ):
        """
        Args:
            connector_type: Tipo de conector (MT5, NT, TV)
            strategy_id: ID de la estrategia
            score_regime_trend: Puntos si régimen es TREND
            score_elephant_candle: Puntos si es vela elefante
            score_volume_high: Puntos si volumen > promedio
            score_near_sma20: Puntos si precio cerca de SMA 20
            premium_threshold: Score mínimo para membresía PREMIUM
            elite_threshold: Score mínimo para membresía ELITE
            elephant_candle_threshold: Multiplicador ATR para vela elefante
            sma20_proximity_pct: % de proximidad a SMA 20 para score
            volume_avg_period: Período para promedio de volumen
            sma_period: Período para SMA de referencia
        """
        self.connector_type = connector_type
        self.strategy_id = strategy_id
        
        # Scoring weights
        self.score_regime_trend = score_regime_trend
        self.score_elephant_candle = score_elephant_candle
        self.score_volume_high = score_volume_high
        self.score_near_sma20 = score_near_sma20
        
        # Membership thresholds
        self.premium_threshold = premium_threshold
        self.elite_threshold = elite_threshold
        
        # Technical parameters
        self.elephant_threshold = elephant_candle_threshold
        self.sma20_proximity_pct = sma20_proximity_pct
        self.volume_avg_period = volume_avg_period
        self.sma_period = sma_period
        
        logger.info(
            f"SignalFactory inicializado: {strategy_id}, "
            f"Premium threshold: {premium_threshold}, "
            f"Elite threshold: {elite_threshold}"
        )
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calcula Average True Range (ATR) para medir volatilidad.
        
        Args:
            df: DataFrame con columnas 'high', 'low', 'close'
            period: Período para ATR
        
        Returns:
            Series con valores de ATR
        """
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        
        ranges = pd.DataFrame({
            'hl': high_low,
            'hc': high_close,
            'lc': low_close
        })
        
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    def _is_elephant_candle(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, float]:
        """
        Determina si una vela es "Vela Elefante" (alto momentum).
        Criterio: Rango (high - low) > ATR * threshold
        
        Args:
            df: DataFrame con OHLC
            index: Índice de la vela a evaluar (-1 = última)
        
        Returns:
            Tupla (es_elefante, ratio_vs_atr)
        """
        if len(df) < 20:
            return False, 0.0
        
        atr = self._calculate_atr(df)
        
        if atr.isna().all():
            return False, 0.0
        
        # Rango de la vela actual
        candle_range = df['high'].iloc[index] - df['low'].iloc[index]
        current_atr = atr.iloc[index]
        
        if pd.isna(current_atr) or current_atr == 0:
            return False, 0.0
        
        ratio = candle_range / current_atr
        is_elephant = ratio >= self.elephant_threshold
        
        return is_elephant, ratio
    
    def _is_volume_above_average(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, float]:
        """
        Verifica si el volumen está por encima del promedio.
        
        Args:
            df: DataFrame con columna 'tick_volume' o 'volume'
            index: Índice de la vela a evaluar
        
        Returns:
            Tupla (volumen_alto, ratio_vs_promedio)
        """
        # Intentar con 'tick_volume' primero (MT5), luego 'volume'
        vol_col = 'tick_volume' if 'tick_volume' in df.columns else 'volume'
        
        if vol_col not in df.columns or len(df) < self.volume_avg_period:
            return False, 0.0
        
        current_vol = df[vol_col].iloc[index]
        avg_vol = df[vol_col].iloc[index - self.volume_avg_period:index].mean()
        
        if pd.isna(avg_vol) or avg_vol == 0:
            return False, 0.0
        
        ratio = current_vol / avg_vol
        is_high = ratio > 1.0
        
        return is_high, ratio
    
    def _is_near_sma20(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, float]:
        """
        Verifica si el precio está cerca de la SMA 20 (zona de rebote).
        
        Args:
            df: DataFrame con columna 'close'
            index: Índice de la vela a evaluar
        
        Returns:
            Tupla (cerca_sma, distancia_pct)
        """
        if len(df) < self.sma_period:
            return False, 0.0
        
        sma = df['close'].rolling(window=self.sma_period).mean()
        
        if sma.isna().all():
            return False, 0.0
        
        current_price = df['close'].iloc[index]
        current_sma = sma.iloc[index]
        
        if pd.isna(current_sma) or current_sma == 0:
            return False, 0.0
        
        distance_pct = abs((current_price - current_sma) / current_sma) * 100
        is_near = distance_pct <= self.sma20_proximity_pct
        
        return is_near, distance_pct
    
    def _calculate_score(
        self,
        regime: MarketRegime,
        is_elephant: bool,
        volume_high: bool,
        near_sma: bool
    ) -> float:
        """
        Calcula el score de oportunidad (0-100) basado en criterios.
        
        Sistema de Scoring:
        - +30 si régimen es TREND
        - +20 si es vela elefante
        - +20 si volumen > promedio
        - +30 si está cerca de SMA 20
        
        Args:
            regime: Régimen de mercado
            is_elephant: Es vela elefante
            volume_high: Volumen alto
            near_sma: Cerca de SMA 20
        
        Returns:
            Score de 0 a 100
        """
        score = 0.0
        
        if regime == MarketRegime.TREND:
            score += self.score_regime_trend
        
        if is_elephant:
            score += self.score_elephant_candle
        
        if volume_high:
            score += self.score_volume_high
        
        if near_sma:
            score += self.score_near_sma20
        
        return min(100.0, max(0.0, score))
    
    def _determine_membership_tier(self, score: float) -> MembershipTier:
        """
        Determina el tier de membresía basado en el score.
        
        Args:
            score: Score de oportunidad (0-100)
        
        Returns:
            Tier de membresía correspondiente
        """
        if score >= self.elite_threshold:
            return MembershipTier.ELITE
        elif score >= self.premium_threshold:
            return MembershipTier.PREMIUM
        else:
            return MembershipTier.FREE
    
    def _determine_signal_type(
        self, 
        df: pd.DataFrame,
        regime: MarketRegime,
        index: int = -1
    ) -> Optional[SignalType]:
        """
        Determina el tipo de señal basado en precio y régimen.
        
        Estrategia Oliver Vélez:
        - BUY: Precio rebota en SMA 20 en uptrend
        - SELL: Precio rechaza en SMA 20 en downtrend
        
        Args:
            df: DataFrame con OHLC
            regime: Régimen de mercado
            index: Índice de la vela
        
        Returns:
            SignalType o None si no hay señal clara
        """
        if len(df) < self.sma_period + 2:
            return None
        
        sma = df['close'].rolling(window=self.sma_period).mean()
        
        # Verificar tendencia con SMA
        current_sma = sma.iloc[index]
        previous_sma = sma.iloc[index - 1]
        current_close = df['close'].iloc[index]
        previous_close = df['close'].iloc[index - 1]
        
        if pd.isna(current_sma) or pd.isna(previous_sma):
            return None
        
        # Uptrend: SMA ascendente y precio por encima
        is_uptrend = current_sma > previous_sma and current_close > current_sma
        
        # Downtrend: SMA descendente y precio por debajo
        is_downtrend = current_sma < previous_sma and current_close < current_sma
        
        # Solo operar en TREND
        if regime != MarketRegime.TREND:
            return None
        
        # BUY: Rebote en uptrend
        if is_uptrend and previous_close <= previous_sma and current_close > current_sma:
            return SignalType.BUY
        
        # SELL: Rechazo en downtrend
        if is_downtrend and previous_close >= previous_sma and current_close < current_sma:
            return SignalType.SELL
        
        return None
    
    def generate_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        regime: MarketRegime,
        index: int = -1
    ) -> Optional[Signal]:
        """
        Genera una señal de trading basada en el análisis del DataFrame.
        
        Args:
            symbol: Símbolo del instrumento
            df: DataFrame con OHLC y volumen
            regime: Régimen de mercado actual
            index: Índice de la vela a analizar (-1 = última)
        
        Returns:
            Objeto Signal o None si no hay oportunidad
        """
        if df is None or len(df) < max(self.sma_period, 20):
            logger.debug(f"Datos insuficientes para {symbol}")
            return None
        
        try:
            # Análisis técnico
            is_elephant, elephant_ratio = self._is_elephant_candle(df, index)
            volume_high, volume_ratio = self._is_volume_above_average(df, index)
            near_sma, sma_distance = self._is_near_sma20(df, index)
            
            # Calcular score
            score = self._calculate_score(regime, is_elephant, volume_high, near_sma)
            
            # Determinar tier de membresía
            membership_tier = self._determine_membership_tier(score)
            
            # Determinar tipo de señal
            signal_type = self._determine_signal_type(df, regime, index)
            
            if signal_type is None:
                logger.debug(f"No hay señal clara para {symbol} (score: {score:.1f})")
                return None
            
            # Obtener precio actual
            current_price = float(df['close'].iloc[index])
            atr = self._calculate_atr(df).iloc[index]
            
            # Calcular SL y TP basado en ATR (Oliver Vélez usa 2:1 reward/risk)
            if not pd.isna(atr) and atr > 0:
                if signal_type == SignalType.BUY:
                    stop_loss = current_price - (1.5 * atr)
                    take_profit = current_price + (3.0 * atr)
                elif signal_type == SignalType.SELL:
                    stop_loss = current_price + (1.5 * atr)
                    take_profit = current_price - (3.0 * atr)
                else:
                    stop_loss = None
                    take_profit = None
            else:
                stop_loss = None
                take_profit = None
            
            # Crear señal
            signal = Signal(
                connector=self.connector_type,
                symbol=symbol,
                signal_type=signal_type,
                price=current_price,
                timestamp=datetime.now(),
                volume=0.01,  # Volumen por defecto (ajustable según capital)
                stop_loss=stop_loss,
                take_profit=take_profit,
                regime=regime,
                strategy_id=self.strategy_id,
                score=score,
                membership_tier=membership_tier,
                is_elephant_candle=is_elephant,
                volume_above_average=volume_high,
                near_sma20=near_sma,
                metadata={
                    "elephant_ratio": float(elephant_ratio),
                    "volume_ratio": float(volume_ratio),
                    "sma_distance_pct": float(sma_distance),
                    "atr": float(atr) if not pd.isna(atr) else None
                }
            )
            
            logger.info(
                f"Señal generada: {symbol} {signal_type.value} @ {current_price:.5f} | "
                f"Score: {score:.1f} | Tier: {membership_tier.value} | "
                f"Régimen: {regime.value}"
            )
            
            return signal
        
        except Exception as e:
            logger.error(f"Error generando señal para {symbol}: {e}", exc_info=True)
            return None
    
    def generate_signals_batch(
        self,
        scan_results: Dict[str, Dict]
    ) -> List[Signal]:
        """
        Genera señales para múltiples símbolos basándose en resultados del escáner.
        
        Args:
            scan_results: Dict con resultados del escáner por símbolo
                         {symbol: {"regime": MarketRegime, "df": DataFrame, "metrics": dict}}
        
        Returns:
            Lista de señales generadas
        """
        signals = []
        
        for symbol, data in scan_results.items():
            try:
                regime = data.get("regime")
                df = data.get("df")
                
                if regime is None or df is None:
                    continue
                
                signal = self.generate_signal(symbol, df, regime)
                
                if signal is not None:
                    signals.append(signal)
            
            except Exception as e:
                logger.error(f"Error procesando {symbol}: {e}")
                continue
        
        logger.info(f"Batch completado: {len(signals)} señales generadas de {len(scan_results)} símbolos")
        
        return signals
    
    def filter_by_membership(
        self,
        signals: List[Signal],
        user_tier: MembershipTier = MembershipTier.FREE
    ) -> List[Signal]:
        """
        Filtra señales según el tier de membresía del usuario.
        
        Args:
            signals: Lista de señales
            user_tier: Tier del usuario
        
        Returns:
            Lista de señales filtradas
        """
        tier_order = {
            MembershipTier.FREE: 0,
            MembershipTier.PREMIUM: 1,
            MembershipTier.ELITE: 2
        }
        
        user_level = tier_order.get(user_tier, 0)
        
        filtered = [
            signal for signal in signals
            if tier_order.get(signal.membership_tier, 0) <= user_level
        ]
        
        logger.info(
            f"Filtrado por membresía {user_tier.value}: "
            f"{len(filtered)}/{len(signals)} señales disponibles"
        )
        
        return filtered
