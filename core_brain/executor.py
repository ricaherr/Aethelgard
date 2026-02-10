"""
Order Executor Module
Executes trading signals with RiskManager validation and agnostic connector routing.
Aligned with Aethelgard's principles: Autonomy, Resilience, Agnosticism, and Security.
"""
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime

from models.signal import Signal, ConnectorType
from core_brain.risk_manager import RiskManager
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
        connectors: Optional[Dict[ConnectorType, Any]] = None
    ):
        """
        Initialize OrderExecutor.
        
        Args:
            risk_manager: RiskManager instance for validation
            storage: StorageManager for persistence (creates if None)
            notificator: Notificator for alerts (optional)
            connectors: Dictionary mapping ConnectorType to connector instances
        """
        self.risk_manager = risk_manager
        self.storage = storage or StorageManager()
        self.notificator = notificator
        self.connectors = connectors or {}
        self.persists_signals = True
        
        # Auto-detect and load MT5Connector if configured
        # This maintains agnosticism: core doesn't depend on MT5, but uses it if available
        if ConnectorType.METATRADER5 not in self.connectors:
            self._try_load_mt5_connector()
        
        logger.info(
            f"OrderExecutor initialized with {len(self.connectors)} connectors: "
            f"{[ct.value for ct in self.connectors.keys()]}"
        )
    
    def _try_load_mt5_connector(self) -> None:
        """
        Attempt to load MT5Connector (lazy loading - no connection yet).
        Follows Aethelgard's agnosticism principle: core doesn't require MT5,
        but will use it opportunistically if configured.
        """
        try:
            # Import only when needed (lazy loading)
            from connectors.mt5_connector import MT5Connector
            
            logger.info("🔌 Loading MT5 connector from DB (lazy loading)...")
            
            mt5_connector = MT5Connector()
            
            # Store connector - connection will be started later via .start()
            self.connectors[ConnectorType.METATRADER5] = mt5_connector
            logger.info("✅ MT5Connector loaded (connection deferred)")
                
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
                logger.info(f"✅ Reconciliation cleared ghost position for {signal.symbol}, proceeding with signal")
            else:
                logger.warning(
                    f"❌ Signal rejected: Real open position confirmed for {signal.symbol} [{signal.timeframe}]. "
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
        
        # Step 3.5: Calculate position size
        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            logger.warning(f"Position size calculation failed or too small: {position_size}")
            self._register_failed_signal(signal, "INVALID_POSITION_SIZE")
            return False
        signal.volume = position_size
        
        # Step 4: Register signal as PENDING
        self._register_pending_signal(signal)
        
        # Step 5: Route to connector using Factory pattern
        try:
            connector = self._get_connector(signal.connector_type)
            
            if connector is None:
                error_msg = f"Connector not configured: {signal.connector_type}"
                logger.error(error_msg)
                self._register_failed_signal(signal, error_msg)
                if self.notificator:
                    await self.notificator.send_alert(
                        f"⚠️ Missing Connector\nSymbol: {signal.symbol}\nConnector: {signal.connector_type}"
                    )
                return False
            
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
                    logger.info(f"[RACE FIX] ✅ MT5 connected successfully after {waited}s wait")
            
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
                            f"⚠️ Execution Failed\nSymbol: {signal.symbol}\nError: {error_msg}"
                        )
                    return False

                logger.info(
                    f"✅ Signal executed successfully: {signal.symbol} {signal.signal_type}, "
                    f"Ticket={ticket}"
                )
                # Registrar observación de éxito
                if hasattr(signal, 'metadata') and isinstance(signal.metadata, dict):
                    signal.metadata['execution_observation'] = f"Executed successfully. Ticket={ticket}"
                self._register_successful_signal(signal, result)
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
                    f"⚠️ Connection Error\nSymbol: {signal.symbol}\nError: {str(e)}"
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
        """Calculate position size for the signal"""
        try:
            connector = self._get_connector(signal.connector_type)
            if connector and hasattr(connector, 'get_account_balance'):
                account_balance = connector.get_account_balance()
            else:
                # Default balance for paper trading
                account_balance = 10000.0
            
            # Get stop loss distance in PRICE units and convert to PIPS
            if signal.stop_loss and signal.entry_price:
                price_distance = abs(signal.stop_loss - signal.entry_price)
                # For forex pairs (5 decimal places), 1 pip = 0.0001
                # For JPY pairs (3 decimal places), 1 pip = 0.01
                # Use 0.0001 as default (most forex pairs)
                pip_size = 0.01 if 'JPY' in signal.symbol else 0.0001
                stop_loss_distance = price_distance / pip_size
            else:
                stop_loss_distance = 50.0  # Default 50 pips
            
            # Get point value: For 1 standard lot (100,000 units) in forex:
            # - 1 pip movement = $10 for most pairs
            # - 1 pip movement = $1000 for JPY pairs (because smaller pip size)
            # We'll use $10 as standard for 1 lot
            point_value = 10.0
            
            # Get current regime (assume RANGE if not available)
            from models.signal import MarketRegime
            current_regime = MarketRegime.RANGE
            
            position_size = self.risk_manager.calculate_position_size(
                account_balance, stop_loss_distance, point_value, current_regime
            )
            
            # Clamp position size to reasonable limits
            # Min: 0.01 lots (micro lot)
            # Max: 10 lots (conservative limit for demo)
            position_size = max(0.01, min(position_size, 10.0))
            
            # Memory dump for high-confidence signals (>90)
            if signal.confidence > 0.9:
                risk_amount = account_balance * 0.01  # 1% risk
                memory_dump = {
                    "Score": f"{signal.confidence * 100:.1f}%",
                    "LotSize_Calculated": f"{position_size:.4f}",
                    "Risk_Amount_$": f"{risk_amount:.2f}",
                    "Has_Open_Position": self.storage.has_open_position(signal.symbol)
                }
                logger.info(f"🔍 HIGH-CONFIDENCE SIGNAL MEMORY DUMP: {memory_dump}")
            
            logger.debug(f"Position size calculated: {position_size:.2f} lots (SL distance: {stop_loss_distance:.1f} pips)")
            return position_size
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
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
        
        # Update existing signal to EXECUTED status with execution details
        connector_str = signal.connector_type.value if hasattr(signal.connector_type, 'value') else str(signal.connector_type)
        self.storage.update_signal_status(signal_id, 'EXECUTED', {
            'ticket': ticket,
            'execution_price': result.get('price'),
            'execution_time': datetime.now().isoformat(),
            'connector': connector_str,
            'reason': f"Executed successfully. Ticket={ticket}"
        })
        
        logger.debug(f"Signal updated to EXECUTED: {signal.symbol}, Ticket: {ticket}")
    
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
