"""
CircuitBreaker Gate Service - Strategy Execution Authorization
Encapsulates CircuitBreaker integration logic extracted from Executor.

Responsibility: Check if strategy is allowed to send orders (LIVE only).
- Strategy in LIVE: ALLOW order execution
- Strategy in QUARANTINE/SHADOW: BLOCK order
- CircuitBreaker unavailable: BLOCK (fail-secure)

This service centralizes the CB gating logic to reduce executor.py complexity
and enable reuse across multiple execution points.
"""
import logging
from typing import Tuple, Optional

from core_brain.circuit_breaker import CircuitBreaker
from data_vault.storage import StorageManager
from core_brain.notification_service import NotificationService, NotificationCategory

logger = logging.getLogger(__name__)


class CircuitBreakerGate:
    """
    Gate service for CircuitBreaker authorization checks.
    
    Responsible for:
    - Verifying strategy execution mode (LIVE/SHADOW/QUARANTINE)
    - Logging decisions with [CIRCUIT_BREAKER] pattern
    - Notifying users of rejections
    - Pipelin tracking of rejections
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        storage: StorageManager,
        notificator: Optional[NotificationService] = None
    ):
        """
        Initialize CBGate with dependencies.
        
        Args:
            circuit_breaker: CircuitBreaker instance for authorization checks
            storage: StorageManager for pipeline tracking
            notificator: NotificationService for user alerts (optional)
        """
        self.circuit_breaker = circuit_breaker
        self.storage = storage
        self.notificator = notificator
        logger.debug("CircuitBreakerGate initialized")

    def check_strategy_authorization(
        self,
        strategy_id: Optional[str],
        symbol: str,
        signal_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if strategy is authorized to send orders.
        
        Args:
            strategy_id: Strategy identifier (may be None)
            symbol: Trading symbol (for logging)
            signal_id: Signal identifier (for tracking)
            
        Returns:
            Tuple[authorized (bool), rejection_reason (str or None)]
            - (True, None) if strategy is LIVE and can trade
            - (False, reason) if strategy is blocked or error occurred
        """
        # Skip check if no strategy_id (unmanaged signals)
        if not strategy_id:
            logger.debug("No strategy_id: CB gate skipped (unmanaged signal)")
            return (True, None)

        try:
            # Query CircuitBreaker: is strategy blocked?
            is_blocked = self.circuit_breaker.is_strategy_blocked_for_trading(strategy_id)
            
            if is_blocked:
                reason = f"Strategy {strategy_id} not in LIVE execution mode"
                logger.warning(
                    f"[CIRCUIT_BREAKER] Strategy {strategy_id} blocked from trading. "
                    f"Symbol={symbol}, Status=REJECTED (execution_mode not LIVE)"
                )
                
                # Log to pipeline tracking
                self.storage.log_signal_pipeline_event(
                    signal_id=signal_id,
                    stage='CIRCUIT_BREAKER',
                    decision='REJECTED',
                    reason=reason
                )
                
                # Notify user
                if self.notificator:
                    self.notificator.create_notification(
                        category=NotificationCategory.EXECUTION,
                        context={
                            "symbol": symbol,
                            "status": "REJECTED",
                            "reason": "Circuit breaker: strategy blocked"
                        }
                    )
                
                return (False, "CIRCUIT_BREAKER_BLOCKED")
            
            # Strategy is LIVE: authorized
            logger.debug(f"[CIRCUIT_BREAKER] Strategy {strategy_id} authorized (LIVE mode)")
            return (True, None)
            
        except Exception as e:
            # CircuitBreaker check failed - fail-secure (block order)
            reason = f"CircuitBreaker error checking strategy {strategy_id}: {str(e)}"
            logger.error(reason, exc_info=False)
            
            # Log to pipeline tracking
            self.storage.log_signal_pipeline_event(
                signal_id=signal_id,
                stage='CIRCUIT_BREAKER',
                decision='REJECTED',
                reason=reason
            )
            
            # Notify user
            if self.notificator:
                self.notificator.create_notification(
                    category=NotificationCategory.EXECUTION,
                    context={
                        "symbol": symbol,
                        "status": "REJECTED",
                        "reason": "Circuit breaker check error"
                    }
                )
            
            return (False, "CIRCUIT_BREAKER_ERROR")
