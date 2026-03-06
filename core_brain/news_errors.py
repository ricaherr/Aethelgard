"""
Economic Data Validation Errors
=================================

Error classes for NewsSanitizer and economic calendar data governance.
"""


class DataSchemaError(Exception):
    """
    Raised when economic event data fails schema validation.
    
    Causes:
    - Missing mandatory fields (event_name, country, impact_score, event_time_utc)
    - Invalid country code (not ISO 3166-1 alpha-2)
    - Unparseable timestamp
    - Non-enum impact score that cannot be normalized
    
    Log Level: WARNING
    Action: Skip record, continue batch processing
    """
    pass


class DataLatencyError(Exception):
    """
    Raised when economic event is outside acceptable time window.
    
    Criteria:
    - Age > 30 days in the past → REJECT (stale data)
    - Age ≤ 30 days forward → ACCEPT (forecast)
    
    Log Level: WARNING
    Action: Skip record, continue batch processing
    """
    pass


class DataIncompatibilityError(Exception):
    """
    Raised when economic data cannot be reconciled to standard format.
    
    Causes:
    - Impact value impossible to normalize to HIGH|MEDIUM|LOW
    - Country/currency code invalid (unmappable)
    - Data violates business logic constraints
    
    Log Level: ERROR
    Action: Skip record, escalate to admin
    """
    pass


class ImmutabilityViolation(Exception):
    """
    Raised when attempting to modify an immutable economic calendar record.
    
    Immutability Rule:
    - Once economic_calendar row is persisted → NO UPDATES ALLOWED
    - Corrections = new INSERT with new event_id
    - Updates attempt → ImmutabilityViolation exception
    
    Log Level: ERROR
    Action: Abort operation, escalate to operator
    """
    pass


class PersistenceError(Exception):
    """
    Raised when database operation (INSERT/SELECT) fails.
    
    Causes:
    - Database connection error
    - Constraint violation during INSERT
    - Schema mismatch
    
    Log Level: ERROR
    Action: Skip record, log detailed error
    """
    pass
