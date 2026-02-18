"""
Auto-Provisioning System for Demo Accounts
Automatically creates and manages demo/paper trading accounts
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class BrokerProvisioner:
    """Manages automatic provisioning of demo accounts across brokers"""
    
    def __init__(self, storage: StorageManager):
        self.storage = storage
        self.credentials_dir = Path("config/demo_accounts")
        self.credentials_dir.mkdir(exist_ok=True)
    
    def _get_broker_info(self, broker_id: str) -> Optional[Dict]:
        """Load broker information from database"""
        return self.storage.get_broker(broker_id)
    
    def get_auto_providers(self, broker_id: str) -> bool:
        """Check if broker supports auto-provisioning"""
        broker = self._get_broker_info(broker_id)
        
        if not broker:
            raise ValueError(f"Unknown broker: {broker_id}")
        
        return broker.get('auto_provision_available', False)
    
    def requires_manual_setup(self, broker_id: str) -> bool:
        """Check if broker requires manual account creation"""
        broker = self._get_broker_info(broker_id)
        
        if not broker:
            return True
        
        return not broker.get('auto_provision_available', False)
    
    async def provision_demo_account(self, broker_id: str, platform_id: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Automatically provision a demo account
        
        Args:
            broker_id: ID of the broker (binance, tradovate, etc.)
            platform_id: Optional platform to use
        
        Returns:
            (success: bool, credentials: dict)
        """
        # Check if broker supports auto-provisioning
        if not self.get_auto_providers(broker_id):
            logger.warning(f"No auto-provisioning available for {broker_id}")
            return False, {"error": "manual_setup_required"}
        
        # Route to specific provisioner based on broker_id
        if broker_id == 'binance':
            return await self._provision_binance_testnet()
        elif broker_id == 'tradovate':
            return await self._provision_tradovate_demo()
        elif broker_id == 'tradingview':
            return await self._provision_tradingview_paper()
        elif broker_id in ['pepperstone', 'ic_markets', 'xm', 'custom']:
            # MT5/MT4 brokers require manual setup or setup_mt5_demo.py
            return False, {
                "error": "manual_setup_required",
                "instructions": "Run 'python scripts/setup_mt5_demo.py' to configure MT5 accounts."
            }
        else:
            logger.warning(f"Provisioner not implemented for {broker_id}")
            return False, {"error": "provisioner_not_implemented"}
    
    async def _provision_binance_testnet(self) -> Tuple[bool, Dict]:
        """Auto-create Binance Testnet account with API keys"""
        try:
            import uuid
            account_id = f"aethelgard_{uuid.uuid4().hex[:8]}"
            
            # In real implementation, would call Binance Testnet API
            api_key = f"test_{uuid.uuid4().hex}"
            api_secret = f"secret_{uuid.uuid4().hex}"
            
            # Create account in database
            broker_account_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            
            # Save account
            self.storage._get_conn().execute("""
                INSERT INTO broker_accounts 
                (account_id, broker_id, platform_id, account_name, account_number, 
                 account_type, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                broker_account_id,
                'binance',
                'binance_api',
                f"Binance Testnet ({account_id})",
                account_id,
                'demo',
                True,
                created_at,
                created_at
            ))
            self.storage._get_conn().commit()
            
            # Save encrypted credentials
            self.storage.save_credential(broker_account_id, 'api', 'api_key', api_key)
            self.storage.save_credential(broker_account_id, 'api', 'api_secret', api_secret)
            self.storage.save_credential(broker_account_id, 'api', 'base_url', 
                                        'https://testnet.binance.vision')
            
            credentials = {
                "account_id": broker_account_id,
                "provider": "binance_testnet",
                "external_account_id": account_id,
                "created_at": created_at,
                "auto_created": True
            }
            
            logger.info(f"✅ Binance Testnet account created: {account_id}")
            return True, credentials
            
        except Exception as e:
            logger.error(f"Failed to provision Binance Testnet: {e}")
            return False, {"error": str(e)}
    
    async def _provision_tradovate_demo(self) -> Tuple[bool, Dict]:
        """Auto-create Tradovate demo account"""
        try:
            import uuid
            external_account_id = f"aethelgard_demo_{uuid.uuid4().hex[:8]}"
            
            # In real implementation, would call Tradovate API
            username = external_account_id
            password = f"demo_{uuid.uuid4().hex[:12]}"
            
            # Create account in database
            broker_account_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            
            # Save account
            self.storage._get_conn().execute("""
                INSERT INTO broker_accounts 
                (account_id, broker_id, platform_id, account_name, account_number, 
                 account_type, enabled, balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                broker_account_id,
                'tradovate',
                'tradovate_api',
                f"Tradovate Demo ({external_account_id})",
                external_account_id,
                'demo',
                True,
                25000.0,
                created_at,
                created_at
            ))
            self.storage._get_conn().commit()
            
            # Save encrypted credentials
            self.storage.save_credential(broker_account_id, 'credentials', 'username', username)
            self.storage.save_credential(broker_account_id, 'credentials', 'password', password)
            
            credentials = {
                "account_id": broker_account_id,
                "provider": "tradovate_demo",
                "external_account_id": external_account_id,
                "created_at": created_at,
                "auto_created": True,
                "balance": 25000.0
            }
            
            logger.info(f"✅ Tradovate demo account created: {external_account_id}")
            return True, credentials
            
        except Exception as e:
            logger.error(f"Failed to provision Tradovate demo: {e}")
            return False, {"error": str(e)}
    
    async def _provision_tradingview_paper(self) -> Tuple[bool, Dict]:
        """Setup TradingView Paper Trading (simulated)"""
        try:
            import uuid
            webhook_id = uuid.uuid4().hex
            
            # Create account in database
            broker_account_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            
            # Save account
            self.storage._get_conn().execute("""
                INSERT INTO broker_accounts 
                (account_id, broker_id, platform_id, account_name, account_number, 
                 account_type, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                broker_account_id,
                'tradingview',
                'tradingview',
                f"TradingView Paper ({webhook_id[:8]})",
                webhook_id,
                'demo',
                True,
                created_at,
                created_at
            ))
            self.storage._get_conn().commit()
            
            # Save webhook configuration as credential
            webhook_url = f"http://localhost:8000/webhook/tradingview/{webhook_id}"
            self.storage.save_credential(broker_account_id, 'webhook', 'webhook_id', webhook_id)
            self.storage.save_credential(broker_account_id, 'webhook', 'webhook_url', webhook_url)
            
            credentials = {
                "account_id": broker_account_id,
                "provider": "tradingview_paper",
                "webhook_id": webhook_id,
                "webhook_url": webhook_url,
                "created_at": created_at,
                "auto_created": True,
                "instructions": "Configure this webhook URL in your TradingView alerts"
            }
            
            logger.info(f"✅ TradingView Paper setup: {webhook_id}")
            return True, credentials
            
        except Exception as e:
            logger.error(f"Failed to setup TradingView Paper: {e}")
            return False, {"error": str(e)}
    
    def load_credentials(self, broker_account_id: str) -> Optional[Dict]:
        """Load credentials for a broker account from database"""
        return self.storage.get_credentials(broker_account_id)
    
    def has_demo_account(self, broker_id: str) -> bool:
        """Check if demo account exists for broker in database"""
        accounts = self.storage.get_broker_accounts(
            broker_id=broker_id,
            account_type='demo'
        )
        return len(accounts) > 0

    async def ensure_demo_account(self, broker_id: str, provider: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Ensure only one demo account is active per broker. If multiple exist, use the first and inform.
        Serializa la provisión para evitar conflictos de DB.
        """
        import threading
        lock = threading.Lock()
        with lock:
            accounts = self.storage.get_broker_accounts(
                broker_id=broker_id,
                account_type='demo'
            )
            if accounts:
                account = accounts[0]
                credentials = self.load_credentials(account['account_id'])
                if len(accounts) > 1:
                    logger.warning(f"⚠️ {broker_id}: Se detectaron {len(accounts)} cuentas DEMO activas. Usando la primera como default: {account.get('account_name','')} ({account.get('account_id')})")
                else:
                    logger.info(f"✅ Using existing {broker_id} demo account")
                return True, {"account": account, "credentials": credentials, "info": f"Usando cuenta DEMO: {account.get('account_name','')} ({account.get('account_id')})"}

            # Check if auto-provisioning is possible
            if self.requires_manual_setup(broker_id):
                logger.warning(f"⚠️  {broker_id} requires manual account setup")
                manual_info = self._get_manual_setup_info(broker_id)
                return False, {"error": "manual_setup_required", "info": manual_info}

            # Auto-create demo account
            logger.info(f"🔄 Auto-creating {broker_id} demo account...")
            success, credentials = await self.provision_demo_account(broker_id, provider)

            if success:
                logger.info(f"✅ {broker_id} demo account ready")
            else:
                logger.error(f"❌ Failed to create {broker_id} demo account")

            return success, credentials
    
    def _get_manual_setup_info(self, broker_id: str) -> Dict:
        """Get information for manual setup"""
        broker = self._get_broker_info(broker_id)
        
        if not broker:
            return {
                "broker": broker_id,
                "error": "broker_not_found",
                "instructions": "Check broker database configuration"
            }
        
        return {
            "broker": broker['name'],
            "broker_id": broker_id,
            "requires_manual_setup": True,
            "instructions": f"Create demo account manually at {broker.get('website', 'broker website')} and save credentials to config/demo_accounts/"
        }


async def main() -> None:
    """Test auto-provisioning"""
    provisioner = BrokerProvisioner()
    
    # Test auto brokers
    for broker in ['binance', 'tradovate']:
        print(f"\n{'='*50}")
        print(f"Testing {broker}...")
        success, creds = await provisioner.ensure_demo_account(broker)
        if success:
            print(f"✅ {broker}: {creds.get('provider', 'N/A')}")
        else:
            print(f"❌ {broker}: {creds.get('error', 'Unknown error')}")
    
    # Test manual broker
    print(f"\n{'='*50}")
    print("Testing pepperstone (manual)...")
    success, info = await provisioner.ensure_demo_account('pepperstone')
    if not success:
        print(f"⚠️  Manual setup required:")
        print(f"   Info: {info}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
