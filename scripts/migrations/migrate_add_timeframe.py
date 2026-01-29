"""
Migration: Add timeframe column to signals table
================================================

Adds timeframe column to support multi-timeframe signal deduplication.
This allows the system to track signals from the same instrument on different
timeframes independently (e.g., M5 scalping vs H4 swing trading).

Run this ONCE before starting the system with the new deduplication logic.
"""
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_add_timeframe_to_signals(db_path: str = "data_vault/aethelgard.db"):
    """
    Add timeframe column to signals table.
    
    Args:
        db_path: Path to SQLite database
    """
    db_file = Path(db_path)
    
    if not db_file.exists():
        logger.warning(f"Database not found: {db_path}. Will be created on first run.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(signals)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "timeframe" in columns:
            logger.info("✅ Column 'timeframe' already exists in signals table. No migration needed.")
            conn.close()
            return
        
        # Add timeframe column with default value
        logger.info("Adding 'timeframe' column to signals table...")
        cursor.execute("""
            ALTER TABLE signals ADD COLUMN timeframe TEXT DEFAULT 'M5'
        """)
        
        # Update existing rows to have M5 as default timeframe
        cursor.execute("""
            UPDATE signals SET timeframe = 'M5' WHERE timeframe IS NULL
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Migration completed successfully!")
        logger.info("   - Column 'timeframe' added to signals table")
        logger.info("   - Existing signals set to default timeframe 'M5'")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRATION: Add timeframe to signals table")
    print("=" * 60)
    
    migrate_add_timeframe_to_signals()
    
    print("\n✅ Migration complete. System ready for multi-timeframe trading.")
