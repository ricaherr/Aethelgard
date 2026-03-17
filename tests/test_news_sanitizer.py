"""
Tests for NewsSanitizer - Economic Calendar Data Validation
==========================================================

Comprehensive test suite covering all 3 pillars of validation:
1. Schema Validation
2. Latency Validation
3. Immutability Enforcement

Plus UUID generation, batch processing, and integration with StorageManager.
"""
import pytest
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from uuid import UUID

from core_brain.news_sanitizer import NewsSanitizer, VALID_COUNTRY_CODES
from core_brain.news_errors import (
    DataSchemaError,
    DataLatencyError,
    ImmutabilityViolation,
    PersistenceError,
)
from data_vault.storage import StorageManager
from tests.conftest import TEST_PROVIDER_SOURCE


class TestNewsSanitizerSchemaValidation:
    """Test Pilar 1: Schema Validation"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    @pytest.fixture
    def valid_event(self) -> Dict[str, Any]:
        """Create a valid economic event"""
        return {
            "event_name": "Non-Farm Payrolls",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
            "event_time_utc": datetime.now(timezone.utc).isoformat(),
            "forecast": 150000.0,
            "actual": None,
            "previous": 145000.0,
        }
    
    def test_valid_event_passes_schema(self, sanitizer, valid_event):
        """Test that valid event passes schema validation"""
        # Should not raise
        sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_missing_event_name_rejected(self, sanitizer, valid_event):
        """Test that missing event_name is rejected"""
        del valid_event["event_name"]
        
        with pytest.raises(DataSchemaError, match="Missing mandatory field: event_name"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_missing_country_rejected(self, sanitizer, valid_event):
        """Test that missing country is rejected"""
        del valid_event["country"]
        
        with pytest.raises(DataSchemaError, match="Missing mandatory field: country"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_missing_impact_score_rejected(self, sanitizer, valid_event):
        """Test that missing impact_score is rejected"""
        del valid_event["impact_score"]
        
        with pytest.raises(DataSchemaError, match="Missing mandatory field: impact_score"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_missing_event_time_utc_rejected(self, sanitizer, valid_event):
        """Test that missing event_time_utc is rejected"""
        del valid_event["event_time_utc"]
        
        with pytest.raises(DataSchemaError, match="Missing mandatory field: event_time_utc"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_empty_event_name_rejected(self, sanitizer, valid_event):
        """Test that empty event_name is rejected"""
        valid_event["event_name"] = ""
        
        with pytest.raises(DataSchemaError, match="event_name must be non-empty string"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_invalid_country_code_rejected(self, sanitizer, valid_event):
        """Test that invalid country code is rejected"""
        valid_event["country"] = "INVALID"
        
        with pytest.raises(DataSchemaError, match="Invalid country code"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_valid_country_codes_accepted(self, sanitizer, valid_event):
        """Test that all valid ISO country codes are accepted"""
        # Use VALID_COUNTRY_CODES from source of truth (SSOT)
        for code in list(VALID_COUNTRY_CODES)[:5]:  # Test first 5
            valid_event["country"] = code
            # Should not raise
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_invalid_impact_score_rejected(self, sanitizer, valid_event):
        """Test that invalid impact score is rejected"""
        valid_event["impact_score"] = "INVALID"
        
        with pytest.raises(DataSchemaError, match="Impact score not normalizable"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_unparseable_timestamp_rejected(self, sanitizer, valid_event):
        """Test that unparseable timestamp is rejected"""
        valid_event["event_time_utc"] = "not-a-date"
        
        with pytest.raises(DataSchemaError, match="event_time_utc unparseable"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)
    
    def test_invalid_currency_code_rejected(self, sanitizer, valid_event):
        """Test that invalid currency code is rejected"""
        valid_event["currency"] = "INVALID"
        
        with pytest.raises(DataSchemaError, match="Invalid currency code"):
            sanitizer._validate_schema(valid_event, TEST_PROVIDER_SOURCE)


class TestNewsSanitizerLatencyValidation:
    """Test Pilar 2: Latency Validation"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    @pytest.fixture
    def base_event(self) -> Dict[str, Any]:
        """Create base event for testing"""
        return {
            "event_name": "Test Event",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
        }
    
    def test_recent_event_accepted(self, sanitizer, base_event):
        """Test that event from 5 days ago is accepted"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        
        # Should not raise
        sanitizer._validate_latency(base_event)
    
    def test_event_at_boundary_30_days_accepted(self, sanitizer, base_event):
        """Test that event from exactly 30 days ago is accepted"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        # Should not raise
        sanitizer._validate_latency(base_event)
    
    def test_stale_event_31_days_rejected(self, sanitizer, base_event):
        """Test that event from 31 days ago is rejected (DataLatencyError)"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        
        with pytest.raises(DataLatencyError, match="exceeds 30-day window"):
            sanitizer._validate_latency(base_event)
    
    def test_very_old_event_rejected(self, sanitizer, base_event):
        """Test that very old event (60 days) is rejected"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        
        with pytest.raises(DataLatencyError):
            sanitizer._validate_latency(base_event)
    
    def test_future_forecast_accepted(self, sanitizer, base_event):
        """Test that future event (forecast) is accepted if < 30 days forward"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        
        # Should not raise
        sanitizer._validate_latency(base_event)
    
    def test_future_forecast_boundary_30_days_accepted(self, sanitizer, base_event):
        """Test that future event at exactly 30 days forward is accepted"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        
        # Should not raise
        sanitizer._validate_latency(base_event)
    
    def test_too_far_future_rejected(self, sanitizer, base_event):
        """Test that event > 30 days in future is rejected"""
        base_event["event_time_utc"] = (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()
        
        with pytest.raises(DataLatencyError, match="exceeds forecast window"):
            sanitizer._validate_latency(base_event)


class TestNewsSanitizerNormalization:
    """Test data normalization (country, impact, timestamp)"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    def test_country_normalization_free_text(self, sanitizer):
        """Test that free-text country names are normalized to ISO codes"""
        event = {
            "event_name": "Test",
            "country": "United States",
            "currency": "USD",
            "impact_score": "HIGH",
            "event_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        # First validate, then normalize
        sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
        normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
        
        assert normalized["country"] == "USA"
    
    def test_impact_score_normalization(self, sanitizer):
        """Test that impact scores are normalized to standard enum"""
        test_cases = [
            ("HIGH", "HIGH"),
            ("high", "HIGH"),
            ("3", "HIGH"),
            ("MEDIUM", "MEDIUM"),
            ("medium", "MEDIUM"),
            ("2", "MEDIUM"),
            ("LOW", "LOW"),
            ("low", "LOW"),
            ("1", "LOW"),
        ]
        
        for input_val, expected in test_cases:
            event = {
                "event_name": "Test",
                "country": "USA",
                "currency": "USD",
                "impact_score": input_val,
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            }
            
            sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
            normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
            assert normalized["impact_score"] == expected


class TestNewsSanitizerUUIDGeneration:
    """Test Pilar 3: UUID generation and uniqueness"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    def test_event_id_generated_uuid(self, sanitizer):
        """Test that event_id is generated as UUID"""
        event = {
            "event_name": "Test",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
            "event_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
        normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
        
        # Should have event_id added by system
        assert "event_id" in normalized
        assert normalized["event_id"] is not None
        
        # Should be valid UUID
        UUID(normalized["event_id"])  # Raises ValueError if invalid
    
    def test_event_id_from_provider_ignored(self, sanitizer):
        """Test that event_id from external provider is replaced with system UUID"""
        event = {
            "event_name": "Test",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
            "event_time_utc": datetime.now(timezone.utc).isoformat(),
            "event_id": "provider-id-12345",  # Should be ignored
        }
        
        sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
        normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
        
        # System-generated ID should replace provider's
        assert normalized["event_id"] != "provider-id-12345"
        UUID(normalized["event_id"])  # Valid UUID
    
    def test_batch_event_ids_unique(self, sanitizer):
        """Test that event_ids in batch are unique"""
        events = [
            {
                "event_name": f"Event {i}",
                "country": "USA",
                "currency": "USD",
                "impact_score": "HIGH",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(5)
        ]
        
        validated, accepted, rejected, _ = sanitizer.sanitize_batch(events, "INVESTING")
        
        # All should be accepted
        assert accepted == 5
        assert rejected == 0
        
        # All event_ids should be unique
        event_ids = [e["event_id"] for e in validated]
        assert len(event_ids) == len(set(event_ids))


class TestNewsSanitizerBatchProcessing:
    """Test batch processing with mixed valid/invalid records"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    def test_batch_with_mixed_records(self, sanitizer):
        """Test that bad records don't block good ones"""
        events = [
            {  # Valid
                "event_name": "Event 1",
                "country": "USA",
                "currency": "USD",
                "impact_score": "HIGH",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            },
            {  # Invalid: missing country
                "event_name": "Event 2",
                "currency": "USD",
                "impact_score": "HIGH",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            },
            {  # Valid
                "event_name": "Event 3",
                "country": "GBR",
                "currency": "GBP",
                "impact_score": "MEDIUM",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            },
            {  # Invalid: stale (>30 days)
                "event_name": "Event 4",
                "country": "JPY",
                "currency": "JPY",
                "impact_score": "LOW",
                "event_time_utc": (datetime.now(timezone.utc) - timedelta(days=35)).isoformat(),
            },
        ]
        
        validated, accepted, rejected, rejections = sanitizer.sanitize_batch(events, "INVESTING")
        
        assert accepted == 2  # Events 1 and 3
        assert rejected == 2  # Events 2 and 4
        assert len(validated) == 2
        assert len(rejections) == 2
    
    def test_batch_summary_logging(self, sanitizer):
        """Test that batch summary includes counts"""
        events = [
            {
                "event_name": f"Event {i}",
                "country": "USA",
                "currency": "USD",
                "impact_score": "HIGH",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(3)
        ]
        
        validated, accepted, rejected, _ = sanitizer.sanitize_batch(events, "INVESTING")
        
        assert len(validated) == accepted
        assert accepted == 3
        assert rejected == 0


class TestNewsSanitizerImmutability:
    """Test immutability enforcement"""
    
    def test_update_always_raises_immutability_violation(self):
        """Test that update_economic_event() always raises ImmutabilityViolation"""
        sanitizer = NewsSanitizer()
        
        with pytest.raises(ImmutabilityViolation, match="POST-PERSISTENCE UPDATES ARE FORBIDDEN"):
            sanitizer.validate_immutability("event-id-123", {"impact_score": "LOW"})


class TestNewsSanitizerStorageIntegration:
    """Test integration with StorageManager"""
    
    @pytest.fixture
    def sanitizer(self) -> NewsSanitizer:
        """Create sanitizer instance"""
        return NewsSanitizer()
    
    @pytest.fixture
    def tmp_storage(self, tmp_path) -> StorageManager:
        """Create temporary StorageManager for testing"""
        db_path = tmp_path / "test_economic.db"
        return StorageManager(db_path=str(db_path))
    
    def test_save_sanitized_event_to_storage(self, sanitizer, tmp_storage):
        """Test saving sanitized event to StorageManager"""
        event = {
            "event_name": "Non-Farm Payrolls",
            "country": "USA",
            "currency": "USD",
            "impact_score": "HIGH",
            "event_time_utc": datetime.now(timezone.utc).isoformat(),
            "forecast": 150000.0,
            "provider_source": "INVESTING",
        }
        
        # Sanitize
        sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
        sanitizer._validate_latency(event)
        normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
        
        # Persist
        event_id = tmp_storage.save_economic_event(normalized)
        
        assert event_id is not None
        assert event_id == normalized["event_id"]
    
    def test_retrieve_saved_events(self, sanitizer, tmp_storage):
        """Test retrieving saved events from storage"""
        # Save multiple events
        for i in range(3):
            event = {
                "event_name": f"Event {i}",
                "country": "USA",
                "currency": "USD",
                "impact_score": "HIGH",
                "event_time_utc": datetime.now(timezone.utc).isoformat(),
                "provider_source": "INVESTING",
            }
            
            sanitizer._validate_schema(event, TEST_PROVIDER_SOURCE)
            sanitizer._validate_latency(event)
            normalized = sanitizer._normalize_event(event, TEST_PROVIDER_SOURCE)
            tmp_storage.save_economic_event(normalized)
        
        # Retrieve
        events = tmp_storage.get_economic_events(days_back=30)
        
        assert len(events) == 3
    
    def test_update_persisted_event_raises_immutability(self, tmp_storage):
        """Test that updating persisted event raises ImmutabilityViolation"""
        with pytest.raises(ImmutabilityViolation):
            tmp_storage.update_economic_event("event-123", {"impact_score": "LOW"})
