"""
Test: Module Toggle System (Feature Flags) - Global + Individual
==================================================================

Tests the module enable/disable system with two-level control:
- GLOBAL: Affects all users/accounts (priority 1)
- INDIVIDUAL: Per-account overrides (priority 2)

Resolution Logic:
- If GLOBAL=false -> module disabled for ALL (no matter individual)
- If GLOBAL=true + INDIVIDUAL=false -> disabled only for that account
- If both true -> module active

TDD Approach: Tests define behavior before implementation.
"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime
from data_vault.storage import StorageManager


class TestModuleTogglesGlobal:
    """Test GLOBAL module toggles (affects all accounts)"""
    
    def test_get_global_modules_default_all_enabled(self):
        """By default, all modules should be enabled globally"""
        storage = StorageManager(":memory:")
        
        # Act
        modules_enabled = storage.get_global_modules_enabled()
        
        # Assert
        assert modules_enabled["scanner"] is True
        assert modules_enabled["executor"] is True
        assert modules_enabled["position_manager"] is True
        assert modules_enabled["risk_manager"] is True
        assert modules_enabled["monitor"] is True
        assert modules_enabled["notificator"] is True
    
    def test_set_global_module_disabled(self):
        """Should be able to disable a module globally"""
        storage = StorageManager(":memory:")
        
        # Act
        storage.set_global_module_enabled("scanner", False)
        modules = storage.get_global_modules_enabled()
        
        # Assert
        assert modules["scanner"] is False
        assert modules["executor"] is True  # Others unaffected
    
    def test_set_multiple_global_modules_disabled(self):
        """Should be able to disable multiple modules at once"""
        storage = StorageManager(":memory:")
        
        # Act
        storage.set_global_modules_enabled({
            "scanner": False,
            "executor": False,
            "position_manager": True
        })
        modules = storage.get_global_modules_enabled()
        
        # Assert
        assert modules["scanner"] is False
        assert modules["executor"] is False
        assert modules["position_manager"] is True


class TestModuleTogglesIndividual:
    """Test INDIVIDUAL module toggles (per-account overrides)"""
    
    def test_get_individual_modules_default_empty(self):
        """By default, no individual overrides (inherits global)"""
        storage = StorageManager(":memory:")
        
        # Create test account (using kwargs format)
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        
        # Act
        modules = storage.get_individual_modules_enabled(account_id)
        
        # Assert - Should return empty dict (no overrides)
        assert modules == {}
    
    def test_set_individual_module_disabled(self):
        """Should be able to disable module for specific account"""
        storage = StorageManager(":memory:")
        
        # Create test account (using kwargs format)
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        
        # Act
        storage.set_individual_module_enabled(account_id, "executor", False)
        modules = storage.get_individual_modules_enabled(account_id)
        
        # Assert
        assert modules["executor"] is False


class TestModuleTogglesPriority:
    """Test priority logic: Global > Individual"""
    
    def test_global_disabled_overrides_individual_enabled(self):
        """When global=false, individual=true has no effect"""
        storage = StorageManager(":memory:")
        
        # Create account with individual executor=true
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        storage.set_individual_module_enabled(account_id, "scanner", True)
        
        # Disable scanner globally
        storage.set_global_module_enabled("scanner", False)
        
        # Act - Resolve final state
        final_state = storage.resolve_module_enabled(account_id, "scanner")
        
        # Assert - Global wins
        assert final_state is False
    
    def test_global_enabled_individual_disabled(self):
        """When global=true, individual=false disables for that account only"""
        storage = StorageManager(":memory:")
        
        # Global scanner enabled (default)
        assert storage.get_global_modules_enabled()["scanner"] is True
        
        # Create account with individual scanner=false
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        storage.set_individual_module_enabled(account_id, "scanner", False)
        
        # Act
        final_state = storage.resolve_module_enabled(account_id, "scanner")
        
        # Assert - Individual wins (when global allows)
        assert final_state is False
    
    def test_both_enabled_returns_true(self):
        """When both global and individual are true, module is active"""
        storage = StorageManager(":memory:")
        
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        
        # Both enabled (global default + no individual override)
        final_state = storage.resolve_module_enabled(account_id, "executor")
        
        # Assert
        assert final_state is True
    
    def test_no_individual_override_uses_global(self):
        """When no individual override exists, use global setting"""
        storage = StorageManager(":memory:")
        
        account_id = storage.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        
        # Set global disabled
        storage.set_global_module_enabled("position_manager", False)
        
        # Act (no individual override set)
        final_state = storage.resolve_module_enabled(account_id, "position_manager")
        
        # Assert - Uses global
        assert final_state is False


class TestModuleTogglesOrchestrator:
    """Test integration with MainOrchestrator"""
    
    @pytest.mark.asyncio
    async def test_scanner_disabled_skips_scan(self):
        """When scanner globally disabled, scan should be skipped"""
        # Arrange
        storage = StorageManager(":memory:")
        storage.set_global_module_enabled("scanner", False)
        
        mock_scanner = Mock()
        mock_scanner.get_scan_results_with_data = Mock(return_value={})
        
        # Import here to avoid circular dependencies
        from core_brain.main_orchestrator import MainOrchestrator
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=Mock(),
            risk_manager=Mock(),
            executor=Mock(),
            storage=storage
        )
        
        # Act
        await orchestrator.run_single_cycle()
        
        # Assert
        mock_scanner.get_scan_results_with_data.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_executor_disabled_skips_execution(self):
        """When executor globally disabled, signals are not executed"""
        # Arrange
        storage = StorageManager(":memory:")
        storage.set_global_module_enabled("executor", False)
        
        # Create executor mock with explicit execute_signal method
        mock_executor = Mock()
        mock_executor.execute_signal = AsyncMock()
        mock_executor.persists_signals = False
        
        mock_scanner = Mock()
        mock_scanner.get_scan_results_with_data = Mock(return_value={
            "EURUSD": {"regime": "TREND", "data": Mock()}
        })
        
        mock_signal_factory = AsyncMock()
        mock_signal_factory.generate_signals_batch = AsyncMock(return_value=[
            Mock(id="test_signal", symbol="EURUSD")
        ])
        
        mock_risk = Mock()
        mock_risk.validate_signal = Mock(return_value=True)
        
        from core_brain.main_orchestrator import MainOrchestrator
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk,
            executor=mock_executor,
            storage=storage
        )
        
        # Act
        await orchestrator.run_single_cycle()
        
        # Assert
        mock_executor.execute_signal.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_position_manager_disabled_skips_monitoring(self):
        """When position_manager disabled, no position monitoring occurs"""
        # Arrange
        storage = StorageManager(":memory:")
        storage.set_global_module_enabled("position_manager", False)
        
        mock_position_manager = Mock()
        mock_position_manager.monitor_positions = Mock(return_value={
            'monitored': 0,
            'actions': []
        })
        
        from core_brain.main_orchestrator import MainOrchestrator
        
        orchestrator = MainOrchestrator(
            scanner=Mock(),
            signal_factory=Mock(),
            risk_manager=Mock(),
            executor=Mock(),
            storage=storage
        )
        orchestrator.position_manager = mock_position_manager
        
        # Disable scanner to avoid other logic
        storage.set_global_module_enabled("scanner", False)
        
        # Act
        await orchestrator.run_single_cycle()
        
        # Assert
        mock_position_manager.monitor_positions.assert_not_called()


class TestModuleTogglesPersistence:
    """Test that toggles persist across storage instances"""
    
    def test_global_toggles_persist(self, tmp_path):
        """Global module settings should persist in database"""
        db_path = str(tmp_path / "test.db")
        
        # Set toggles in first instance
        storage1 = StorageManager(db_path)
        storage1.set_global_module_enabled("scanner", False)
        storage1.set_global_module_enabled("executor", False)
        del storage1
        
        # Load in second instance
        storage2 = StorageManager(db_path)
        modules = storage2.get_global_modules_enabled()
        
        # Assert - Settings persisted
        assert modules["scanner"] is False
        assert modules["executor"] is False
    
    def test_individual_toggles_persist(self, tmp_path):
        """Individual module settings should persist in database"""
        db_path = str(tmp_path / "test.db")
        
        # Set toggles in first instance
        storage1 = StorageManager(db_path)
        account_id = storage1.save_broker_account(
            broker_id="test_broker",
            platform_id="MT5",
            account_name="DEMO_123"
        )
        storage1.set_individual_module_enabled(account_id, "executor", False)
        del storage1
        
        # Load in second instance
        storage2 = StorageManager(db_path)
        modules = storage2.get_individual_modules_enabled(account_id)
        
        # Assert - Settings persisted
        assert modules["executor"] is False
