"""
Degradation Alert Service (PRIORIDAD 3: Alertas de Degradación)

Handles strategy degradation events and creates alerts with:
- RULE T1: User isolation (user_id in every alert)
- RULE 4.3: Try/Except protection on all external calls
- Trace_ID for traceability
- Integration with NotificationService for sending alerts
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from data_vault.storage import StorageManager
from core_brain.notification_service import NotificationService, NotificationCategory, NotificationPriority

logger = logging.getLogger(__name__)


class DegradationAlertService:
    """
    Service for handling strategy degradation alerts.
    
    When CircuitBreaker detects degradation (LIVE -> QUARANTINE),
    this service:
    1. Creates alert payload with metrics
    2. Ensures RULE T1 (user_id) present
    3. Calls notification_service with try/except
    4. Persists alert to storage
    5. Logs with Trace_ID
    """
    
    def __init__(
        self,
        storage: StorageManager,
        notification_service: NotificationService
    ):
        """
        Initialize alert service with dependencies.
        
        Args:
            storage: StorageManager for persistence
            notification_service: NotificationService for sending alerts
        """
        self.storage = storage
        self.notification_service = notification_service
        logger.debug("[DEGRADATION_ALERT] Service initialized")
    
    def handle_degradation(
        self,
        degradation_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle a strategy degradation event and create alert.
        
        Args:
            degradation_event: Dict with:
                - strategy_id: str
                - from_status: str (LIVE, SHADOW, etc.)
                - to_status: str (QUARANTINE, etc.)
                - reason: str (why degraded)
                - user_id: str (RULE T1)
                - Optional: dd_pct, consecutive_losses, etc.
        
        Returns:
            Alert payload dict with:
            - strategy_id, from_status, to_status, reason
            - user_id (RULE T1)
            - trace_id: ALERT-{uuid}
            - timestamp: ISO8601
            - message: Human-readable alert text
            - severity: critical | high | medium | low
            - notification_id: ID from notification_service (if sent)
        """
        
        # RULE T1: Validate user_id presence
        user_id = degradation_event.get('user_id')
        if not user_id:
            logger.warning("[DEGRADATION_ALERT] Missing user_id in degradation event")
            user_id = 'unknown'
        
        # Extract degradation details
        strategy_id = degradation_event.get('strategy_id', 'UNKNOWN')
        from_status = degradation_event.get('from_status', 'UNKNOWN')
        to_status = degradation_event.get('to_status', 'QUARANTINE')
        reason = degradation_event.get('reason', 'Unknown reason')
        
        # Generate Trace_ID for traceability (.ai_rules § 5)
        trace_id = f"ALERT-{uuid4().hex[:12].upper()}"
        
        # Build alert message with metrics
        message = self._build_alert_message(degradation_event)
        
        # Create alert payload
        alert = {
            'strategy_id': strategy_id,
            'from_status': from_status,
            'to_status': to_status,
            'reason': reason,
            'user_id': user_id,
            'trace_id': trace_id,
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'severity': 'critical',  # All LIVE->QUARANTINE are critical
            'metrics': {
                'dd_pct': degradation_event.get('dd_pct'),
                'consecutive_losses': degradation_event.get('consecutive_losses'),
                'profit_factor': degradation_event.get('profit_factor'),
                'win_rate': degradation_event.get('win_rate')
            }
        }
        
        # RULE 4.3: Try/Except on notification service integration
        try:
            notification = self.notification_service.create_notification(
                category=NotificationCategory.RISK,
                context={
                    'type': 'strategy_degradation',
                    'strategy_id': strategy_id,
                    'from_status': from_status,
                    'to_status': to_status,
                    'reason': reason,
                    'trace_id': trace_id
                },
                user_id=user_id  # User context
            )
            
            if notification:
                alert['notification_id'] = notification.get('id')
                logger.info(
                    f"[DEGRADATION_ALERT] {trace_id}: Notification created for "
                    f"{strategy_id} ({from_status}->{to_status})"
                )
        
        except Exception as exc:
            # RULE 4.3: Log error but don't crash
            logger.error(
                f"[DEGRADATION_ALERT] {trace_id}: Error notifying: {exc}",
                exc_info=True
            )
            alert['notification_error'] = str(exc)
        
        # RULE 4.3: Try/Except on storage persistence
        try:
            self.storage.log_alert(
                alert_type='strategy_degradation',
                user_id=user_id,
                alert_data=alert,
                trace_id=trace_id
            )
            logger.info(
                f"[DEGRADATION_ALERT] {trace_id}: Alert persisted for "
                f"{strategy_id} for user {user_id}"
            )
        
        except Exception as exc:
            logger.error(
                f"[DEGRADATION_ALERT] {trace_id}: Error persisting alert: {exc}",
                exc_info=True
            )
            alert['storage_error'] = str(exc)
        
        logger.critical(
            f"[DEGRADATION_ALERT] {trace_id}: Strategy {strategy_id} "
            f"degraded {from_status}->{to_status} ({reason})"
        )
        
        return alert
    
    @staticmethod
    def _build_alert_message(degradation_event: Dict[str, Any]) -> str:
        """
        Build human-readable alert message from degradation event.
        
        Args:
            degradation_event: Degradation event dict
        
        Returns:
            Readable alert message
        """
        strategy_id = degradation_event.get('strategy_id', 'UNKNOWN')
        from_status = degradation_event.get('from_status', '?')
        to_status = degradation_event.get('to_status', 'QUARANTINE')
        reason = degradation_event.get('reason', 'Unknown')
        
        # Build parts of message
        parts = [
            f"⚠️ STRATEGY DEGRADATION ALERT",
            f"Strategy: {strategy_id}",
            f"Status: {from_status} → {to_status}",
            f"Reason: {reason}"
        ]
        
        # Add metrics if present
        if 'dd_pct' in degradation_event:
            parts.append(f"Drawdown: {degradation_event['dd_pct']:.2f}%")
        
        if 'consecutive_losses' in degradation_event:
            parts.append(f"Consecutive Losses: {degradation_event['consecutive_losses']}")
        
        if 'profit_factor' in degradation_event:
            parts.append(f"Profit Factor: {degradation_event['profit_factor']:.2f}")
        
        return " | ".join(parts)
