import logging
from datetime import datetime
from typing import Optional, Dict
import pandas as pd

from models.signal import (
    Signal, SignalType, MarketRegime, MembershipTier, ConnectorType
)
from core_brain.strategies.base_strategy import BaseStrategy
from core_brain.instrument_manager import InstrumentManager
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class OliverVelezStrategy(BaseStrategy):
    """
    Implementación de la estrategia Oliver Vélez (Bullish/Bearish).
    Enfocada en:
    1. Tendencia mayor (SMA 200)
    2. Zona de valor (SMA 20)
    3. Velas de ignición (Elefante)
    4. Score dinámico por instrumento (majors: 70, exotics: 90)
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
        
        # Instrument Manager para validación dinámica de scores
        self.instrument_manager = InstrumentManager()
        
        logger.info(
            f"[{self.strategy_id}] Initialized with InstrumentManager. "
            f"Enabled symbols: {len(self.instrument_manager.get_enabled_symbols())}"
        )

    @property
    def strategy_id(self) -> str:
        return "oliver_velez_swing_v2"
    
    def _detect_available_connector(self) -> ConnectorType:
        """
        Auto-detecta el conector disponible basándose en configuración.
        Prioridad: MT5 > NT8 > GENERIC
        
        Esto mantiene el agnosticismo: la estrategia no depende de un conector específico.
        """
        # Verificar MT5 vía DB (single source of truth)
        try:
            storage = StorageManager()
            accounts = storage.get_broker_accounts(enabled_only=True)
            has_mt5_demo = any(
                acc.get('platform_id') == 'mt5'
                and str(acc.get('account_type', '')).lower() == 'demo'
                for acc in accounts
            )
            if has_mt5_demo:
                logger.info(f"[{self.strategy_id}] Usando MT5 connector (DB detectada)")
                return ConnectorType.METATRADER5
        except Exception as e:
            logger.warning(f"[{self.strategy_id}] MT5 detection failed: {e}")
        
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

        from core_brain.tech_utils import TechnicalAnalyzer
        
        # Asegurar que el DataFrame tiene los indicadores necesarios
        # (Idealmente el scanner ya lo hizo, pero garantizamos consistencia)
        if f'sma_{self.sma_long_p}' not in df.columns:
            df[f'sma_{self.sma_long_p}'] = TechnicalAnalyzer.calculate_sma(df, self.sma_long_p)
        
        if f'sma_{self.sma_short_p}' not in df.columns:
            df[f'sma_{self.sma_short_p}'] = TechnicalAnalyzer.calculate_sma(df, self.sma_short_p)
        
        if 'atr' not in df.columns:
            df['atr'] = TechnicalAnalyzer.calculate_atr(df, 14)

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

        # Debug logs (use logger.debug to reduce console noise)
        logger.debug(f"[{symbol}] OV Strategy Analysis:")
        logger.debug(f"  Prices: Close={latest_candle['close']:.4f}, SMA200={latest_candle[f'sma_{self.sma_long_p}']:.4f}")
        logger.debug(f"  Conditions: Trend={is_bullish_trend}, Elephant={is_elephant_body} ({body_atr_ratio:.2f}), NearSMA20={is_near_sma20} ({sma20_dist_pct:.2f}%)")

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
        
        # NUEVO: Validación de score contra umbral dinámico por instrumento
        validation = self.instrument_manager.validate_symbol(symbol, score)
        
        if not validation["valid"]:
            logger.info(
                f"[{symbol}] Setup técnicamente válido pero RECHAZADO: "
                f"{validation['rejection_reason']}. "
                f"Score: {score:.1f}, Categoría: {validation['category']}/{validation['subcategory']}"
            )
            return None
        
        logger.info(
            f"[{symbol}] Setup APROBADO. Score: {score:.1f} >= {validation['min_score_required']:.1f} "
            f"({validation['category']}/{validation['subcategory']})"
        )
        
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
