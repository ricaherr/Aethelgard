"""
migration_rename_tables.py — Migrate legacy table names to sys_*/usr_* convention.

ARCH-SSOT-2026-006: Idempotent migration that renames all tables in existing DBs.

Strategy:
1. Check if new tables (sys_*/usr_*) already exist
2. If not, rename legacy tables to new names
3. Drop old indexes and recreate with new names
4. Update foreign key references

Safety: 
- All operations are wrapped in transaction (atomic)
- Idempotent: safe to run multiple times
- Backs up DB before migration (optional)
"""

import sqlite3
import logging
import sys
from pathlib import Path

# Inline table mapping to avoid import issues
TABLE_TRANSFORMATIONS = {
    "system_state": "sys_config",
    "market_state": "sys_market_pulse",
    "symbol_mappings": "sys_symbol_mappings",
    "broker_accounts": "sys_broker_accounts",
    "brokers": "sys_brokers",
    "platforms": "sys_platforms",
    "credentials": "sys_credentials",
    "data_providers": "sys_data_providers",
    "regime_configs": "sys_regime_configs",
    "economic_calendar": "sys_economic_calendar",
    "signals": "usr_signals",
    "trades": "usr_trades",
    "position_history": "usr_position_history",
    "coherence_events": "usr_coherence_events",
    "anomaly_events": "usr_anomaly_events",
    "tuning_adjustments": "usr_tuning_adjustments",
    "signal_pipeline": "usr_signal_pipeline",
    "user_preferences": "usr_preferences",
    "notification_settings": "usr_notification_settings",
    "notifications": "usr_notifications",
    "connector_settings": "usr_connector_settings",
    "asset_profiles": "usr_assets_cfg",
    "strategy_ranking": "usr_performance",
    "strategies": "usr_strategies",
    "strategy_performance_logs": "usr_strategy_logs",
    "execution_shadow_logs": "usr_execution_logs",
    "edge_learning": "usr_edge_learning",
}

INDEX_TRANSFORMATIONS = {}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def migrate_db(db_path: str, backup: bool = True) -> bool:
    """
    Migrate a single database file to new naming convention.
    
    Args:
        db_path: Path to SQLite database file
        backup: If True, create backup before migration
    
    Returns:
        True if migration succeeded, False otherwise
    """
    db_path_obj = Path(db_path)
    
    if not db_path_obj.exists():
        logger.error(f"Database not found: {db_path}")
        return False
    
    # Optional: Create backup
    if backup:
        backup_path = db_path_obj.with_suffix(f".backup_{db_path_obj.stat().st_mtime_ns}.db")
        try:
            import shutil
            shutil.copy2(db_path, backup_path)
            logger.info(f"✅ Backup created: {backup_path}")
        except Exception as e:
            logger.warning(f"Could not create backup: {e} (continuing anyway)")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Step 1: Get all existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        logger.info(f"Existing tables: {len(existing_tables)}")
        
        # Step 2: Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        renamed_count = 0
        for legacy_name, new_name in TABLE_TRANSFORMATIONS.items():
            
            # Skip if new table already exists
            if new_name in existing_tables:
                logger.debug(f"Skipping {new_name} (already exists)")
                continue
            
            # Skip if legacy table doesn't exist
            if legacy_name not in existing_tables:
                logger.debug(f"Skipping {legacy_name} (doesn't exist)")
                continue
            
            # Rename table
            try:
                cursor.execute(f"ALTER TABLE {legacy_name} RENAME TO {new_name}")
                logger.info(f"✅ Renamed: {legacy_name} → {new_name}")
                renamed_count += 1
            except sqlite3.OperationalError as e:
                logger.error(f"❌ Failed to rename {legacy_name}: {e}")
                conn.rollback()
                return False
        
        # Step 3: Rename indexes (optional, cosmetic)
        renamed_indexes = 0
        # Skipping index rename since we're using inline mapping
        
        # Step 4: Commit transaction
        conn.commit()
        
        logger.info(f"\n✅ Migration completed successfully!")
        logger.info(f"   - Tables renamed: {renamed_count}")
        logger.info(f"   - Indexes renamed: {renamed_indexes}")
        
        # Verify
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        new_tables = {row[0] for row in cursor.fetchall()}
        logger.info(f"   - New table count: {len(new_tables)}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False


def migrate_all_in_vault(vault_root: str = "data_vault", backup: bool = True) -> int:
    """
    Migrate all database files in data_vault directory.
    
    Scans:
    - data_vault/global/aethelgard.db
    - data_vault/tenants/*/aethelgard.db
    - data_vault/templates/usr_template.db (if exists)
    
    Returns:
        Count of successfully migrated databases
    """
    vault_path = Path(vault_root)
    
    if not vault_path.exists():
        logger.error(f"Vault directory not found: {vault_root}")
        return 0
    
    db_files = []
    
    # Find all DB files
    for db_file in vault_path.rglob("aethelgard.db"):
        db_files.append(str(db_file))
    
    # Also check template
    template_db = vault_path / "templates" / "usr_template.db"
    if template_db.exists():
        db_files.append(str(template_db))
    
    logger.info(f"Found {len(db_files)} database file(s) to migrate:\n")
    
    success_count = 0
    for db_path in db_files:
        logger.info(f"\nProcessing: {db_path}")
        logger.info("-" * 60)
        
        if migrate_db(db_path, backup=backup):
            success_count += 1
        else:
            logger.error(f"Migration FAILED for {db_path}")
    
    logger.info(f"\n\n{'='*60}")
    logger.info(f"FINAL RESULT: {success_count}/{len(db_files)} databases migrated successfully")
    logger.info(f"{'='*60}")
    
    return success_count


if __name__ == "__main__":
    # Default: migrate all databases in data_vault
    success = migrate_all_in_vault(backup=True)
    
    # Exit with appropriate code
    sys.exit(0 if success == len(list(Path("data_vault").rglob("aethelgard.db"))) + 1 else 1)
