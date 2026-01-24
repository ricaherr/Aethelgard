"""
Signal Factory - Motor de Generación de Señales para Aethelgard
==============================================================

Implementa la lógica de generación de señales basada en la estrategia
Oliver Vélez, integrando un sistema de scoring dinámico y notificaciones
diferenciadas por membresía, conforme al AETHELGARD_MANIFESTO.

Estrategia Oliver Vélez (Implementación Bullish):
1.  **Tendencia Mayor Alcista:** El precio debe estar por encima de la SMA 200.
2.  **Zona de Compra:** El precio debe estar cerca de la SMA 20, que actúa como soporte dinámico.
3.  **Vela de Ignición (Elefante):** Debe aparecer una vela alcista con un cuerpo significativamente
    más grande que el ATR, demostrando momentum comprador.
4.  **Régimen de Mercado:** La señal tiene mayor validez en un Régimen de 'TREND'.
"""
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

# Modelos de datos y componentes del core
from models.signal import Signal, SignalType, MarketRegime, MembershipTier, ConnectorType
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier, TelegramNotifier
from core_brain.module_manager import MembershipLevel

logger = logging.getLogger(__name__)

class SignalFactory:
    """
    Motor que recibe datos del ScannerEngine, los procesa y genera señales de trading.
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        # Parámetros de la estrategia Oliver Vélez
        strategy_id: str = "oliver_velez_swing_v2",
        sma_long_period: int = 200,
        sma_short_period: int = 20,
        elephant_atr_multiplier: float = 2.0,  # Cuerpo de la vela > 2x ATR
        sma20_proximity_percent: float = 1.5,  # Precio a < 1.5% de la SMA20
        # Parámetros de Scoring dinámico
        base_score: float = 60.0,
        regime_bonus: float = 20.0,
        proximity_bonus_weight: float = 10.0,
        candle_bonus_weight: float = 10.0,
        # Umbrales de membresía
        premium_threshold: float = 85.0,
        elite_threshold: float = 95.0,
    ):
        """
        Inicializa la SignalFactory.

        Args:
            storage_manager: Instancia del gestor de persistencia.
            strategy_id: Identificador de la estrategia.
            ... (parámetros de estrategia y scoring)
        """
        self.storage_manager = storage_manager
        self.notifier: Optional[TelegramNotifier] = get_notifier()
        
        # Parámetros de estrategia
        self.strategy_id = strategy_id
        self.sma_long_p = sma_long_period
        self.sma_short_p = sma_short_period
        self.elephant_atr_multiplier = elephant_atr_multiplier
        self.sma20_proximity_percent = sma20_proximity_percent
        
        # Parámetros de scoring
        self.base_score = base_score
        self.regime_bonus = regime_bonus
        self.proximity_bonus_weight = proximity_bonus_weight
        self.candle_bonus_weight = candle_bonus_weight
        
        # Umbrales de membresía
        self.premium_threshold = premium_threshold
        self.elite_threshold = elite_threshold

        if not self.notifier or not self.notifier.is_configured():
            logger.warning("Notificador de Telegram no está configurado. No se enviarán alertas.")
        
        logger.info(
            f"SignalFactory inicializado para '{self.strategy_id}'. "
            f"Umbral Premium: {self.premium_threshold}, Umbral Elite: {self.elite_threshold}"
        )

    def _determine_membership_tier(self, score: float) -> MembershipTier:
        """Determina el tier de membresía basado en el score."""
        if score >= self.elite_threshold:
            return MembershipTier.ELITE
        elif score >= self.premium_threshold:
            return MembershipTier.PREMIUM
        return MembershipTier.FREE

    def _calculate_opportunity_score(self, validation_results: dict, candle_data: dict, regime: MarketRegime) -> float:
        """
        Calcula el Score de Oportunidad dinámicamente.

        Args:
            validation_results: Resultados booleanos de la validación de la estrategia.
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
        # proximity_ratio es 0 si está pegado a la SMA20, 1 si está en el límite del umbral.
        proximity_ratio = candle_data["sma20_dist_pct"] / self.sma20_proximity_percent
        score += (1 - proximity_ratio) * self.proximity_bonus_weight

        # 3. Bonificación por Fuerza de la Vela (mucho más grande que el ATR es mejor)
        # strength_ratio es 1 si está justo en el umbral (2x ATR), > 1 si es más grande.
        strength_ratio = candle_data["body_atr_ratio"] / self.elephant_atr_multiplier
        # Se añade un bono limitado por la fuerza extra de la vela.
        score += min(1.0, strength_ratio - 1.0) * self.candle_bonus_weight
        
        return min(100.0, max(0.0, score))

    async def generate_signal(self, symbol: str, df: pd.DataFrame, regime: MarketRegime) -> Optional[Signal]:
        """
        Analiza los datos de un mercado y, si cumple las condiciones, genera,
        guarda y notifica una señal de trading.

        Esta función asume que el DataFrame `df` viene del ScannerEngine y ya
        contiene las columnas pre-calculadas: 'sma_200', 'sma_20', 'atr'.

        Args:
            symbol: Símbolo del instrumento (e.g., 'EURUSD').
            df: DataFrame con datos OHLC e indicadores ('sma_200', 'sma_20', 'atr').
            regime: Régimen actual del mercado.

        Returns:
            Un objeto Signal si se genera una oportunidad, o None.
        """
        required_cols = ['open', 'high', 'low', 'close', f'sma_{self.sma_short_p}', f'sma_{self.sma_long_p}', 'atr']
        if df is None or len(df) < 2 or not all(col in df.columns for col in required_cols):
            logger.debug(f"[{symbol}] Datos insuficientes o columnas faltantes para generar señal.")
            return None

        try:
            latest_candle = df.iloc[-1]
            
            # --- Validación de la Estrategia Oliver Vélez (Bullish) ---
            is_bullish_trend = latest_candle['close'] > latest_candle[f'sma_{self.sma_long_p}']
            
            candle_body = abs(latest_candle['close'] - latest_candle['open'])
            body_atr_ratio = candle_body / latest_candle['atr'] if latest_candle['atr'] > 0 else 0
            is_elephant_body = body_atr_ratio > self.elephant_atr_multiplier
            
            sma20_dist_pct = abs(latest_candle['close'] - latest_candle[f'sma_{self.sma_short_p}']) / latest_candle[f'sma_{self.sma_short_p}'] * 100
            is_near_sma20 = sma20_dist_pct < self.sma20_proximity_percent
            
            is_bullish_candle = latest_candle['close'] > latest_candle['open']

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
                logger.debug(f"[{symbol}] No cumple condiciones de señal Oliver Vélez. Score: 0")
                return None

            # --- Creación del objeto Signal ---
            current_price = latest_candle['close']
            membership_tier = self._determine_membership_tier(score)
            
            # Gestión de Riesgo (ejemplo simple basado en ATR)
            stop_loss = current_price - (1.5 * latest_candle['atr'])
            take_profit = current_price + (3.0 * latest_candle['atr']) # Ratio 2:1

            signal = Signal(
                connector=ConnectorType.NINJATRADER, # Asumimos un conector por defecto
                symbol=symbol,
                signal_type=SignalType.BUY, # Lógica de venta a implementar
                price=current_price,
                timestamp=datetime.now(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                regime=regime,
                strategy_id=self.strategy_id,
                score=score,
                membership_tier=membership_tier,
                is_elephant_candle=is_elephant_body,
                near_sma20=is_near_sma20,
                metadata={
                    "body_atr_ratio": round(body_atr_ratio, 2),
                    "sma20_dist_pct": round(sma20_dist_pct, 2),
                    "atr": round(latest_candle['atr'], 5),
                    "sma_20": round(latest_candle[f'sma_{self.sma_short_p}'], 5),
                    "sma_200": round(latest_candle[f'sma_{self.sma_long_p}'], 5),
                }
            )

            # --- Persistencia y Notificación ---
            try:
                signal_id = self.storage_manager.save_signal(signal)
                logger.info(
                    f"SEÑAL GENERADA [ID: {signal_id}] -> {signal.symbol} {signal.signal_type.value} @ {signal.price:.5f} | "
                    f"Score: {signal.score:.1f} ({signal.membership_tier.value})"
                )
            except Exception as e:
                logger.error(f"[{symbol}] Error al guardar la señal en la base de datos: {e}")
                return None # No notificar si no se pudo guardar

            if self.notifier and membership_tier in [MembershipTier.PREMIUM, MembershipTier.ELITE]:
                logger.debug(f"[{symbol}] Disparando notificación PREMIUM para señal con score {score:.1f}")
                # Usamos create_task para no bloquear el bucle principal del scanner
                asyncio.create_task(
                    self.notifier.notify_oliver_velez_signal(signal, membership=MembershipLevel.PREMIUM)
                )

            return signal

        except Exception as e:
            logger.error(f"Error generando señal para {symbol}: {e}", exc_info=True)
            return None
            
    async def generate_signals_batch(self, scan_results: Dict[str, Dict]) -> List[Signal]:
        """
        Procesa un lote de resultados del ScannerEngine y genera señales.

        Args:
            scan_results: Diccionario {symbol: {"regime": MarketRegime, "df": DataFrame}}

        Returns:
            Una lista de objetos Signal generados.
        """
        tasks = [
            self.generate_signal(symbol, data.get("df"), data.get("regime"))
            for symbol, data in scan_results.items()
            if data.get("regime") and data.get("df") is not None
        ]
        
        generated_signals = await asyncio.gather(*tasks)
        
        # Filtrar los resultados None
        signals = [s for s in generated_signals if s is not None]
        
        if signals:
            logger.info(f"Batch completado. {len(signals)} señales generadas de {len(scan_results)} símbolos analizados.")
        
        return signals

    def filter_by_membership(self, signals: List[Signal], user_tier: MembershipTier) -> List[Signal]:
        """Filtra una lista de señales según el tier de membresía del usuario."""
        tier_order = {
            MembershipTier.FREE: 0,
            MembershipTier.PREMIUM: 1,
            MembershipTier.ELITE: 2
        }
        user_level = tier_order.get(user_tier, 0)
        
        filtered = [s for s in signals if tier_order.get(s.membership_tier, 0) <= user_level]
        
        logger.debug(f"Filtrando {len(signals)} señales para tier {user_tier.value}. Disponibles: {len(filtered)}")
        return filtered