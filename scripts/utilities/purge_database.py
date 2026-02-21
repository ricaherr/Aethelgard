"""
PURGE DATABASE SCRIPT
=====================
Emergency script to clean all testing/false data from the database.
Deletes all records from: signals, trades, edge_learning, session_stats.

WARNING: This will remove ALL historical data. Use only in emergency situations.

Usage:
    python scripts/purge_database.py
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_database_paths() -> list[str]:
    """
    Get SQLite database files in data_vault (excluding test databases).
    
    Returns:
        List of database file paths
    """
    data_vault_dir = project_root / "data_vault"
    if not data_vault_dir.exists():
        print(f"❌ ERROR: data_vault directory not found at {data_vault_dir}")
        return []
    
    # Only use main database (aethelgard.db)
    main_db = data_vault_dir / "aethelgard.db"
    
    if main_db.exists():
        return [str(main_db)]
    
    # Fallback: find first non-test database
    db_files = list(data_vault_dir.glob("*.db"))
    
    # Filter out test databases
    production_dbs = [
        db for db in db_files 
        if not any(test_word in db.name.lower() for test_word in ['test', 'temp', 'backup'])
    ]
    
    if production_dbs:
        return [str(production_dbs[0])]
    
    print("⚠️  No production database found")
    return []


def count_records(conn: sqlite3.Connection, table: str) -> int:
    """Count records in a table."""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        # Table doesn't exist
        return 0


def purge_table(conn: sqlite3.Connection, table: str) -> tuple[int, bool]:
    """
    Delete all records from a table.
    
    Returns:
        Tuple of (records_deleted, success)
    """
    try:
        count_before = count_records(conn, table)
        if count_before == 0:
            return 0, True
        
        conn.execute(f"DELETE FROM {table}")
        conn.commit()
        
        count_after = count_records(conn, table)
        records_deleted = count_before - count_after
        
        # Verify deletion
        if count_after == 0:
            return records_deleted, True
        else:
            return records_deleted, False
            
    except sqlite3.OperationalError as e:
        print(f"   ⚠️  Table '{table}' not found or error: {e}")
        return 0, False


def purge_database(db_path: str) -> dict:
    """
    Purge all critical tables from a database.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        Dictionary with purge results
    """
    tables_to_purge = [
        "signals",
        "trades", 
        "edge_learning",
        "trade_results",
        "coherence_events"
    ]
    
    # Special handling for session_stats (it's in system_state table)
    keys_to_reset = [
        "session_stats",
        "pending_signals",
        "rejected_signals",
        "failed_signals"
    ]
    
    results = {
        "database": db_path,
        "timestamp": datetime.now().isoformat(),
        "tables": {}
    }
    
    print(f"\n🔥 Purging database: {os.path.basename(db_path)}")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        
        for table in tables_to_purge:
            count_before = count_records(conn, table)
            print(f"📋 {table}: {count_before} records", end=" -> ")
            
            deleted, success = purge_table(conn, table)
            
            results["tables"][table] = {
                "before": count_before,
                "deleted": deleted,
                "success": success
            }
            
            if success:
                print(f"✅ PURGED ({deleted} deleted)")
            else:
                print(f"❌ FAILED")
        
        # Reset system_state keys
        print(f"\n📋 Resetting system_state keys...")
        for key in keys_to_reset:
            try:
                conn.execute("DELETE FROM system_state WHERE key = ?", (key,))
                print(f"   ✅ {key} reset")
            except Exception as e:
                print(f"   ⚠️  {key}: {e}")
        
        conn.commit()
        
        # Vacuum to reclaim space
        print("\n🗜️  Running VACUUM to reclaim disk space...")
        conn.execute("VACUUM")
        conn.commit()
        print("✅ VACUUM completed")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        results["error"] = str(e)
    
    return results


def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("🚨 AETHELGARD DATABASE PURGE - EMERGENCY CLEANUP")
    print("="*60)
    print("\nThis will DELETE ALL records from:")
    print("  - signals")
    print("  - trades")
    print("  - edge_learning")
    print("  - trade_results")
    print("  - coherence_events")
    print("\nAnd RESET system_state keys:")
    print("  - session_stats")
    print("  - pending_signals")
    print("  - rejected_signals")
    print("  - failed_signals")
    print("\n⚠️  WARNING: This action CANNOT be undone!\n")
    
    # Confirmation
    response = input("Type 'PURGE' to confirm deletion: ").strip()
    
    if response != "PURGE":
        print("\n❌ Purge cancelled. No changes made.")
        return
    
    print("\n🔄 Starting purge operation...\n")
    
    # Get all database files
    db_paths = get_database_paths()
    
    if not db_paths:
        print("❌ No database files found.")
        return
    
    all_results = []
    total_deleted = 0
    
    for db_path in db_paths:
        result = purge_database(db_path)
        all_results.append(result)
        
        # Count total deletions
        for table_result in result.get("tables", {}).values():
            total_deleted += table_result.get("deleted", 0)
    
    # Final summary
    print("\n" + "="*60)
    print("📊 PURGE SUMMARY")
    print("="*60)
    print(f"Databases processed: {len(db_paths)}")
    print(f"Total records deleted: {total_deleted}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Detailed results per database
    for result in all_results:
        if result.get("tables"):
            print(f"\n📁 {os.path.basename(result['database'])}:")
            for table, data in result["tables"].items():
                if data["deleted"] > 0:
                    print(f"   - {table}: {data['deleted']} records deleted")
    
    print("\n✅ Purge operation completed.")
    print("💡 Next step: Run check_integrity.py to verify system state.\n")


if __name__ == "__main__":
    main()
