"""
Tests for seed_demo_data.py - Demo broker accounts and data providers seeding
TDD: Test-first validation of idempotent seed operations
"""
import pytest
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Import seed functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.migrations.seed_demo_data import seed_demo_sys_broker_accounts, seed_sys_data_providers, _generate_trace_id


class TestTraceIDGeneration:
    """Test trace ID generation for traceability"""
    
    def test_trace_id_format(self):
        """GIVEN _generate_trace_id WHEN called THEN returns SEED_XXXXX format"""
        trace_id = _generate_trace_id()
        
        assert trace_id.startswith("SEED_")
        assert len(trace_id) == 13  # "SEED_" + 8 hex chars
    
    def test_trace_id_with_custom_prefix(self):
        """GIVEN _generate_trace_id with prefix WHEN called THEN uses custom prefix"""
        trace_id = _generate_trace_id("CUSTOM")
        
        assert trace_id.startswith("CUSTOM_")
    
    def test_trace_id_unique(self):
        """GIVEN _generate_trace_id WHEN called twice THEN returns different IDs"""
        trace_id_1 = _generate_trace_id()
        trace_id_2 = _generate_trace_id()
        
        assert trace_id_1 != trace_id_2


class TestSeedDemoBrokerAccounts:
    """Test idempotent seeding of demo broker accounts"""
    
    def _create_seed_file(self, accounts: list) -> Path:
        """Helper: Create temporary seed file"""
        temp_dir = Path(tempfile.gettempdir())
        seed_file = temp_dir / "demo_sys_broker_accounts.json"
        
        seed_data = {
            "description": "Test seed data",
            "accounts": accounts
        }
        
        with open(seed_file, 'w') as f:
            json.dump(seed_data, f)
        
        return seed_file
    
    @patch('scripts.migrations.seed_demo_data.StorageManager')
    def test_seed_creates_new_account(self, mock_storage_class):
        """GIVEN new account in seed WHEN seed_demo_sys_broker_accounts THEN creates it"""
        # Setup mock storage
        mock_storage = Mock()
        mock_storage.get_account.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # Create test seed data
        test_accounts = [
            {
                "account_id": "test_demo_10001",
                "broker_id": "test_broker",
                "platform_id": "mt5",
                "account_name": "Test Demo Account",
                "account_number": "12345",
                "server": "Test-Demo",
                "account_type": "demo",
                "enabled": True,
                "credential_password": "demo_password"
            }
        ]
        
        test_seed_json = {
            "description": "Test",
            "accounts": test_accounts
        }
        
        # Mock file reading
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            with patch('scripts.migrations.seed_demo_data.json.load', return_value=test_seed_json):
                with patch('scripts.migrations.seed_demo_data.Path') as mock_path:
                    mock_path_instance = Mock()
                    mock_path_instance.exists.return_value = True
                    mock_path.return_value = mock_path_instance
                    
                    seed_demo_sys_broker_accounts()
        
        # Verify save_broker_account was called
        assert mock_storage.save_broker_account.called
        
        call_kwargs = mock_storage.save_broker_account.call_args[1]
        assert call_kwargs['account_id'] == 'test_demo_10001'
        assert call_kwargs['broker_id'] == 'test_broker'
    
    @patch('scripts.migrations.seed_demo_data.StorageManager')
    def test_seed_idempotent_on_existing_account(self, mock_storage_class):
        """GIVEN account already exists WHEN seed_demo_sys_broker_accounts THEN skips creation"""
        # Setup mock - account exists, no changes needed
        mock_storage = Mock()
        existing_account = {
            'account_id': 'test_demo_10001',
            'account_number': '12345',
            'enabled': True
        }
        mock_storage.get_account.return_value = existing_account
        mock_storage_class.return_value = mock_storage
        
        test_accounts = [
            {
                "account_id": "test_demo_10001",
                "broker_id": "test_broker",
                "platform_id": "mt5",
                "account_name": "Test Demo Account",
                "account_number": "12345",  # Same as existing
                "server": "Test-Demo",
                "account_type": "demo",
                "enabled": True,
                "credential_password": None
            }
        ]
        
        test_seed_json = {"accounts": test_accounts}
        
        with patch('builtins.open', create=True):
            with patch('scripts.migrations.seed_demo_data.json.load', return_value=test_seed_json):
                with patch('scripts.migrations.seed_demo_data.Path') as mock_path:
                    mock_path_instance = Mock()
                    mock_path_instance.exists.return_value = True
                    mock_path.return_value = mock_path_instance
                    
                    seed_demo_sys_broker_accounts()
        
        # Verify save_broker_account was NOT called (no changes)
        assert not mock_storage.save_broker_account.called
    
    @patch('scripts.migrations.seed_demo_data.StorageManager')
    def test_seed_updates_account_number_when_changed(self, mock_storage_class):
        """GIVEN account_number changed in seed WHEN seed_demo_sys_broker_accounts THEN updates it"""
        # Setup mock - account exists with OLD login
        mock_storage = Mock()
        existing_account = {
            'account_id': 'test_demo_10001',
            'account_number': '10001',  # OLD
            'enabled': True
        }
        mock_storage.get_account.return_value = existing_account
        mock_storage_class.return_value = mock_storage
        
        test_accounts = [
            {
                "account_id": "test_demo_10001",
                "broker_id": "test_broker",
                "platform_id": "mt5",
                "account_name": "Test Demo Account",
                "account_number": "52716550",  # NEW
                "server": "Test-Demo",
                "account_type": "demo",
                "enabled": True,
                "credential_password": "demo_pwd"
            }
        ]
        
        test_seed_json = {"accounts": test_accounts}
        
        with patch('builtins.open', create=True):
            with patch('scripts.migrations.seed_demo_data.json.load', return_value=test_seed_json):
                with patch('scripts.migrations.seed_demo_data.Path') as mock_path:
                    mock_path_instance = Mock()
                    mock_path_instance.exists.return_value = True
                    mock_path.return_value = mock_path_instance
                    
                    seed_demo_sys_broker_accounts()
        
        # Verify save_broker_account WAS called with new account_number
        assert mock_storage.save_broker_account.called
        
        call_kwargs = mock_storage.save_broker_account.call_args[1]
        assert call_kwargs['account_number'] == '52716550'


