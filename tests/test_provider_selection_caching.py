"""
Test provider selection caching mechanism.
Ensures that provider selection happens ONCE at startup, not repeatedly.
"""
import pytest
from unittest.mock import patch, MagicMock
from core_brain.data_provider_manager import DataProviderManager


class TestProviderSelectionCaching:
    """Tests for provider selection caching"""
    
    def test_provider_selected_once_on_initialization(self):
        """
        CRITICAL: Provider should be selected ONCE during __init__
        NOT on every get_best_provider() call
        
        This prevents:
        - Repeated log messages (16+ logs in one second)
        - Unnecessary iteration through providers
        - Non-deterministic behavior
        """
        with patch('core_brain.data_provider_manager.StorageManager') as mock_storage:
            # Mock DB response
            mock_storage.return_value.get_data_providers.return_value = [
                {
                    'name': 'mt5',
                    'enabled': True,
                    'priority': 100,
                    'requires_auth': True,
                    'is_system': True,
                    'config': {'login': '123', 'server': 'test'}
                },
                {
                    'name': 'yahoo',
                    'enabled': True,
                    'priority': 50,
                    'requires_auth': False,
                    'is_system': True,
                    'config': {}
                }
            ]
            
            mock_storage.return_value.get_broker_accounts.return_value = []
            
            manager = DataProviderManager()
            
            # Capture initial selection
            first_call = manager.get_best_provider()
            assert first_call is not None
            assert manager._selected_provider_name == 'mt5'
            
            # Multiple get_best_provider calls should return CACHED instance
            # WITHOUT re-running selection logic
            for _ in range(10):
                result = manager.get_best_provider()
                assert result is first_call  # Should be same object reference
                assert manager._selected_provider_name == 'mt5'
            
            # Should still be the same cached instance
            assert manager._selected_provider is first_call
    
    def test_provider_cache_initialized_flag(self):
        """Test that selection is marked as initialized"""
        with patch('core_brain.data_provider_manager.StorageManager') as mock_storage:
            mock_storage.return_value.get_data_providers.return_value = [
                {
                    'name': 'yahoo',
                    'enabled': True,
                    'priority': 50,
                    'requires_auth': False,
                    'is_system': True,
                    'config': {}
                }
            ]
            mock_storage.return_value.get_broker_accounts.return_value = []
            
            manager = DataProviderManager()
            
            # Before first call, not initialized
            assert not manager._provider_selection_initialized
            
            # After first call, initialized
            manager.get_best_provider()
            assert manager._provider_selection_initialized
    
    def test_force_reselect_provider_on_failure(self):
        """Test that force_reselect_provider resets cache"""
        with patch('core_brain.data_provider_manager.StorageManager') as mock_storage:
            mock_storage.return_value.get_data_providers.return_value = [
                {
                    'name': 'mt5',
                    'enabled': True,
                    'priority': 100,
                    'requires_auth': True,
                    'is_system': True,
                    'config': {'login': '123', 'server': 'test'}
                },
                {
                    'name': 'yahoo',
                    'enabled': True,
                    'priority': 50,
                    'requires_auth': False,
                    'is_system': True,
                    'config': {}
                }
            ]
            mock_storage.return_value.get_broker_accounts.return_value = []
            
            manager = DataProviderManager()
            
            # Get initial provider
            first_provider = manager.get_best_provider()
            assert manager._selected_provider_name == 'mt5'
            assert manager._provider_selection_initialized
            
            # Call force_reselect_provider and store the result
            new_provider = manager.force_reselect_provider()
            
            # After force_reselect, the cache should be re-initialized
            # (because force_reselect calls get_best_provider internally)
            assert manager._provider_selection_initialized
            assert new_provider is not None
    
    def test_multiple_sequential_calls_use_cache(self, caplog):
        """Test that multiple calls use cache without repeated selection logic"""
        import logging
        caplog.set_level(logging.INFO)
        
        with patch('core_brain.data_provider_manager.StorageManager') as mock_storage:
            with patch('core_brain.data_provider_manager.logger') as mock_logger:
                mock_storage.return_value.get_data_providers.return_value = [
                    {
                        'name': 'yahoo',
                        'enabled': True,
                        'priority': 50,
                        'requires_auth': False,
                        'is_system': True,
                        'config': {}
                    }
                ]
                mock_storage.return_value.get_broker_accounts.return_value = []
                
                manager = DataProviderManager()
                
                # Call get_best_provider multiple times
                for _ in range(5):
                    manager.get_best_provider()
                
                # Should log STARTUP message only ONCE
                startup_logs = [
                    call for call in mock_logger.info.call_args_list
                    if '[STARTUP]' in str(call)
                ]
                assert len(startup_logs) == 1, f"Expected 1 STARTUP log, got {len(startup_logs)}"
                assert 'Selected primary provider' in str(startup_logs[0])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
