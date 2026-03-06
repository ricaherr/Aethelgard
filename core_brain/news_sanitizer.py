"""
News Sanitizer - Economic Calendar Data Validation Gate
========================================================

Validates and transforms raw economic data (Bloomberg, Investing.com, etc.)
to system-compatible format with 3 pillars of validation:

Pilar 1: Schema Validation (mandatory fields, normalization)
Pilar 2: Latency Validation (age window: NOW-30 to NOW+30 days)
Pilar 3: Immutability Enforcement (no updates after persistence)

Responsibility: Act as gate keeper before economic_calendar table persistence.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4

from core_brain.news_errors import (
    DataSchemaError,
    DataLatencyError,
    DataIncompatibilityError,
)

logger = logging.getLogger(__name__)


# ISO 3166-1 Alpha-2 Country Codes (Forex/Economic focused)
VALID_COUNTRY_CODES: set = {
    "USA", "EUR", "GBR", "JPY", "CHF", "CNY", "AUD", "CAD", "NZD",
    "INR", "BRL", "ZAR", "MXN", "RUB", "SGD", "HKD", "KRW"
}

# Normalization: Free-text to standard ISO codes
COUNTRY_NORMALIZER: Dict[str, str] = {
    "United States": "USA", "US": "USA", "America": "USA",
    "Eurozone": "EUR", "EU": "EUR", "Euro Area": "EUR",
    "United Kingdom": "GBR", "UK": "GBR", "Britain": "GBR",
    "Japan": "JPY", "Switzerland": "CHF", "China": "CNY",
    "Australia": "AUD", "Canada": "CAD", "New Zealand": "NZD",
}

# ISO 4217 Currency Codes (subset for forex)
VALID_CURRENCY_CODES: set = {
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", "AUD", "CAD", "NZD",
    "INR", "BRL", "ZAR", "MXN", "RUB", "SGD", "HKD", "KRW"
}

# Impact Score Normalization: free-text/numeric to standard ENUM
IMPACT_NORMALIZER: Dict[str, str] = {
    "high": "HIGH", "HIGH": "HIGH", "3": "HIGH", "alto": "HIGH",
    "medium": "MEDIUM", "MEDIUM": "MEDIUM", "2": "MEDIUM", "medio": "MEDIUM",
    "low": "LOW", "LOW": "LOW", "1": "LOW", "bajo": "LOW",
}


class NewsSanitizer:
    """
    Economic calendar data sanitizer: validates and transforms raw external data.
    
    Implements 3-pillar validation:
    1. Schema Validation: Mandatory fields, type checks, normalization
    2. Latency Validation: Age window (NOW-30 to NOW+30 days)
    3. Immutability Enforcement: Post-persistence read-only guarantee
    
    Responsibility:
    - Transform raw economic data to system-compatible format
    - Reject invalid/stale data with detailed logging
    - Generate system-assigned event_id (UUID)
    - Prepare data for StorageManager persistence
    """
    
    def __init__(self) -> None:
        """
        Initialize sanitizer with static validators.
        
        Note: No dependencies injected (stateless validator class).
        """
        self.valid_countries = VALID_COUNTRY_CODES
        self.valid_currencies = VALID_CURRENCY_CODES
        self.country_map = COUNTRY_NORMALIZER
        self.impact_map = IMPACT_NORMALIZER
    
    def sanitize_batch(
        self, 
        events: List[Dict[str, Any]], 
        provider_source: str
    ) -> Tuple[List[Dict[str, Any]], int, int, List[str]]:
        """
        Process batch of economic events through validation gates.
        
        Args:
            events: Raw event objects from provider
            provider_source: Source provider (BLOOMBERG, INVESTING, FOREXFACTORY)
        
        Returns:
            (validated_events, accepted_count, rejected_count, rejection_reasons)
        
        Implementation:
        - Process each event independently
        - Bad records don't block good records
        - Collect rejection reasons for logging
        """
        validated: List[Dict[str, Any]] = []
        rejected = 0
        rejections: List[str] = []
        
        for idx, event in enumerate(events):
            try:
                # Pilar 1: Schema Validation
                self._validate_schema(event, provider_source)
                
                # Pilar 2: Latency Validation
                self._validate_latency(event)
                
                # Normalize event
                normalized = self._normalize_event(event, provider_source)
                
                # Generate event_id (system-assigned, not from provider)
                normalized["event_id"] = str(uuid4())
                normalized["is_verified"] = False
                
                validated.append(normalized)
                logger.info(
                    f"[NEWS_SANITIZER] Event {idx} ACCEPTED: "
                    f"{normalized.get('event_name')} ({normalized.get('country')})"
                )
                
            except (DataSchemaError, DataLatencyError, DataIncompatibilityError) as e:
                rejected += 1
                reason = f"Event {idx}: {type(e).__name__} - {str(e)}"
                rejections.append(reason)
                logger.warning(f"[NEWS_SANITIZER] {reason}")
                # Continue processing next event
        
        logger.info(
            f"[NEWS_SANITIZER] Batch summary: {len(events)} total, "
            f"{len(validated)} accepted, {rejected} rejected"
        )
        
        return validated, len(validated), rejected, rejections
    
    def _validate_schema(self, event: Dict[str, Any], provider_source: str) -> None:
        """
        Pilar 1: Schema Validation
        
        Mandatory fields:
        - event_name: Non-empty string
        - country: Valid ISO code or normalizable
        - impact_score: HIGH|MEDIUM|LOW or normalizable
        - event_time_utc: Valid UTC datetime
        - currency: Valid ISO 4217 code
        
        Raises:
            DataSchemaError: If validation fails
        """
        # Check mandatory fields presence
        mandatory = ["event_name", "country", "impact_score", "event_time_utc"]
        for field in mandatory:
            if field not in event or event[field] is None:
                raise DataSchemaError(f"Missing mandatory field: {field}")
        
        # Validate event_name (non-empty string)
        if not isinstance(event.get("event_name"), str) or not event["event_name"].strip():
            raise DataSchemaError("event_name must be non-empty string")
        
        # Validate country code
        country_input = event.get("country", "")
        country_upper = str(country_input).upper()
        
        # Check if it's already a valid ISO code OR if it can be normalized
        is_valid_iso = country_upper in self.valid_countries
        is_normalizable = any(
            key.lower() == str(country_input).lower() 
            for key in self.country_map.keys()
        )
        
        if not is_valid_iso and not is_normalizable:
            raise DataSchemaError(f"Invalid country code: {country_input}")
        
        # Validate impact_score
        impact = str(event.get("impact_score", "")).upper()
        if impact not in self.impact_map and impact not in ["HIGH", "MEDIUM", "LOW"]:
            raise DataSchemaError(f"Impact score not normalizable: {event.get('impact_score')}")
        
        # Validate event_time_utc is parseable to datetime
        try:
            time_str = event.get("event_time_utc")
            if isinstance(time_str, str):
                datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            elif not isinstance(time_str, datetime):
                raise ValueError("event_time_utc must be string or datetime")
        except (ValueError, TypeError) as e:
            raise DataSchemaError(f"event_time_utc unparseable: {str(e)}")
        
        # Validate currency (if present)
        if "currency" in event and event["currency"]:
            currency = str(event["currency"]).upper()
            if currency not in self.valid_currencies:
                raise DataSchemaError(f"Invalid currency code: {event.get('currency')}")
    
    def _validate_latency(self, event: Dict[str, Any]) -> None:
        """
        Pilar 2: Latency Validation
        
        Age window:
        - Accept: NOW - 30 days to NOW + 30 days
        - Reject: older than 30 days (stale)
        - Allow: future events (forecasts)
        
        Raises:
            DataLatencyError: If event is outside window
        """
        time_str = event.get("event_time_utc")
        
        try:
            if isinstance(time_str, str):
                event_dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                event_dt = time_str
            
            # Ensure UTC comparison
            now = datetime.utcnow()
            if event_dt.tzinfo is not None:
                now = now.replace(tzinfo=event_dt.tzinfo)
            
            age_days = (now - event_dt).days
            
            # Reject if older than 30 days
            if age_days > 30:
                raise DataLatencyError(
                    f"Event age {age_days} days exceeds 30-day window"
                )
            
            # Allow future events (up to 30 days forward)
            if age_days < -30:
                raise DataLatencyError(
                    f"Event {abs(age_days)} days in future exceeds forecast window"
                )
            
        except (ValueError, TypeError) as e:
            raise DataLatencyError(f"Cannot calculate event age: {str(e)}")
    
    def _normalize_event(
        self, 
        event: Dict[str, Any], 
        provider_source: str
    ) -> Dict[str, Any]:
        """
        Normalize raw event to system format.
        
        Transformations:
        - country: normalize free-text to ISO code
        - impact_score: normalize to HIGH|MEDIUM|LOW enum
        - event_time_utc: ensure ISO format with Z/+00:00
        - currency: uppercase ISO code
        - event_id: ALWAYS generate UUID (system-assigned)
        
        Args:
            event: Raw event from provider
            provider_source: Provider name (for audit)
        
        Returns:
            Normalized event dict (ready for persistence)
        """
        normalized: Dict[str, Any] = {}
        
        # Copy base fields
        normalized["provider_source"] = provider_source
        normalized["event_name"] = event["event_name"].strip()
        
        # Normalize country
        country = str(event["country"]).upper()
        if country not in self.valid_countries and country in self.country_map.values():
            # Already normalized
            pass
        elif country not in self.valid_countries:
            # Try lowercase lookup in normalizer
            for key, val in self.country_map.items():
                if key.lower() == str(event["country"]).lower():
                    country = val
                    break
        normalized["country"] = country
        
        # Normalize impact_score
        impact = str(event.get("impact_score", "")).upper()
        if impact in self.impact_map:
            impact = self.impact_map[impact]
        normalized["impact_score"] = impact
        
        # Normalize currency
        if "currency" in event and event["currency"]:
            normalized["currency"] = str(event["currency"]).upper()
        
        # Normalize timestamp to ISO format
        time_str = event.get("event_time_utc")
        if isinstance(time_str, datetime):
            normalized["event_time_utc"] = time_str.isoformat()
        else:
            # Ensure Z suffix for UTC
            normalized["event_time_utc"] = time_str.replace("+00:00", "Z") if "+00:00" in time_str else time_str
        
        # Copy numeric fields (nullable)
        for field in ["forecast", "actual", "previous"]:
            if field in event:
                try:
                    normalized[field] = float(event[field]) if event[field] is not None else None
                except (ValueError, TypeError):
                    normalized[field] = None
        
        # System fields set by Sanitizer
        normalized["event_id"] = str(uuid4())  # ALWAYS generate, never from provider
        normalized["created_at"] = datetime.utcnow().isoformat() + "Z"
        normalized["data_version"] = 1
        
        return normalized
    
    def sanitize_event(
        self, 
        event: Dict[str, Any], 
        provider_source: str
    ) -> Dict[str, Any]:
        """
        Main entry point: validate → normalize → return.
        
        Flow:
        1. Normalize event (country codes, impact levels, etc.)
        2. Validate schema (check mandatory fields now in normalized form)
        3. Validate latency (event_time_utc within valid window)
        4. Return sanitized event ready for persistence
        
        Args:
            event: Raw event from provider (may have free-text country names, etc.)
            provider_source: Provider name (BLOOMBERG, INVESTING, FOREXFACTORY, etc.)
        
        Returns:
            Fully normalized, validated, UUID-assigned event dict
        
        Raises:
            DataSchemaError: Missing/invalid mandatory fields
            DataLatencyError: Event outside valid time window
            DataIncompatibilityError: Cannot be normalized
        """
        # Step 1: NORMALIZE FIRST (converts "United States" → "USA", etc.)
        try:
            normalized = self._normalize_event(event, provider_source)
        except (KeyError, ValueError) as e:
            raise DataIncompatibilityError(
                f"Cannot normalize event from {provider_source}: {str(e)}"
            )
        
        # Step 2: VALIDATE SCHEMA (now safe - all fields normalized)
        self._validate_schema(normalized, provider_source)
        
        # Step 3: VALIDATE LATENCY
        self._validate_latency(normalized)
        
        return normalized
    
    @staticmethod
    def validate_immutability(event_id: str, update_fields: Dict[str, Any]) -> None:
        """
        Pilar 3: Immutability enforcement check.
        
        Post-persistence, economic_calendar records are READ-ONLY.
        
        Args:
            event_id: UUID of record to update
            update_fields: Fields requested for update
        
        Raises:
            ImmutabilityViolation: Always (updates are forbidden)
        """
        from core_brain.news_errors import ImmutabilityViolation
        
        raise ImmutabilityViolation(
            f"POST-PERSISTENCE UPDATES ARE FORBIDDEN: event_id={event_id}. "
            f"Corrections must be new INSERTs, not updates."
        )
