"""
Clean Duplicate Signals from Database
Removes exact duplicates based on (symbol, signal_type, timestamp).
Keeps the first occurrence, deletes subsequent duplicates.
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "data_vault/aethelgard.db"

def clean_duplicate_signals(dry_run=True):
    """
    Remove duplicate signals from database.
    
    Args:
        dry_run: If True, only show what would be deleted without actually deleting
    """
    
    if not Path(DB_PATH).exists():
        logger.error(f"Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Find duplicates
        cursor.execute('''
            SELECT symbol, signal_type, timestamp, COUNT(*) as count, GROUP_CONCAT(id) as ids
            FROM signals
            GROUP BY symbol, signal_type, timestamp
            HAVING count > 1
        ''')
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            logger.info("✅ No duplicate signals found!")
            return
        
        logger.info(f"🔍 Found {len(duplicates)} groups of duplicate signals")
        
        total_to_delete = 0
        for dup in duplicates:
            symbol, signal_type, timestamp, count, ids_str = dup
            ids = ids_str.split(',')
            
            # Keep first, delete rest
            to_keep = ids[0]
            to_delete = ids[1:]
            total_to_delete += len(to_delete)
            
            logger.info(
                f"  {symbol} {signal_type} @ {timestamp}: "
                f"{count} copies → keeping {to_keep[:8]}..., "
                f"deleting {len(to_delete)} duplicates"
            )
            
            if not dry_run:
                for delete_id in to_delete:
                    cursor.execute("DELETE FROM signals WHERE id = ?", (delete_id,))
                    logger.debug(f"    Deleted {delete_id}")
        
        if dry_run:
            logger.info(f"\n⚠️  DRY RUN: Would delete {total_to_delete} duplicate signals")
            logger.info("Run with dry_run=False to actually delete")
        else:
            conn.commit()
            logger.info(f"\n✅ Deleted {total_to_delete} duplicate signals")
            
            # Verify
            cursor.execute('''
                SELECT COUNT(*) FROM (
                    SELECT symbol, signal_type, timestamp, COUNT(*) as count
                    FROM signals
                    GROUP BY symbol, signal_type, timestamp
                    HAVING count > 1
                )
            ''')
            remaining = cursor.fetchone()[0]
            
            if remaining == 0:
                logger.info("✅ All duplicates cleaned successfully!")
            else:
                logger.warning(f"⚠️  {remaining} duplicate groups still remain")
        
    except Exception as e:
        logger.error(f"Error cleaning duplicates: {e}")
        conn.rollback()
    finally:
        conn.close()


def analyze_database():
    """Show database statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total signals
    cursor.execute("SELECT COUNT(*) FROM signals")
    total = cursor.fetchone()[0]
    
    # By platform
    cursor.execute("""
        SELECT platform, COUNT(*) as count 
        FROM signals 
        GROUP BY platform 
        ORDER BY count DESC
    """)
    platforms = cursor.fetchall()
    
    # By account type
    cursor.execute("""
        SELECT account_type, COUNT(*) as count 
        FROM signals 
        GROUP BY account_type 
        ORDER BY count DESC
    """)
    accounts = cursor.fetchall()
    
    # By market type
    cursor.execute("""
        SELECT market_type, COUNT(*) as count 
        FROM signals 
        GROUP BY market_type 
        ORDER BY count DESC
    """)
    markets = cursor.fetchall()
    
    logger.info(f"\n📊 Database Statistics:")
    logger.info(f"  Total signals: {total}")
    
    logger.info(f"\n  By Platform:")
    for platform, count in platforms:
        platform_name = platform if platform else "NULL/Unknown"
        logger.info(f"    - {platform_name}: {count}")
    
    logger.info(f"\n  By Account Type:")
    for acc_type, count in accounts:
        acc_name = acc_type if acc_type else "NULL/Unknown"
        logger.info(f"    - {acc_name}: {count}")
    
    logger.info(f"\n  By Market:")
    for market, count in markets:
        market_name = market if market else "NULL/Unknown"
        logger.info(f"    - {market_name}: {count}")
    
    conn.close()


if __name__ == "__main__":
    logger.info("🔍 Analyzing database...")
    analyze_database()
    
    logger.info("\n🧹 Checking for duplicates...")
    clean_duplicate_signals(dry_run=True)
    
    # Uncomment to actually delete duplicates:
    # logger.info("\n🗑️  Deleting duplicates...")
    # clean_duplicate_signals(dry_run=False)
