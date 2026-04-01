#!/usr/bin/env python3
"""
Diagnose SQLite database lock contention.

TRACE_ID: FIX-SHADOW-CONTENTION-002-DIAGNOSTICS
"""
import sqlite3
import os
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db"

def diagnose():
    print("=" * 80)
    print("DATABASE LOCK DIAGNOSTICS — FIX-SHADOW-CONTENTION-002")
    print("=" * 80)

    # 1. Check DB file
    if not DB_PATH.exists():
        print(f"ERROR: DB NOT FOUND: {DB_PATH}")
        return

    print(f"OK: DB Path: {DB_PATH}")
    print(f"📊 DB Size: {DB_PATH.stat().st_size / (1024*1024):.2f} MB")
    print()

    # 2. Check WAL files
    wal_path = Path(str(DB_PATH) + "-wal")
    shm_path = Path(str(DB_PATH) + "-shm")

    print("WAL Files Status:")
    print(f"  WAL exists: {wal_path.exists()}")
    if wal_path.exists():
        print(f"  WAL size: {wal_path.stat().st_size / (1024*1024):.2f} MB")
    print(f"  SHM exists: {shm_path.exists()}")
    if shm_path.exists():
        print(f"  SHM size: {shm_path.stat().st_size / 1024:.2f} KB")
    print()

    # 3. Check backup files
    backup_dir = DB_PATH.parent / "backups"
    if backup_dir.exists():
        backups = sorted(backup_dir.glob("sqlite_backup_*.sqlite"), key=os.path.getmtime, reverse=True)
        print(f"Backup Files ({len(backups)} total):")
        for b in backups[:5]:
            age_min = (time.time() - b.stat().st_mtime) / 60
            print(f"  - {b.name} | {b.stat().st_size / (1024*1024):.2f} MB | {age_min:.1f} min ago")
        if len(backups) > 5:
            print(f"  ... and {len(backups) - 5} more")
    print()

    # 4. Try to connect with timeout
    print("Database Connection Test:")
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        print("OK: Connection successful (5s timeout)")

        # Get last market tick
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM sys_config WHERE key='last_market_tick_ts' LIMIT 1")
        result = cursor.fetchone()

        if result:
            last_tick = result[0]
            print(f"  Last market tick: {last_tick}")

            # Calculate staleness
            try:
                last_tick_dt = datetime.fromisoformat(last_tick.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                age_sec = (now - last_tick_dt).total_seconds()
                age_min = age_sec / 60

                status = "OK" if age_sec < 300 else "FROZEN"
                print(f"  Age: {age_min:.1f} minutes [{status}] (threshold: 5 min)")
            except:
                pass
        else:
            print("  Last market tick: NOT SET [ERROR]")

        # Get current table counts
        cursor.execute("SELECT COUNT(*) FROM sys_signals")
        sig_count = cursor.fetchone()[0]
        print(f"  Total signals: {sig_count}")

        # Get ADX values
        cursor.execute("""
            SELECT COUNT(*) as cnt,
                   COUNT(DISTINCT json_extract(metadata, '$.adx')) as unique_adx
            FROM sys_signals
            WHERE metadata IS NOT NULL
        """)
        sig_adx = cursor.fetchone()
        print(f"  Signals with ADX: {sig_adx[0] if sig_adx else 0}")

        # Get last operations from audit log
        cursor.execute("""
            SELECT COUNT(*) as cnt,
                   MAX(timestamp) as latest
            FROM sys_audit_logs
        """)
        audit = cursor.fetchone()
        if audit:
            print(f"  Audit log entries: {audit[0]}")
            if audit[1]:
                print(f"  Last audit: {audit[1]}")

        # Get state of sys_trades (shadow)
        cursor.execute("SELECT COUNT(*) FROM sys_trades WHERE execution_mode='SHADOW'")
        shadow_trades = cursor.fetchone()[0]
        print(f"  SHADOW trades recorded: {shadow_trades}")

        conn.close()

    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            print(f"ERROR: DATABASE LOCKED: {e}")
            print("\nACTION REQUIRED:")
            print("   1. Run: python scripts/emergency_checkpoint.py")
            print("   2. If still locked, restart Aethelgard system")
        else:
            print(f"ERROR: CONNECTION ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    diagnose()
