"""
TEST: Economic Calendar Consolidation (Correction 3)
Verifies that get_economic_calendar() is the primary method with filtering capability.
"""
import pytest
from unittest.mock import MagicMock
from data_vault.storage import StorageManager


@pytest.fixture
def mock_storage(tmp_path):
    """Create in-memory StorageManager for testing"""
    db_path = str(tmp_path / "test.db")
    storage = StorageManager(db_path=db_path)
    return storage


class TestEconomicCalendarConsolidation:
    """Verify get_economic_calendar() is unified primary method"""
    
    def test_get_economic_calendar_has_parameters(self, mock_storage):
        """
        CORRECTION 3: get_economic_calendar() must accept days_back and country_filter
        """
        import inspect
        
        sig = inspect.signature(mock_storage.get_economic_calendar)
        params = list(sig.parameters.keys())
        
        # Must have days_back parameter
        assert "days_back" in params, "Missing days_back parameter"
        
        # Must have country_filter parameter
        assert "country_filter" in params, "Missing country_filter parameter"
        
        # days_back should default to 30
        assert sig.parameters["days_back"].default == 30
        
        # country_filter should default to None
        assert sig.parameters["country_filter"].default is None
    
    def test_get_economic_calendar_returns_list(self, mock_storage):
        """get_economic_calendar() returns List[Dict]"""
        result = mock_storage.get_economic_calendar()
        assert isinstance(result, list)
    
    def test_get_economic_events_is_deprecated_wrapper(self, mock_storage):
        """
        CORRECTION 3: get_economic_events() must be wrapper (backwards compatibility)
        """
        import inspect
        
        # Check docstring mentions DEPRECATED
        docstring = mock_storage.get_economic_events.__doc__
        assert docstring is not None
        assert "DEPRECATED" in docstring.upper()
        
        # Check signature matches get_economic_calendar
        sig_calendar = inspect.signature(mock_storage.get_economic_calendar)
        sig_events = inspect.signature(mock_storage.get_economic_events)
        
        assert list(sig_calendar.parameters.keys()) == list(sig_events.parameters.keys())
    
    def test_get_economic_events_delegates_to_calendar(self, mock_storage):
        """Verify get_economic_events() correctly delegates to get_economic_calendar()"""
        # Both should return same result (empty list if no data)
        result_calendar = mock_storage.get_economic_calendar(days_back=30)
        result_events = mock_storage.get_economic_events(days_back=30)
        
        assert result_calendar == result_events
    
    def test_get_economic_calendar_type_hints(self, mock_storage):
        """Verify get_economic_calendar() has proper type hints"""
        import inspect
        
        sig = inspect.signature(mock_storage.get_economic_calendar)
        
        # Check return type hint
        assert sig.return_annotation != inspect.Signature.empty, \
            "get_economic_calendar() must have return type hint"
        
        # Check parameter type hints
        for param_name in ["days_back", "country_filter"]:
            param = sig.parameters[param_name]
            assert param.annotation != inspect.Parameter.empty, \
                f"Parameter '{param_name}' must have type hint"
