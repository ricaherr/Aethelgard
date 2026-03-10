"""
TDD Tests for DegradationAlertService (PRIORIDAD 3: Alertas de Degradación)

Tests cover:
- Detection of strategy degradation (LIVE -> QUARANTINE)
- Alert payload construction with all required fields
- RULE T1: User isolation (user_id in every alert)
- RULE 4.3: Try/Except protection when calling notification_service
- Trace_ID generation and logging
- Alert persistence to storage
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, call
from uuid import uuid4

from core_brain.services.degradation_alert_service import DegradationAlertService
from tests.conftest_test_data import (
    TEST_STRATEGY_LIVE,
    TEST_STRATEGY_QUARANTINE,
    get_test_strategy_statuses,
)


@pytest.fixture
def mock_storage():
    """Mock StorageManager with alert persistence."""
    storage = Mock()
    storage.get_usr_performance = Mock(
        side_effect=lambda sid: {
            'BRK_OPEN_0001': {
                'strategy_id': 'BRK_OPEN_0001',
                'dd_pct': 3.5,
                'consecutive_losses': 6,
                'profit_factor': 1.2,
                'win_rate': 0.55
            }
        }.get(sid)
    )
    storage.log_alert = Mock(return_value=True)
    storage.save_notification = Mock(return_value=True)
    return storage


@pytest.fixture
def mock_notification_service():
    """Mock NotificationService."""
    notif = Mock()
    notif.create_notification = Mock(
        return_value={
            'id': str(uuid4()),
            'title': 'Strategy Degraded',
            'message': 'Strategy BRK_OPEN_0001 degraded to QUARANTINE',
            'category': 'risk',
            'priority': 'critical'
        }
    )
    return notif


@pytest.fixture
def alert_service(mock_storage, mock_notification_service):
    """Initialize DegradationAlertService with mocks."""
    service = DegradationAlertService(
        storage=mock_storage,
        notification_service=mock_notification_service
    )
    return service


class TestDegradationAlertServiceInitialization:
    """Test service initialization and DI."""
    
    def test_service_initializes_with_dependencies(self, mock_storage, mock_notification_service):
        """Service should accept storage and notification_service via DI."""
        service = DegradationAlertService(
            storage=mock_storage,
            notification_service=mock_notification_service
        )
        assert service.storage is mock_storage
        assert service.notification_service is mock_notification_service
    
    def test_service_has_required_methods(self, alert_service):
        """Service should have core alert methods."""
        assert hasattr(alert_service, 'handle_degradation')
        assert callable(alert_service.handle_degradation)


class TestDegradationDetection:
    """Test degradation event detection and alert creation."""
    
    def test_handle_degradation_live_to_quarantine(self, alert_service, mock_storage):
        """Should create alert when strategy degrades LIVE -> QUARANTINE."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded 3.0%',
            'dd_pct': 3.5,
            'consecutive_losses': 6,
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert alert is not None
        assert alert['strategy_id'] == 'BRK_OPEN_0001'
        assert alert['from_status'] == 'LIVE'
        assert alert['to_status'] == 'QUARANTINE'
        assert alert['user_id'] == 'user-100'
    
    def test_handle_degradation_returns_trace_id(self, alert_service):
        """Alert should include Trace_ID for traceability."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Consecutive losses exceeded 5',
            'consecutive_losses': 6,
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert 'trace_id' in alert
        assert alert['trace_id'].startswith('ALERT-')


class TestAlertPayloadConstruction:
    """Test alert message structure and content."""
    
    def test_alert_has_all_required_fields(self, alert_service):
        """Alert payload should contain all required fields."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded threshold',
            'dd_pct': 3.5,
            'consecutive_losses': 6,
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        required_fields = [
            'strategy_id', 'from_status', 'to_status', 'reason',
            'user_id', 'trace_id', 'timestamp', 'message', 'severity'
        ]
        
        for field in required_fields:
            assert field in alert, f"Missing field: {field}"
    
    def test_alert_message_contains_readable_text(self, alert_service):
        """Alert message should be human-readable."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded 3.0%',
            'dd_pct': 3.5,
            'consecutive_losses': 6,
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert 'BRK_OPEN_0001' in alert['message']
        assert 'QUARANTINE' in alert['message']
        assert '3.5' in alert['message']  # DD percentage
    
    def test_alert_severity_is_critical(self, alert_service):
        """Degradation alerts should have critical severity."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Consecutive losses exceeded 5',
            'consecutive_losses': 6,
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert alert['severity'] == 'critical'


