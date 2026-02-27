#!/usr/bin/env python
"""
[AUDIT] DB Uniqueness Audit - Aethelgard (Milestone 6.2)
=========================================================
Enforces the Single Source of Truth (SSOT) rule for SQLite databases:
- The ONLY permitted database is: data_vault/aethelgard.db
- Any .db file found outside of excluded directories is a violation.

Excluded directories (legitimate, non-production locations):
  - backups/   -> automated rolling backups (system-managed)
  - venv/      -> third-party packages
  - __pycache__/  -> compiled artifacts
  - .git/      -> version control internals

Exit codes:
  0  -> Integrity verified: exactly one DB in the correct location.
  1  -> Violation detected: unexpected .db file(s) found.
  2  -> Critical: the primary database is missing entirely.
"""
import sys
from pathlib import Path


# Directories excluded from the uniqueness constraint
EXCLUDED_DIRS = {"backups", "venv", ".venv", "__pycache__", ".git", "node_modules"}

# Directory containing isolated databases
TENANTS_DIR_RELATIVE = Path("data_vault") / "tenants"

# 1. The primary structural database path (relative to workspace root)
PERMITTED_PRIMARY_DB = Path("data_vault") / "aethelgard.db"

# 2. The global authentication database (HU 1.1)
PERMITTED_AUTH_DB = Path("data_vault") / "global" / "auth.db"


def audit_db_uniqueness(workspace: Path) -> int:
    """
    Scans the workspace for .db files, applying exclusion rules.

    Returns:
        0 on success, 1 on violation, 2 on missing primary DB.
    """
    primary_db = workspace / PERMITTED_PRIMARY_DB

    # --- Check 1: Primary DB must exist ---
    if not primary_db.exists():
        print(f"[CRITICAL] Primary database NOT FOUND: {PERMITTED_PRIMARY_DB}")
        print(f"  Expected location: {primary_db}")
        print("  The system cannot operate without its primary database.")
        return 2

    print(f"[OK] Primary database confirmed: {PERMITTED_PRIMARY_DB}")

    # --- Check 2: Scan for unauthorized .db files ---
    violations: list[Path] = []

    for db_file in workspace.rglob("*.db"):
        relative = db_file.relative_to(workspace)

        # Check if any part of the path matches an excluded directory
        parts = relative.parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue  # Legitimate location, skip

        # The authorized databases in non-excluded paths
        if relative == PERMITTED_PRIMARY_DB or relative == PERMITTED_AUTH_DB:
            continue  # This is the expected primary or auth DB
        
        # Also allow databases located inside data_vault/tenants/
        if len(parts) >= 3 and parts[0] == "data_vault" and parts[1] == "tenants":
            continue

        # Anything else is a violation
        violations.append(relative)

    if violations:
        print(f"\n[VIOLATION] {len(violations)} unauthorized database(s) found outside allowed paths:")
        print("=" * 70)
        for v in sorted(violations):
            print(f"  [!] {v}")
        print("=" * 70)
        print("\n  ACTION REQUIRED: These databases violate the SSOT principle.")
        print("  -> If test databases: use :memory: or tmp_path fixtures.")
        print("  -> If legacy data: migrate to data_vault/aethelgard.db and delete.")
        return 1

    print(f"[OK] DB Uniqueness verified — no unauthorized databases detected.")
    print(f"     (Excluded directories: {', '.join(sorted(EXCLUDED_DIRS))})")
    return 0


def main() -> int:
    workspace = Path(__file__).parent.parent.parent
    print("\n[AUDIT] DB UNIQUENESS AUDIT — Aethelgard Safety Governor")
    print("=" * 70)
    print(f"Workspace: {workspace}")
    print(f"Permitted Primary: {PERMITTED_PRIMARY_DB}")
    print(f"Permitted Auth   : {PERMITTED_AUTH_DB}")
    print(f"Permitted Tenants: {TENANTS_DIR_RELATIVE}/*.db")
    print(f"Excluded Dirs    : {', '.join(sorted(EXCLUDED_DIRS))}")
    print("=" * 70)

    result = audit_db_uniqueness(workspace)

    print()
    if result == 0:
        print("[SUCCESS] Database integrity confirmed.")
    elif result == 1:
        print("[FAIL] Database integrity COMPROMISED — review violations above.")
    else:
        print("[FAIL] Primary database is MISSING — system cannot start.")

    return result


if __name__ == "__main__":
    sys.exit(main())
