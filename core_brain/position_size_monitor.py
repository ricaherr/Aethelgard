"""
PositionSizeMonitor: EDGE Component

Monitors position size calculations in real-time and activates circuit breaker
if anomalies or failures are detected.

Features:
- Tracks calculation success/failure rate
- Detects anomalies (extreme sizes, risk exceedance)
- Circuit breaker: blocks trading after N consecutive failures
- Self-healing: auto-resets after successful calculations
- Comprehensive logging and alerts
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger(__name__)


class CalculationStatus(Enum):
    """Status of a position size calculation"""
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"  # Calculation succeeded but with warnings
    ERROR = "ERROR"  # Calculation failed
    CRITICAL = "CRITICAL"  # Critical failure (risk exceeded, margin insufficient)


@dataclass
class CalculationEvent:
    """Records a single position size calculation event"""
    timestamp: datetime
    symbol: str
    status: CalculationStatus
    position_size: float
    risk_target: float
    risk_actual: Optional[float] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class PositionSizeMonitor:
    """
    Real-time monitor for position size calculations with circuit breaker.
    
    This component ensures EDGE compliance by:
    1. Tracking ALL position size calculations
    2. Detecting patterns of failures
    3. Activating circuit breaker when quality degrades
    4. Providing real-time health metrics
    """
    
    def __init__(
        self,
        max_consecutive_failures: int = 3,
        circuit_breaker_timeout: int = 300,  # 5 minutes
        history_window: int = 100  # Keep last 100 events
    ):
        """
        Initialize PositionSizeMonitor.
        
        Args:
            max_consecutive_failures: Number of consecutive failures before circuit breaker activates.
            circuit_breaker_timeout: Seconds to keep circuit breaker active (auto-reset).
            history_window: Number of recent events to keep in memory.
        """
        self.max_consecutive_failures = max_consecutive_failures
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self.history_window = history_window
        
        # State
        self.consecutive_failures = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_activated_at: Optional[datetime] = None
        
        # History
        self.event_history: List[CalculationEvent] = []
        
        # Statistics
        self.total_calculations = 0
        self.successful_calculations = 0
        self.failed_calculations = 0
        self.warnings_count = 0
        
        logger.info(
            f"PositionSizeMonitor initialized: "
            f"max_failures={max_consecutive_failures}, "
            f"timeout={circuit_breaker_timeout}s"
        )
    
    def record_calculation(
        self,
        symbol: str,
        position_size: float,
        risk_target: float,
        risk_actual: Optional[float] = None,
        status: CalculationStatus = CalculationStatus.SUCCESS,
        warnings: Optional[List[str]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Record a position size calculation event.
        
        Args:
            symbol: Instrument symbol
            position_size: Calculated position size (lots)
            risk_target: Target risk amount ($)
            risk_actual: Actual risk amount ($) if calculable
            status: Calculation status
            warnings: List of warning messages
            error_message: Error message if failed
        """
        
        event = CalculationEvent(
            timestamp=datetime.now(),
            symbol=symbol,
            status=status,
            position_size=position_size,
            risk_target=risk_target,
            risk_actual=risk_actual,
            error_message=error_message,
            warnings=warnings or []
        )
        
        # Add to history
        self.event_history.append(event)
        
        # Trim history to window
        if len(self.event_history) > self.history_window:
            self.event_history = self.event_history[-self.history_window:]
        
        # Update statistics
        self.total_calculations += 1
        
        if status == CalculationStatus.SUCCESS:
            self.successful_calculations += 1
            self.consecutive_failures = 0  # Reset on success
            
            # Auto-reset circuit breaker after successful calculation
            if self.circuit_breaker_active:
                elapsed = (datetime.now() - self.circuit_breaker_activated_at).total_seconds()
                if elapsed >= self.circuit_breaker_timeout:
                    self._reset_circuit_breaker()
                    logger.info("✅ Circuit breaker AUTO-RESET after successful calculation")
        
        elif status == CalculationStatus.WARNING:
            self.successful_calculations += 1
            self.warnings_count += 1
            self.consecutive_failures = 0  # Reset (warning is not failure)
            
            logger.warning(
                f"⚠️  Position Size WARNING: {symbol} | "
                f"Size: {position_size:.2f} lots | "
                f"Warnings: {', '.join(event.warnings)}"
            )
        
        elif status in [CalculationStatus.ERROR, CalculationStatus.CRITICAL]:
            self.failed_calculations += 1
            self.consecutive_failures += 1
            
            logger.error(
                f"❌ Position Size {status.value}: {symbol} | "
                f"Size: {position_size:.2f} lots | "
                f"Error: {error_message}"
            )
            
            # Check if circuit breaker should activate
            if self.consecutive_failures >= self.max_consecutive_failures:
                self._activate_circuit_breaker()
    
    def _activate_circuit_breaker(self) -> None:
        """Activate circuit breaker to block trading"""
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            self.circuit_breaker_activated_at = datetime.now()
            
            logger.critical(
                f"🔥 CIRCUIT BREAKER ACTIVATED! "
                f"Consecutive failures: {self.consecutive_failures}/{self.max_consecutive_failures} "
                f"Trading BLOCKED for {self.circuit_breaker_timeout}s"
            )
            
            # Generate alert (could integrate with Notificator)
            self._send_alert(
                "CIRCUIT BREAKER ACTIVATED",
                f"Position size calculations failed {self.consecutive_failures} times consecutively. "
                f"Trading is blocked for {self.circuit_breaker_timeout} seconds."
            )
    
    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker"""
        self.circuit_breaker_active = False
        self.circuit_breaker_activated_at = None
        self.consecutive_failures = 0
        
        logger.info("✅ Circuit breaker RESET - Trading re-enabled")
    
    def force_reset_circuit_breaker(self) -> None:
        """Force reset circuit breaker (manual recovery from extended outages)"""
        if self.circuit_breaker_active:
            logger.warning(f"⚠️ MANUAL RESET after {self.consecutive_failures} failures")
            self._reset_circuit_breaker()
        else:
            logger.info("Circuit breaker already inactive - no reset needed")
    
    def _send_alert(self, title: str, message: str) -> None:
        """Send alert (placeholder for Notificator integration)"""
        # TODO: Integrate with Notificator for Telegram alerts
        logger.critical(f"🚨 ALERT: {title} - {message}")
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is allowed (circuit breaker not active).
        
        Returns:
            True if trading is allowed, False if blocked.
        """
        if not self.circuit_breaker_active:
            return True
        
        # Check if timeout expired
        if self.circuit_breaker_activated_at:
            elapsed = (datetime.now() - self.circuit_breaker_activated_at).total_seconds()
            if elapsed >= self.circuit_breaker_timeout:
                self._reset_circuit_breaker()
                return True
        
        return False
    
    def get_health_metrics(self) -> Dict:
        """
        Get current health metrics.
        
        Returns:
            Dict with comprehensive health statistics.
        """
        success_rate = (
            (self.successful_calculations / self.total_calculations * 100)
            if self.total_calculations > 0
            else 0
        )
        
        # Recent trend (last 10 calculations)
        recent_events = self.event_history[-10:] if len(self.event_history) >= 10 else self.event_history
        recent_successes = sum(
            1 for e in recent_events 
            if e.status in [CalculationStatus.SUCCESS, CalculationStatus.WARNING]
        )
        recent_trend = (
            (recent_successes / len(recent_events) * 100)
            if recent_events
            else 0
        )
        
        return {
            'total_calculations': self.total_calculations,
            'successful': self.successful_calculations,
            'failed': self.failed_calculations,
            'warnings': self.warnings_count,
            'success_rate': success_rate,
            'recent_trend': recent_trend,
            'consecutive_failures': self.consecutive_failures,
            'circuit_breaker_active': self.circuit_breaker_active,
            'trading_allowed': self.is_trading_allowed(),
            'circuit_breaker_timeout_remaining': self._get_timeout_remaining()
        }
    
    def _get_timeout_remaining(self) -> Optional[int]:
        """Get remaining seconds until circuit breaker auto-resets"""
        if not self.circuit_breaker_active or not self.circuit_breaker_activated_at:
            return None
        
        elapsed = (datetime.now() - self.circuit_breaker_activated_at).total_seconds()
        remaining = max(0, self.circuit_breaker_timeout - elapsed)
        return int(remaining)
    
    def get_recent_failures(self, limit: int = 5) -> List[CalculationEvent]:
        """
        Get recent failure events.
        
        Args:
            limit: Maximum number of failures to return.
            
        Returns:
            List of recent failure/error events.
        """
        failures = [
            e for e in self.event_history
            if e.status in [CalculationStatus.ERROR, CalculationStatus.CRITICAL]
        ]
        return failures[-limit:]
    
    def reset_statistics(self) -> None:
        """Reset all statistics including circuit breaker (use with caution)"""
        self.total_calculations = 0
        self.successful_calculations = 0
        self.failed_calculations = 0
        self.warnings_count = 0
        self.event_history.clear()
        
        # Also reset circuit breaker
        if self.circuit_breaker_active:
            self._reset_circuit_breaker()
        else:
            self.consecutive_failures = 0
        
        logger.info("PositionSizeMonitor statistics RESET (including circuit breaker)")
    
    def __str__(self) -> str:
        """String representation of monitor status"""
        metrics = self.get_health_metrics()
        return (
            f"PositionSizeMonitor("
            f"calcs={metrics['total_calculations']}, "
            f"success_rate={metrics['success_rate']:.1f}%, "
            f"circuit_breaker={'ACTIVE' if metrics['circuit_breaker_active'] else 'OK'}"
            f")"
        )