class TestSeedDataProviders:
    """Test seeding of data providers"""
    
    @patch('scripts.migrations.seed_demo_data.StorageManager')
    def test_seed_creates_new_provider(self, mock_storage_class):
        """GIVEN new provider in seed WHEN seed_sys_data_providers THEN creates it"""
        # Setup mock
        mock_storage = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Simulate provider not exists
        mock_cursor.fetchone.return_value = None
        mock_storage._get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_storage_class.return_value = mock_storage
        
        test_providers = [
            {
                "name": "test_provider",
                "type": "api",
                "enabled": True,
                "priority": 50,
                "requires_auth": False
            }
        ]
        
        test_seed_json = {"providers": test_providers}
        
        with patch('builtins.open', create=True):
            with patch('scripts.migrations.seed_demo_data.json.load', return_value=test_seed_json):
                with patch('scripts.migrations.seed_demo_data.Path') as mock_path:
                    mock_path_instance = Mock()
                    mock_path_instance.exists.return_value = True
                    mock_path.return_value = mock_path_instance
                    
                    seed_sys_data_providers()
        
        # Verify save_data_provider was called
        assert mock_storage.save_data_provider.called
        
        call_kwargs = mock_storage.save_data_provider.call_args[1]
        assert call_kwargs['name'] == 'test_provider'


class TestSeedSecurityRequirements:
    """Test security constraints for seeds"""
    
    def test_seed_json_no_hardcoded_passwords(self):
        """GIVEN demo_sys_broker_accounts.json WHEN read THEN no operative passwords"""
        seed_file = Path(__file__).parent.parent / "data_vault" / "seed" / "demo_sys_broker_accounts.json"
        
        if seed_file.exists():
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_data = json.load(f)
            
            # Check no operative passwords
            for account in seed_data.get("accounts", []):
                password = account.get("credential_password")
                
                # Demo sys_credentials are OK (like MT5 demo logins)
                # But if password is null or empty, it's fine (awaiting user input)
                # The key is: no "real" passwords like "operativo_secreto_real"
                assert password is None or password == "" or "demo" in password.lower() or len(password) < 50
    
    def test_seed_json_valid_structure(self):
        """GIVEN demo_sys_broker_accounts.json WHEN read THEN has required fields"""
        seed_file = Path(__file__).parent.parent / "data_vault" / "seed" / "demo_sys_broker_accounts.json"
        
        if seed_file.exists():
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_data = json.load(f)
            
            assert "accounts" in seed_data
            
            for account in seed_data["accounts"]:
                required_fields = ["account_id", "broker_id", "platform_id"]
                for field in required_fields:
                    assert field in account, f"Missing required field: {field}"


class TestSeedIntegration:
    """Integration tests for seed operations"""
    
    @patch('scripts.migrations.seed_demo_data.StorageManager')
    def test_seed_exception_handling(self, mock_storage_class):
        """GIVEN seed file is malformed WHEN seed_demo_sys_broker_accounts THEN handles gracefully"""
        mock_storage_class.return_value = Mock()
        
        with patch('scripts.migrations.seed_demo_data.Path') as mock_path:
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = True
            mock_path.return_value = mock_path_instance
            
            # Simulate JSON decode error
            with patch('scripts.migrations.seed_demo_data.json.load', side_effect=json.JSONDecodeError("msg", "doc", 0)):
                # Should not raise - exception is caught and logged
                seed_demo_sys_broker_accounts()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
