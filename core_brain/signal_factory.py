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
    Signal, MarketRegime, MembershipTier, ConnectorType
)
from data_vault.storage import StorageManager
from core_brain.notificator import get_notifier, NotificationEngine
from core_brain.module_manager import MembershipLevel
from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
from core_brain.strategies.trifecta_logic import TrifectaAnalyzer

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
        strategies: List[BaseStrategy],
        confluence_analyzer: MultiTimeframeConfluenceAnalyzer,
        trifecta_analyzer: TrifectaAnalyzer,
        mt5_connector: Optional[Any] = None,
    ):
        """
        Inicializa la SignalFactory con inyección de dependencias estricta.

        Args:
            storage_manager: Instancia del gestor de persistencia.
            strategies: Lista de estrategias inyectadas.
            confluence_analyzer: Analizador de confluencia inyectado.
            trifecta_analyzer: Analizador de trifecta inyectado.
            mt5_connector: Opcional MT5 connector para reconciliación.
        """
        self.storage_manager = storage_manager
        self.notifier: Optional[NotificationEngine] = get_notifier()
        self.mt5_connector = mt5_connector
        
        # Cargar parámetros generales desde DB (SSOT)
        self.config_data = self.storage_manager.get_dynamic_params()
        
        # Estrategias inyectadas
        self.strategies = strategies
        
        # Analizadores inyectados
        self.confluence_analyzer = confluence_analyzer
        self.trifecta_analyzer = trifecta_analyzer
        
        if not self.notifier or not self.notifier.is_configured():
            logger.warning("NotificationEngine no está configurado o no tiene canales activos.")

        logger.info(
            f"SignalFactory initialized with {len(self.strategies)} injected strategies. "
            f"Confluence enabled: {self.confluence_analyzer.enabled}"
        )

    def set_mt5_connector(self, mt5_connector: Any) -> None:
        """Set MT5 connector for reconciliation (optional)."""
        self.mt5_connector = mt5_connector
        if mt5_connector:
            logger.info("MT5 connector set for SignalFactory reconciliation")
        else:
            logger.debug("MT5 connector cleared from SignalFactory")

    def _load_parameters(self) -> Dict:
        """Deprecado: Usar storage_manager.get_dynamic_params() directamente."""
        return self.storage_manager.get_dynamic_params()

    def _register_default_strategies(self) -> None:
        """Registra las estrategias por defecto."""
        # En el futuro, esto podría ser dinámico o vía plugin
        try:
            ov_strategy = OliverVelezStrategy(self.config_data)
            self.strategies.append(ov_strategy)
            logger.info(f"Strategy registered: {ov_strategy.strategy_id}")
        except Exception as e:
            logger.error(f"Failed to register OliverVelezStrategy: {e}", exc_info=True)

    async def generate_signal(
        self, symbol: str, df: pd.DataFrame, regime: MarketRegime, timeframe: Optional[str] = None, trace_id: Optional[str] = None
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
                    
                    # Set trace_id for pipeline tracking
                    if trace_id:
                        signal.trace_id = trace_id
                    
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
        
        # FASE 2.5 FIX: Normalize symbol BEFORE checking for duplicates
        # Providers send 'GBPUSD=X', but we save 'GBPUSD'.
        # We must check against the NORMALIZED symbol.
        normalized_symbol = signal.symbol
        if signal.connector_type == ConnectorType.METATRADER5:
            try:
                # Lazy import to avoid circular dependency
                from connectors.mt5_connector import MT5Connector
                normalized_symbol = MT5Connector.normalize_symbol(signal.symbol)
            except ImportError:
                # Fallback: simple replace if connector not available
                normalized_symbol = signal.symbol.replace("=X", "")
            except Exception as e:
                logger.warning(f"Normalization failed in is_duplicate_signal: {e}")
        
        # Verificar posición abierta (filtrar por symbol + timeframe)
        if self.storage_manager.has_open_position(normalized_symbol, signal.timeframe):
            # Reconcilia directamente con MT5 reality
            if self.mt5_connector:
                logger.debug(f"[CHECK] Reconciling position for {signal.symbol} with MT5")
                # Get open signal ID
                open_signal_id = self.storage_manager.get_open_signal_id(signal.symbol)
                if open_signal_id:
                    # Check MT5 positions
                    real_positions = self.mt5_connector.get_open_positions()
                    if real_positions is not None:
                        real_symbols = {pos.get('symbol') for pos in real_positions}
                        if normalized_symbol not in real_symbols:
                            # Ghost position detected - clear it
                            self.storage_manager._clear_ghost_position_inline(normalized_symbol)
                            logger.info(f"[CLEAN] Cleared ghost position for {normalized_symbol} (ID: {open_signal_id})")
                            # EDGE Learning
                            self.storage_manager.save_edge_learning(
                                detection=f"Discrepancia DB vs MT5: {signal.symbol} tiene posición en DB pero no en MT5",
                                action_taken="Limpieza de registros fantasma",
                                learning="El delay de cierre en MT5 es de 200ms, ajustar timeout",
                                details=f"Signal ID: {open_signal_id}"
                            )
                        else:
                            # Position exists in MT5, keep as is
                            pass
                    else:
                        logger.warning("Failed to get MT5 positions for reconciliation")
                # Check again after reconciliation
                if self.storage_manager.has_open_position(signal.symbol):
                    # Volcado por excepción técnica: posición abierta
                    score = signal.metadata.get('score', 0)
                    lot_size = signal.volume
                    risk_usd = abs(signal.entry_price - signal.stop_loss) * lot_size * 100000
                    ghost_id = self.storage_manager.get_open_signal_id(signal.symbol)
                    dump = {
                        "Razón": "Posición abierta existente",
                        "Score": score,
                        "LotSize": lot_size,
                        "Riesgo_$": round(risk_usd, 2),
                        "ID_Posicion_Existente": ghost_id or "UNKNOWN"
                    }
                    logger.info(f"[DUMP] VOLCADO EXCEPCION: Señal descartada por posición abierta: {dump}")
                    return True
            else:
                # Sin MT5, asumir existe
                score = signal.metadata.get('score', 0)
                lot_size = signal.volume
                risk_usd = abs(signal.entry_price - signal.stop_loss) * lot_size * 100000
                dump = {
                    "Razón": "Posición abierta (sin MT5 para verificar)",
                    "Score": score,
                    "LotSize": lot_size,
                    "Riesgo_$": round(risk_usd, 2),
                    "ID_Posicion_Existente": "UNKNOWN"
                }
                logger.info(f"[DUMP] VOLCADO EXCEPCION: Señal descartada por posición abierta: {dump}")
                return True
        
        # Check DB for recent duplicates using NORMALIZED symbol
        if self.storage_manager.has_recent_signal(
            normalized_symbol, 
            signal_type_str, 
            timeframe=signal.timeframe
        ):
            logger.info(
                f"[DUPLICATE] Signal for {normalized_symbol} ({signal_type_str} {signal.timeframe}) "
                f"skipped (Normalized from {signal.symbol})"
            )
            return True
            
        return False

    async def _process_valid_signal(self, signal: Signal) -> None:
        """Maneja persistencia y notificación de una señal válida."""
        try:
            # 0. Normalize symbol for MT5 (provider → MT5 format) BEFORE saving to DB
            if signal.connector_type == ConnectorType.METATRADER5:
                try:
                    from connectors.mt5_connector import MT5Connector
                    normalized = MT5Connector.normalize_symbol(signal.symbol)
                    if normalized != signal.symbol:
                        logger.debug(f"[FACTORY NORM] {signal.symbol} → {normalized}")
                        if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                            signal.metadata.setdefault("symbol_normalized_from", signal.symbol)
                        signal.symbol = normalized
                except Exception as e:
                    logger.warning(f"Symbol normalization failed in SignalFactory: {e}")
            
            # 1. Persistencia (guarda con status='PENDING' por defecto)
            signal_id = self.storage_manager.save_signal(signal)
            
            # CLAVE: Asignar ID al objeto Signal para que Executor lo use (evita duplicados)
            signal.metadata['signal_id'] = signal_id
            
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
        self, scan_results: Dict[str, Dict], trace_id: Optional[str] = None
    ) -> List[Signal]:
        """
        Procesa un lote de resultados del ScannerEngine y genera señales.
        
        FASE 2.5: Aplica confluencia multi-timeframe para reforzar/penalizar señales.

        Args:
            scan_results: Dict con "symbol|timeframe" -> {"regime": MarketRegime, "df": DataFrame, "symbol": str, "timeframe": str}

        Returns:
            Lista plana de todas las señales generadas (con confluencia aplicada).
        """
        try:
            logger.info(f"DEBUG: generate_signals_batch called with {len(scan_results)} items")
            tasks = []
            
            if not self.strategies:
                logger.error("DEBUG: No strategies registered in SignalFactory!")
                return []
            logger.info(f"DEBUG: Strategies available: {[s.strategy_id for s in self.strategies]}")

            for key, data in scan_results.items():
                regime = data.get("regime")
                df = data.get("df")
                symbol = data.get("symbol")  # Extraer symbol del dict
                timeframe = data.get("timeframe")  # Extraer timeframe del dict
                
                if regime and df is not None and symbol:
                    # Pass both symbol and timeframe to strategies
                    # Strategies will use timeframe for signal metadata
                    tasks.append(self.generate_signal(symbol, df, regime, timeframe, trace_id))

            if not tasks:
                # Diagnóstico detallado: ¿por qué no se crearon tasks?
                empty_keys = []
                for key, data in scan_results.items():
                    regime = data.get("regime")
                    df = data.get("df")
                    symbol = data.get("symbol")
                    timeframe = data.get("timeframe")
                    if not regime:
                        empty_keys.append(f"{key}: regime=None")
                    elif df is None:
                        empty_keys.append(f"{key}: df=None")
                    elif not symbol:
                        empty_keys.append(f"{key}: symbol=None")
                logger.warning(
                    "No tasks created: ningún instrumento elegible para señal. "
                    f"scan_results keys: {list(scan_results.keys())}. "
                    f"Problemas detectados: {empty_keys if empty_keys else 'Todos los datos faltan o vacíos.'}"
                )
                return []

            # results es una lista de listas de señales: [[s1, s2], [], [s3]]
            results = await asyncio.gather(*tasks)
            
            # Aplanar lista
            all_signals = []
            for batch in results:
                all_signals.extend(batch)

            logger.info(f"DEBUG: Raw signals generated: {len(all_signals)}")

            # FASE 2.5: Apply Multi-Timeframe Confluence
            # if all_signals and self.confluence_analyzer.enabled:
            #     all_signals = self._apply_confluence(all_signals, scan_results)
            
            # FASE 2.6: Apply Trifecta Optimization (Oliver Velez Multi-TF)
            # FASE 2.6: Apply Trifecta Optimization
            if all_signals:
                all_signals = self._apply_trifecta_optimization(all_signals, scan_results)

            if all_signals:
                logger.info(
                    f"Batch completado. {len(all_signals)} señales generadas de "
                    f"{len(scan_results)} instrumentos analizados (multi-timeframe)."
                )

            return all_signals
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR in generate_signals_batch: {e}", exc_info=True)
            return []
    
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

    def _apply_trifecta_optimization(
        self, 
        signals: List[Signal], 
        scan_results: Dict[str, Dict]
    ) -> List[Signal]:
        """
        Apply Trifecta Logic (Oliver Velez 2m-5m-15m) to filter and score signals.
        
        Only applies to Oliver Velez strategy signals.
        Recalculates score with 40% original + 60% trifecta.
        Filters out signals with final score < 60.
        
        Args:
            signals: List of generated signals
            scan_results: Original scan data with DataFrames for M1, M5, M15
        
        Returns:
            Filtered and re-scored signals
        """
        optimized_signals = []
        
        # Group market data by symbol for multi-timeframe analysis
        # IMPORTANT: Normalize symbols to match signal.symbol format (remove Yahoo Finance suffix)
        symbol_data = defaultdict(dict)
        for key, data in scan_results.items():
            if data.get("df") is not None:
                # Normalize: "EURUSD=X" -> "EURUSD" to match signal.symbol
                normalized_symbol = data["symbol"].replace("=X", "")
                symbol_data[normalized_symbol][data["timeframe"]] = data["df"]

        for signal in signals:
            # Only apply to Oliver Velez strategy signals
            strategy_id = str(signal.metadata.get("strategy_id", "")).lower()
            if "oliver" in strategy_id:
                market_data = symbol_data.get(signal.symbol, {})
                
                # Analyze Trifecta
                analysis = self.trifecta_analyzer.analyze(signal.symbol, market_data)
                
                if analysis["valid"]:
                    # Check if operating in DEGRADED MODE (fallback)
                    is_degraded = analysis.get("metadata", {}).get("degraded_mode", False)
                    
                    if is_degraded:
                        # HYBRID FALLBACK 2: Pass signal without Trifecta modification
                        signal.metadata["trifecta_degraded"] = True
                        signal.metadata["trifecta_missing_data"] = analysis["metadata"]["missing_timeframes"]
                        
                        logger.warning(
                            f"[WARNING] [{signal.symbol}] Trifecta DEGRADED MODE: "
                            f"Passing original signal without multi-TF filtering. "
                            f"Missing: {analysis['metadata']['missing_timeframes']}"
                        )
                        
                        # Keep original signal as-is (no score modification)
                        optimized_signals.append(signal)
                    else:
                        # FULL TRIFECTA MODE: Apply scoring and filtering
                        signal.metadata["trifecta_score"] = analysis["score"]
                        signal.metadata["trifecta_data"] = analysis["metadata"]
                        
                        # Combine original score with Trifecta score (weighted average)
                        original_score = signal.metadata.get("score", 50.0)
                        final_score = (original_score * 0.4) + (analysis["score"] * 0.6)
                        signal.metadata["score"] = final_score
                        
                        # Update signal confidence (0-1 scale)
                        signal.confidence = final_score / 100.0
                        
                        # Filter: only keep signals with final score >= 60
                        if final_score >= 60.0:
                            optimized_signals.append(signal)
                            logger.info(
                                f"[OK] [{signal.symbol}] Trifecta APPROVED: "
                                f"Original={original_score:.1f}, Trifecta={analysis['score']:.1f}, "
                                f"Final={final_score:.1f}"
                            )
                        else:
                            logger.info(
                                f"[FILTER] [{signal.symbol}] Trifecta FILTERED: "
                                f"Final score {final_score:.1f} < 60 threshold"
                            )
                else:
                    # FULL REJECTION (not degraded mode, but failed validation)
                    logger.info(
                        f"[REJECT] [{signal.symbol}] Trifecta REJECTED: {analysis['reason']}"
                    )
            else:
                # Pass non-Oliver strategies without changes
                optimized_signals.append(signal)
                
        return optimized_signals

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
