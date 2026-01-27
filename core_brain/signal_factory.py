"""
Signal Factory - Motor de Generación de Señales para Aethelgard
==============================================================

Implementa la lógica de generación de señales basada en la estrategia
Oliver Vélez, integrando un sistema de scoring dinámico y notificaciones
diferenciadas por membresía, conforme al AETHELGARD_MANIFESTO.

Estrategia Oliver Vélez (Implementación Bullish):
1.  **Tendencia Mayor Alcista:** El precio debe estar por encima de la SMA 200.
2.  **Zona de Compra:** El precio debe estar cerca de la SMA 20, que actúa como
    soporte dinámico.
3.  **Vela de Ignición (Elefante):** Debe aparecer una vela alcista con un
    cuerpo significativamente más grande que el ATR, demostrando momentum
    comprador.
4.  **Régimen de Mercado:** La señal tiene mayor validez en un Régimen de
    'TREND'.
"""
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from models.signal import (
    Signal, SignalType, MarketRegime, MembershipTier, ConnectorType
)
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier, TelegramNotifier
from core_brain.module_manager import MembershipLevel

logger = logging.getLogger(__name__)

class SignalFactory:
    """
    Motor que recibe datos del ScannerEngine, los procesa y genera señales de
    trading.
    
    EDGE: Lee parámetros desde dynamic_params.json (auto-ajustados por tuner.py)
    """

    def __init__(
        self,
        storage_manager: StorageManager,
        config_path: str = "config/dynamic_params.json",
        strategy_id: str = "oliver_velez_swing_v2",
    ):
        """
        Inicializa la SignalFactory.

        Args:
            storage_manager: Instancia del gestor de persistencia.
            config_path: Ruta a dynamic_params.json (fuente de verdad para parámetros)
            strategy_id: Identificador de la estrategia.
        """
        self.storage_manager = storage_manager
        self.notifier: Optional[TelegramNotifier] = get_notifier()
        self.config_path = config_path
        self.strategy_id = strategy_id
        
        # Cargar parámetros desde config (EDGE)
        self._load_parameters()
        
        logger.info(f"✅ SignalFactory initialized with EDGE parameters from {config_path}")
        logger.info(f"   ADX: {self.adx_threshold}, ATR: {self.elephant_atr_multiplier}, SMA20: {self.sma20_proximity_percent}%")
    
    def _load_parameters(self):
        """Carga parámetros desde dynamic_params.json (auto-ajustados por EDGE)"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config not found: {self.config_path}. Using defaults.")
            config = {}
        
        # Parámetros EDGE (auto-ajustables)
        self.adx_threshold = config.get("adx_threshold", 25)
        self.elephant_atr_multiplier = config.get("elephant_atr_multiplier", 0.3)
        self.sma20_proximity_percent = config.get("sma20_proximity_percent", 1.5)
        self.min_signal_score = config.get("min_signal_score", 60)
        
        # Parámetros de estrategia (fijos)
        self.sma_long_p = config.get("sma_long_period", 200)
        self.sma_short_p = config.get("sma_short_period", 20)
        
        # Parámetros de scoring (fijos)
        self.base_score = 60.0
        self.regime_bonus = 20.0
        self.proximity_bonus_weight = 10.0
        self.candle_bonus_weight = 10.0

        # Umbrales de membresía (fijos)
        self.premium_threshold = 85.0
        self.elite_threshold = 95.0

        if not self.notifier or not self.notifier.is_configured():
            logger.warning(
                "Notificador de Telegram no está configurado. "
                "No se enviarán alertas."
            )

        logger.info(
            f"SignalFactory inicializado para '{self.strategy_id}'. "
            f"Umbral Premium: {self.premium_threshold}, "
            f"Umbral Elite: {self.elite_threshold}"
        )

    def _determine_membership_tier(self, score: float) -> MembershipTier:
        """Determina el tier de membresía basado en el score."""
        if score >= self.elite_threshold:
            return MembershipTier.ELITE
        elif score >= self.premium_threshold:
            return MembershipTier.PREMIUM
        return MembershipTier.FREE

    def _calculate_opportunity_score(
        self, validation_results: dict, candle_data: dict, regime: MarketRegime
    ) -> float:
        """
        Calcula el Score de Oportunidad dinámicamente.

        Args:
            validation_results: Resultados booleanos de la validación.
            candle_data: Datos numéricos de la vela y sus indicadores.
            regime: El régimen de mercado actual.

        Returns:
            El score de oportunidad (0-100).
        """
        if not all(validation_results.values()):
            return 0.0

        # --- Scoring Dinámico ---
        score = self.base_score

        # 1. Bonificación por Régimen
        if regime == MarketRegime.TREND:
            score += self.regime_bonus

        # 2. Bonificación por Proximidad a SMA20 (más cerca es mejor)
        proximity_ratio = (
            candle_data["sma20_dist_pct"] / self.sma20_proximity_percent
        )
        score += (1 - proximity_ratio) * self.proximity_bonus_weight

        # 3. Bonificación por Fuerza de la Vela
        strength_ratio = (
            candle_data["body_atr_ratio"] / self.elephant_atr_multiplier
        )
        score += min(1.0, strength_ratio - 1.0) * self.candle_bonus_weight

        return min(100.0, max(0.0, score))

    async def generate_signal(
        self, symbol: str, df: pd.DataFrame, regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Analiza, genera, guarda y notifica una señal de trading.

        Calcula indicadores si no existen en el DataFrame.

        Args:
            symbol: Símbolo del instrumento (e.g., 'EURUSD').
            df: DataFrame con datos OHLC.
            regime: Régimen actual del mercado.

        Returns:
            Un objeto Signal si se genera una oportunidad, o None.
        """
        if df is None or len(df) < self.sma_long_p + 10:
            logger.debug(f"[{symbol}] Datos insuficientes (<{self.sma_long_p + 10} velas)")
            return None

        try:
            # Calcular indicadores si no existen
            if f'sma_{self.sma_long_p}' not in df.columns:
                df[f'sma_{self.sma_long_p}'] = df['close'].rolling(window=self.sma_long_p).mean()
            
            if f'sma_{self.sma_short_p}' not in df.columns:
                df[f'sma_{self.sma_short_p}'] = df['close'].rolling(window=self.sma_short_p).mean()
            
            if 'atr' not in df.columns:
                # ATR = Average True Range
                df['tr'] = pd.concat([
                    df['high'] - df['low'],
                    abs(df['high'] - df['close'].shift()),
                    abs(df['low'] - df['close'].shift())
                ], axis=1).max(axis=1)
                df['atr'] = df['tr'].rolling(window=14).mean()
            
            latest_candle = df.iloc[-1]
            
            # Verificar que los indicadores estén calculados (no NaN)
            if pd.isna(latest_candle[f'sma_{self.sma_long_p}']) or pd.isna(latest_candle['atr']):
                logger.debug(f"[{symbol}] Indicadores aún no calculados (necesita más datos)")
                return None

            # --- Validación de la Estrategia Oliver Vélez (Bullish) ---
            is_bullish_trend = (
                latest_candle['close'] >
                latest_candle[f'sma_{self.sma_long_p}']
            )

            candle_body = abs(latest_candle['close'] - latest_candle['open'])
            body_atr_ratio = (
                candle_body / latest_candle['atr'] if latest_candle['atr'] > 0
                else 0
            )
            is_elephant_body = body_atr_ratio >= self.elephant_atr_multiplier

            sma20_dist_pct = (
                abs(
                    latest_candle['close'] -
                    latest_candle[f'sma_{self.sma_short_p}']
                ) / latest_candle[f'sma_{self.sma_short_p}'] * 100
            )
            is_near_sma20 = sma20_dist_pct < self.sma20_proximity_percent

            is_bullish_candle = latest_candle['close'] > latest_candle['open']

            # === LOGGING DETALLADO ===
            logger.info(f"[{symbol}] Validación:")
            logger.info(f"  - Precio: {latest_candle['close']:.5f} | SMA200: {latest_candle[f'sma_{self.sma_long_p}']:.5f} | BullishTrend: {is_bullish_trend}")
            logger.info(f"  - Cuerpo: {candle_body:.5f} | ATR: {latest_candle['atr']:.5f} | Ratio: {body_atr_ratio:.2f} | Elephant: {is_elephant_body} (>{self.elephant_atr_multiplier})")
            logger.info(f"  - Dist SMA20: {sma20_dist_pct:.2f}% | Near: {is_near_sma20} (<{self.sma20_proximity_percent}%)")
            logger.info(f"  - Candle Bullish: {is_bullish_candle} | Régimen: {regime.value}")

            validation_results = {
                "trend_ok": is_bullish_trend and regime == MarketRegime.TREND,
                "candle_ok": is_elephant_body and is_bullish_candle,
                "proximity_ok": is_near_sma20,
            }

            candle_data = {
                "sma20_dist_pct": sma20_dist_pct,
                "body_atr_ratio": body_atr_ratio,
            }

            logger.info(f"[{symbol}] Resultados: trend_ok={validation_results['trend_ok']}, candle_ok={validation_results['candle_ok']}, proximity_ok={validation_results['proximity_ok']}")

            score = self._calculate_opportunity_score(
                validation_results, candle_data, regime
            )

            if score <= 0:
                logger.warning(
                    f"[{symbol}] ❌ No cumple condiciones. Score: {score}"
                )
                return None
            
            logger.info(f"[{symbol}] ✅ SEÑAL GENERADA - Score: {score}")

            # --- Creación del objeto Signal ---
            current_price = latest_candle['close']
            membership_tier = self._determine_membership_tier(score)

            # Gestión de Riesgo (ejemplo simple basado en ATR)
            stop_loss = current_price - (1.5 * latest_candle['atr'])
            take_profit = current_price + (3.0 * latest_candle['atr'])

            signal = Signal(
                symbol=symbol,
                signal_type="BUY",
                confidence=score / 100.0,  # Convertir score 0-100 a confidence 0-1
                connector_type=ConnectorType.NINJATRADER8,
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
                    "atr": round(latest_candle['atr'], 5),
                    f"sma_{self.sma_short_p}": round(
                        latest_candle[f'sma_{self.sma_short_p}'], 5
                    ),
                    f"sma_{self.sma_long_p}": round(
                        latest_candle[f'sma_{self.sma_long_p}'], 5
                    ),
                }
            )

            # --- Persistencia y Notificación ---
            try:
                signal_id = self.storage_manager.save_signal(signal)
                logger.info(
                    f"SEÑAL GENERADA [ID: {signal_id}] -> {signal.symbol} "
                    f"{signal.signal_type} @ {signal.entry_price:.5f} | "
                    f"Score: {score:.1f} "
                    f"({membership_tier.value})"
                )
            except Exception as e:
                logger.error(
                    f"[{symbol}] Error al guardar señal en BBDD: {e}"
                )
                return None

            if self.notifier and membership_tier in [
                MembershipTier.PREMIUM, MembershipTier.ELITE
            ]:
                logger.debug(
                    f"[{symbol}] Disparando notificación PREMIUM para "
                    f"score {score:.1f}"
                )
                asyncio.create_task(
                    self.notifier.notify_oliver_velez_signal(
                        signal, membership=MembershipLevel.PREMIUM
                    )
                )

            return signal

        except Exception as e:
            logger.error(
                f"Error generando señal para {symbol}: {e}", exc_info=True
            )
            return None

    async def generate_signals_batch(
        self, scan_results: Dict[str, Dict]
    ) -> List[Signal]:
        """
        Procesa un lote de resultados del ScannerEngine y genera señales.

        Args:
            scan_results: {symbol: {"regime": MarketRegime, "df": DataFrame}}

        Returns:
            Una lista de objetos Signal generados.
        """
        tasks = [
            self.generate_signal(s, d.get("df"), d.get("regime"))
            for s, d in scan_results.items()
            if d.get("regime") and d.get("df") is not None
        ]

        generated_signals = await asyncio.gather(*tasks)

        signals = [s for s in generated_signals if s is not None]

        if signals:
            logger.info(
                f"Batch completado. {len(signals)} señales generadas de "
                f"{len(scan_results)} símbolos analizados."
            )

        return signals

    async def process_scan_results(self, scan_results: Dict[str, MarketRegime]) -> List[Signal]:
        """
        Procesa los resultados del scanner y genera señales.
        
        Este método es llamado por el MainOrchestrator con los regímenes
        detectados por el scanner. Solo procesa símbolos en TREND.
        
        Args:
            scan_results: Dict con symbol -> MarketRegime
            
        Returns:
            Lista de señales generadas
        """
        logger.debug(f"Processing scan results for {len(scan_results)} symbols")
        
        signals = []
        
        # Filtrar solo símbolos en TREND (condición crítica de la estrategia)
        trending_symbols = {
            symbol: regime for symbol, regime in scan_results.items()
            if regime == MarketRegime.TREND
        }
        
        if not trending_symbols:
            logger.debug("No trending symbols found in scan results")
            return signals
        
        logger.info(f"Found {len(trending_symbols)} symbols in TREND: {list(trending_symbols.keys())}")
        
        # Generar señales para cada símbolo en tendencia
        # Nota: Este método solo recibe regímenes, no DataFrames
        # La lógica completa con datos históricos debe ir en generate_signals_batch()
        for symbol, regime in trending_symbols.items():
            logger.debug(f"Symbol {symbol} in {regime.value} - ready for signal generation")
            # Las señales se generarán cuando el scanner proporcione DataFrames completos
            # vía generate_signals_batch() que tiene acceso a datos OHLC
        
        return signals

    def filter_by_membership(
        self, signals: List[Signal], user_tier: MembershipTier
    ) -> List[Signal]:
        """Filtra señales según el tier de membresía del usuario."""
        tier_order = {
            MembershipTier.FREE: 0,
            MembershipTier.PREMIUM: 1,
            MembershipTier.ELITE: 2
        }
        user_level = tier_order.get(user_tier, 0)

        filtered = [
            s for s in signals
            if tier_order.get(s.membership_tier, 0) <= user_level
        ]

        logger.debug(
            f"Filtrando {len(signals)} señales para tier "
            f"{user_tier.value}. Disponibles: {len(filtered)}"
        )
        return filtered
