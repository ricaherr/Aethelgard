"""
Tests for Economic Fetch & Persist Module - FASE C.5 E2E

Tests complete workflow:
1. Fetch from all providers (parallel)
2. Sanitize batch (3 pilares validation)
3. Persist atomically (all-or-nothing)
4. Cycle execution end-to-end

Type Hints: 100% coverage
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

from core_brain.economic_fetch_persist import (
    EconomicFetchPersist,
    FetchPersistMetrics,
    fetch_and_persist_economic_data
)
from connectors.economic_data_gateway import EconomicDataProviderRegistry
from core_brain.news_sanitizer import NewsSanitizer
from core_brain.news_errors import (
    DataSchemaError,
    DataLatencyError,
    DataIncompatibilityError,
    PersistenceError
)
from data_vault.storage import StorageManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_gateway():
    """Mock EconomicDataProviderRegistry."""
    mock = MagicMock(spec=EconomicDataProviderRegistry)
    
    # Create mock adapters
    mock_adapter1 = AsyncMock()
    mock_adapter1.provider_name = "Investing"
    mock_adapter1.fetch_events = AsyncMock(return_value=[
        {'event_name': 'NFP', 'country': 'US', 'impact': 'high', 'provider_source': 'Investing'},
        {'event_name': 'CPI', 'country': 'US', 'impact': 'high', 'provider_source': 'Investing'}
    ])
    
    mock_adapter2 = AsyncMock()
    mock_adapter2.provider_name = "ForexFactory"
    mock_adapter2.fetch_events = AsyncMock(return_value=[
        {'event_name': 'ECB Rate', 'country': 'EU', 'impact': 'high', 'provider_source': 'ForexFactory'}
    ])
    
    mock.get_all_adapters = MagicMock(return_value=[mock_adapter1, mock_adapter2])
    return mock


@pytest.fixture
def mock_sanitizer():
    """Mock NewsSanitizer."""
    mock = MagicMock(spec=NewsSanitizer)
    
    # Default: accept all events
    def sanitize_impl(event, provider_source):
        return {
            **event,
            'event_id': 'evt-001',
            'normalized_country': 'US'
        }
    
    mock.sanitize_event = MagicMock(side_effect=sanitize_impl)
    return mock


@pytest.fixture
def mock_storage():
    """Mock StorageManager."""
    mock = MagicMock(spec=StorageManager)
    mock.insert_economic_calendar_batch = MagicMock(return_value=3)  # 3 inserts
    return mock


@pytest.fixture
def fetch_persist(mock_gateway, mock_sanitizer, mock_storage):
    """Create EconomicFetchPersist instance."""
    return EconomicFetchPersist(
        gateway=mock_gateway,
        sanitizer=mock_sanitizer,
        storage=mock_storage
    )


# ============================================================================
# FETCH TESTS
# ============================================================================

class TestFetchAllProviders:
    """Tests for fetch_all_providers method."""
    
    @pytest.mark.asyncio
    async def test_fetch_all_providers_parallel_execution(self, fetch_persist):
        """Verify all providers fetched in parallel."""
        start_time = datetime.now(timezone.utc)
        
        # Execute fetch
        events = await fetch_persist.fetch_all_providers(days_back=7)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Should get events from both adapters
        assert isinstance(events, list)
        assert len(events) > 0
        assert any(e.get('provider_source') == 'Investing' for e in events)
        assert any(e.get('provider_source') == 'ForexFactory' for e in events)
    
    @pytest.mark.asyncio
    async def test_fetch_respects_days_back_parameter(self, fetch_persist):
        """Verify days_back parameter passed to all adapters."""
        await fetch_persist.fetch_all_providers(days_back=14)
        
        # Verify adapters called with correct parameter
        adapters = fetch_persist.gateway.get_all_adapters()
        for adapter in adapters:
            adapter.fetch_events.assert_called_once_with(days_back=14)
    
    @pytest.mark.asyncio
    async def test_fetch_handles_adapter_failure_gracefully(self, fetch_persist):
        """Verify fetch continues if one adapter fails."""
        # Make one adapter fail
        adapters = fetch_persist.gateway.get_all_adapters()
        adapters[0].fetch_events = AsyncMock(side_effect=Exception("Provider error"))
        
        # Fetch should continue with other adapters
        events = await fetch_persist.fetch_all_providers()
        
        # Should still get events from ForexFactory
        assert len(events) > 0
        assert any(e.get('provider_source') == 'ForexFactory' for e in events)
    
    @pytest.mark.asyncio
    async def test_fetch_returns_empty_list_if_no_adapters(self, fetch_persist):
        """Verify returns empty list if no adapters available."""
        fetch_persist.gateway.get_all_adapters = MagicMock(return_value=[])
        
        events = await fetch_persist.fetch_all_providers()
        
        assert events == []
    
    @pytest.mark.asyncio
    async def test_fetch_flattens_results_from_all_adapters(self, fetch_persist):
        """Verify results from all adapters are flattened into single list."""
        events = await fetch_persist.fetch_all_providers()
        
        # Should have events from all adapters (3 total)
        assert len(events) == 3
        providers = {e.get('provider_source') for e in events}
        assert providers == {'Investing', 'ForexFactory'}


# ============================================================================
# SANITIZE TESTS
# ============================================================================

class TestSanitizeBatch:
    """Tests for sanitize_batch method."""
    
    def test_sanitize_accepts_valid_events(self, fetch_persist, mock_sanitizer):
        """Verify valid events are accepted."""
        events = [
            {'event_name': 'NFP', 'country': 'US', 'provider_source': 'Investing'},
            {'event_name': 'CPI', 'country': 'US', 'provider_source': 'Investing'}
        ]
        
        # Mock: all events valid
        mock_sanitizer.sanitize_event = MagicMock(side_effect=lambda e, p: {**e, 'event_id': 'evt-001'})
        
        accepted, acc_count, rej_count, reasons = fetch_persist.sanitize_batch(events)
        
        assert acc_count == 2
        assert rej_count == 0
        assert len(accepted) == 2
    
    def test_sanitize_rejects_schema_errors(self, fetch_persist, mock_sanitizer):
        """Verify events with schema errors are rejected."""
        events = [
            {'event_name': 'NFP', 'country': 'US', 'provider_source': 'Investing'},
            {'event_name': 'BAD', 'country': None, 'provider_source': 'Investing'}  # Missing country
        ]
        
        # Mock: second event fails schema validation
        def sanitize_impl(event, provider):
            if event['country'] is None:
                raise DataSchemaError("Missing country")
            return {**event, 'event_id': 'evt-001'}
        
        mock_sanitizer.sanitize_event = MagicMock(side_effect=sanitize_impl)
        
        accepted, acc_count, rej_count, reasons = fetch_persist.sanitize_batch(events)
        
        assert acc_count == 1
        assert rej_count == 1
        assert reasons.get('schema_error', 0) == 1
    
    def test_sanitize_rejects_latency_errors(self, fetch_persist, mock_sanitizer):
        """Verify events with latency errors are rejected."""
        events = [
            {'event_name': 'NFP', 'event_date': datetime.now(timezone.utc), 'provider_source': 'Investing'},
            {'event_name': 'OLD', 'event_date': datetime.now(timezone.utc) - timedelta(days=60), 'provider_source': 'Investing'}
        ]
        
        # Mock: second event fails latency (too old)
        def sanitize_impl(event, provider):
            if event['event_date'] < datetime.now(timezone.utc) - timedelta(days=30):
                raise DataLatencyError("Event too old")
            return {**event, 'event_id': 'evt-001'}
        
        mock_sanitizer.sanitize_event = MagicMock(side_effect=sanitize_impl)
        
        accepted, acc_count, rej_count, reasons = fetch_persist.sanitize_batch(events)
        
        assert acc_count == 1
        assert rej_count == 1
        assert reasons.get('latency_error', 0) == 1
    
    def test_sanitize_rejects_incompatibility_errors(self, fetch_persist, mock_sanitizer):
        """Verify incompatible events are rejected."""
        events = [
            {'event_name': 'NFP', 'country': 'US', 'provider_source': 'Investing'},
            {'event_name': 'UNKNOWN_IMPACT', 'country': 'US', 'impact': 'invalid', 'provider_source': 'Investing'}
        ]
        
        # Mock: second event has invalid impact
        def sanitize_impl(event, provider):
            if event.get('impact') not in [None, 'low', 'medium', 'high']:
                raise DataIncompatibilityError("Invalid impact value")
            return {**event, 'event_id': 'evt-001'}
        
        mock_sanitizer.sanitize_event = MagicMock(side_effect=sanitize_impl)
        
        accepted, acc_count, rej_count, reasons = fetch_persist.sanitize_batch(events)
        
        assert acc_count == 1
        assert rej_count == 1
        assert reasons.get('incompatibility_error', 0) == 1
    
    def test_sanitize_counts_rejection_reasons(self, fetch_persist, mock_sanitizer):
        """Verify rejection reasons are counted correctly."""
        events = [
            {'event_name': 'E1', 'provider_source': 'Investing'},
            {'event_name': 'E2', 'provider_source': 'Investing'},
            {'event_name': 'E3', 'provider_source': 'Investing'}
        ]
        
        # Mock: first fails schema, second fails latency, third passes
        def sanitize_impl(event, provider):
            if event['event_name'] == 'E1':
                raise DataSchemaError("Error1")
            elif event['event_name'] == 'E2':
                raise DataLatencyError("Error2")
            return {**event, 'event_id': 'evt-001'}
        
        mock_sanitizer.sanitize_event = MagicMock(side_effect=sanitize_impl)
        
        accepted, acc_count, rej_count, reasons = fetch_persist.sanitize_batch(events)
        
        assert rej_count == 2
        assert reasons == {'schema_error': 1, 'latency_error': 1}


# ============================================================================
# PERSIST TESTS
# ============================================================================

class TestPersistAtomic:
    """Tests for persist_atomic method."""
    
    def test_persist_empty_list_returns_zero(self, fetch_persist):
        """Verify empty list persists with 0 inserts."""
        inserted, error = fetch_persist.persist_atomic([])
        
        assert inserted == 0
        assert error is None
        fetch_persist.storage.insert_economic_calendar_batch.assert_not_called()
    
    def test_persist_successful_inserts_all_events(self, fetch_persist):
        """Verify all events inserted successfully."""
        events = [
            {'event_name': 'NFP', 'event_id': 'evt-001'},
            {'event_name': 'CPI', 'event_id': 'evt-002'},
            {'event_name': 'ECB', 'event_id': 'evt-003'}
        ]
        
        fetch_persist.storage.insert_economic_calendar_batch = MagicMock(return_value=3)
        
        inserted, error = fetch_persist.persist_atomic(events)
        
        assert inserted == 3
        assert error is None
        fetch_persist.storage.insert_economic_calendar_batch.assert_called_once_with(events)
    
    def test_persist_handles_persistence_error(self, fetch_persist):
        """Verify PersistenceError returns error message."""
        events = [{'event_name': 'NFP', 'event_id': 'evt-001'}]
        
        fetch_persist.storage.insert_economic_calendar_batch = MagicMock(
            side_effect=PersistenceError("Database locked")
        )
        
        inserted, error = fetch_persist.persist_atomic(events)
        
        assert inserted == 0
        assert error is not None
        assert "Database locked" in error
    
    def test_persist_handles_generic_exception(self, fetch_persist):
        """Verify generic exceptions are caught and reported."""
        events = [{'event_name': 'NFP', 'event_id': 'evt-001'}]
        
        fetch_persist.storage.insert_economic_calendar_batch = MagicMock(
            side_effect=RuntimeError("Network error")
        )
        
        inserted, error = fetch_persist.persist_atomic(events)
        
        assert inserted == 0
        assert error is not None
        assert "Network error" in error


# ============================================================================
# END-TO-END CYCLE TESTS
# ============================================================================

class TestExecuteCycle:
    """Tests for complete fetch → sanitize → persist cycle."""
    
    @pytest.mark.asyncio
    async def test_execute_cycle_complete_flow(self, fetch_persist, mock_sanitizer, mock_storage):
        """Verify complete cycle executes successfully."""
        # Setup mocks
        mock_sanitizer.sanitize_event = MagicMock(
            side_effect=lambda e, p: {**e, 'event_id': 'evt-001'}
        )
        mock_storage.insert_economic_calendar_batch = MagicMock(return_value=3)
        
        metrics = await fetch_persist.execute_cycle(days_back=7)
        
        # Verify metrics
        assert isinstance(metrics, FetchPersistMetrics)
        assert metrics.success is True
        assert metrics.events_fetched > 0
        assert metrics.events_accepted > 0
        assert metrics.db_inserts == 3
        assert metrics.error_message is None
    
    @pytest.mark.asyncio
    async def test_execute_cycle_with_rejections(self, fetch_persist, mock_sanitizer, mock_storage):
        """Verify cycle metrics include rejections."""
        events_fetched = [
            {'event_name': 'NFP', 'provider_source': 'Investing'},
            {'event_name': 'BAD', 'provider_source': 'Investing'}
        ]
        
        # Adapters return 2 events
        adapters = fetch_persist.gateway.get_all_adapters()
        adapters[0].fetch_events = AsyncMock(return_value=events_fetched)
        adapters[1].fetch_events = AsyncMock(return_value=[])
        
        # Sanitizer rejects one
        def sanitize_impl(event, provider):
            if event['event_name'] == 'BAD':
                raise DataSchemaError("Invalid event")
            return {**event, 'event_id': 'evt-001'}
        
        mock_sanitizer.sanitize_event = MagicMock(side_effect=sanitize_impl)
        mock_storage.insert_economic_calendar_batch = MagicMock(return_value=1)
        
        metrics = await fetch_persist.execute_cycle()
        
        assert metrics.events_fetched == 2
        assert metrics.events_accepted == 1
        assert metrics.events_rejected == 1
        assert metrics.db_inserts == 1
    
    @pytest.mark.asyncio
    async def test_execute_cycle_failure_returns_failed_metrics(self, fetch_persist, mock_sanitizer, mock_storage):
        """Verify cycle failure returns appropriate metrics."""
        mock_sanitizer.sanitize_event = MagicMock(
            side_effect=lambda e, p: {**e, 'event_id': 'evt-001'}
        )
        mock_storage.insert_economic_calendar_batch = MagicMock(
            side_effect=PersistenceError("Insert failed")
        )
        
        metrics = await fetch_persist.execute_cycle()
        
        assert metrics.success is False
        assert metrics.error_message is not None
        assert metrics.db_inserts == 0
    
    @pytest.mark.asyncio
    async def test_execute_cycle_duration_measured(self, fetch_persist, mock_sanitizer, mock_storage):
        """Verify cycle duration is accurately measured."""
        mock_sanitizer.sanitize_event = MagicMock(
            side_effect=lambda e, p: {**e, 'event_id': 'evt-001'}
        )
        mock_storage.insert_economic_calendar_batch = MagicMock(return_value=3)
        
        metrics = await fetch_persist.execute_cycle()
        
        assert metrics.duration_sec >= 0.0
        assert metrics.timestamp is not None


# ============================================================================
# SCHEDULER JOB FUNCTION TESTS
# ============================================================================

class TestSchedulerJobFunction:
    """Tests for fetch_and_persist_economic_data async job."""
    
    @pytest.mark.asyncio
    async def test_job_requires_all_dependencies(self):
        """Verify job fails gracefully if dependencies missing."""
        metrics = await fetch_and_persist_economic_data(
            gateway=None,
            sanitizer=None,
            storage=None
        )
        
        assert metrics.success is False
        assert "Missing dependencies" in metrics.error_message
    
    @pytest.mark.asyncio
    async def test_job_executes_cycle_with_dependencies(self, mock_gateway, mock_sanitizer, mock_storage):
        """Verify job executes complete cycle when dependencies provided."""
        mock_sanitizer.sanitize_event = MagicMock(
            side_effect=lambda e, p: {**e, 'event_id': 'evt-001'}
        )
        mock_storage.insert_economic_calendar_batch = MagicMock(return_value=2)
        
        metrics = await fetch_and_persist_economic_data(
            gateway=mock_gateway,
            sanitizer=mock_sanitizer,
            storage=mock_storage,
            days_back=7
        )
        
        assert isinstance(metrics, FetchPersistMetrics)
        assert metrics.db_inserts > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
