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
            "auto_provisioning": "full",
            "providers": {
                "testnet": {
                    "auto_create": True,
                    "requires_credentials": False,
                    "api_available": True,
                    "method": "api",
                    "base_url": "https://testnet.binance.vision"
                }
            },
            "enabled": True
        }
        
        # Save broker
        storage.save_broker_config(broker_config)
        
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
            "auto_provisioning": "partial",
            "providers": {"metaquotes_demo": {"auto_create": True}},
            "enabled": True
        }
        
        storage.save_broker_config(broker_config)
        
        # Get specific broker
        broker = storage.get_broker('mt5')
        assert broker is not None
        assert broker['broker_id'] == 'mt5'
        assert broker['name'] == 'MetaTrader 5'
        
        # Non-existent broker
        assert storage.get_broker('nonexistent') is None
    
    def test_update_broker_status(self, storage):
        """Enable/disable broker"""
        broker_config = {
            "broker_id": "ibkr",
            "name": "Interactive Brokers",
            "type": "multi_asset",
            "auto_provisioning": "none",
            "providers": {},
            "enabled": True
        }
        
        storage.save_broker_config(broker_config)
        
        # Disable broker
        storage.update_broker_status('ibkr', enabled=False)
        
        broker = storage.get_broker('ibkr')
        assert broker['enabled'] == 0  # SQLite stores as integer
        
        # Enable again
        storage.update_broker_status('ibkr', enabled=True)
        broker = storage.get_broker('ibkr')
        assert broker['enabled'] == 1
    
    def test_get_enabled_brokers(self, storage):
        """Get only enabled brokers"""
        brokers = [
            {
                "broker_id": "binance",
                "name": "Binance",
                "type": "crypto",
                "auto_provisioning": "full",
                "providers": {},
                "enabled": True
            },
            {
                "broker_id": "ibkr",
                "name": "Interactive Brokers",
                "type": "multi_asset",
                "auto_provisioning": "none",
                "providers": {},
                "enabled": False
            },
            {
                "broker_id": "mt5",
                "name": "MetaTrader 5",
                "type": "forex_cfd",
                "auto_provisioning": "partial",
                "providers": {},
                "enabled": True
            }
        ]
        
        for broker in brokers:
            storage.save_broker_config(broker)
        
        # Get only enabled
        enabled = storage.get_enabled_brokers()
        assert len(enabled) == 2
        assert all(b['enabled'] == 1 for b in enabled)
        assert {b['broker_id'] for b in enabled} == {'binance', 'mt5'}
    
    def test_update_broker_credentials_path(self, storage):
        """Update credentials path after auto-provisioning"""
        broker_config = {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "auto_provisioning": "full",
            "providers": {},
            "enabled": True
        }
        
        storage.save_broker_config(broker_config)
        
        # Update credentials path
        creds_path = "config/demo_accounts/binance_demo.json"
        storage.update_broker_credentials('binance', creds_path)
        
        broker = storage.get_broker('binance')
        assert broker['credentials_path'] == creds_path
    
    def test_get_auto_provision_brokers(self, storage):
        """Get brokers that support auto-provisioning"""
        brokers = [
            {
                "broker_id": "binance",
                "name": "Binance",
                "type": "crypto",
                "auto_provisioning": "full",
                "providers": {},
                "enabled": True
            },
            {
                "broker_id": "mt5",
                "name": "MetaTrader 5",
                "type": "forex_cfd",
                "auto_provisioning": "partial",
                "providers": {},
                "enabled": True
            },
            {
                "broker_id": "ibkr",
                "name": "Interactive Brokers",
                "type": "multi_asset",
                "auto_provisioning": "none",
                "providers": {},
                "enabled": True
            }
        ]
        
        for broker in brokers:
            storage.save_broker_config(broker)
        
        # Get full + partial auto-provision
        auto_brokers = storage.get_auto_provision_brokers()
        assert len(auto_brokers) == 2
        assert {b['broker_id'] for b in auto_brokers} == {'binance', 'mt5'}
    
    def test_providers_json_serialization(self, storage):
        """Verify providers dict is properly serialized/deserialized"""
        complex_providers = {
            "testnet": {
                "auto_create": True,
                "requires_credentials": False,
                "api_available": True,
                "method": "api",
                "base_url": "https://testnet.binance.vision",
                "notes": "Public testnet with auto-generated API keys"
            },
            "mainnet": {
                "auto_create": False,
                "requires_credentials": True,
                "registration_url": "https://www.binance.com/register"
            }
        }
        
        broker_config = {
            "broker_id": "binance",
            "name": "Binance",
            "type": "crypto",
            "auto_provisioning": "full",
            "providers": complex_providers,
            "enabled": True
        }
        
        storage.save_broker_config(broker_config)
        
        # Retrieve and verify
        broker = storage.get_broker('binance')
        providers = json.loads(broker['providers_json'])
        
        assert providers == complex_providers
        assert providers['testnet']['auto_create'] is True
        assert providers['testnet']['base_url'] == "https://testnet.binance.vision"
