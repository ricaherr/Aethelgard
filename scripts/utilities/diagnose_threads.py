"""
THREAD DIAGNOSTICS SCRIPT
=========================
Diagnóstico de hilos: Detecta módulos congelados y excepciones silenciosas.

Verifica:
1. Estado de heartbeats en la base de datos
2. Módulos que no responden (timeout > 60 segundos)
3. Logs recientes de errores/excepciones
4. Bloqueos en acceso a base de datos

Usage:
    python scripts/diagnose_threads.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
import logging

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import centralized diagnostics
from scripts.utilities.system_diagnostics import SystemDiagnostics

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def get_recent_log_errors() -> List[str]:
    """
    Scan recent log files for errors/exceptions.
    
    Returns:
        List of error lines found
    """
    logs_dir = project_root / "logs"
    
    if not logs_dir.exists():
        return []
    
    errors = []
    cutoff_time = datetime.now() - timedelta(hours=1)
    
    # Find today's log file
    log_files = list(logs_dir.glob("*.log"))
    
    for log_file in sorted(log_files, reverse=True)[:3]:  # Check last 3 logs
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    # Look for ERROR, CRITICAL, Exception
                    if any(keyword in line for keyword in ["ERROR", "CRITICAL", "Exception", "Traceback"]):
                        errors.append(f"{log_file.name}: {line.strip()}")
                        
                        if len(errors) >= 20:  # Limit to 20 errors
                            return errors
        except Exception:
            continue
    
    return errors


def check_module_status() -> Dict[str, str]:
    """
    Expected modules and their status.
    
    Returns:
        Dict of expected modules
    """
    expected_modules = [
        "scanner",
        "signal_factory",
        "risk_manager",
        "executor"
    ]
    
    return {module: "Expected" for module in expected_modules}


def main():
    """Main execution function."""
    print("\n" + "=" * 70)
    print("  AETHELGARD THREAD DIAGNOSTICS")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Find database using centralized function
    db_path = SystemDiagnostics.get_database_path()
    
    if not db_path:
        print("\n No database found in data_vault/")
        return
    
    print(f"\n Database: {Path(db_path).name}")
    
    # Check pending signals using centralized function
    pending_signals = SystemDiagnostics.get_pending_signals_count(db_path)
    if pending_signals > 0:
        print(f"  {pending_signals} signal(s) generated in last 5 minutes")
    
    # Step 1: Check heartbeats using centralized functions
    print_header("1. MODULE HEARTBEATS")
    
    heartbeats = SystemDiagnostics.get_heartbeats(db_path)
    
    if not heartbeats:
        print("  No heartbeats found in database")
        print("   This could mean:")
        print("   - System never started")
        print("   - Heartbeats not being written")
        print("   - Database corruption")
    else:
        status = SystemDiagnostics.analyze_heartbeats(heartbeats, pending_signals)
        
        for module, state in status.items():
            print(f"   {module:20} {state}")
    
    # Step 2: Expected modules check
    print_header("2. EXPECTED MODULES")
    
    expected = check_module_status()
    actual_modules = set(heartbeats.keys())
    expected_modules = set(expected.keys())
    
    missing = expected_modules - actual_modules
    extra = actual_modules - expected_modules
    
    if missing:
        print(f"  Missing modules (never started):")
        for module in missing:
            print(f"   - {module}")
    
    if extra:
        print(f"  Additional modules:")
        for module in extra:
            print(f"   - {module}")
    
    if not missing and not extra:
        print("✅ All expected modules present")
    
    # Step 3: Database lock check using centralized function
    print_header("3. DATABASE STATUS")
    
    lock_status = SystemDiagnostics.check_database_locks(db_path)
    
    if lock_status["locked"]:
        print("❌ Database is LOCKED")
        print("   → This could block writes from RiskManager/Executor")
        if "error" in lock_status:
            print(f"   → Error: {lock_status['error']}")
    else:
        print("✅ Database is accessible (no locks)")
    
    if lock_status["wal_mode"]:
        print("✅ WAL mode enabled (good for concurrent access)")
    else:
        print("⚠️  WAL mode not enabled")
        print("   → Run: PRAGMA journal_mode=WAL; to enable")
    
    # Step 4: Recent errors
    print_header("4. RECENT LOG ERRORS (Last Hour)")
    
    errors = get_recent_log_errors()
    
    if not errors:
        print("✅ No recent errors found in logs")
    else:
        print(f"⚠️  Found {len(errors)} error(s):")
        for error in errors[:10]:  # Show first 10
            print(f"   {error}")
        
        if len(errors) > 10:
            print(f"   ... and {len(errors) - 10} more")
    
    # Step 5: Recommendations
    print_header("DIAGNOSIS SUMMARY")
    
    status_analysis = SystemDiagnostics.analyze_heartbeats(heartbeats, pending_signals)
    frozen_modules = [m for m, s in status_analysis.items() if "FROZEN" in s]
    idle_modules = [m for m, s in status_analysis.items() if "IDLE" in s]
    active_modules = [m for m, s in status_analysis.items() if "OK" in s]
    
    if frozen_modules:
        print(f"\nCRITICAL: {len(frozen_modules)} module(s) frozen:")
        for module in frozen_modules:
            print(f"   - {module}: {status_analysis[module]}")
        
        print("\nPossible causes:")
        print("   1. Infinite loop or blocking operation")
        print("   2. Database lock preventing writes")
        print("   3. Unhandled exception killed the thread")
        print("   4. Deadlock waiting for resources")
        
        print("\nRecommended actions:")
        print("   1. Check logs for exceptions in frozen modules")
        print("   2. Restart the system (python main.py)")
        print("   3. Enable DEBUG logging to trace execution")
        print("   4. Review thread implementation for blocking calls")
    
    if idle_modules:
        print(f"\nINFO: {len(idle_modules)} module(s) idle (waiting for work):")
        for module in idle_modules:
            print(f"   - {module}: {status_analysis[module]}")
        print("   This is NORMAL if no signals are being generated.")
    
    if active_modules and not frozen_modules:
        print(f"\nOK: System running normally ({len(active_modules)} active modules)")
        for module in active_modules:
            print(f"   - {module}: {status_analysis[module]}")
    
    if lock_status["locked"]:
        print("\n⚠️  Database lock detected:")
        print("   → Close all connections to the database")
        print("   → Restart the system")
    
    print("\n" + "=" * 70)
    print("  END OF DIAGNOSTICS")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
