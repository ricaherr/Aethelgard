#!/usr/bin/env python3
"""
Force update demo broker account logins and credentials from seed.
Useful when seed data changes but bootstrap has already run.
"""
import sys
import logging
from pathlib import Path

# Add workspace root to path
workspace_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(workspace_root))

from data_vault.storage import StorageManager
from scripts.migrations.seed_demo_data import seed_demo_broker_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    """Force update demo accounts from seed"""
    logger.info("=" * 70)
    logger.info("FORCE UPDATE DEMO ACCOUNTS FROM SEED")
    logger.info("=" * 70)
    
    try:
        # Run seed_demo_broker_accounts with idempotent update logic
        # This will update account_number and credentials if they differ from seed
        seed_demo_broker_accounts()
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ Demo accounts updated successfully")
        logger.info("=" * 70)
        
        # Verify update
        storage = StorageManager()
        ic_markets = storage.get_account("ic_markets_demo_10001")
        if ic_markets:
            logger.info(f"\nIC Markets current state:")
            logger.info(f"  Account ID: {ic_markets.get('account_id')}")
            logger.info(f"  Login (account_number): {ic_markets.get('account_number')}")
            logger.info(f"  Enabled: {ic_markets.get('enabled')}")
            
        return 0
    except Exception as e:
        logger.error(f"[ERROR] Failed to update demo accounts: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
