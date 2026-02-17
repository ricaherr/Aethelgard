"""
Order Executor Module
Executes trading signals with RiskManager validation and agnostic connector routing.
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

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Executes trading signals with the following features:
    
    - RiskManager Validation: Checks lockdown mode before execution
    - Factory Pattern: Routes signals to appropriate connector
    - Resilience: Handles connector failures gracefully
    - Audit Trail: Registers all signals in data_vault
    - Notifications: Alerts via Telegram on failures
    """
    
    def __init__(
        self,
        risk_manager: RiskManager,
        storage: Optional[StorageManager] = None,
        notificator: Optional[Any] = None,
        connectors: Optional[Dict[ConnectorType, Any]] = None,
        config_path: str = "config/dynamic_params.json"
    ):
        """
        Initialize OrderExecutor.
        
        Args:
            risk_manager: RiskManager instance for validation
            storage: StorageManager for persistence (creates if None)
            notificator: Notificator for alerts (optional)
            connectors: Dictionary mapping ConnectorType to connector instances
            config_path: Path to config file (for MultiTimeframeLimiter)
        """
        self.risk_manager = risk_manager
        self.storage = storage or StorageManager()
        self.notificator = notificator
        self.connectors = connectors or {}
        self.persists_signals = True
        
        # EDGE: Load config for multi-timeframe limiter
        self.config = self._load_config(config_path)
        self.multi_tf_limiter = MultiTimeframeLimiter(self.storage, self.config)
        
        # Initialize RiskCalculator for universal risk computation
        # Will use first available connector (typically MT5)
        self.risk_calculator = None
        if self.connectors:
            first_connector = list(self.connectors.values())[0]
            self.risk_calculator = RiskCalculator(first_connector)
            logger.info("RiskCalculator initialized with connector")
        
        # Auto-detect and load MT5Connector if configured
        # This maintains agnosticism: core doesn't depend on MT5, but uses it if available
        if ConnectorType.METATRADER5 not in self.connectors:
            self._try_load_mt5_connector()
        
        logger.info(
            f"OrderExecutor initialized with {len(self.connectors)} connectors: "
            f"{[ct.value for ct in self.connectors.keys()]}"
        )
    
    def _load_config(self, config_path: str) -> Dict:
        """
        Load configuration from JSON file.
        
        Args:
            config_path: Path to config JSON file
        
        Returns:
            Dict with configuration (empty dict if file not found)
        """
        try:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"Config file not found: {config_path}, using empty config")
                return {}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return {}
    
    def _try_load_mt5_connector(self) ->None:
        """
        Attempt to load MT5Connector (lazy loading - connection managed by start.py).
        Follows Aethelgard's agnosticism principle: core doesn't require MT5,
        but will use it opportunistically if configured.
        """
        try:
            # Import only when needed (lazy loading)
            from connectors.mt5_connector import MT5Connector
            
            logger.info("[CONNECT] Loading MT5 connector from DB (lazy loading)...")
            
            mt5_connector = MT5Connector()
            
            # Store connector - connection will be initialized by start.py
            self.connectors[ConnectorType.METATRADER5] = mt5_connector
            logger.info("[OK] MT5Connector loaded (connection managed by start.py)")
                
        except ImportError:
            logger.warning("MT5Connector not available (MetaTrader5 library not installed)")
        except Exception as e:
            logger.error(f"Error loading MT5Connector: {e}", exc_info=True)
    
    async def execute_signal(self, signal: Signal) -> bool:
        """
        Execute a trading signal with full validation and resilience.
        
        Workflow:
        1. Validate signal data
        2. Check for duplicate signals (recent or open position)
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
            return False
        
        # Step 2: Check for duplicate signals
        signal_type_str = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        
        # 2a. Check if there's an open position for this symbol + timeframe
        if self.storage.has_open_position(signal.symbol, signal.timeframe):
            logger.info(
                f"[DEDUP CHECK] Open position detected for {signal.symbol} [{signal.timeframe}]. "
                f"Attempting reconciliation with MT5..."
            )
            
            # Perform immediate reconciliation before rejecting
            if self._reconcile_positions(signal.symbol):
                logger.info(f"[OK] Reconciliation cleared ghost position for {signal.symbol}, proceeding with signal")
            else:
                logger.warning(
                    f"[ERROR] Signal rejected: Real open position confirmed for {signal.symbol} [{signal.timeframe}]. "
                    f"Preventing duplicate operation."
                )
                self._register_failed_signal(signal, "DUPLICATE_OPEN_POSITION")
                return False
        
        # Duplicate validation removed: has_recent_signal() checks PENDING signals
        # which creates false positives. Only check for EXECUTED positions above.
        # PENDING signals are normal - they're waiting for execution, not duplicates.
        
        # Step 3: Check RiskManager lockdown
        if self.risk_manager.is_locked():
            logger.warning(
                f"Signal rejected: RiskManager in LOCKDOWN mode. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}"
            )
            self._register_failed_signal(signal, "REJECTED_LOCKDOWN")
            return False
        
        # Step 3.25: EDGE - Check multi-timeframe limits
        is_valid, reason = self.multi_tf_limiter.validate_new_signal(signal)
        if not is_valid:
            logger.warning(
                f"Signal rejected: {reason}. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}, TF={signal.timeframe}"
            )
            self._register_failed_signal(signal, reason)
            return False
        
        # Step 3.5: Get connector (needed for risk validation and execution)
        try:
            connector = self._get_connector(signal.connector_type)
        except Exception as e:
            logger.error(f"Failed to get connector for {signal.connector_type}: {e}")
            self._register_failed_signal(signal, "CONNECTOR_UNAVAILABLE")
            return False
        
        # Step 3.75: Check total account risk
        can_trade, risk_reason = self.risk_manager.can_take_new_trade(signal, connector)
        if not can_trade:
            logger.warning(
                f"Signal rejected: {risk_reason}. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}"
            )
            self._register_failed_signal(signal, "EXCEEDED_ACCOUNT_RISK")
            return False
        
        # Step 4: Calculate position size
        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
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
            
            # Execute signal through connector
            result = connector.execute_signal(signal)
            
            # Verify execution success (support both formats)
            success = result.get('success', False) or result.get("status") == "success"
            

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
                
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.warning(f"Signal execution failed: {error_msg}")
                # Registrar motivo de fallo en la señal
                if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                    signal.metadata['execution_observation'] = f"Execution failed: {error_msg}"
                # Marcar como REJECTED (consolidamos FAILED en REJECTED)
                self._register_failed_signal(signal, f"Execution failed: {error_msg}")
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
        
        return True
    
    def _get_connector(self, connector_type: ConnectorType) -> Optional[Any]:
        """
        Get connector using Factory pattern.
        Agnostic routing based on ConnectorType.
        
        Args:
            connector_type: Type of connector to retrieve
        
        Returns:
            Connector instance or None if not found
        """
        return self.connectors.get(connector_type)
    
    def _calculate_position_size(self, signal: Signal) -> float:
        """
        Calculate position size for the signal.
        
        DELEGATED to RiskManager.calculate_position_size_master() - Single Source of Truth.
        """
        try:
            connector = self._get_connector(signal.connector_type)
            if not connector:
                logger.error(f"No connector found for {signal.connector_type}")
                return 0.01  # Fallback
            
            # Usar función maestra consolidada
            position_size = self.risk_manager.calculate_position_size_master(
                signal=signal,
                connector=connector,
                regime_classifier=None  # TODO: inyectar RegimeClassifier cuando esté disponible
            )
            
            # Memory dump for high-confidence signals (>90)
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
        """Register signal with PENDING status in data_vault."""
        signal_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "signal_type": signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
            "confidence": signal.confidence,
            "connector_type": signal.connector_type.value,
            "status": "PENDING",
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "volume": signal.volume
        }
        
        self.storage.update_system_state({
            "pending_signals": [signal_record]
        })
        
        logger.debug(f"Signal registered as PENDING: {signal.symbol}")
    
    def _register_successful_signal(self, signal: Signal, result: Dict) -> None:
        """Update signal to EXECUTED status (signal already saved by SignalFactory)."""
        # Extract signal ID assigned by SignalFactory
        signal_id = signal.metadata.get('signal_id')
        if not signal_id:
            logger.error(f"Signal missing ID from SignalFactory: {signal.symbol}. Cannot update status.")
            return
        
        # Extract ticket from result (supports both formats)
        ticket = result.get('ticket') or result.get('order_id')
        
        # Build metadata update with execution details AND critical trade params
        metadata_update = {
            'ticket': ticket,
            'execution_price': result.get('price'),
            'execution_time': datetime.now().isoformat(),
            'connector': signal.connector_type.value if hasattr(signal.connector_type, 'value') else str(signal.connector_type),
            'reason': f"Executed successfully. Ticket={ticket}",
            # Critical trade parameters (for audit & recovery)
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'lot_size': signal.volume if hasattr(signal, 'volume') else None
        }
        
        # Update existing signal to EXECUTED status with complete execution details
        self.storage.update_signal_status(signal_id, 'EXECUTED', metadata_update)
        
        logger.debug(f"Signal updated to EXECUTED: {signal.symbol}, Ticket: {ticket}, SL: {signal.stop_loss}, TP: {signal.take_profit}")
    
    def _register_failed_signal(self, signal: Signal, reason: str) -> None:
        """Update signal to REJECTED status (signal already saved by SignalFactory)."""
        # Extract signal ID assigned by SignalFactory
        signal_id = signal.metadata.get('signal_id')
        if not signal_id:
            logger.warning(f"Signal missing ID from SignalFactory: {signal.symbol}. Skipping rejection update.")
            return
        
        # Update existing signal to REJECTED status with reason
        self.storage.update_signal_status(signal_id, 'REJECTED', {
            'reason': reason
        })
        
        signal_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "signal_type": signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
            "confidence": signal.confidence,
            "status": "REJECTED",
            "reason": reason,
            "connector_type": signal.connector_type.value if signal.connector_type else "UNKNOWN"
        }
        
        self.storage.update_system_state({
            "rejected_signals": [signal_record]
        })
    
    def _save_position_metadata(self, signal: Signal, result: Dict, ticket: int) -> None:
        """
        Save position metadata for PositionManager monitoring.
        
        FASE 2.3: Metadata persistence on position open.
        
        Args:
            signal: Original signal executed
            result: Execution result from connector
            ticket: Order ticket/ID from broker
        """
        try:
            # Calculate initial risk in USD
            entry_price = result.get('entry_price', signal.entry_price)
            sl = result.get('sl', signal.stop_loss)
            tp = result.get('tp', signal.take_profit)
            volume = result.get('volume', signal.volume)
            
            # Get regime from signal metadata
            regime_str = signal.metadata.get('regime', 'NEUTRAL')
            if hasattr(regime_str, 'value'):
                regime_str = regime_str.value
            
            # Calculate initial risk using RiskCalculator (universal, multi-asset)
            if self.risk_calculator:
                initial_risk_usd = self.risk_calculator.calculate_initial_risk_usd(
                    symbol=signal.symbol,
                    entry_price=entry_price,
                    stop_loss=sl,
                    volume=volume
                )
            else:
                # Fallback if RiskCalculator not available (shouldn't happen in production)
                logger.warning("[METADATA] RiskCalculator not available, using fallback")
                pips_risked = abs(entry_price - sl)
                initial_risk_usd = pips_risked * volume * 10.0  # Simplified fallback
            
            # Build metadata dict
            metadata = {
                'ticket': ticket,
                'symbol': signal.symbol,
                'entry_price': entry_price,
                'direction': signal.signal_type.value,  # BUY or SELL from signal_type enum
                'sl': sl,
                'tp': tp,
                'initial_risk_usd': float(initial_risk_usd),
                'entry_time': datetime.now().isoformat(),
                'entry_regime': regime_str,
                'timeframe': signal.timeframe or 'M5',
                'strategy': signal.strategy_id or 'RSI_MACD',
                'volume': volume
            }
            
            # Save to database
            success = self.storage.update_position_metadata(ticket, metadata)
            
            if success:
                logger.info(
                    f"[METADATA] Saved position metadata for ticket {ticket}: "
                    f"{signal.symbol}, initial_risk=${initial_risk_usd:.2f}, regime={regime_str}"
                )
            else:
                logger.warning(f"[METADATA] Failed to save metadata for ticket {ticket}")
                
        except Exception as e:
            logger.error(f"[METADATA] Error saving position metadata for ticket {ticket}: {e}", exc_info=True)
    
    def _reconcile_positions(self, symbol: str) -> bool:
        """
        Perform immediate reconciliation with MT5 reality.
        
        Checks if MT5 actually has open positions. If not, clears any ghost
        positions from DB and returns True to allow new trade.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            True if reconciliation cleared ghost positions, False if real position exists
        """
        try:
            # Get MT5 connector
            mt5_connector = self.connectors.get(ConnectorType.METATRADER5)
            if not mt5_connector or not mt5_connector.is_connected:
                logger.warning("MT5 connector not available for reconciliation")
                return False
            
            # Query real MT5 positions
            positions = mt5_connector.get_open_positions()
            if positions is None:
                logger.error("Failed to query MT5 positions for reconciliation")
                return False
            
            # Check if symbol has real position
            symbol_positions = [p for p in positions if p.get('symbol') == symbol]
            
            if symbol_positions:
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
    
    def get_status(self) -> Dict:
        """Get current executor status."""
        return {
            "connectors_available": [ct.value for ct in self.connectors.keys()],
            "risk_manager_locked": self.risk_manager.is_locked(),
            "notifications_enabled": self.notificator is not None
        }
