#!/usr/bin/env python3
"""
Emergency database checkpoint to clear WAL lock.

TRACE_ID: FIX-SHADOW-CONTENTION-002-EMERGENCY-UNLOCK
Use when database is locked and blocking all operations.
"""
import sqlite3
import os
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db"
WAL_PATH = Path(str(DB_PATH) + "-wal")
SHM_PATH = Path(str(DB_PATH) + "-shm")

def emergency_checkpoint():
    print("=" * 80)
    print("EMERGENCY DATABASE CHECKPOINT - FIX-SHADOW-CONTENTION-002")
    print("=" * 80)

    if not DB_PATH.exists():
        print(f"ERROR: DB NOT FOUND: {DB_PATH}")
        return False

    print(f"Target DB: {DB_PATH}")
    wal_size = WAL_PATH.stat().st_size / (1024*1024) if WAL_PATH.exists() else 0
    print(f"WAL size before: {wal_size:.2f} MB" if wal_size > 0 else "WAL: not present")
    print()

    # Try PASSIVE checkpoint first (non-blocking)
    print("[Step 1] Attempting PASSIVE checkpoint (non-blocking)...")
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        print("[OK] PASSIVE checkpoint successful")
        conn.close()
        time.sleep(1)
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            print(f"[WARNING] DB still locked after PASSIVE: {e}")
        else:
            print(f"[ERROR] Error: {e}")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

    # Try RESTART checkpoint (blocking, but forces unlock)
    print("\n[Step 2] Attempting RESTART checkpoint (may block briefly)...")
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=60)
        result = conn.execute("PRAGMA wal_checkpoint(RESTART)").fetchone()
        print(f"[OK] RESTART checkpoint completed: {result}")

        # Verify integrity
        check_result = conn.execute("PRAGMA integrity_check").fetchone()
        if check_result[0] == 'ok':
            print("[OK] Integrity check passed")
        else:
            print(f"[WARNING] Integrity check: {check_result[0]}")

        conn.close()
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            print(f"[ERROR] DB still locked: {e}")
            print(f"\n[NUCLEAR OPTION]:")
            print(f"If above fails, manually remove WAL files and restart:")
            print(f"   rm -f {WAL_PATH}")
            print(f"   rm -f {SHM_PATH}")
            print(f"   systemctl restart aethelgard")
            return False
        else:
            print(f"[ERROR] {e}")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

    # Verify WAL is cleared
    time.sleep(2)
    wal_size_after = WAL_PATH.stat().st_size / (1024*1024) if WAL_PATH.exists() else 0
    print(f"\nWAL size after: {wal_size_after:.2f} MB" if wal_size_after > 0 else "WAL: cleared")

    print("\n" + "=" * 80)
    print("[OK] Database checkpoint completed successfully!")
    print("System should now be able to write normally.")
    print("=" * 80)
    return True

if __name__ == "__main__":
    success = emergency_checkpoint()
    exit(0 if success else 1)
