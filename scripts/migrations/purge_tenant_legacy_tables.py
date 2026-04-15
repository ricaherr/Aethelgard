"""
Migration: Purge legacy tables from tenant databases
=====================================================

Drops tables that have been superseded by canonical sys_/usr_ equivalents:
  - notifications      → superseded by usr_notifications
  - position_metadata  → superseded by sys_position_metadata
  - session_tokens     → superseded by sys_session_tokens (LEGACY per ETI-SRE-2026-04-14)

Scope: ONLY tenant DBs (data_vault/tenants/**/*.db). The global DB retains
session_tokens while the migration comment in initialize_schema() is active.

Safe to re-run — uses IF EXISTS guards, all operations are idempotent.
"""
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TENANTS_BASE = Path(__file__).parent.parent.parent / "data_vault" / "tenants"

LEGACY_TABLES = ["notifications", "position_metadata", "session_tokens"]


def _get_tenant_dbs() -> list[Path]:
    """Return all tenant DB paths found under TENANTS_BASE."""
    if not TENANTS_BASE.exists():
        logger.error("Tenants directory not found: %s", TENANTS_BASE)
        return []
    return sorted(TENANTS_BASE.glob("**/*.db"))


def _audit_table(conn: sqlite3.Connection, table: str) -> int:
    """Return row count for table, or -1 if table does not exist."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return -1
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


def _drop_legacy_tables(db_path: Path, dry_run: bool = False) -> dict:
    """Drop legacy tables from a single tenant DB. Returns a summary dict."""
    summary = {"db": str(db_path), "dropped": [], "skipped": [], "errors": []}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        for table in LEGACY_TABLES:
            row_count = _audit_table(conn, table)
            if row_count == -1:
                summary["skipped"].append(f"{table} (not present)")
                continue
            if dry_run:
                summary["dropped"].append(f"{table} [DRY-RUN, rows={row_count}]")
                continue
            if row_count > 0:
                logger.warning(
                    "%s — dropping %s with %d row(s) (data will be lost)",
                    db_path.parent.name,
                    table,
                    row_count,
                )
            conn.execute(f"DROP TABLE IF EXISTS {table}")  # noqa: S608
            summary["dropped"].append(f"{table} (rows purged: {row_count})")
        conn.commit()
        conn.close()
    except Exception as exc:
        summary["errors"].append(str(exc))
        logger.error("Error processing %s: %s", db_path, exc)
    return summary


def run_migration(dry_run: bool = False) -> None:
    """
    Run the legacy table purge across all tenant DBs.

    Args:
        dry_run: If True, only reports what would be dropped without executing DDL.
    """
    dbs = _get_tenant_dbs()
    if not dbs:
        logger.warning("No tenant DBs found — nothing to do.")
        return

    mode = "DRY-RUN" if dry_run else "LIVE"
    logger.info("[PURGE] Starting legacy table purge [%s] across %d tenant DB(s)", mode, len(dbs))

    total_dropped = 0
    total_errors = 0

    for db_path in dbs:
        result = _drop_legacy_tables(db_path, dry_run=dry_run)
        if result["dropped"]:
            total_dropped += len(result["dropped"])
            logger.info(
                "[PURGE] %s → dropped: %s",
                db_path.parent.name,
                ", ".join(result["dropped"]),
            )
        if result["skipped"]:
            logger.debug(
                "[PURGE] %s → skipped: %s",
                db_path.parent.name,
                ", ".join(result["skipped"]),
            )
        if result["errors"]:
            total_errors += 1

    logger.info(
        "[PURGE] Done — %d table(s) %s, %d DB(s) with errors",
        total_dropped,
        "would be dropped" if dry_run else "dropped",
        total_errors,
    )


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    run_migration(dry_run=dry)
