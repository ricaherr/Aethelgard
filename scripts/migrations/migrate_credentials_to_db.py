"""
Migrate credentials from JSON files to encrypted database storage
One-time migration script
"""
import sys
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager
from utils.encryption import get_encryptor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_json_credentials():
    """Migrate existing JSON credential files to encrypted DB"""
    
    storage = StorageManager()
    credentials_dir = Path("config/demo_accounts")
    
    if not credentials_dir.exists():
        logger.info("No credentials directory found - nothing to migrate")
        return
    
    # Find all JSON credential files
    json_files = list(credentials_dir.glob("*_demo.json"))
    
    if not json_files:
        logger.info("No credential JSON files found - nothing to migrate")
        return
    
    logger.info(f"Found {len(json_files)} credential files to migrate")
    
    for json_file in json_files:
        try:
            logger.info(f"\n{'='*50}")
            logger.info(f"Migrating {json_file.name}...")
            
            # Read JSON credentials
            with open(json_file, 'r', encoding='utf-8') as f:
                creds = json.load(f)
            
            # Extract broker name from filename (binance_demo.json -> binance)
            broker_id = json_file.stem.replace('_demo', '')
            
            logger.info(f"  Broker ID: {broker_id}")
            logger.info(f"  Provider: {creds.get('provider', 'unknown')}")
            
            # Check if account already exists in DB
            existing_accounts = storage.get_broker_accounts(
                broker_id=broker_id,
                account_type='demo'
            )
            
            if existing_accounts:
                logger.warning(f"  ⚠️  Account already exists in DB - skipping")
                logger.info(f"     Account ID: {existing_accounts[0]['account_id']}")
                continue
            
            # Create account in database
            import uuid
            from datetime import datetime
            
            account_id = str(uuid.uuid4())
            created_at = creds.get('created_at', datetime.now().isoformat())
            
            # Determine platform_id based on provider
            platform_map = {
                'binance_testnet': 'binance_api',
                'tradovate_demo': 'tradovate_api',
                'tradingview_paper': 'tradingview'
            }
            platform_id = platform_map.get(creds.get('provider'), broker_id)
            
            logger.info(f"  Creating account: {account_id}")
            
            # Save account
            with storage._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO broker_accounts 
                    (account_id, broker_id, platform_id, account_name, account_number, 
                     account_type, enabled, balance, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    account_id,
                    broker_id,
                    platform_id,
                    f"{broker_id.title()} Demo (Migrated)",
                    creds.get('account_id', str(uuid.uuid4())),
                    'demo',
                    True,
                    creds.get('balance', 10000.0),
                    created_at,
                    datetime.now().isoformat()
                ))
                conn.commit()
            
            logger.info(f"  ✅ Account created")
            
            # Migrate credentials to encrypted storage
            credential_count = 0
            
            # Map JSON keys to credential storage
            credential_mappings = {
                'api_key': ('api', 'api_key'),
                'api_secret': ('api', 'api_secret'),
                'base_url': ('api', 'base_url'),
                'username': ('credentials', 'username'),
                'password': ('credentials', 'password'),
                'webhook_id': ('webhook', 'webhook_id'),
                'webhook_url': ('webhook', 'webhook_url'),
            }
            
            for json_key, (cred_type, cred_key) in credential_mappings.items():
                if json_key in creds:
                    storage.save_credential(
                        account_id=account_id,
                        credential_type=cred_type,
                        credential_key=cred_key,
                        value=str(creds[json_key])
                    )
                    credential_count += 1
                    logger.info(f"    ✅ Saved {cred_key}")
            
            logger.info(f"  ✅ Migrated {credential_count} credentials")
            logger.info(f"  📁 Original file: {json_file}")
            
            # Backup JSON file (don't delete yet)
            backup_path = json_file.with_suffix('.json.bak')
            json_file.rename(backup_path)
            logger.info(f"  💾 Backed up to: {backup_path}")
            
        except Exception as e:
            logger.error(f"  ❌ Failed to migrate {json_file.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    logger.info(f"\n{'='*50}")
    logger.info("Migration complete!")
    logger.info("\nVerify accounts in database:")
    
    # Show migrated accounts
    all_demo_accounts = storage.get_broker_accounts(account_type='demo')
    for acc in all_demo_accounts:
        logger.info(f"  - {acc['broker_id']}: {acc['account_name']} ({acc['account_id']})")
        creds = storage.get_credentials(acc['account_id'])
        logger.info(f"    Credentials: {list(creds.keys())}")


if __name__ == "__main__":
    # Initialize encryptor (will create key if needed)
    encryptor = get_encryptor()
    logger.info(f"🔑 Encryption ready")
    
    migrate_json_credentials()
