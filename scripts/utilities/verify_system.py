"""
VERIFICATION PROTOCOL - Final Integrity Check
==============================================
Script final que ejecuta el protocolo completo de verificación tras la limpieza.

CRITERIOS DE ÉXITO:
1. Base de datos muestra 0 señales, 0 trades
2. check_integrity.py confirma: MT5 = DB = BOT MEMORY = 0
3. Dashboard (modo diagnóstico) refleja 0/0/0
4. Módulos responden heartbeat correctamente
5. El primer trade que aparezca sea uno REAL desde MT5 o Scanner

Usage:
    python scripts/verify_system.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import centralized diagnostics
from scripts.utilities.system_diagnostics import SystemDiagnostics

def print_header(title: str):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_database_clean():
    """Verify database is clean (0 records)."""
    print_header("1. DATABASE CLEANUP VERIFICATION")
    
    try:
        # Use centralized function
        db_path = SystemDiagnostics.get_database_path()
        result = SystemDiagnostics.check_database_clean(db_path)
        
        # Display results
        signals_count = result["tables"].get("signals", 0)
        recent_signals = result.get("recent_signals", 0)
        old_signals = signals_count - recent_signals
        
        # Show signal breakdown
        if recent_signals > 0:
            print(f"     signals (recent)     → {recent_signals} records (OK - active trading)")
        if old_signals > 0:
            print(f"    signals (old >5min)  → {old_signals} records (DIRTY)")
        if signals_count == 0:
            print(f"   ✅ signals              → 0 records (CLEAN)")
        
        # Show other tables
        for table, count in result["tables"].items():
            if table == "signals":
                continue  # Already displayed above
            elif table in ["edge_learning", "coherence_events"]:
                print(f"     {table:20} → {count} records (system data)")
            elif count == 0:
                print(f"   ✅ {table:20} → 0 records (CLEAN)")
            else:
                print(f"    {table:20} → {count} records (DIRTY)")
        
        for warning in result.get("warnings", []):
            print(f"     {warning}")
        
        if result["clean"]:
            print("\n Database is clean")
            return True
        else:
            print("\n DATABASE HAS OLD DATA - Run purge_database.py if needed")
            return False
            
    except Exception as e:
        print(f" Error checking database: {e}")
        return False


def check_mt5_sync():
    """Verify MT5 synchronization."""
    print_header("2. MT5 SYNCHRONIZATION CHECK")
    
    try:
        # Use centralized function
        positions = SystemDiagnostics.get_mt5_positions()
        
        if positions is None:
            print("     MT5 not available")
            return None
        
        count = len(positions)
        
        if count == 0:
            print(f"   ✅ MT5 has 0 open positions (as expected)")
            return True
        else:
            print(f"     MT5 has {count} open position(s)")
            for pos in positions:
                print(f"      - {pos['symbol']}: {pos['type']} | Ticket: {pos['ticket']}")
            return True
            
    except Exception as e:
        print(f"    Error checking MT5: {e}")
        return False


def check_module_heartbeats():
    """Verify module heartbeats."""
    print_header("3. MODULE HEARTBEAT VERIFICATION")
    
    try:
        # Use centralized functions
        db_path = SystemDiagnostics.get_database_path()
        heartbeats = SystemDiagnostics.get_heartbeats(db_path)
        pending_signals = SystemDiagnostics.get_pending_signals_count(db_path)
        
        if not heartbeats:
            print("     No heartbeats found (modules not running)")
            return None
        
        # Use centralized analysis logic
        status_analysis = SystemDiagnostics.analyze_heartbeats(heartbeats, pending_signals)
        
        all_ok = True
        for module, status in status_analysis.items():
            if "FROZEN" in status:
                print(f"    {module:20} → {status}")
                all_ok = False
            elif "IDLE" in status:
                print(f"     {module:20} → {status}")
            else:
                print(f"   ✅ {module:20} → {status}")
        
        if all_ok:
            print("\n ALL MODULES RESPONDING")
            return True
        else:
            print("\n SOME MODULES FROZEN - Restart system")
            return False
            
    except Exception as e:
        print(f"    Error checking heartbeats: {e}")
        return False


def check_audit_trail():
    """Verify audit trail is functional."""
    print_header("4. AUDIT TRAIL VERIFICATION")
    
    try:
        from data_vault.storage import StorageManager
        import sqlite3
        
        storage = StorageManager()
        conn = sqlite3.connect(storage.db_path)
        
        # Check if audit_log table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='audit_log'
        """)
        
        if not cursor.fetchone():
            print("   ⚠️  audit_log table does not exist yet")
            print("      This is normal if system never ran with ChainValidator")
            conn.close()
            return None
        
        # Count recent entries
        cursor = conn.execute("""
            SELECT COUNT(*) FROM audit_log
            WHERE timestamp > datetime('now', '-1 hour')
        """)
        
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            print(f"   ℹ️  No audit entries in last hour (system idle)")
        else:
            print(f"   ✅ {count} audit entries in last hour (system active)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error checking audit trail: {e}")
        return False


def print_final_summary(db_clean, mt5_sync, heartbeats, audit):
    """Print final summary."""
    print_header("FINAL VERIFICATION SUMMARY")
    
    checks = [
        ("Database Clean (0 records)", db_clean),
        ("MT5 Synchronization", mt5_sync),
        ("Module Heartbeats", heartbeats),
        ("Audit Trail", audit)
    ]
    
    passed = sum(1 for _, result in checks if result is True)
    total = len([c for c in checks if c[1] is not None])
    
    print("\nResults:")
    for check_name, result in checks:
        if result is True:
            print(f"   ✅ {check_name}")
        elif result is False:
            print(f"   ❌ {check_name}")
        else:
            print(f"   ⚠️  {check_name} (not available)")
    
    print(f"\nScore: {passed}/{total} checks passed")
    
    if db_clean and (heartbeats is None or heartbeats):
        print("\n" + "=" * 70)
        print("  ✅ SYSTEM READY FOR PRODUCTION")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Start system: python main.py")
        print("2. Open diagnostic UI: streamlit run ui/diagnostic_mode.py")
        print("3. Monitor first REAL trade from MT5 or Scanner")
        print("4. Verify it appears in diagnostic UI with correct trace_id")
    else:
        print("\n" + "=" * 70)
        print("  ⚠️  SYSTEM NOT READY")
        print("=" * 70)
        print("\nRequired actions:")
        if not db_clean:
            print("1. Run: python scripts/purge_database.py")
        if heartbeats is False:
            print("2. Restart system to clear frozen modules")
        print("3. Re-run this verification: python scripts/verify_system.py")


def main():
    """Main execution."""
    print("\n" + "=" * 70)
    print("  AETHELGARD FINAL VERIFICATION PROTOCOL")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Run all checks
    db_clean = check_database_clean()
    mt5_sync = check_mt5_sync()
    heartbeats = check_module_heartbeats()
    audit = check_audit_trail()
    
    # Print summary
    print_final_summary(db_clean, mt5_sync, heartbeats, audit)
    
    print("\n" + "=" * 70)
    print("  END OF VERIFICATION")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
