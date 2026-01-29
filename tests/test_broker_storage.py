"""
Tests for Broker Configuration Storage
"""
import pytest
import json
from pathlib import Path
from data_vault.storage import StorageManager


class TestBrokerStorage:
    """Test broker configuration persistence"""
    
    @pytest.fixture
    def storage(self):
        """In-memory storage for testing"""
        return StorageManager(db_path=":memory:")
    
    def test_table_brokers_exists(self, storage):
        """Verify brokers table is created"""
        conn = storage._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='brokers'
        """)
        result = cursor.fetchone()
        assert result is not None, "Table 'brokers' should exist"
    
    def test_save_broker_config(self, storage):
        """Save broker configuration"""
        broker_config = {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "website": "https://binance.com",
            "platforms_available": ["binance_api", "tradingview"],
            "data_server": "https://testnet.binance.vision",
            "auto_provision_available": True,
            "registration_url": "https://binance.com/register"
        }
        
        # Save broker
        storage.save_broker(broker_config)
        
        # Verify saved
        brokers = storage.get_brokers()
        assert len(brokers) == 1
        assert brokers[0]['broker_id'] == 'binance'
        assert brokers[0]['name'] == 'Binance'
        assert brokers[0]['auto_provisioning'] == 'full'
    
    def test_get_broker_by_id(self, storage):
        """Retrieve specific broker"""
        broker_config = {
            "broker_id": "mt5",
            "name": "MetaTrader 5",
            "type": "forex_cfd",
            "website": "https://metaquotes.net",
            "platforms_available": ["mt5"],
            "auto_provision_available": False,
            "registration_url": "https://metaquotes.net/demo"
        }
        
        storage.save_broker(broker_config)
        
        # Get specific broker
        broker = storage.get_broker('mt5')
        assert broker is not None
        assert broker['broker_id'] == 'mt5'
        assert broker['name'] == 'MetaTrader 5'
        
        # Non-existent broker
        assert storage.get_broker('nonexistent') is None
    
    def test_save_and_get_broker_account(self, storage):
        """Save and retrieve broker accounts (enabled status applies to accounts, not brokers)"""
        # First save a broker
        broker_config = {
            "broker_id": "ibkr",
            "name": "Interactive Brokers",
            "type": "multi_asset",
            "website": "https://interactivebrokers.com",
            "platforms_available": ["ibkr_api"],
            "auto_provision_available": False,
            "registration_url": "https://interactivebrokers.com/demo"
        }
        
        storage.save_broker(broker_config)
        
        # Create an account for this broker
        account_id = storage.save_broker_account(
            broker_id='ibkr',
            platform_id='ibkr_api',
            account_name='IBKR Demo',
            account_type='demo',
            server='demo.ibkr.com',
            login='DU12345',
            password='test_password',
            enabled=True
        )
        
        # Get account and verify
        account = storage.get_account(account_id)
        assert account is not None
        assert account['broker_id'] == 'ibkr'
        assert account['enabled'] == 1
        
        # Update account status (disable)
        storage.update_account_status(account_id, enabled=False)
        account = storage.get_account(account_id)
        assert account['enabled'] == 0
        
        # Enable again
        storage.update_account_status(account_id, enabled=True)
        account = storage.get_account(account_id)
        assert account['enabled'] == 1
    
    def test_get_enabled_accounts(self, storage):
        """Get only enabled broker accounts"""
        # Create brokers
        brokers = [
            {"broker_id": "binance", "name": "Binance", "type": "crypto", "auto_provision_available": True},
            {"broker_id": "ibkr", "name": "Interactive Brokers", "type": "multi_asset", "auto_provision_available": False},
            {"broker_id": "mt5", "name": "MetaTrader 5", "type": "forex_cfd", "auto_provision_available": False}
        ]
        
        for broker in brokers:
            storage.save_broker(broker)
        
        # Create accounts (some enabled, some disabled)
        storage.save_broker_account('binance', 'binance_api', 'Binance Demo', enabled=True)
        storage.save_broker_account('ibkr', 'ibkr_api', 'IBKR Demo', enabled=False)
        storage.save_broker_account('mt5', 'mt5', 'MT5 Demo', enabled=True)
        
        # Get only enabled accounts
        enabled_accounts = storage.get_broker_accounts(enabled_only=True)
        assert len(enabled_accounts) == 2
        assert all(acc['enabled'] == 1 for acc in enabled_accounts)
        assert {acc['broker_id'] for acc in enabled_accounts} == {'binance', 'mt5'}
    
    def test_account_credentials_storage(self, storage):
        """Verify account credentials are stored securely"""
        broker_config = {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "auto_provision_available": True
        }
        
        storage.save_broker(broker_config)
        
        # Create account with password
        account_id = storage.save_broker_account(
            broker_id='binance',
            platform_id='binance_api',
            account_name='Binance Demo',
            login='test_user',
            password='secret_password'
        )
        
        # Verify account exists
        account = storage.get_account(account_id)
        assert account is not None
        assert account['account_number'] == 'test_user'
        
        # Verify credentials are stored (encrypted)
        creds = storage.get_credentials(account_id, 'password')
        assert creds is not None
        assert len(creds) > 0
    
    def test_filter_auto_provision_brokers(self, storage):
        """Get brokers that support auto-provisioning"""
        brokers = [
            {
                "broker_id": "binance",
                "name": "Binance",
                "type": "crypto",
                "auto_provision_available": True
            },
            {
                "broker_id": "mt5",
                "name": "MetaTrader 5",
                "type": "forex_cfd",
                "auto_provision_available": True
            },
            {
                "broker_id": "ibkr",
                "name": "Interactive Brokers",
                "type": "multi_asset",
                "auto_provision_available": False
            }
        ]
        
        for broker in brokers:
            storage.save_broker(broker)
        
        # Get all brokers and filter by auto_provision_available
        all_brokers = storage.get_brokers()
        auto_brokers = [b for b in all_brokers if b.get('auto_provision_available')]
        assert len(auto_brokers) == 2
        assert {b['broker_id'] for b in auto_brokers} == {'binance', 'mt5'}
    
    def test_platforms_json_serialization(self, storage):
        """Verify platforms_available list is properly serialized/deserialized"""
        platforms = ["binance_api", "binance_futures", "tradingview"]
        
        broker_config = {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "platforms_available": platforms,
            "auto_provision_available": True
        }
        
        storage.save_broker(broker_config)
        
        # Retrieve and verify platforms are deserialized
        broker = storage.get_broker('binance')
        assert broker is not None
        
        # platforms_available is stored as JSON string, parse it
        stored_platforms = json.loads(broker['platforms_available'])
        assert stored_platforms == platforms
        assert 'binance_api' in stored_platforms