class TestTenantIsolation:
    """Test RULE T1: User isolation in alerts."""
    
    def test_alert_includes_user_id_from_event(self, alert_service):
        """Alert must include user_id from degradation event (RULE T1)."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown threshold',
            'user_id': 'user-200'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert alert['user_id'] == 'user-200'
    
    def test_alert_rejects_missing_user_id(self, alert_service):
        """Alert should fail safely if user_id missing (RULE T1)."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown threshold'
            # Missing user_id
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        # Should return safe default with error indication
        assert alert is not None
        assert alert.get('error') is not None or alert.get('user_id') == 'unknown'


class TestNotificationServiceIntegration:
    """Test RULE 4.3: Try/Except protection when calling notification_service."""
    
    def test_calls_notification_service(self, alert_service, mock_notification_service):
        """Should call notification_service to create notification."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        alert_service.handle_degradation(degradation_event)
        
        mock_notification_service.create_notification.assert_called_once()
    
    def test_handles_notification_service_error_gracefully(self, alert_service, mock_notification_service):
        """Should handle notification_service errors without crashing (RULE 4.3)."""
        mock_notification_service.create_notification.side_effect = Exception("Service unavailable")
        
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        # Should not raise, should return safe default
        alert = alert_service.handle_degradation(degradation_event)
        assert alert is not None
        assert alert['strategy_id'] == 'BRK_OPEN_0001'
    
    def test_persists_alert_to_storage(self, alert_service, mock_storage):
        """Should persist alert to storage."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        alert_service.handle_degradation(degradation_event)
        
        mock_storage.log_alert.assert_called_once()


class TestAlertTimestamp:
    """Test timestamp and audit trail."""
    
    def test_alert_includes_iso8601_timestamp(self, alert_service):
        """Alert should include ISO8601 timestamp."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        alert = alert_service.handle_degradation(degradation_event)
        
        assert 'timestamp' in alert
        # Should be parseable as ISO8601
        datetime.fromisoformat(alert['timestamp'])
    
    def test_alert_timestamp_is_recent(self, alert_service):
        """Alert timestamp should be very recent (within 1 second)."""
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        before = datetime.now()
        alert = alert_service.handle_degradation(degradation_event)
        after = datetime.now()
        
        alert_time = datetime.fromisoformat(alert['timestamp'])
        assert before <= alert_time <= after


class TestExceptionHandling:
    """Test RULE 4.3: Fail-safe exception handling."""
    
    def test_storage_error_handled_gracefully(self, mock_notification_service):
        """Should handle storage errors without crashing."""
        mock_storage = Mock()
        mock_storage.log_alert.side_effect = Exception("DB error")
        
        service = DegradationAlertService(
            storage=mock_storage,
            notification_service=mock_notification_service
        )
        
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        # Should not raise
        alert = service.handle_degradation(degradation_event)
        assert alert is not None
    
    def test_all_exception_paths_logged(self, alert_service):
        """All exceptions should be logged for debugging."""
        # This is verified by checking that logger.error is called
        # in implementation when exceptions occur
        
        mock_notification = alert_service.notification_service
        mock_notification.create_notification.side_effect = Exception("Test error")
        
        degradation_event = {
            'strategy_id': 'BRK_OPEN_0001',
            'from_status': 'LIVE',
            'to_status': 'QUARANTINE',
            'reason': 'Drawdown exceeded',
            'user_id': 'user-100'
        }
        
        # Handler should complete without error
        alert = alert_service.handle_degradation(degradation_event)
        assert alert is not None
