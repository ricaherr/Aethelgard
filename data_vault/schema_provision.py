"""
schema_provision.py — Tenant DB provisioning and template bootstrap.

Responsibility:
- provision_tenant_db(): Full DDL + migrations + seeds for a new tenant DB.
- bootstrap_tenant_template(): Create a reusable template from global DB.

Rules:
- NO direct DDL — delegates to initialize_schema(), run_migrations().
- Uses DatabaseManager for connection pooling.
"""
import logging
import os
import shutil
import sqlite3
from pathlib import Path

from .schema_ddl import initialize_schema
from .schema_migrations import run_migrations
from .schema_seeds import seed_default_usr_preferences, bootstrap_symbol_mappings

logger = logging.getLogger(__name__)

def provision_tenant_db(db_path: str) -> None:
    """
    Full DDL + migrations + default seeds for a brand-new tenant DB.
    Called exclusively by TenantDBFactory on first access (auto-provisioning).

    Idempotent: safe to call even if the DB already exists.
    Uses DatabaseManager for connection pooling (SSOT).
    """
    from .database_manager import get_database_manager

    import os
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # Use DatabaseManager singleton to get pooled connection (NOT direct sqlite3.connect)
    db_manager = get_database_manager()
    conn = db_manager.get_connection(db_path)

    try:
        initialize_schema(conn)
        run_migrations(conn)
        seed_default_usr_preferences(conn)
        bootstrap_symbol_mappings(conn)
        conn.commit()  # Explicit commit for provisioning
        logger.info("[TENANT] DB provisioned: %s", db_path)
    except Exception as exc:
        conn.rollback()
        logger.error("[TENANT] Provisioning failed for %s: %s", db_path, exc)
        raise
    # NOTE: DO NOT close conn - DatabaseManager owns lifecycle


# ── Internal helpers ──────────────────────────────────────────────────────────



def bootstrap_tenant_template(global_conn: sqlite3.Connection, mode: str = "manual") -> bool:
    """
    Create template DB for new tenants by copying usr_* tables from global DB.
    
    Args:
        global_conn: Connection to data_vault/global/aethelgard.db
        mode: "manual" (default) or "automatic"
            - "manual": Only run if explicitly called, flag stored in sys_config
            - "automatic": Run on every startup (for convenience, not recommended)
    
    Returns:
        True if bootstrap succeeded, False if already done
    
    Idempotent: Safe to call multiple times, will skip if template already exists.
    """
    from pathlib import Path
    import shutil
    
    template_dir = Path("data_vault/templates")
    template_path = template_dir / "usr_template.db"
    
    # Check if bootstrap is enabled in config
    mode_config_key = "tenant_template_bootstrap_mode"
    cursor = global_conn.cursor()
    cursor.execute("SELECT value FROM sys_config WHERE key = ?", (mode_config_key,))
    result = cursor.fetchone()
    
    # First time: store config
    if result is None:
        cursor.execute(
            "INSERT INTO sys_config (key, value) VALUES (?, ?)",
            (mode_config_key, mode)
        )
        global_conn.commit()
        logger.info(f"[TEMPLATE] Bootstrap mode configured: {mode}")
    else:
        mode = result[0]  # Read from config
    
    # Check if already completed (manual mode only)
    if mode == "manual":
        bootstrap_done_key = "tenant_template_bootstrap_done"
        cursor.execute("SELECT value FROM sys_config WHERE key = ?", (bootstrap_done_key,))
        if cursor.fetchone():
            logger.debug("[TEMPLATE] Bootstrap already completed (manual mode)")
            return False
    
    # Skip if template already physically exists
    if template_path.exists():
        # Mark as done if manual mode
        if mode == "manual":
            cursor.execute(
                "INSERT OR IGNORE INTO sys_config (key, value) VALUES (?, ?)",
                ("tenant_template_bootstrap_done", "1")
            )
            global_conn.commit()
        logger.info(f"[TEMPLATE] Template already exists: {template_path}")
        return False
    
    # Create template: copy usr_* tables from global to template
    try:
        logger.info("[TEMPLATE] Creating tenant template DB...")
        template_dir.mkdir(parents=True, exist_ok=True)
        
        # Create new template DB
        template_conn = sqlite3.connect(str(template_path))
        template_cursor = template_conn.cursor()
        
        # Get list of usr_* tables from global DB
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE 'usr_%'
            ORDER BY name
        """)
        usr_tables = [row[0] for row in cursor.fetchall()]
        
        if not usr_tables:
            logger.warning("[TEMPLATE] No usr_* tables found in global DB")
            template_conn.close()
            return False
        
        logger.info(f"[TEMPLATE] Copying {len(usr_tables)} usr_* tables to template...")
        
        # Copy each usr_* table schema + data from global to template
        for table_name in usr_tables:
            # GET table creation SQL
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            create_sql = cursor.fetchone()[0]
            
            # Create table in template
            template_cursor.execute(create_sql)
            
            # Copy data from global to template
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            if rows:
                placeholders = ", ".join(["?" for _ in columns])
                template_cursor.execute(
                    f"INSERT INTO {table_name} VALUES ({placeholders})",
                    rows[0]
                )
                for row in rows[1:]:
                    template_cursor.execute(
                        f"INSERT INTO {table_name} VALUES ({placeholders})",
                        row
                    )
            
            logger.debug(f"[TEMPLATE] Copied {table_name}: {len(rows)} rows")
        
        template_conn.commit()
        template_conn.close()
        
        # Mark as done in global config
        if mode == "manual":
            cursor.execute(
                "INSERT OR IGNORE INTO sys_config (key, value) VALUES (?, ?)",
                ("tenant_template_bootstrap_done", "1")
            )
        
        global_conn.commit()
        logger.info(f"[TEMPLATE] Bootstrap successful: {template_path} ({len(usr_tables)} tables)")
        return True
        
    except Exception as e:
        logger.error(f"[TEMPLATE] Bootstrap failed: {e}", exc_info=True)
        return False
