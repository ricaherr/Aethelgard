"""
Order Executor Module
Executes trading usr_signals with RiskManager validation and agnostic connector routing.
Aligned with Aethelgard's principles: Autonomy, Resilience, Agnosticism, and Security.
"""
import asyncio
import logging
import json
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path

from models.signal import Signal, ConnectorType
from core_brain.risk_manager import RiskManager
from core_brain.risk_calculator import RiskCalculator
from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
from data_vault.storage import StorageManager
from core_brain.notification_service import NotificationService, NotificationCategory
from core_brain.services.execution_service import ExecutionService
from core_brain.services.slippage_controller import SlippageController
from core_brain.services.circuit_breaker_gate import CircuitBreakerGate
from core_brain.services.signal_lifecycle_manager import SignalLifecycleManager
from core_brain.services.order_gate import OrderGate
from core_brain.close_only_guard import CloseOnlyGuard

logger = logging.getLogger(__name__)

class ConnectorDisabledError(Exception):
    """Raised when trying to execute via a manually disabled connector."""
    pass


class OrderExecutor:
    """
    Executes trading usr_signals with the following features:
    
    - RiskManager Validation: Checks lockdown mode before execution
    - Factory Pattern: Routes usr_signals to appropriate connector
    - Resilience: Handles connector failures gracefully
    - Audit Trail: Registers all usr_signals in data_vault
    - Notifications: Alerts via Telegram on failures
    """
    
    def __init__(
        self,
        risk_manager: RiskManager,
        storage: Optional[StorageManager] = None,
        multi_tf_limiter: Optional[MultiTimeframeLimiter] = None,
        notificator: Optional[Any] = None,
        notification_service: Optional[NotificationService] = None,
        connectors: Optional[Dict[ConnectorType, Any]] = None,
        execution_service: Optional[ExecutionService] = None,
        circuit_breaker_gate: Optional[CircuitBreakerGate] = None,
        lifecycle_manager: Optional[SignalLifecycleManager] = None,
        close_only_guard: Optional[CloseOnlyGuard] = None,
    ):
        """
        Initialize OrderExecutor with Dependency Injection.
        
        Args:
            risk_manager: RiskManager instance for validation
            storage: StorageManager for persistence (DI)
            multi_tf_limiter: MultiTimeframeLimiter (DI)
            notificator: Notificator for alerts (optional)
            connectors: Dictionary mapping ConnectorType to connector instances
        """
        self.risk_manager = risk_manager
        
        if storage is None:
            logger.warning("OrderExecutor initialized without explicit storage! Violates strict DI.")
            self.storage = StorageManager()
        else:
            self.storage = storage
        
        # Initialize CircuitBreakerGate for strategy execution authorization
        if circuit_breaker_gate is None:
            logger.debug("OrderExecutor: CircuitBreakerGate not injected, creating default")
            from core_brain.circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(storage=self.storage)
            self.circuit_breaker_gate = CircuitBreakerGate(
                circuit_breaker=cb,
                storage=self.storage,
                notificator=notification_service
            )
        else:
            self.circuit_breaker_gate = circuit_breaker_gate
            
        self.notificator = notificator
        self.internal_notifier = notification_service
        self.connectors = connectors or {}
        
        if multi_tf_limiter is None:
            logger.warning("OrderExecutor initialized without explicit multi_tf_limiter! Violates strict DI.")
            from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
            # Need config for limiter, try to get from storage or use empty
            config = self.storage.get_dynamic_params() if hasattr(self.storage, "get_dynamic_params") else {}
            if not isinstance(config, dict):
                config = {}
            self.multi_tf_limiter = MultiTimeframeLimiter(self.storage, config)
        else:
            self.multi_tf_limiter = multi_tf_limiter
            
        if execution_service is None:
            slippage_ctrl = SlippageController(self.storage)
            self.execution_service = ExecutionService(self.storage, slippage_controller=slippage_ctrl)
        else:
            self.execution_service = execution_service
            
        # Initialize RiskCalculator for universal risk computation
        self.risk_calculator = None
        if self.connectors:
            # Prefer MT5 for risk calculation if available
            mt5_conn = self.connectors.get(ConnectorType.METATRADER5)
            calc_connector = mt5_conn if mt5_conn else list(self.connectors.values())[0]
            self.risk_calculator = RiskCalculator(calc_connector)
        
        # Initialize SignalLifecycleManager for signal state transitions
        if lifecycle_manager is None:
            logger.debug("OrderExecutor: SignalLifecycleManager not injected, creating default")
            self.lifecycle_manager = SignalLifecycleManager(
                storage=self.storage,
                risk_calculator=self.risk_calculator
            )
        else:
            self.lifecycle_manager = lifecycle_manager
            
        self.persists_usr_signals = True

        # OrderGate: gates new entries in close-only mode while allowing CLOSE signals.
        _guard = close_only_guard or CloseOnlyGuard()
        self.order_gate = OrderGate(close_only_guard=_guard)

        logger.info(
            f"OrderExecutor initialized with {len(self.connectors)} injected connectors: "
            f"{[ct.value for ct in self.connectors.keys()]}"
        )

        # Track last rejection reason for better error reporting
        self.last_rejection_reason = None
        # Track last execution response for failure reason extraction (DOMINIO-10 feedback)
        self.last_execution_response = None
    
    async def execute_signal(self, signal: Signal) -> bool:
        """
        Execute a trading signal with full validation and resilience.
        
        Workflow:
        1. Validate signal data
        2. Check for duplicate usr_signals (recent or open position)
        3. Check RiskManager lockdown status
        4. Register signal as PENDING in data_vault
        5. Route to appropriate connector using Factory pattern
        6. Handle failures with REJECTED_CONNECTION status
        7. Notify Telegram on errors
        
        Args:
            signal: Signal object to execute (symbol already normalized by SignalFactory)
        
        Returns:
            True if signal was executed successfully, False otherwise
        """
        # NOTE: Symbol normalization now happens in SignalFactory BEFORE saving to DB
        # This ensures DB, CoherenceMonitor, and Executor all see normalized symbols
        
        # Step 1: Validate signal data
        if not self._validate_signal(signal):
            self.last_rejection_reason = "Invalid signal data (missing required fields)"
            logger.warning(f"Invalid signal rejected: {signal.symbol}")
            self._register_failed_signal(signal, "INVALID_DATA")
            # PIPELINE TRACKING: Log rejection
            signal_id = signal.metadata.get('signal_id', signal.symbol)
            self.storage.log_signal_pipeline_event(
                signal_id=signal_id,
                stage='RISK_VALIDATION',
                decision='REJECTED',
                reason='Invalid signal data'
            )
            
            if self.internal_notifier:
                self.internal_notifier.create_notification(
                    category=NotificationCategory.EXECUTION,
                    context={"symbol": signal.symbol, "status": "REJECTED", "reason": "Invalid data"}
                )
            return False
        
        # Step 1.2: CircuitBreaker Gate Check - Verify strategy authorization
        # Delegate to CircuitBreakerGate for clean separation of concerns
        # SHADOW mode: Will validate 4 Pillars before authorization
        strategy_id = signal.metadata.get('strategy_id', signal.strategy_id)
        signal_id = signal.metadata.get('signal_id', signal.symbol)
        
        is_authorized, rejection_reason = self.circuit_breaker_gate.check_strategy_authorization(
            strategy_id=strategy_id,
            symbol=signal.symbol,
            signal_id=signal_id,
            signal=signal  # Pass signal for 4-Pillar validation in SHADOW mode
        )
        
        if not is_authorized:
            self.last_rejection_reason = f"[CIRCUIT_BREAKER] {rejection_reason}"
            self._register_failed_signal(signal, rejection_reason)
            return False
        
        # Step 1.3: SHADOW Account Type Injector - Force DEMO account for SHADOW execution mode
        # If strategy is in SHADOW mode, override account_type to DEMO (real broker, paper account)
        # Architecture: Use real MT5/broker connector but with DEMO account for high fidelity simulation
        if strategy_id:
            try:
                ranking = self.storage.get_signal_ranking(strategy_id)
                if ranking and ranking.get('execution_mode') == 'SHADOW':
                    # Mark signal for DEMO execution (keeps original connector, adds metadata)
                    if not hasattr(signal, 'metadata') or signal.metadata is None:
                        signal.metadata = {}
                    signal.metadata['account_type'] = 'DEMO'
                    signal.metadata['shadow_mode'] = True
                    logger.info(
                        f"[SHADOW_ACCOUNT_INJECTOR] Strategy {strategy_id} in SHADOW mode. "
                        f"Account type forced to DEMO for high-fidelity simulation."
                    )
            except Exception as e:
                logger.warning(f"[SHADOW_ACCOUNT_INJECTOR] Error injecting DEMO account type: {e}")
        

        # Step 1.4: Close-only mode gate (EDGE STRESSED posture).
        # CLOSE signals always pass; BUY/SELL are blocked when close-only is active.
        gate_allowed, gate_reason = self.order_gate.is_allowed(signal)
        if not gate_allowed:
            self.last_rejection_reason = gate_reason
            self._register_failed_signal(signal, "REJECTED_CLOSE_ONLY")
            return False

        # Step 1.5: Legacy lockdown check (backward compatibility with existing tests)
        if hasattr(self.risk_manager, "is_locked") and self.risk_manager.is_locked():
            self.last_rejection_reason = "RiskManager lockdown active"
            logger.warning("Signal rejected by lockdown mode")
            self._register_failed_signal(signal, "REJECTED_LOCKDOWN")
            
            if self.internal_notifier:
                self.internal_notifier.create_notification(
                    category=NotificationCategory.RISK,
                    context={"symbol": signal.symbol, "event_type": "lockdown", "message": "Signal rejected by lockdown mode"}
                )
            return False
        
        # Step 2: Check for duplicate usr_signals (Standard & Advanced)
        # Standard: Check if there's any open position for this symbol (Legacy compatibility)
        # Note: We check ANY timeframe if signal.timeframe is None, or specific if provided.
        if self.storage.has_open_position(signal.symbol, signal.timeframe):
            # Attempt reconciliation with MT5 before rejecting (to clear ghost usr_positions)
            # Only if it's a real broker connector (not Paper)
            if signal.connector_type != ConnectorType.PAPER:
                if self._reconcile_usr_positions(signal.symbol):
                    logger.info(f"[OK] Reconciliation cleared ghost position for {signal.symbol}, proceeding with signal")
                else:
                    self.last_rejection_reason = f"Duplicate signal: already have an open position for {signal.symbol}"
                    logger.warning(self.last_rejection_reason)
                    self._register_failed_signal(signal, "DUPLICATE_OPEN_POSITION")
                    return False
            else:
                # In PAPER mode, we trust the DB and don't reconcile
                self.last_rejection_reason = f"Duplicate signal: already have an open position for {signal.symbol} (Paper Mode)"
                logger.warning(self.last_rejection_reason)
                self._register_failed_signal(signal, "DUPLICATE_OPEN_POSITION")
                return False
                
        # Advanced: Check multi-timeframe limits (EDGE feature)
        is_valid, reason = self.multi_tf_limiter.validate_new_signal(signal)
        if not is_valid:
            self.last_rejection_reason = f"Multi-timeframe limit: {reason}"
            logger.warning(
                f"Signal rejected: {reason}. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}, TF={signal.timeframe}"
            )
            self._register_failed_signal(signal, reason)
            return False
            
        # Additional: Check for recently executed (within timeframe window)
        # This prevents "double-execution" if two similar usr_signals arrive 1 second apart
        # Support exclude_id to avoid self-collision when signal is already saved in DB
        signal_id = signal.metadata.get('signal_id')
        if self.storage.has_recent_signal(
            signal.symbol, 
            signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
            timeframe=signal.timeframe,
            exclude_id=signal_id
        ):
            self.last_rejection_reason = f"Duplicate signal: recent signal already registered for {signal.symbol}"
            logger.warning(self.last_rejection_reason)
            self._register_failed_signal(signal, "DUPLICATE_RECENT_SIGNAL")
            return False
        
        # Step 3.5: Get connector (needed for risk validation and execution)
        try:
            connector = self._get_connector(signal)
        except Exception as e:
            self.last_rejection_reason = f"Connector unavailable: {signal.connector_type.value} not connected"
            logger.error(f"Failed to get connector for {signal.connector_type}: {e}")
            self._register_failed_signal(signal, "CONNECTOR_UNAVAILABLE")
            return False
        
        # Step 3.75: Check total account risk
        can_trade = True
        risk_reason = "OK"
        if hasattr(self.risk_manager, "can_take_new_trade"):
            risk_result = self.risk_manager.can_take_new_trade(signal, connector)
            if isinstance(risk_result, tuple) and len(risk_result) >= 2:
                can_trade, risk_reason = bool(risk_result[0]), str(risk_result[1])
            elif isinstance(risk_result, bool):
                can_trade = risk_result
                risk_reason = "" if risk_result else "RiskManager rejected trade"
        
        if not can_trade:
            logger.warning(
                f"Signal rejected: {risk_reason}. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}"
            )
            self._register_failed_signal(signal, "EXCEEDED_ACCOUNT_RISK")
            
            if self.internal_notifier:
                self.internal_notifier.create_notification(
                    category=NotificationCategory.RISK,
                    context={"symbol": signal.symbol, "event_type": "risk_limit", "message": f"Risk limit exceeded: {risk_reason}"}
                )
            return False

        # Step 3.8: Closed-Loop Sync Gatekeeper (Source Fidelity)
        # For DECENTRALIZED markets (Forex/Crypto), provider_source must match connector
        market_type_str = (signal.market_type or "FOREX").upper()
        if market_type_str in ["FOREX", "CRYPTO"]:
            from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
            orch = ConnectivityOrchestrator()
            prov_id = getattr(connector, 'provider_id', signal.connector_type.value)
            
            # If signal source is known and differs from current executor provider, REJECT TRADE
            if signal.provider_source and signal.provider_source != "UNKNOWN":
                # Note: Normalize comparison if needed (e.g., MT5 vs mt5)
                if signal.provider_source.upper() != prov_id.upper():
                    rejection_msg = (
                        f"DESINCRONIZACIÓN DE FUENTE: Señal de {signal.provider_source} "
                        f"no apta para ejecución en {prov_id} (Mercado Descentralizado)"
                    )
                    self.last_rejection_reason = rejection_msg
                    logger.critical(f"> [INTEGRITY CHECK] {rejection_msg}")
                    # Log to Edge's Thought Stream (Learning)
                    if hasattr(self.storage, "save_edge_learning"):
                        self.storage.save_edge_learning(
                            detection="Desincronización de fuente en mercado descentralizado",
                            action_taken="TRADE_REJECTED",
                            learning="Blindaje de veracidad: Datos y Ejecución deben ser indivisibles en Forex/Crypto",
                            details=f"Source: {signal.provider_source}, Executor: {prov_id}"
                        )
                    self._register_failed_signal(signal, "SOURCE_SYNC_FAILURE")
                    return False
        
        # Step 4: Calculate position size
        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            self.last_rejection_reason = f"Position size calculation failed (result: {position_size})"
            logger.warning(f"Position size calculation failed or too small: {position_size}")
            self._register_failed_signal(signal, "INVALID_POSITION_SIZE")
            return False
        signal.volume = position_size
        
        # Step 4: Register signal as PENDING
        self._register_pending_signal(signal)
        
        # PIPELINE TRACKING: Log risk validation approval
        signal_id = signal.metadata.get('signal_id', signal.symbol)
        self.storage.log_signal_pipeline_event(
            signal_id=signal_id,
            stage='RISK_VALIDATION',
            decision='APPROVED',
            reason='Risk checks passed',
            metadata={'position_size': position_size, 'account_risk_ok': True}
        )
        
        # Step 5: Execute via connector
        # (connector already obtained in Step 3.5)
        try:
            # MANUAL_DISABLED Check (Satellite Link Control)
            from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
            orchestrator = ConnectivityOrchestrator()
            status_report = orchestrator.get_status_report()
            prov_id = getattr(connector, 'provider_id', signal.connector_type.value)
            
            if status_report.get(prov_id, {}).get("status") == "MANUAL_DISABLED":
                error_msg = f"Connector {prov_id} is MANUAL_DISABLED. Execution aborted."
                logger.warning(error_msg)
                self._register_failed_signal(signal, "CONNECTOR_MANUAL_DISABLED")
                raise ConnectorDisabledError(error_msg)

            # RACE CONDITION FIX: Wait for MT5 connection if background thread is still connecting
            if signal.connector_type == ConnectorType.METATRADER5 and hasattr(connector, 'is_connected'):
                max_wait = 15  # seconds
                waited = 0
                while not connector.is_connected and waited < max_wait:
                    if waited == 0:
                        logger.info(f"[RACE FIX] MT5 not yet connected, waiting up to {max_wait}s for background thread...")
                    await asyncio.sleep(1)
                    waited += 1
                
                if not connector.is_connected:
                    logger.error(f"[RACE FIX] MT5 still not connected after {max_wait}s wait. Signal rejected.")
                    self._register_failed_signal(signal, "MT5_CONNECTION_TIMEOUT")
                    return False
                else:
                    logger.info(f"[RACE FIX] [OK] MT5 connected successfully after {waited}s wait")
            
            # --- NUEVO FLUJO HU 5.1: ExecutionService with Protection ---
            execution_response = await self.execution_service.execute_with_protection(signal, connector)
            # Store response for MainOrchestrator feedback loop (DOMINIO-10 INFRA_RESILIENCY)
            self.last_execution_response = execution_response
            
            success = execution_response.success
            # Map response to result format for backward compatibility
            result = {
                'success': success,
                'ticket': execution_response.order_id,
                'price': float(execution_response.real_price) if execution_response.real_price else None,
                'error': execution_response.error_message,
                'status': execution_response.status
            }
            

            if success:
                # Extract ticket/order_id
                ticket = result.get('ticket') or result.get('order_id')

                if signal.connector_type == ConnectorType.METATRADER5 and not ticket:
                    error_msg = "Missing MT5 ticket/order_id"
                    logger.warning(f"Signal execution failed: {error_msg}")
                    # Registrar motivo de fallo en la señal
                    if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                        signal.metadata['execution_observation'] = error_msg
                    self._register_failed_signal(signal, error_msg)
                    if self.notificator:
                        await self.notificator.send_alert(
                            f"[ERROR] Execution Failed\nSymbol: {signal.symbol}\nError: {error_msg}"
                        )
                    return False

                logger.info(
                    f"[OK] Signal executed successfully: {signal.symbol} {signal.signal_type}, "
                    f"Ticket={ticket}"
                )
                # Registrar observación de éxito
                if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                    signal.metadata['execution_observation'] = f"Executed successfully. Ticket={ticket}"
                self._register_successful_signal(signal, result)
                
                # PIPELINE TRACKING: Log successful execution
                signal_id = signal.metadata.get('signal_id', signal.symbol)
                self.storage.log_signal_pipeline_event(
                    signal_id=signal_id,
                    stage='EXECUTED',
                    decision='APPROVED',
                    reason=f'Order executed successfully. Ticket={ticket}',
                    metadata={'ticket': ticket, 'execution_price': result.get('price')}
                )
                
                # FASE 2.3: Save position metadata for PositionManager
                self._save_position_metadata(signal, result, ticket)
                
                if self.internal_notifier:
                    self.internal_notifier.create_notification(
                        category=NotificationCategory.EXECUTION,
                        context={
                            "symbol": signal.symbol,
                            "type": signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type),
                            "ticket": ticket,
                            "status": "SUCCESS",
                            "price": result.get('price', signal.entry_price)
                        }
                    )
                
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.warning(f"Signal execution failed: {error_msg}")
                # Registrar motivo de fallo en la señal
                if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                    signal.metadata['execution_observation'] = f"Execution failed: {error_msg}"
                # Marcar como REJECTED (consolidamos FAILED en REJECTED)
                self._register_failed_signal(signal, f"Execution failed: {error_msg}")

                # Notify for critical connection/timeout errors (same as exception path)
                if self.notificator and result.get('status') in ('CONNECTION_ERROR', 'TIMEOUT', 'CONNECTOR_LOST'):
                    await self.notificator.send_alert(
                        f"[ERROR] Execution Failed\nSymbol: {signal.symbol}\nError: {error_msg}"
                    )

                if self.internal_notifier:
                    self.internal_notifier.create_notification(
                        category=NotificationCategory.EXECUTION,
                        context={"symbol": signal.symbol, "status": "FAILED", "reason": error_msg}
                    )
                return False
                
        except ConnectionError as e:
            # Step 5: Handle connection failures
            logger.error(f"Connection error executing signal: {e}")
            if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                signal.metadata['execution_observation'] = f"Connection error: {str(e)}"
            # Marcar como REJECTED (consolidamos errores de conexión en REJECTED)
            self._register_failed_signal(signal, f"Connection error: {str(e)}")
            # Notify about connection failure
            if self.notificator:
                await self.notificator.send_alert(
                    f"[ERROR] Connection Error\nSymbol: {signal.symbol}\nError: {str(e)}"
                )
            return False
        
        except Exception as e:
            # Step 6: Handle unexpected errors
            logger.error(f"Unexpected error executing signal: {e}", exc_info=True)
            if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                signal.metadata['execution_observation'] = f"Unexpected error: {str(e)}"
            # Marcar como REJECTED (consolidamos errores inesperados en REJECTED)
            self._register_failed_signal(signal, f"Unexpected error: {str(e)}")
            return False
    
    def _validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal data before execution.
        Security principle: validate all external inputs.
        
        Args:
            signal: Signal to validate
        
        Returns:
            True if signal is valid, False otherwise
        """
        # Check confidence range
        if not 0.0 <= signal.confidence <= 1.0:
            logger.warning(f"Invalid confidence: {signal.confidence}")
            return False
        
        # Check required fields
        if not signal.symbol or not signal.signal_type:
            logger.warning("Missing required fields: symbol or signal_type")
            return False
        
        # Check signal type (support both enum and string)
        signal_type_str = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        if signal_type_str not in ["BUY", "SELL", "HOLD"]:
            logger.warning(f"Invalid signal_type: {signal_type_str}")
            return False
        
        # CRITICAL: Check entry_price is not 0 (prevents division by zero in PositionSizeEngine)
        if signal.entry_price <= 0.0:
            logger.error(
                f"[VALIDATION ERROR] Signal has invalid entry_price={signal.entry_price} "
                f"(symbol={signal.symbol}, strategy={signal.strategy_id}). "
                f"Signal rejected. Strategy must provide valid entry_price."
            )
            return False
        
        # Check stop_loss is not 0 for proper risk calculations
        if signal.stop_loss <= 0.0:
            logger.warning(
                f"[VALIDATION WARNING] Signal {signal.symbol} has stop_loss={signal.stop_loss}. "
                f"Using default 50-pips stop loss."
            )
            # Default to 50 pips below entry (for BUY)
            if hasattr(signal.signal_type, 'value'):
                signal_type_str = signal.signal_type.value
            else:
                signal_type_str = str(signal.signal_type)
            
            pip_size = 0.01 if signal.symbol.endswith("JPY") else 0.0001
            signal.stop_loss = (signal.entry_price - 50 * pip_size if signal_type_str == "BUY" 
                              else signal.entry_price + 50 * pip_size)
        
        return True
    
    def _get_connector(self, signal: Signal) -> Optional[Any]:
        """
        Get connector using Factory pattern.
        Agnostic routing based on account_id via ConnectivityOrchestrator, with fallback to ConnectorType.

        ConnectorType.GENERIC signals are resolved dynamically: the first healthy
        registered connector is returned, so strategies remain broker-agnostic.

        Args:
            signal: Signal object with metadata containing the target account_id

        Returns:
            Connector instance or None if not found
        """
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
        from models.signal import ConnectorType
        orchestrator = ConnectivityOrchestrator()

        account_id = signal.metadata.get('account_id') if hasattr(signal, 'metadata') and hasattr(signal.metadata, 'get') else None
        is_generic = signal.connector_type == ConnectorType.GENERIC

        # 1. GENERIC: resolve to the first healthy registered connector
        if is_generic:
            for pid, conn in orchestrator.connectors.items():
                if orchestrator.manual_states.get(pid, True) and orchestrator.failure_counts.get(pid, 0) < 3:
                    return conn
            return None

        platform = signal.connector_type.value if hasattr(signal.connector_type, 'value') else str(signal.connector_type)
        platform_lower = platform.lower()

        # 2. Attempt lookup by account_id in orchestrator
        # Try both the enum value ("METATRADER5_acc") and the DB platform_id ("mt5_acc")
        if account_id:
            for pid in (f"{platform}_{account_id}", f"{platform_lower}_{account_id}"):
                conn = orchestrator.get_connector(pid)
                if conn:
                    return conn

        # 3. Check explicitly injected connectors (backward compat / tests)
        if signal.connector_type in self.connectors:
            return self.connectors[signal.connector_type]

        # 4. Fallback to orchestrator by platform name (try original then lowercase)
        return orchestrator.get_connector(platform) or orchestrator.get_connector(platform_lower)
    
    def _calculate_position_size(self, signal: Signal) -> float:
        """
        Calculate position size for the signal.
        
        DELEGATED to RiskManager.calculate_position_size_master() - Single Source of Truth.
        """
        try:
            connector = self._get_connector(signal)
            if not connector:
                logger.error(f"No connector found for {signal.connector_type}")
                return 0.01  # Fallback
            
            # Usar función maestra consolidada
            position_size = self.risk_manager.calculate_position_size_master(
                signal=signal,
                connector=connector,
                regime_classifier=None  # TODO: inyectar RegimeClassifier cuando esté disponible
            )
            
            # Memory dump for high-confidence usr_signals (>90)
            if signal.confidence > 0.9 and position_size > 0:
                account_balance = self.risk_manager._get_account_balance(connector)
                memory_dump = {
                    "Score": f"{signal.confidence * 100:.1f}%",
                    "LotSize_Calculated": f"{position_size:.4f}",
                    "Risk_Pct": f"{self.risk_manager.risk_per_trade * 100:.2f}%",
                    "Has_Open_Position": self.storage.has_open_position(signal.symbol)
                }
                logger.info(f"🔍 HIGH-CONFIDENCE SIGNAL MEMORY DUMP: {memory_dump}")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            return 0.01  # Fallback
    
    def _register_pending_signal(self, signal: Signal) -> None:
        """Register signal with PENDING status in data_vault (delegated to lifecycle manager)."""
        self.lifecycle_manager.register_pending(signal)
    
    def _register_successful_signal(self, signal: Signal, result: Dict) -> None:
        """Update signal to EXECUTED status (delegated to lifecycle manager)."""
        self.lifecycle_manager.register_successful(signal, result)
    
    def _register_failed_signal(self, signal: Signal, reason: str) -> None:
        """Update signal to REJECTED status (delegated to lifecycle manager)."""
        self.lifecycle_manager.register_failed(signal, reason)
    
    def _save_position_metadata(self, signal: Signal, result: Dict, ticket: int) -> None:
        """
        Save position metadata for PositionManager monitoring (delegated to lifecycle manager).
        """
        self.lifecycle_manager.save_position_metadata(signal, result, ticket)
    
    def _reconcile_usr_positions(self, symbol: str) -> bool:
        """
        Perform immediate reconciliation with MT5 reality.
        
        Checks if MT5 actually has open usr_positions. If not, clears any ghost
        usr_positions from DB and returns True to allow new trade.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            True if reconciliation cleared ghost usr_positions, False if real position exists
        """
        try:
            # Get MT5 connector
            mt5_connector = self.connectors.get(ConnectorType.METATRADER5)
            if not mt5_connector or not mt5_connector.is_connected:
                logger.warning("MT5 connector not available for reconciliation")
                return False
            
            # Query real MT5 positions
            usr_positions = mt5_connector.get_open_positions()
            if usr_positions is None:
                logger.error("Failed to query MT5 usr_positions for reconciliation")
                return False
            
            # Check if symbol has real position
            symbol_usr_positions = [p for p in usr_positions if p.get('symbol') == symbol]
            
            if symbol_usr_positions:
                # Real position exists, don't clear
                logger.info(f"Real position confirmed in MT5 for {symbol}, rejecting duplicate")
                return False
            
            # No real position, clear ghost from DB
            logger.warning(f"No real position in MT5 for {symbol}, clearing ghost position from DB")
            self.storage.clear_ghost_position(symbol)
            return True
            
        except Exception as e:
            logger.error(f"Error during position reconciliation: {e}")
            return False
    
    # ── Exploración Adaptativa (Handshake DEMO) ───────────────────────────────

    def _log_exploration_handshake(
        self, asset: str, strategy_id: str, account_mode: str
    ) -> None:
        """
        Registra el evento de handshake cuando un activo en exploración ejecuta.
        Solo persiste en modo DEMO — silent en LIVE/SHADOW.
        """
        if account_mode != "DEMO":
            return
        trace_id = f"HANDSHAKE-EXPLORE-{asset}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.storage.log_strategy_state_change(
            strategy_id=strategy_id,
            old_mode="EXPLORATION_ON",
            new_mode="EXPLORATION_EXECUTING",
            trace_id=trace_id,
            reason=f"Exploration handshake: {asset} executing in DEMO",
            metrics={"asset": asset, "account_mode": account_mode},
        )
        logger.info(
            "[EXECUTOR] Exploration handshake registered: %s@%s (trace=%s)",
            asset, strategy_id, trace_id,
        )

    def get_status(self) -> Dict:
        """Get current executor status."""
        return {
            "connectors_available": [ct.value for ct in self.connectors.keys()],
            "risk_manager_locked": self.risk_manager.is_locked(),
            "notifications_enabled": self.notificator is not None
        }
