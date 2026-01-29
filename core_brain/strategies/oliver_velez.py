import logging
from datetime import datetime
from typing import Optional, Dict
import pandas as pd

from models.signal import (
    Signal, SignalType, MarketRegime, MembershipTier, ConnectorType
)
from core_brain.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class OliverVelezStrategy(BaseStrategy):
    """
    Implementación de la estrategia Oliver Vélez (Bullish/Bearish).
    Enfocada en:
    1. Tendencia mayor (SMA 200)
    2. Zona de valor (SMA 20)
    3. Velas de ignición (Elefante)
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Parámetros EDGE (auto-ajustables)
        self.adx_threshold = config.get("adx_threshold", 25)
        self.elephant_atr_multiplier = config.get("elephant_atr_multiplier", 0.3)
        self.sma20_proximity_percent = config.get("sma20_proximity_percent", 1.5)
        self.min_signal_score = config.get("min_signal_score", 60)
        
        # Parámetros de estrategia (fijos)
        self.sma_long_p = config.get("sma_long_period", 200)
        self.sma_short_p = config.get("sma_short_period", 20)
        
        # Parámetros de scoring (hardcoded o config)
        self.base_score = 60.0
        self.regime_bonus = 20.0
        self.proximity_bonus_weight = 10.0
        self.candle_bonus_weight = 10.0
        
        # Umbrales
        self.premium_threshold = 85.0
        self.elite_threshold = 95.0
        
        # Auto-detectar conector disponible (agnosticismo)
        self.connector_type = self._detect_available_connector()

    @property
    def strategy_id(self) -> str:
        return "oliver_velez_swing_v2"
    
    def _detect_available_connector(self) -> ConnectorType:
        """
        Auto-detecta el conector disponible basándose en configuración.
        Prioridad: MT5 > NT8 > GENERIC
        
        Esto mantiene el agnosticismo: la estrategia no depende de un conector específico.
        """
        from pathlib import Path
        
        # Verificar MT5
        if Path('config/mt5_config.json').exists():
            logger.info(f"[{self.strategy_id}] Usando MT5 connector (config detectada)")
            return ConnectorType.METATRADER5
        
        # Verificar NT8 (si existe configuración en el futuro)
        # if Path('config/nt8_config.json').exists():
        #     return ConnectorType.NINJATRADER8
        
        # Fallback a PAPER (si no hay configs específicas)
        logger.info(f"[{self.strategy_id}] Usando PAPER connector (modo simulación)")
        return ConnectorType.PAPER

    async def analyze(self, symbol: str, df: pd.DataFrame, regime: MarketRegime) -> Optional[Signal]:
        """
        Analiza el activo buscando setup de Oliver Vélez.
        """
        if df is None or len(df) < self.sma_long_p + 10:
            return None

        # Validación básica de indicadores (se asume que el scanner o factory puede haberlos calculado, 
        # pero por seguridad los recalculamos o verificamos aquí si es necesario).
        # Para mantener el agnosticismo, calculamos si faltan.
        
        if f'sma_{self.sma_long_p}' not in df.columns:
            df[f'sma_{self.sma_long_p}'] = df['close'].rolling(window=self.sma_long_p).mean()
        
        if f'sma_{self.sma_short_p}' not in df.columns:
            df[f'sma_{self.sma_short_p}'] = df['close'].rolling(window=self.sma_short_p).mean()
        
        if 'atr' not in df.columns:
            df['tr'] = pd.concat([
                df['high'] - df['low'],
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            ], axis=1).max(axis=1)
            df['atr'] = df['tr'].rolling(window=14).mean()

        latest_candle = df.iloc[-1]

        if pd.isna(latest_candle[f'sma_{self.sma_long_p}']) or pd.isna(latest_candle['atr']):
            return None

        # --- Lógica de Trading (Copiada de SignalFactory) ---
        is_bullish_trend = latest_candle['close'] > latest_candle[f'sma_{self.sma_long_p}']
        
        candle_body = abs(latest_candle['close'] - latest_candle['open'])
        body_atr_ratio = (
            candle_body / latest_candle['atr'] if latest_candle['atr'] > 0 else 0
        )
        is_elephant_body = body_atr_ratio >= self.elephant_atr_multiplier
        
        sma20_dist_pct = (
            abs(latest_candle['close'] - latest_candle[f'sma_{self.sma_short_p}']) 
            / latest_candle[f'sma_{self.sma_short_p}'] * 100
        )
        is_near_sma20 = sma20_dist_pct < self.sma20_proximity_percent
        is_bullish_candle = latest_candle['close'] > latest_candle['open']

        # Debug logs
        logger.info(f"[{symbol}] OV Strategy Analysis:")
        logger.info(f"  Prices: Close={latest_candle['close']:.4f}, SMA200={latest_candle[f'sma_{self.sma_long_p}']:.4f}")
        logger.info(f"  Conditions: Trend={is_bullish_trend}, Elephant={is_elephant_body} ({body_atr_ratio:.2f}), NearSMA20={is_near_sma20} ({sma20_dist_pct:.2f}%)")

        validation_results = {
            "trend_ok": is_bullish_trend and regime == MarketRegime.TREND,
            "candle_ok": is_elephant_body and is_bullish_candle,
            "proximity_ok": is_near_sma20,
        }

        candle_data = {
            "sma20_dist_pct": sma20_dist_pct,
            "body_atr_ratio": body_atr_ratio,
        }

        score = self._calculate_opportunity_score(validation_results, candle_data, regime)

        if score <= 0:
            return None
        
        # --- Construcción de Señal ---
        current_price = latest_candle['close']
        membership_tier = self._determine_membership_tier(score)
        
        stop_loss = current_price - (1.5 * latest_candle['atr'])
        take_profit = current_price + (3.0 * latest_candle['atr'])

        signal = Signal(
            symbol=symbol,
            signal_type="BUY",
            confidence=score / 100.0,
            connector_type=self.connector_type,  # Auto-detectado
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=datetime.now(),
            metadata={
                "regime": regime.value,
                "strategy_id": self.strategy_id,
                "score": score,
                "membership_tier": membership_tier.value,
                "is_elephant_candle": is_elephant_body,
                "near_sma20": is_near_sma20,
                "body_atr_ratio": round(body_atr_ratio, 2),
                "sma20_dist_pct": round(sma20_dist_pct, 2),
                "atr": round(latest_candle['atr'], 5)
            }
        )
        
        return signal

    def _calculate_opportunity_score(
        self, validation_results: dict, candle_data: dict, regime: MarketRegime
    ) -> float:
        if not all(validation_results.values()):
            return 0.0

        score = self.base_score

        if regime == MarketRegime.TREND:
            score += self.regime_bonus

        proximity_ratio = (candle_data["sma20_dist_pct"] / self.sma20_proximity_percent)
        score += (1 - proximity_ratio) * self.proximity_bonus_weight

        strength_ratio = (candle_data["body_atr_ratio"] / self.elephant_atr_multiplier)
        score += min(1.0, strength_ratio - 1.0) * self.candle_bonus_weight

        return min(100.0, max(0.0, score))

    def _determine_membership_tier(self, score: float) -> MembershipTier:
        if score >= self.elite_threshold:
            return MembershipTier.ELITE
        elif score >= self.premium_threshold:
            return MembershipTier.PREMIUM
        return MembershipTier.FREE
