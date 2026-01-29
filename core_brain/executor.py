"""
Order Executor Module
Executes trading signals with RiskManager validation and agnostic connector routing.
Aligned with Aethelgard's principles: Autonomy, Resilience, Agnosticism, and Security.
"""
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path

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
        
        # Auto-detect and load MT5Connector if configured
        # This maintains agnosticism: core doesn't depend on MT5, but uses it if available
        if ConnectorType.METATRADER5 not in self.connectors:
            self._try_load_mt5_connector()
        
        logger.info(
            f"OrderExecutor initialized with {len(self.connectors)} connectors: "
            f"{[ct.value for ct in self.connectors.keys()]}"
        )
    
    def _try_load_mt5_connector(self):
        """
        Attempt to load MT5Connector if configuration exists.
        Follows Aethelgard's agnosticism principle: core doesn't require MT5,
        but will use it opportunistically if configured.
        """
        mt5_config_path = Path('config/mt5_config.json')
        
        if not mt5_config_path.exists():
            logger.debug("MT5 config not found, skipping MT5Connector auto-load")
            return
        
        try:
            # Import only when needed (lazy loading)
            from connectors.mt5_connector import MT5Connector
            
            logger.info("🔌 MT5 configuration detected, attempting to load connector...")
            
            mt5_connector = MT5Connector()
            
            if mt5_connector.connect():
                self.connectors[ConnectorType.METATRADER5] = mt5_connector
                logger.info("✅ MT5Connector loaded and connected successfully")
            else:
                logger.warning("⚠️  MT5Connector failed to connect, skipping")
                
        except ImportError:
            logger.warning("MT5Connector not available (MetaTrader5 library not installed)")
        except FileNotFoundError as e:
            logger.warning(f"MT5 configuration incomplete: {e}")
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
            signal: Signal object to execute
        
        Returns:
            True if signal was executed successfully, False otherwise
        """
        # Step 1: Validate signal data
        if not self._validate_signal(signal):
            logger.warning(f"Invalid signal rejected: {signal.symbol}")
            self._register_failed_signal(signal, "INVALID_DATA")
            return False
        
        # Step 2: Check for duplicate signals
        signal_type_str = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        
        # 2a. Check if there's an open position for this symbol
        if self.storage.has_open_position(signal.symbol):
            logger.warning(
                f"Signal rejected: Open position already exists for {signal.symbol}. "
                f"Preventing duplicate operation."
            )
            self._register_failed_signal(signal, "DUPLICATE_OPEN_POSITION")
            return False
        
        # 2b. Check if there's a recent signal (within 60 minutes)
        if self.storage.has_recent_signal(signal.symbol, signal_type_str, minutes=60):
            logger.warning(
                f"Signal rejected: Recent {signal_type_str} signal for {signal.symbol} "
                f"already processed within last 60 minutes. Preventing duplicate."
            )
            self._register_failed_signal(signal, "DUPLICATE_RECENT_SIGNAL")
            return False
        
        # Step 3: Check RiskManager lockdown
        if self.risk_manager.is_locked():
            logger.warning(
                f"Signal rejected: RiskManager in LOCKDOWN mode. "
                f"Symbol={signal.symbol}, Type={signal.signal_type}"
            )
            self._register_failed_signal(signal, "REJECTED_LOCKDOWN")
            return False
        
        # Step 4: Register signal as PENDING
        self._register_pending_signal(signal)
        
        # Step 5: Route to connector using Factory pattern
        try:
            connector = self._get_connector(signal.connector_type)
            
            if connector is None:
                logger.error(f"No connector found for type: {signal.connector_type}")
                await self._handle_connector_failure(signal, "Connector not configured")
                return False
            
            # Execute signal through connector
            result = connector.execute_signal(signal)
            
            # Verify execution success (support both formats)
            success = result.get('success', False) or result.get("status") == "success"
            
            if success:
                # Extract ticket/order_id
                ticket = result.get('ticket') or result.get('order_id')
                
                logger.info(
                    f"✅ Signal executed successfully: {signal.symbol} {signal.signal_type}, "
                    f"Ticket={ticket}"
                )
                self._register_successful_signal(signal, result)
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.warning(f"Signal execution failed: {error_msg}")
                await self._handle_connector_failure(signal, f"Execution failed: {error_msg}")
                return False
                
        except ConnectionError as e:
            # Step 5: Handle connection failures
            logger.error(f"Connection error executing signal: {e}")
            await self._handle_connector_failure(signal, f"Connection error: {str(e)}")
            return False
            
        except Exception as e:
            # Step 6: Handle unexpected errors
            logger.error(f"Unexpected error executing signal: {e}", exc_info=True)
            await self._handle_connector_failure(signal, f"Unexpected error: {str(e)}")
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
    
    def _register_pending_signal(self, signal: Signal):
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
    
    def _register_successful_signal(self, signal: Signal, result: Dict):
        """Register successfully executed signal."""
        # Extract ticket from result (supports both formats)
        ticket = result.get('ticket') or result.get('order_id')
        
        # Save signal to database
        signal_id = self.storage.save_signal(signal)
        
        # Update to EXECUTED status with execution details
        connector_str = signal.connector_type.value if hasattr(signal.connector_type, 'value') else str(signal.connector_type)
        self.storage.update_signal_status(signal_id, 'EXECUTED', {
            'ticket': ticket,
            'execution_price': result.get('price'),
            'execution_time': datetime.now().isoformat(),
            'connector': connector_str
        })
        
        logger.debug(f"Signal registered as EXECUTED: {signal.symbol}, Ticket: {ticket}")
    
    def _register_failed_signal(self, signal: Signal, reason: str):
        """Register failed signal attempt in data_vault."""
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
    
    async def _handle_connector_failure(self, signal: Signal, error_message: str):
        """
        Handle connector failures with resilience:
        1. Mark signal as REJECTED_CONNECTION in database
        2. Notify via Telegram immediately
        
        Args:
            signal: Failed signal
            error_message: Description of the failure
        """
        # Step 1: Register as REJECTED_CONNECTION
        signal_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "signal_type": signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
            "confidence": signal.confidence,
            "status": "REJECTED_CONNECTION",
            "error": error_message,
            "connector_type": signal.connector_type.value
        }
        
        self.storage.update_system_state({
            "failed_signals": [signal_record]
        })
        
        # Step 2: Notify via Telegram
        if self.notificator:
            alert_message = (
                f"🚨 EXECUTOR FAILURE\n"
                f"Symbol: {signal.symbol}\n"
                f"Action: {signal.signal_type}\n"
                f"Connector: {signal.connector_type.value}\n"
                f"Error: {error_message}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            try:
                await self.notificator.send_alert(alert_message)
                logger.info("Failure notification sent to Telegram")
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
        else:
            logger.warning("Notificator not configured, skipping Telegram alert")
    
    def get_status(self) -> Dict:
        """Get current executor status."""
        return {
            "connectors_available": [ct.value for ct in self.connectors.keys()],
            "risk_manager_locked": self.risk_manager.is_locked(),
            "notifications_enabled": self.notificator is not None
        }
