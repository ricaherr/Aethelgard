"""
Seed migration: Load demo broker accounts and credentials from data_vault/seed/
Idempotent - safe to run multiple times
"""
import logging
import sys
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager
from utils.encryption import get_encryptor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _generate_trace_id(prefix: str = "SEED") -> str:
    """Generate unique trace ID for traceability"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}".upper()


def seed_demo_broker_accounts():
    """Load demo broker accounts from seed"""
    
    trace_id = _generate_trace_id("SEED_BROKER_ACCOUNTS")
    
    seed_file = Path("data_vault/seed/demo_broker_accounts.json")
    
    if not seed_file.exists():
        logger.warning(f"[{trace_id}] [SKIP] Seed file not found: {seed_file}")
        return
    
    logger.info(f"[{trace_id}] {'='*70}")
    logger.info(f"[{trace_id}] SEEDING DEMO BROKER ACCOUNTS")
    logger.info(f"[{trace_id}] {'='*70}")
    
    try:
        with open(seed_file, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)
        
        storage = StorageManager()
        accounts = seed_data.get("accounts", [])
        
        logger.info(f"[{trace_id}] Found {len(accounts)} accounts in seed")
        
        for account_data in accounts:
            account_id = account_data.get("account_id")
            broker_id = account_data.get("broker_id")
            
            # Check if already exists
            existing = storage.get_account(account_id)
            
            if existing:
                logger.info(f"[{trace_id}] [EXISTS] {broker_id}: {account_id}")
                
                # Update account_number and enabled status if changed in seed
                new_account_number = account_data.get("account_number")
                new_enabled = account_data.get("enabled", False)
                
                if (new_account_number and existing.get('account_number') != new_account_number) or \
                   (existing.get('enabled') != new_enabled):
                    logger.info(f"[{trace_id}] [UPDATE] Updating account_number or enabled status for {account_id}")
                    # Use save_broker_account with INSERT OR REPLACE to update existing account
                    storage.save_broker_account(
                        account_id=account_id,
                        broker_id=broker_id,
                        platform_id=account_data.get("platform_id"),
                        account_name=account_data.get("account_name"),
                        account_number=new_account_number,
                        server=account_data.get("server"),
                        account_type=account_data.get("account_type", "demo"),
                        enabled=new_enabled
                    )
                    logger.info(f"[{trace_id}]   Updated to login: {new_account_number}, enabled: {new_enabled}")
                
                # Check if credentials need to be added
                if account_data.get("credential_password"):
                    creds = storage.get_credentials(account_id)
                    if not creds or 'password' not in creds:
                        logger.info(f"[{trace_id}] [UPDATE] Adding missing password for {account_id}")
                        storage.update_credential(
                            account_id,
                            {'password': account_data['credential_password']}
                        )
                continue
            
            # Create new account
            logger.info(f"[{trace_id}] [CREATE] {broker_id}: {account_id}")
            
            storage.save_broker_account(
                account_id=account_id,
                broker_id=broker_id,
                platform_id=account_data.get("platform_id"),
                account_name=account_data.get("account_name"),
                account_number=account_data.get("account_number"),
                server=account_data.get("server"),
                account_type=account_data.get("account_type", "demo"),
                enabled=account_data.get("enabled", False)
            )
            
            logger.info(f"[{trace_id}]   Number: {account_data.get('account_number')}")
            logger.info(f"[{trace_id}]   Server: {account_data.get('server')}")
            logger.info(f"[{trace_id}]   Enabled: {account_data.get('enabled')}")
            
            # Add credentials if present
            if account_data.get("credential_password"):
                storage.update_credential(
                    account_id,
                    {'password': account_data['credential_password']}
                )
                logger.info(f"[{trace_id}]   Password: *** (encrypted)")
        
        logger.info(f"[{trace_id}] {'='*70}")
        logger.info(f"[{trace_id}] ✅ Demo broker accounts seeded successfully")
        
    except Exception as e:
        logger.error(f"[{trace_id}] [ERROR] Failed to seed accounts: {e}")
        import traceback
        logger.error(f"[{trace_id}] Traceback: {traceback.format_exc()}")


def seed_data_providers():
    """Load data providers from seed"""
    
    trace_id = _generate_trace_id("SEED_DATA_PROVIDERS")
    
    seed_file = Path("data_vault/seed/data_providers.json")
    
    if not seed_file.exists():
        logger.warning(f"[{trace_id}] [SKIP] Seed file not found: {seed_file}")
        return
    
    logger.info(f"[{trace_id}] {'='*70}")
    logger.info(f"[{trace_id}] SEEDING DATA PROVIDERS")
    logger.info(f"[{trace_id}] {'='*70}")
    
    try:
        with open(seed_file, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)
        
        storage = StorageManager()
        providers = seed_data.get("providers", [])
        
        logger.info(f"[{trace_id}] Found {len(providers)} providers in seed")
        
        for provider_data in providers:
            name = provider_data.get("name")
            
            # Check if already exists - use StorageManager API
            try:
                cursor = storage._get_conn().cursor()
                cursor.execute("SELECT name FROM data_providers WHERE name = ?", (name,))
                existing = cursor.fetchone()
                storage._close_conn(cursor.connection)
                
                if existing:
                    logger.info(f"[{trace_id}] [EXISTS] {name}")
                    continue
            except Exception as e:
                logger.warning(f"[{trace_id}] Could not check existence of {name}: {str(e)[:50]}")
            
            # Create new provider
            logger.info(f"[{trace_id}] [CREATE] {name}")
            
            try:
                storage.save_data_provider(
                    name=name,
                    enabled=provider_data.get("enabled", False),
                    priority=provider_data.get("priority", 50),
                    requires_auth=provider_data.get("requires_auth", False),
                    supports_data=provider_data.get("supports_data", False),
                    supports_exec=provider_data.get("supports_exec", False),
                    additional_config=provider_data.get("additional_config", {})
                )
                
                logger.info(f"[{trace_id}]   Type: {provider_data.get('type')}")
                logger.info(f"[{trace_id}]   Enabled: {provider_data.get('enabled')}")
                logger.info(f"[{trace_id}]   Requires Auth: {provider_data.get('requires_auth')}")
            except Exception as e:
                logger.warning(f"[{trace_id}] Could not save {name}: {str(e)[:50]}")
        
        logger.info(f"[{trace_id}] {'='*70}")
        logger.info(f"[{trace_id}] ✅ Data providers seeded successfully")
        
    except Exception as e:
        logger.error(f"[{trace_id}] [ERROR] Failed to seed providers: {e}")
        import traceback
        logger.error(f"[{trace_id}] Traceback: {traceback.format_exc()}")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to seed providers: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    logger.info("\n" + "="*70)
    logger.info("SEED MIGRATION: Demo Accounts & Providers")
    logger.info("="*70)
    
    seed_demo_broker_accounts()
    seed_data_providers()
    
    logger.info("\n" + "="*70)
    logger.info("SEED MIGRATION COMPLETE")
    logger.info("="*70)
    logger.info("\nNote: Seeds are idempotent - safe to run on every startup or manually")
    logger.info("To integrate with schema.py, call seed_demo_data() from _bootstrap_from_json()")
