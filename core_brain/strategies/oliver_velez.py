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

    def __init__(self, config: Dict, instrument_manager):
        super().__init__(config)
        # Parámetros EDGE STRICT (Innegociables)
        self.elephant_zscore_threshold = config.get("elephant_zscore_threshold", 2.0)
        self.elephant_solidness_min = config.get("elephant_solidness_min", 0.8)
        self.sma20_proximity_atr_max = config.get("sma20_proximity_atr_max", 0.5)
        self.min_signal_score = config.get("min_signal_score", 85)
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
        # Instrument Manager por DI
        self.instrument_manager = instrument_manager
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
        Analiza el activo buscando setup de Oliver Vélez (BUY y SELL).
        """
        try:
            if df is None or len(df) < self.sma_long_p + 10:
                return None

            from core_brain.tech_utils import TechnicalAnalyzer
            
            # Asegurar que el DataFrame tiene los indicadores necesarios
            if f'sma_{self.sma_long_p}' not in df.columns:
                df[f'sma_{self.sma_long_p}'] = TechnicalAnalyzer.calculate_sma(df, self.sma_long_p)
            
            if f'sma_{self.sma_short_p}' not in df.columns:
                df[f'sma_{self.sma_short_p}'] = TechnicalAnalyzer.calculate_sma(df, self.sma_short_p)
            
            if 'atr' not in df.columns:
                df['atr'] = TechnicalAnalyzer.calculate_atr(df, 14)

            # --- Nuevas Métricas Estadísticas (EDGE STRICT) ---
            if 'zscore_body' not in df.columns:
                df['zscore_body'] = TechnicalAnalyzer.calculate_body_zscore(df, 50)
            
            if 'solidness' not in df.columns:
                df['solidness'] = TechnicalAnalyzer.calculate_candle_solidness(df)

            latest_candle = df.iloc[-1]

            if pd.isna(latest_candle[f'sma_{self.sma_long_p}']) or pd.isna(latest_candle['atr']):
                return None

            # --- Análisis de Fuerza de Tendencia (Nuevo) ---
            trend_class = TechnicalAnalyzer.classify_trend(df, self.sma_short_p, self.sma_long_p)
            trend_strength = TechnicalAnalyzer.calculate_trend_strength(df, self.sma_short_p, self.sma_long_p)
            
            # --- Lógica de Tendencia ---
            is_bullish_trend = latest_candle['close'] > latest_candle[f'sma_{self.sma_long_p}']
            is_bearish_trend = latest_candle['close'] < latest_candle[f'sma_{self.sma_long_p}']
            
            # --- 1. Lógica de Vela Elefante (Z-Score + Solidez) ---
            current_zscore = latest_candle['zscore_body']
            current_solidness = latest_candle['solidness']
            is_elephant_body = (
                current_zscore >= self.elephant_zscore_threshold and
                current_solidness >= self.elephant_solidness_min
            )
            
            # --- 2. Direccionalidad OHLC Innegociable ---
            is_bullish_candle = latest_candle['close'] > latest_candle['open']
            is_bearish_candle = latest_candle['close'] < latest_candle['open']
            
            # --- 3. Ubicación Táctica SMA20 (Zona ATR) ---
            sma20 = latest_candle[f'sma_{self.sma_short_p}']
            atr = latest_candle['atr']
            
            # Rangos de ubicación milimétricos
            # BUY: Low debe estar cerca o tocando SMA20. Cierre debe estar por encima.
            is_located_buy = (
                latest_candle['low'] <= sma20 + (0.5 * atr) and
                latest_candle['low'] >= sma20 - (0.2 * atr) and
                latest_candle['close'] > sma20
            )
            
            # SELL: High debe estar cerca o tocando SMA20. Cierre debe estar por debajo.
            is_located_sell = (
                latest_candle['high'] >= sma20 - (0.5 * atr) and
                latest_candle['high'] <= sma20 + (0.2 * atr) and
                latest_candle['close'] < sma20
            )
            
            # --- 4. Filtro de Tendencia SMA200 (LA LOCOMOTORA) ---
            sma200 = latest_candle[f'sma_{self.sma_long_p}']
            slope_slow = trend_strength["slope_slow"]
            
            is_trend_aligned_buy = latest_candle['close'] > sma200 and slope_slow > 0.05
            is_trend_aligned_sell = latest_candle['close'] < sma200 and slope_slow < -0.05

            # --- Consolidación de Señal ---
            signal_type = None
            if is_elephant_body and is_bullish_candle and is_located_buy and is_trend_aligned_buy:
                signal_type = SignalType.BUY
            elif is_elephant_body and is_bearish_candle and is_located_sell and is_trend_aligned_sell:
                signal_type = SignalType.SELL

            # Log de diagnóstico estricto
            logger.info(
                f"[{symbol}] STRICT DIAGNOSTIC: "
                f"ELEPHANT={'OK' if is_elephant_body else 'FAIL'} (Z:{current_zscore:.1f}, S:{current_solidness:.2f}), "
                f"DIRECTION={'OK' if (is_bullish_candle if signal_type == SignalType.BUY else is_bearish_candle) else 'FAIL'}, "
                f"LOCATION={'OK' if (is_located_buy if signal_type == SignalType.BUY else is_located_sell) else 'FAIL'}, "
                f"TREND_200={'OK' if (is_trend_aligned_buy if signal_type == SignalType.BUY else is_trend_aligned_sell) else 'FAIL'}"
            )

            if not signal_type:
                return None

            candle_data = {
                "zscore": current_zscore,
                "solidness": current_solidness,
                "trend_class": trend_class,
                "trend_strength": trend_strength,
            }

            score = self._calculate_opportunity_score({}, candle_data, regime)

            if score <= 0:
                return None
            
            # Validación de score contra umbral dinámico por instrumento
            validation = self.instrument_manager.validate_symbol(symbol, score)
            if not isinstance(validation, dict):
                validation = {
                    "valid": True,
                    "category": "UNKNOWN",
                    "subcategory": "UNKNOWN",
                    "min_score_required": 0.0,
                    "rejection_reason": None
                }
            min_required = validation.get("min_score_required", 0.0)
            try:
                min_required = float(min_required)
            except Exception:
                min_required = 0.0
            category = validation.get("category", "UNKNOWN")
            subcategory = validation.get("subcategory", "UNKNOWN")
            
            if not validation["valid"]:
                logger.info(
                    f"[STRATEGY] {symbol} | {category}/{subcategory} | RECHAZADO: "
                    f"{validation['rejection_reason']} (Score: {score:.1f})"
                )
                return None
            
            logger.info(
                f"[STRATEGY] {symbol} | {category}/{subcategory} | APROBADO: {signal_type.value} "
                f"(Score: {score:.1f} >= {min_required:.1f})"
            )
            
            # --- Construcción de Señal ---
            current_price = latest_candle['close']
            membership_tier = self._determine_membership_tier(score)
            
            # 1. Definir Buffer (1 Pip dinámico para seguridad)
            # Usar 0.0001 (5d) o 0.01 (3d) según símbolo
            buffer_pips = 1.0
            from utils.market_ops import calculate_pip_size
            pip_size = calculate_pip_size(None, symbol, self.instrument_manager)
            buffer = buffer_pips * pip_size

            # 2. SL/TP dinámico según la base de la Vela Elefante (OV Original)
            if signal_type == SignalType.BUY:
                # Stop Loss en el Low de la vela de entrada (Elefante)
                stop_loss = latest_candle['low'] - buffer
                risk_pips = (current_price - stop_loss) / pip_size
                # TP al menos 2:1 basado en el riesgo técnico
                take_profit = current_price + (risk_pips * 2.0 * pip_size)
            else: # SELL
                # Stop Loss en el High de la vela de entrada (Elefante)
                stop_loss = latest_candle['high'] + buffer
                risk_pips = (stop_loss - current_price) / pip_size
                # TP al menos 2:1 basado en el riesgo técnico
                take_profit = current_price - (risk_pips * 2.0 * pip_size)

            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                confidence=score / 100.0,
                connector_type=self.connector_type,
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
                    "zscore_body": round(current_zscore, 2),
                    "solidness": round(current_solidness, 2),
                    "trend_classification": trend_class,
                    "trend_strength_score": round(trend_strength["strength_score"], 1),
                    "sma200_slope": round(slope_slow, 3),
                    "execution_observation": f"Setup Oliver Velez {signal_type.value} STRICT en {symbol}"
                }
            )
            
            return signal

        except Exception as e:
            logger.error(f"CRITICAL ERROR in OliverVelezStrategy.analyze for {symbol}: {e}", exc_info=True)
            return None

    def _calculate_opportunity_score(
        self, validation_results: dict, candle_data: dict, regime: MarketRegime
    ) -> float:
        # ESTRICTO: Sistema de Puntuación por Pilares (0-100) - REFINADO
        # Precision Quirúrgica: Refleja calidad exacta de Vela, Ubicación y Tendencia.

        # Pilar 1: Vela Elefante (Max 50 pts)
        # Basado en Z-Score (2.0 = 40 pts, 3.0+ = 50 pts)
        zscore = candle_data.get("zscore", 0.0)
        score_candle = min(50.0, (zscore / 2.0) * 40.0) if zscore >= 2.0 else 0.0

        # Pilar 2: Ubicación / Solidez (Max 50 pts)
        # Mezclamos solidez de la vela con proximidad a SMA20.
        solidness = candle_data.get("solidness", 0.0)
        score_solid = solidness * 25.0
        
        # Proximidad SMA20 (ya validada en analyze, aquí solo puntuamos fine-tuning)
        score_proximity = 25.0 # Ya filtrado
        
        final_score = score_candle + score_solid + score_proximity
        
        return min(100.0, max(0.0, final_score))
        
        return min(100.0, max(0.0, final_score))

    def _determine_membership_tier(self, score: float) -> MembershipTier:
        if score >= self.elite_threshold:
            return MembershipTier.ELITE
        elif score >= self.premium_threshold:
            return MembershipTier.PREMIUM
        return MembershipTier.FREE
