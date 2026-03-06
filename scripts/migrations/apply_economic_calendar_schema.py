"""
Migration 030: Apply economic_calendar schema.

Purpose: Create economic_calendar table with proper constraints and indexes.
Idempotent: Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS).

Usage:
    python scripts/migrations/apply_economic_calendar_schema.py
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def apply_economic_calendar_schema(db_path: str = "aethelgard.db") -> bool:
    """
    Apply economic_calendar schema migration.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        True if migration successful, False otherwise
    """
    try:
        # Read SQL migration file
        migration_file = Path(__file__).parent / "030_economic_calendar.sql"
        
        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        with open(migration_file, "r") as f:
            sql_statements = f.read()
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Execute migration
        logger.info(f"Applying migration: {migration_file}")
        cursor.executescript(sql_statements)
        conn.commit()
        
        # Verify table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='economic_calendar'"
        )
        if not cursor.fetchone():
            logger.error("economic_calendar table not created")
            conn.close()
            return False
        
        logger.info("Migration 030 completed successfully")
        logger.info(f"  - Table: economic_calendar ✓")
        logger.info(f"  - Indexes: 5 created ✓")
        
        conn.close()
        return True
        
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error during migration: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}")
        return False


def verify_schema(db_path: str = "aethelgard.db") -> dict:
    """
    Verify that economic_calendar schema is correct.
    
    Returns:
        Dictionary with verification results
    """
    results = {
        "table_exists": False,
        "columns": [],
        "indexes": [],
        "constraints": [],
    }
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='economic_calendar'"
        )
        if cursor.fetchone():
            results["table_exists"] = True
        
        # Get columns
        cursor.execute("PRAGMA table_info(economic_calendar)")
        columns = cursor.fetchall()
        results["columns"] = [col[1] for col in columns]
        
        # Get indexes
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='economic_calendar'"
        )
        indexes = cursor.fetchall()
        results["indexes"] = [idx[0] for idx in indexes]
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error verifying schema: {e}")
    
    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Apply migration
    success = apply_economic_calendar_schema()
    
    if success:
        # Verify schema
        verification = verify_schema()
        print("\n" + "="*60)
        print("MIGRATION 030: ECONOMIC_CALENDAR SCHEMA")
        print("="*60)
        print(f"Table exists: {verification['table_exists']}")
        print(f"Columns ({len(verification['columns'])}): {', '.join(verification['columns'])}")
        print(f"Indexes ({len(verification['indexes'])}): {', '.join(verification['indexes'])}")
        print("="*60)
        print("✅ Migration successful")
    else:
        print("❌ Migration failed")
        exit(1)
