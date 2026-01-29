"""
Signal Factory - Motor de Generación de Señales para Aethelgard
==============================================================

Refactorizado a Patrón Strategy (Fase 2.2).
Actúa como orquestador que delega la lógica de análisis a estrategias específicas
(e.g., OliverVelezStrategy) y gestiona la persistencia y notificación centralizada.
"""
import logging
import asyncio
import json
from typing import Dict, List, Optional

import pandas as pd

from models.signal import (
    Signal, MarketRegime, MembershipTier
)
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier, TelegramNotifier
from core_brain.module_manager import MembershipLevel

# Import strategies
from core_brain.strategies.base_strategy import BaseStrategy
from core_brain.strategies.oliver_velez import OliverVelezStrategy

logger = logging.getLogger(__name__)

class SignalFactory:
    """
    Orquestador de estrategias.
    
    Responsabilidades:
    1. Administrar lista de estrategias activas.
    2. Recibir datos del Scanner.
    3. Delegar análisis a cada estrategia.
    4. Persistir señales generadas.
    5. Notificar señales generadas.
    """

    def __init__(
        self,
        storage_manager: StorageManager,
        config_path: str = "config/dynamic_params.json",
        strategy_id: str = "deprecated", # Mantenido por compatibilidad
    ):
        """
        Inicializa la SignalFactory.

        Args:
            storage_manager: Instancia del gestor de persistencia.
            config_path: Ruta a dynamic_params.json.
            strategy_id: Deprecado. Las estrategias se cargan internamente.
        """
        self.storage_manager = storage_manager
        self.notifier: Optional[TelegramNotifier] = get_notifier()
        self.config_path = config_path
        
        # Cargar parámetros generales
        self.config_data = self._load_parameters()
        
        # Inicializar estrategias
        self.strategies: List[BaseStrategy] = []
        self._register_default_strategies()
        
        if not self.notifier or not self.notifier.is_configured():
            logger.warning("Notificador de Telegram no está configurado. No se enviarán alertas.")

        logger.info(f"SignalFactory initialized with {len(self.strategies)} strategies.")

    def _load_parameters(self) -> Dict:
        """Carga parámetros desde dynamic_params.json"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config not found: {self.config_path}. Using defaults.")
            return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using empty config.")
            return {}

    def _register_default_strategies(self):
        """Registra las estrategias por defecto."""
        # En el futuro, esto podría ser dinámico o vía plugin
        try:
            ov_strategy = OliverVelezStrategy(self.config_data)
            self.strategies.append(ov_strategy)
            logger.info(f"Strategy registered: {ov_strategy.strategy_id}")
        except Exception as e:
            logger.error(f"Failed to register OliverVelezStrategy: {e}", exc_info=True)

    async def generate_signal(
        self, symbol: str, df: pd.DataFrame, regime: MarketRegime
    ) -> List[Signal]:
        """
        Analiza un símbolo con TODAS las estrategias registradas.
        
        Args:
            symbol: Símbolo del activo.
            df: DataFrame con datos OHLC.
            regime: Régimen actual del mercado.

        Returns:
            Lista de señales generadas (puede estar vacía).
        """
        generated_signals = []
        
        for strategy in self.strategies:
            try:
                # Delegar análisis a la estrategia
                signal = await strategy.analyze(symbol, df, regime)
                
                if signal:
                    # Validar que no sea duplicado antes de procesar
                    if self._is_duplicate_signal(signal):
                        logger.info(
                            f"[{symbol}] Señal {signal.signal_type} descartada: "
                            f"ya existe posición abierta o señal reciente"
                        )
                        continue
                    
                    # Procesar señal válida
                    await self._process_valid_signal(signal)
                    generated_signals.append(signal)
            
            except Exception as e:
                logger.error(
                    f"Error running strategy {strategy.strategy_id} on {symbol}: {e}", 
                    exc_info=True
                )

        return generated_signals

    def _is_duplicate_signal(self, signal: Signal) -> bool:
        """
        Verifica si la señal es un duplicado.
        
        Criterios:
        - Ya existe una posición abierta para el símbolo
        - Ya existe una señal reciente (ventana dinámica según timeframe)
        
        Args:
            signal: Señal a validar
        
        Returns:
            True si es duplicado, False si es válida
        """
        signal_type_str = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        
        # Verificar posición abierta
        if self.storage_manager.has_open_position(signal.symbol):
            return True
        
        # Verificar señal reciente (ventana dinámica basada en timeframe)
        if self.storage_manager.has_recent_signal(
            symbol=signal.symbol, 
            signal_type=signal_type_str, 
            timeframe=signal.timeframe
        ):
            return True
        
        return False

    async def _process_valid_signal(self, signal: Signal):
        """Maneja persistencia y notificación de una señal válida."""
        try:
            # 1. Persistencia
            signal_id = self.storage_manager.save_signal(signal)
            logger.info(
                f"SEÑAL GENERADA [ID: {signal_id}] -> {signal.symbol} "
                f"{signal.signal_type} @ {signal.entry_price:.5f} | "
                f"Strategy: {signal.metadata.get('strategy_id')} | "
                f"Score: {signal.metadata.get('score', 0):.1f}"
            )
            
            # 2. Notificación
            # TODO: Hacer esto más genérico en el futuro
            if self.notifier:
                # Determinar membership level basado en signal metadata
                membership_tier_str = signal.metadata.get("membership_tier", "FREE")
                try:
                    membership_tier = MembershipTier(membership_tier_str)
                except ValueError:
                    membership_tier = MembershipTier.FREE
                
                # Mapear MembershipTier a MembershipLevel (si son distintos enums)
                # Asumimos que MembershipLevel tiene PREMIUM y BASIC
                notif_membership = MembershipLevel.BASIC
                if membership_tier in [MembershipTier.PREMIUM, MembershipTier.ELITE]:
                    notif_membership = MembershipLevel.PREMIUM

                if membership_tier in [MembershipTier.PREMIUM, MembershipTier.ELITE]:
                    logger.debug(f"[{signal.symbol}] Disparando notificación PREMIUM")
                    
                    if signal.metadata.get("strategy_id") == "oliver_velez_swing_v2":
                        asyncio.create_task(
                            self.notifier.notify_oliver_velez_signal(
                                signal, membership=notif_membership
                            )
                        )
                    else:
                        # Fallback para otras estrategias (provisional)
                        # asyncio.create_task(self.notifier.notify_generic_signal(signal))
                        pass

        except Exception as e:
            logger.error(f"Error processing valid signal for {signal.symbol}: {e}")

    async def generate_signals_batch(
        self, scan_results: Dict[str, Dict]
    ) -> List[Signal]:
        """
        Procesa un lote de resultados del ScannerEngine y genera señales.

        Args:
            scan_results: validez con {symbol: {"regime": MarketRegime, "df": DataFrame}}

        Returns:
            Lista plana de todas las señales generadas.
        """
        tasks = [
            self.generate_signal(s, d.get("df"), d.get("regime"))
            for s, d in scan_results.items()
            if d.get("regime") and d.get("df") is not None
        ]

        if not tasks:
            return []

        # results es una lista de listas de señales: [[s1, s2], [], [s3]]
        results = await asyncio.gather(*tasks)
        
        # Aplanar lista
        all_signals = []
        for batch in results:
            all_signals.extend(batch)

        if all_signals:
            logger.info(
                f"Batch completado. {len(all_signals)} señales generadas de "
                f"{len(scan_results)} símbolos analizados."
            )

        return all_signals

    async def process_scan_results(self, scan_results: Dict[str, MarketRegime]) -> List[Signal]:
        """
        Método de compatibilidad/logging. 
        MainOrchestrator ahora usa generate_signals_batch directamente con datos.
        """
        logger.debug("process_scan_results called (metadata only)")
        return []

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
            # Se asume que signal.membership_tier es un enum MembershipTier
            if tier_order.get(MembershipTier(s.metadata.get("membership_tier", "FREE")), 0) <= user_level
        ]
        return filtered
