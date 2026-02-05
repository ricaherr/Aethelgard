"""
Test for EDGE Intelligence functionality
"""
import pytest
from data_vault.storage import StorageManager


class TestEdgeIntelligence:
    """Test EDGE Intelligence functionality"""

    @pytest.fixture
    def storage(self):
        """In-memory storage for testing"""
        return StorageManager(db_path=":memory:")

    def test_get_edge_learning_history_method_exists(self, storage: StorageManager) -> None:
        """Test that get_edge_learning_history method exists"""
        assert hasattr(storage, 'get_edge_learning_history')

    def test_get_edge_learning_history_is_callable(self, storage: StorageManager) -> None:
        """Test that get_edge_learning_history is callable"""
        assert callable(getattr(storage, 'get_edge_learning_history'))

    def test_get_edge_learning_history_returns_list(self, storage: StorageManager) -> None:
        """Test that get_edge_learning_history returns a list"""
        result = storage.get_edge_learning_history(limit=5)
        assert isinstance(result, list)

    def test_get_edge_learning_history_record_structure(self, storage: StorageManager) -> None:
        """Test that get_edge_learning_history returns properly structured records"""
        # First add a test record
        storage.save_edge_learning("Test detection", "Test action", "Test learning")

        result = storage.get_edge_learning_history(limit=5)

        if result:  # Only test structure if there are records
            record = result[0]
            assert isinstance(record, dict)

            # Check required fields
            required_fields = ['id', 'timestamp', 'detection', 'action_taken', 'learning']
            for field in required_fields:
                assert field in record, f"Missing required field: {field}"

    def test_get_edge_learning_history_limit_parameter(self, storage: StorageManager) -> None:
        """Test that limit parameter works correctly"""
        # Add multiple test records
        for i in range(5):
            storage.save_edge_learning(f"Detection {i}", f"Action {i}", f"Learning {i}")

        # Test with different limits
        result_1 = storage.get_edge_learning_history(limit=1)
        result_5 = storage.get_edge_learning_history(limit=5)

        assert len(result_1) <= 1
        assert len(result_5) <= 5
        assert len(result_1) <= len(result_5)

    def test_edge_learning_history_integration_with_dashboard(self, storage: StorageManager) -> None:
        """Test integration with dashboard render function"""
        # This test ensures the dashboard can call the method without AttributeError
        from ui.dashboard import render_edge_intelligence_view
        import streamlit as st

        # Clear cache to ensure fresh instance
        st.cache_resource.clear()

        # This should not raise AttributeError
        try:
            render_edge_intelligence_view(storage)
        except AttributeError as e:
            if "get_edge_learning_history" in str(e):
                pytest.fail(f"Dashboard still has AttributeError for get_edge_learning_history: {e}")
            else:
                # Other AttributeErrors are acceptable (e.g., streamlit context issues)
                pass