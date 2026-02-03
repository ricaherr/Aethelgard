"""
Migration: Add price column to signals table
Date: 2026-02-02
Reason: Signals need price field for entry price storage
"""

import sqlite3
import os
from pathlib import Path

def migrate_add_price_column():
    """Add price column to signals table if it doesn't exist"""
    db_path = Path("data_vault/aethelgard.db")

    if not db_path.exists():
        print("Database not found, skipping migration")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if price column exists
        cursor.execute("PRAGMA table_info(signals)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'price' not in column_names:
            print("Adding price column to signals table...")
            cursor.execute("ALTER TABLE signals ADD COLUMN price REAL")
            conn.commit()
            print("✅ Price column added successfully")
        else:
            print("Price column already exists, skipping")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_add_price_column()