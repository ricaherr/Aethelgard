"""
migrate_broker_accounts.py — Idempotent migration script for usr_broker_accounts.

Purpose:
  - Identifies records in sys_broker_accounts that belong to users (not system accounts)
  - Moves them to usr_broker_accounts under the appropriate user_id
  - Leaves DEMO system accounts (enabled=1, supports_data=1) in sys_broker_accounts

Idempotency: Safe to run multiple times. Uses INSERT OR IGNORE to avoid duplicates.

Trace_ID: ARCH-USR-BROKER-ACCOUNTS-2026-N5
"""
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data_vault.storage import StorageManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def migrate(storage: StorageManager) -> None:
    conn = storage._get_conn()
    try:
        cursor = conn.cursor()

        # 1. Ensure usr_broker_accounts exists (schema.py already creates it on startup)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usr_broker_accounts'"
        )
        if not cursor.fetchone():
            logger.error("usr_broker_accounts table does not exist. Run storage init first.")
            return

        # 2. Fetch sys_broker_accounts records
        cursor.execute("SELECT * FROM sys_broker_accounts")
        sys_accounts = cursor.fetchall()

        if not sys_accounts:
            logger.info("[MIGRATE] No records in sys_broker_accounts. Nothing to migrate.")
            return

        logger.info("[MIGRATE] Found %d records in sys_broker_accounts.", len(sys_accounts))

        migrated = 0
        skipped_system = 0

        # Get default admin user_id to assign orphaned accounts
        cursor.execute("SELECT id FROM sys_users WHERE role='admin' ORDER BY created_at LIMIT 1")
        admin_row = cursor.fetchone()
        admin_user_id = admin_row[0] if admin_row else "system"

        for row in sys_accounts:
            account = dict(row)
            account_id = account.get("account_id", "")
            platform_id = account.get("platform_id", "")
            account_type = account.get("account_type", "demo")

            # Heuristic: system accounts have supports_data=1 (used for data feeds)
            # User accounts have supports_exec=1 (used for trading)
            is_system_account = bool(account.get("supports_data", 0)) and not bool(
                account.get("supports_exec", 0)
            )

            if is_system_account:
                logger.info("[MIGRATE] Skipping system data account: %s", account_id)
                skipped_system += 1
                continue

            # Attempt to migrate to usr_broker_accounts
            cursor.execute(
                """
                INSERT OR IGNORE INTO usr_broker_accounts
                    (user_id, broker_name, broker_account_id, account_type,
                     account_status, balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (
                    admin_user_id,
                    platform_id,
                    account.get("account_number") or account_id,
                    "REAL" if account_type.upper() == "REAL" else "DEMO",
                    account.get("balance"),
                    account.get("created_at"),
                    account.get("updated_at"),
                ),
            )
            if cursor.rowcount > 0:
                migrated += 1
                logger.info("[MIGRATE] Migrated account %s → usr_broker_accounts", account_id)
            else:
                logger.debug("[MIGRATE] Account %s already exists in usr_broker_accounts (skipped)", account_id)

        conn.commit()
        logger.info(
            "[MIGRATE] Done. migrated=%d, skipped_system=%d, total=%d",
            migrated, skipped_system, len(sys_accounts),
        )

    except Exception as exc:
        conn.rollback()
        logger.error("[MIGRATE] Migration failed: %s", exc, exc_info=True)
    finally:
        storage._close_conn(conn)


if __name__ == "__main__":
    logger.info("[MIGRATE] Starting broker accounts migration...")
    storage = StorageManager()
    migrate(storage)
    logger.info("[MIGRATE] Migration complete.")
