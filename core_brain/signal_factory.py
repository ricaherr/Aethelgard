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
from typing import Dict, List, Optional, Any
from collections import defaultdict

import pandas as pd

from models.signal import (
    Signal, SignalType, MarketRegime, MembershipTier, ConnectorType
)
from data_vault.storage import StorageManager
from core_brain.notification_service import NotificationService, NotificationCategory
from core_brain.notificator import get_notifier, NotificationEngine
from core_brain.module_manager import MembershipLevel
from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
from core_brain.tech_utils import TechnicalAnalyzer
from core_brain.services.fundamental_guard import FundamentalGuardService
from core_brain.signal_converter import StrategySignalConverter
from core_brain.signal_enricher import SignalEnricher
from core_brain.signal_deduplicator import SignalDeduplicator
from core_brain.signal_conflict_analyzer import SignalConflictAnalyzer
from core_brain.signal_trifecta_optimizer import SignalTrifectaOptimizer

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
        strategy_engines: Dict[str, Any],
        confluence_analyzer: MultiTimeframeConfluenceAnalyzer,
        trifecta_analyzer: TrifectaAnalyzer,
        notification_service: Optional[NotificationService] = None,
        mt5_connector: Optional[Any] = None,
        fundamental_guard: Optional[FundamentalGuardService] = None,
        execution_feedback_collector: Optional[Any] = None,
        instrument_manager: Optional[Any] = None,
    ):
        """
        Inicializa la SignalFactory con inyección de dependencias estricta.

        Args:
            storage_manager: Instancia del gestor de persistencia.
            strategy_engines: Dict[strategy_id: engine] compiladas por StrategyEngineFactory.
            confluence_analyzer: Analizador de confluencia inyectado.
            trifecta_analyzer: Analizador de trifecta inyectado.
            notification_service: Servicio de notificación opcional.
            mt5_connector: Opcional MT5 connector para reconciliación.
            fundamental_guard: Opcional FundamentalGuardService para veto por noticias.
            execution_feedback_collector: Opcional ExecutionFeedbackCollector para autonomous learning (DOMINIO-10).
        """
        self.storage_manager = storage_manager
        self.notifier: Optional[NotificationEngine] = get_notifier()
        self.internal_notifier = notification_service
        self.mt5_connector = mt5_connector
        self.execution_feedback_collector = execution_feedback_collector  # For signal suppression
        self.instrument_manager = instrument_manager  # SSOT for enabled symbols (HU 3.9)
        
        # Inyectar FundamentalGuardService o crear uno si no está disponible
        if fundamental_guard is None:
            try:
                self.fundamental_guard = FundamentalGuardService(storage=storage_manager)
            except Exception as e:
                logger.warning(f"[SignalFactory] Failed to initialize FundamentalGuardService: {e}")
                self.fundamental_guard = None
        else:
            self.fundamental_guard = fundamental_guard
        
        # Cargar parámetros generales desde DB (SSOT)
        self.config_data = self.storage_manager.get_dynamic_params()
        
        # Motores de estrategia inyectados (Dict en memoria - compilados una sola vez)
        self.strategy_engines = strategy_engines
        
        # Analizadores inyectados
        self.confluence_analyzer = confluence_analyzer
        self.trifecta_analyzer = trifecta_analyzer
        
        # Inyectar Signal Converter y Enricher (NUEVA INFRAESTRUCTURA)
        self.signal_converter = StrategySignalConverter()
        self.signal_enricher = SignalEnricher(
            storage_manager=storage_manager,
            fundamental_guard=self.fundamental_guard
        )
        
        # Inyectar módulos Phase 2 de fragmentación
        self.signal_deduplicator = SignalDeduplicator(
            storage_manager=storage_manager,
            mt5_connector=mt5_connector
        )
        self.signal_conflict_analyzer = SignalConflictAnalyzer(
            confluence_analyzer=confluence_analyzer
        )
        self.signal_trifecta_optimizer = SignalTrifectaOptimizer(
            trifecta_analyzer=trifecta_analyzer
        )
        
        if not self.notifier or not self.notifier.is_configured():
            logger.info("NotificationEngine no está configurado o no tiene canales activos.")

        logger.info(
            f"SignalFactory initialized with {len(self.strategy_engines)} injected engines. "
            f"Confluence enabled: {self.confluence_analyzer.enabled} | "
            f"FundamentalGuard: {'enabled' if self.fundamental_guard else 'disabled'}"
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

    def _register_default_usr_strategies(self) -> None:
        """DEPRECATED: Todas las estrategias se cargan dinámicamente desde StrategyEngineFactory."""
        logger.debug("[DEPRECATED] _register_default_usr_strategies() is now obsolete")

    async def generate_signal(
        self, symbol: str, df: pd.DataFrame, regime: MarketRegime, timeframe: Optional[str] = None, 
        trace_id: Optional[str] = None, provider_source: Optional[str] = None
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
        generated_usr_signals = []
        
        for strategy_id, engine in self.strategy_engines.items():
            try:
                # Logging: Resumen del DataFrame antes de analizar
                if df is not None:
                    logger.info(f"[DEBUG][DF][{strategy_id}] {symbol}: df.shape={getattr(df, 'shape', 'N/A')}, head=\n{df.head(2) if hasattr(df, 'head') else 'N/A'}")
                else:
                    logger.info(f"[DEBUG][DF][{strategy_id}] {symbol}: df=None")

                # Delegar análisis al motor compilado
                # Hay dos tipos: PYTHON_CLASS usr_strategies (con .analyze) y JSON_SCHEMA (con .execute_from_registry)
                # Chequear primero por execute_from_registry (específico de JSON_SCHEMA)
                if hasattr(engine, 'execute_from_registry') and callable(getattr(engine, 'execute_from_registry', None)):
                    # JSON_SCHEMA strategy: use UniversalStrategyEngine.execute_from_registry()
                    result = await engine.execute_from_registry(strategy_id, symbol, df, regime)
                    signal = StrategySignalConverter.convert_from_universal_engine(
                        result, symbol, strategy_id, timeframe, trace_id, provider_source
                    )
                elif hasattr(engine, 'analyze') and callable(getattr(engine, 'analyze', None)):
                    # PYTHON_CLASS strategy: directly call analyze()
                    raw_signal = await engine.analyze(symbol, df, regime)
                    # Logging: Motivo si no hay señal
                    if raw_signal is None:
                        logger.info(f"[DEBUG][{strategy_id}] {symbol}: analyze() no generó señal (raw_signal=None)")
                    signal = StrategySignalConverter.convert_from_python_class(
                        raw_signal, symbol, strategy_id, timeframe, trace_id, provider_source
                    )
                else:
                    logger.warning(f"[{symbol}] Strategy engine {strategy_id} has neither analyze() nor execute_from_registry() method")
                    continue
                
                if signal:
                    # Set metadata fields if provided
                    if timeframe:
                        signal.timeframe = timeframe
                    if trace_id:
                        signal.trace_id = trace_id
                    if provider_source:
                        signal.provider_source = provider_source
                    
                    # Validar que no sea duplicado antes de procesar
                    if self.signal_deduplicator.is_duplicate(signal):
                        logger.info(
                            f"[{symbol}] Señal {signal.signal_type} descartada: "
                            f"ya existe posición abierta o señal reciente"
                        )
                        continue
                    
                    # Procesar señal válida
                    await self._process_valid_signal(signal)
                    
                    # MILESTONE 6.3: Volatility Disconnect tagging
                    try:
                        vol_disconnect = TechnicalAnalyzer.calculate_volatility_disconnect(df)
                        signal.metadata["volatility_disconnect"] = vol_disconnect
                        if vol_disconnect["is_burst"]:
                            signal.metadata["volatility_tag"] = "HIGH_VOLATILITY_BURST"
                            logger.info(
                                f"[{symbol}] HIGH_VOLATILITY_BURST tagged: "
                                f"RV/HV ratio={vol_disconnect['disconnect_ratio']:.2f}x"
                            )
                    except Exception as vol_err:
                        logger.debug(f"[{symbol}] Volatility disconnect skipped: {vol_err}")
                    
                    # MILESTONE 6.3: FVG Detection enrichment
                    try:
                        fvg_result = TechnicalAnalyzer.detect_fvg(df)
                        if not fvg_result.empty:
                            last_fvg = fvg_result.iloc[-1]
                            signal.metadata["fvg_bullish"] = bool(last_fvg.get("fvg_bullish", False))
                            signal.metadata["fvg_bearish"] = bool(last_fvg.get("fvg_bearish", False))
                            signal.metadata["fvg_gap_size"] = float(last_fvg.get("fvg_gap_size", 0.0))
                    except Exception as fvg_err:
                        logger.debug(f"[{symbol}] FVG detection skipped: {fvg_err}")
                    
                    # ──────────────────────────────────────────────────────────────────────────────────
                    # ACCIÓN 2: Enriquecimiento con Reasoning y Affinity Score (UI Real-Time Feed)
                    # ──────────────────────────────────────────────────────────────────────────────────
                    await self.signal_enricher.enrich(signal, symbol, strategy_id)
                    
                    # CHECK EXECUTION FEEDBACK: Suppress if symbol/strategy failing repeatedly
                    if not self._should_suppress_signal(signal):
                        generated_usr_signals.append(signal)
                    else:
                        logger.debug(f"[EXEC-FEEDBACK] Signal {signal.symbol} suppressed by feedback learning")
            
            except Exception as e:
                logger.error(
                    f"Error running strategy {strategy_id} on {symbol}: {e}", 
                    exc_info=True
                )

        return generated_usr_signals



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
            
            # 0.5. Determine execution_mode (SHADOW/LIVE) from strategy_id
            # PHASE E: Signal persistence now tracks whether signal was generated in SHADOW or LIVE mode
            strategy_id = signal.metadata.get('strategy_id') if signal.metadata else None
            origin_mode = 'SHADOW'  # Safe default: unknown strategy = testing mode (no live trading)
            if strategy_id:
                try:
                    ranking = self.storage_manager.get_signal_ranking(strategy_id)
                    if ranking and 'execution_mode' in ranking:
                        origin_mode = ranking['execution_mode']
                        logger.debug(f"[SIGNAL-ORIGIN] {strategy_id} mode={origin_mode}")
                except Exception as e:
                    logger.warning(f"Failed to determine execution_mode for {strategy_id}: {e}")
            
            # 1. Persistencia (guarda con status='PENDING' y origin_mode=SHADOW/LIVE)
            signal_id = self.storage_manager.save_signal(signal, origin_mode=origin_mode)
            
            # CLAVE: Asignar ID al objeto Signal para que Executor lo use (evita duplicados)
            signal.metadata['signal_id'] = signal_id
            
            logger.info(
                f"SEÑAL GENERADA [ID: {signal_id}] -> {signal.symbol} "
                f"{signal.signal_type} @ {signal.entry_price:.5f} | "
                f"Strategy: {signal.metadata.get('strategy_id')} | "
                f"Origin: {origin_mode} | "
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
                
                # 3. Notificación Interna (Persistente)
                if self.internal_notifier:
                    self.internal_notifier.create_notification(
                        category=NotificationCategory.SIGNAL,
                        context={
                            "signal_id": signal_id,
                            "symbol": signal.symbol,
                            "type": signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type),
                            "price": signal.entry_price,
                            "score": signal.metadata.get('score', 0),
                            "timeframe": signal.timeframe or "UNKNOWN",
                            "strategy": signal.metadata.get('strategy_id', "UNKNOWN")
                        }
                    )

        except Exception as e:
            logger.error(f"Error processing valid signal for {signal.symbol}: {e}")

    async def generate_usr_signals_batch(
        self, scan_results: Dict[str, Dict], trace_id: Optional[str] = None
    ) -> List[Signal]:
        """
        Procesa un lote de resultados del ScannerEngine y genera señales.
        
        FASE 2.5: Aplica confluencia multi-timeframe para reforzar/penalizar señales.
        FASE 4: Filtra signals por usr_assets_cfg (solo genera para assets habilitados).

        Args:
            scan_results: Dict con "symbol|timeframe" -> {"regime": MarketRegime, "df": DataFrame, "symbol": str, "timeframe": str}

        Returns:
            Lista plana de todas las señales generadas (con confluencia aplicada).
        """
        try:
            logger.info(f"DEBUG: generate_usr_signals_batch called with {len(scan_results)} items")
            tasks = []
            
            if not self.strategy_engines:
                logger.error("DEBUG: No strategy engines in SignalFactory!")
                return []
            logger.info(f"DEBUG: Engines available: {list(self.strategy_engines.keys())}")

            # FASE 4: Enabled symbol filter — SSOT via InstrumentManager (HU 3.9)
            if self.instrument_manager is not None:
                try:
                    enabled_symbols = self.instrument_manager.get_enabled_symbols()
                    logger.info(f"[FASE4] Enabled symbols (InstrumentManager): {len(enabled_symbols)}")
                except Exception as e:
                    logger.warning(f"[FASE4] InstrumentManager.get_enabled_symbols() failed: {e} — no filter")
                    enabled_symbols = None
            else:
                enabled_symbols = None  # No filter — generate for all scanned symbols
            
            skipped_count = 0
            
            for key, data in scan_results.items():
                regime = data.get("regime")
                df = data.get("df")
                symbol = data.get("symbol")  # Extraer symbol del dict
                timeframe = data.get("timeframe")  # Extraer timeframe del dict

                # Logging: Resumen del DataFrame
                if df is not None:
                    logger.info(f"[DEBUG][DF] {symbol}|{timeframe}: df.shape={getattr(df, 'shape', 'N/A')}, columns={list(df.columns) if hasattr(df, 'columns') else 'N/A'}")
                else:
                    logger.info(f"[DEBUG][DF] {symbol}|{timeframe}: df=None")

                # FASE 4: Filter by enabled assets
                if enabled_symbols is not None and symbol not in enabled_symbols:
                    logger.debug(f"[FASE4] Skipping {symbol}: not in enabled asset config")
                    skipped_count += 1
                    continue

                if regime and df is not None and symbol:
                    provider_source = data.get("provider_source", "UNKNOWN")
                    tasks.append(self.generate_signal(
                        symbol, df, regime, timeframe, trace_id, provider_source
                    ))

            if skipped_count > 0:
                logger.info(f"[FASE4] Skipped {skipped_count} symbols not in asset configuration")

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
            all_usr_signals = []
            for batch in results:
                all_usr_signals.extend(batch)

            logger.info(f"DEBUG: Raw usr_signals generated: {len(all_usr_signals)}")

            # FASE 2.5: Apply Multi-Timeframe Confluence
            if all_usr_signals and self.confluence_analyzer.enabled:
                all_usr_signals = self.signal_conflict_analyzer.apply_confluence(all_usr_signals, scan_results)
            
            # FASE 2.6: Apply Trifecta Optimization (Oliver Velez Multi-TF)
            if all_usr_signals:
                all_usr_signals = self.signal_trifecta_optimizer.optimize(all_usr_signals, scan_results)
            
            # FASE 2.7: Apply Execution Feedback Suppression (DOMINIO-10 Auto-Healing)
            if all_usr_signals and self.execution_feedback_collector:
                before_suppression = len(all_usr_signals)
                all_usr_signals = [
                    s for s in all_usr_signals 
                    if not self._should_suppress_signal(s)
                ]
                if before_suppression > len(all_usr_signals):
                    logger.info(
                        f"[EXEC-FEEDBACK] Suppressed {before_suppression - len(all_usr_signals)} signals "
                        f"based on execution feedback learning"
                    )

            if all_usr_signals:
                logger.info(
                    f"Batch completado. {len(all_usr_signals)} señales generadas de "
                    f"{len(scan_results)} instrumentos analizados (multi-timeframe)."
                )

            return all_usr_signals
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR in generate_usr_signals_batch: {e}", exc_info=True)
            return []

    async def process_scan_results(self, scan_results: Dict[str, MarketRegime]) -> List[Signal]:
        """
        Método de compatibilidad/logging. 
        MainOrchestrator ahora usa generate_usr_signals_batch directamente con datos.
        """
        logger.debug("process_scan_results called (metadata only)")
        return []

    def filter_by_membership(
        self, usr_signals: List[Signal], user_tier: MembershipTier
    ) -> List[Signal]:
        """Filtra señales según el tier de membresía del usuario."""
        tier_order = {
            MembershipTier.FREE: 0,
            MembershipTier.PREMIUM: 1,
            MembershipTier.ELITE: 2
        }
        user_level = tier_order.get(user_tier, 0)

        filtered = [
            s for s in usr_signals
            # Se asume que signal.membership_tier es un enum MembershipTier
            if tier_order.get(MembershipTier(s.metadata.get("membership_tier", "FREE")), 0) <= user_level
        ]
        return filtered    
    def _should_suppress_signal(self, signal: Signal) -> bool:
        """
        Check if a signal should be suppressed based on execution feedback history.
        
        Part of DOMINIO-10 (INFRA_RESILIENCY): Autonomous learning loop.
        Signs are suppressed if:
        - Symbol has >3 recent failures
        - Strategy has >2 recent failures
        
        Args:
            signal: Signal to evaluate
        
        Returns:
            True if signal should be suppressed, False otherwise
        """
        if not self.execution_feedback_collector:
            return False  # No feedback collector, don't suppress
        
        symbol = signal.symbol
        strategy = getattr(signal, 'strategy', None)
        
        # Check symbol failure rate
        symbol_metrics = self.execution_feedback_collector.get_symbol_failure_metrics(symbol)
        if symbol_metrics.get('should_suppress', False):
            logger.warning(
                f"[SUPPRESS] Signal for {symbol} suppressed: "
                f"Symbol has {symbol_metrics['failure_count']} recent failures | "
                f"Streak: {symbol_metrics['failure_streak']}"
            )
            return True
        
        # Check strategy failure rate
        if strategy:
            strategy_metrics = self.execution_feedback_collector.get_strategy_failure_metrics(strategy)
            if strategy_metrics.get('should_suppress', False):
                logger.warning(
                    f"[SUPPRESS] Signal from strategy {strategy} suppressed: "
                    f"Strategy has {strategy_metrics['failure_count']} recent failures | "
                    f"Streak: {strategy_metrics['failure_streak']}"
                )
                return True
        
        return False