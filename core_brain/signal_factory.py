"""
Signal Factory - Motor de Generación de Señales para Aethelgard
==============================================================

Refactorizado a Patrón Strategy (Fase 2.2).
Actúa como orquestador que delega la lógica de análisis a estrategias específicas
(e.g., OliverVelezStrategy) y gestiona la persistencia y notificación centralizada.

FASE 2.5: Multi-Timeframe Confluence Integration
Signals are reinforced or penalized based on alignment across timeframes.
EDGE learning optimizes confluence weights automatically.
"""
import logging
import asyncio
import json
from typing import Dict, List, Optional
from collections import defaultdict

import pandas as pd

from models.signal import (
    Signal, MarketRegime, MembershipTier
)
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier, TelegramNotifier
from core_brain.module_manager import MembershipLevel
from core_brain.confluence import MultiTimeframeConfluenceAnalyzer

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
        
        # FASE 2.5: Initialize Multi-Timeframe Confluence Analyzer
        confluence_config = self.config_data.get("confluence", {})
        confluence_enabled = confluence_config.get("enabled", True)
        self.confluence_analyzer = MultiTimeframeConfluenceAnalyzer(
            config_path=config_path,
            enabled=confluence_enabled
        )
        
        if not self.notifier or not self.notifier.is_configured():
            logger.warning("Notificador de Telegram no está configurado. No se enviarán alertas.")

        logger.info(
            f"SignalFactory initialized with {len(self.strategies)} strategies. "
            f"Confluence enabled: {confluence_enabled}"
        )

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
        self, symbol: str, df: pd.DataFrame, regime: MarketRegime, timeframe: Optional[str] = None
    ) -> List[Signal]:
        """
        Analiza un símbolo con TODAS las estrategias registradas.
        
        Args:
            symbol: Símbolo del activo.
            df: DataFrame con datos OHLC.
            regime: Régimen actual del mercado.
            timeframe: Timeframe del análisis (ej: "M5", "H1"). Se incluye en signal metadata.

        Returns:
            Lista de señales generadas (puede estar vacía).
        """
        generated_signals = []
        
        for strategy in self.strategies:
            try:
                # Delegar análisis a la estrategia
                signal = await strategy.analyze(symbol, df, regime)
                
                if signal:
                    # Set timeframe in signal if provided
                    if timeframe:
                        signal.timeframe = timeframe
                    
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
        
        Criterios de deduplicación (clave única: symbol + signal_type + timeframe):
        - Ya existe una posición abierta para el símbolo
        - Ya existe una señal reciente para el mismo (symbol, signal_type, timeframe)
        
        Esto permite señales del MISMO instrumento en DIFERENTES timeframes.
        Ejemplo: EURUSD BUY en M5 (scalping) y EURUSD BUY en H4 (swing) son válidas simultáneamente.
        
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
        
        FASE 2.5: Aplica confluencia multi-timeframe para reforzar/penalizar señales.

        Args:
            scan_results: Dict con "symbol|timeframe" -> {"regime": MarketRegime, "df": DataFrame, "symbol": str, "timeframe": str}

        Returns:
            Lista plana de todas las señales generadas (con confluencia aplicada).
        """
        tasks = []
        for key, data in scan_results.items():
            regime = data.get("regime")
            df = data.get("df")
            symbol = data.get("symbol")  # Extraer symbol del dict
            timeframe = data.get("timeframe")  # Extraer timeframe del dict
            
            if regime and df is not None and symbol:
                # Pass both symbol and timeframe to strategies
                # Strategies will use timeframe for signal metadata
                tasks.append(self.generate_signal(symbol, df, regime, timeframe))

        if not tasks:
            return []

        # results es una lista de listas de señales: [[s1, s2], [], [s3]]
        results = await asyncio.gather(*tasks)
        
        # Aplanar lista
        all_signals = []
        for batch in results:
            all_signals.extend(batch)

        # FASE 2.5: Apply Multi-Timeframe Confluence
        if all_signals and self.confluence_analyzer.enabled:
            all_signals = self._apply_confluence(all_signals, scan_results)

        if all_signals:
            logger.info(
                f"Batch completado. {len(all_signals)} señales generadas de "
                f"{len(scan_results)} instrumentos analizados (multi-timeframe)."
            )

        return all_signals
    
    def _apply_confluence(
        self, 
        signals: List[Signal], 
        scan_results: Dict[str, Dict]
    ) -> List[Signal]:
        """
        Apply multi-timeframe confluence to signals.
        
        Groups signals by symbol, extracts regime from all timeframes,
        and applies confluence analysis.
        
        Args:
            signals: List of generated signals
            scan_results: Original scan data (needed for regime context)
        
        Returns:
            Signals with adjusted confidence based on confluence
        """
        # Group scan results by symbol to get regime context
        symbol_regimes = defaultdict(dict)
        for key, data in scan_results.items():
            symbol = data.get("symbol")
            timeframe = data.get("timeframe")
            regime = data.get("regime")
            
            if symbol and timeframe and regime:
                symbol_regimes[symbol][timeframe] = regime
        
        # Apply confluence to each signal
        adjusted_signals = []
        for signal in signals:
            # Get timeframe regimes for this symbol
            timeframe_regimes = symbol_regimes.get(signal.symbol, {})
            
            # Remove primary signal's timeframe (don't compare M5 to M5)
            primary_timeframe = signal.timeframe
            higher_timeframes = {
                tf: regime 
                for tf, regime in timeframe_regimes.items() 
                if tf != primary_timeframe
            }
            
            if higher_timeframes:
                # Apply confluence
                adjusted_signal = self.confluence_analyzer.analyze_confluence(
                    signal, higher_timeframes
                )
                adjusted_signals.append(adjusted_signal)
            else:
                # No higher timeframes available, keep signal as-is
                adjusted_signals.append(signal)
        
        return adjusted_signals

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
