"""
Migration: Drop old broker table and recreate with new schema
WARNING: This will delete existing broker data
"""
import logging
import sys
from pathlib import Path
import sqlite3

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_broker_schema():
    """Drop old brokers table and create new schema"""
    
    db_path = Path("data_vault/aethelgard.db")
    
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Backup old data if exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='brokers'")
        if cursor.fetchone():
            logger.info("📋 Old 'brokers' table found. Backing up...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brokers_old AS 
                SELECT * FROM brokers
            """)
            logger.info("✅ Backup created: brokers_old")
            
            # Drop old table
            cursor.execute("DROP TABLE IF EXISTS brokers")
            logger.info("🗑️  Dropped old 'brokers' table")
        
        # Create new tables with correct schema
        logger.info("🔨 Creating new schema...")
        
        # Brokers table (providers)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS brokers (
                broker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                website TEXT,
                platforms_available TEXT,
                data_server TEXT,
                auto_provision_available BOOLEAN DEFAULT 0,
                registration_url TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        logger.info("✅ Table 'brokers' created")
        
        # Platforms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS platforms (
                platform_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                vendor TEXT,
                type TEXT,
                capabilities TEXT,
                connector_class TEXT,
                created_at TEXT
            )
        ''')
        logger.info("✅ Table 'platforms' created")
        
        # Broker accounts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broker_accounts (
                account_id TEXT PRIMARY KEY,
                broker_id TEXT,
                platform_id TEXT,
                account_name TEXT,
                account_number TEXT,
                server TEXT,
                account_type TEXT,
                credentials_path TEXT,
                enabled BOOLEAN DEFAULT 1,
                last_connection TEXT,
                balance REAL,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (broker_id) REFERENCES brokers(broker_id),
                FOREIGN KEY (platform_id) REFERENCES platforms(platform_id)
            )
        ''')
        logger.info("✅ Table 'broker_accounts' created")
        
        conn.commit()
        logger.info("\n✅ Migration successful!")
        logger.info("Run: python scripts/seed_brokers_platforms.py to populate data")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("="*50)
    logger.info("BROKER SCHEMA MIGRATION")
    logger.info("="*50)
    logger.info("\nThis will:")
    logger.info("  1. Backup old 'brokers' table")
    logger.info("  2. Drop old table")
    logger.info("  3. Create new schema (brokers, platforms, broker_accounts)")
    logger.info("\n⚠️  WARNING: Old broker config will be lost")
    
    response = input("\nContinue? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        success = migrate_broker_schema()
        if success:
            print("\n✅ Migration complete!")
            print("Next: python scripts/seed_brokers_platforms.py")
        else:
            print("\n❌ Migration failed")
    else:
        print("\n❌ Migration cancelled")
