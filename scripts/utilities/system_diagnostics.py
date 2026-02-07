"""
System Diagnostics - Centralized Diagnostic Functions
======================================================
Single source of truth for all diagnostic operations.

Provides:
- Heartbeat analysis (IDLE/FROZEN detection)
- Database integrity checks
- Signal pending verification
- MT5 synchronization validation

Used by:
- diagnose_threads.py
- verify_system.py
- check_integrity.py

Design Pattern: DRY (Don't Repeat Yourself)
"""

import sys
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Add project root to sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


class SystemDiagnostics:
    """Centralized diagnostic operations for Aethelgard system."""
    
    @staticmethod
    def get_database_path() -> str:
        """
        Find the main SQLite database.
        
        Returns:
            Path to aethelgard.db or empty string if not found
        """
        data_vault_dir = project_root / "data_vault"
        
        # Check for main database
        db_path = data_vault_dir / "aethelgard.db"
        if db_path.exists():
            return str(db_path)
        
        # Fallback: find first .db file (excluding test databases)
        db_files = [f for f in data_vault_dir.glob("*.db") if "test" not in f.name.lower()]
        if db_files:
            return str(db_files[0])
        
        return ""
    
    @staticmethod
    def get_heartbeats(db_path: str) -> Dict[str, datetime]:
        """
        Query module heartbeats from system_state table.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Dict mapping module_name -> last_heartbeat_time
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("""
                SELECT key, value 
                FROM system_state 
                WHERE key LIKE 'heartbeat_%'
            """)
            
            heartbeats = {}
            for row in cursor.fetchall():
                key, value = row
                module_name = key.replace("heartbeat_", "")
                
                # Clean value (remove quotes if present)
                value_cleaned = value.strip('"').strip("'")
                
                # Parse ISO datetime
                try:
                    heartbeat_time = datetime.fromisoformat(value_cleaned)
                    heartbeats[module_name] = heartbeat_time
                except ValueError:
                    logger.warning(f"Could not parse datetime for {module_name}: {value}")
            
            conn.close()
            return heartbeats
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error: {e}")
            return {}
    
    @staticmethod
    def get_pending_signals_count(db_path: str) -> int:
        """
        Check if there are pending signals in the database.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Number of signals generated in last 5 minutes
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("""
                SELECT COUNT(*) 
                FROM signals 
                WHERE timestamp > datetime('now', 'localtime', '-5 minutes')
            """)
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Could not query signals: {e}")
            return 0
    
    @staticmethod
    def analyze_heartbeats(heartbeats: Dict[str, datetime], pending_signals: int = 0) -> Dict[str, str]:
        """
        Analyze heartbeats and detect frozen/idle/active modules.
        
        Logic:
        - Scanner is the system heartbeat (always updates every cycle)
        - If scanner is alive (< 60s): System is running
          - Scanner/signal_factory with recent heartbeats = OK (actively working)
          - Risk_manager/executor with recent heartbeats = OK (processing signals)
          - Risk_manager/executor with old heartbeats but pending signals exist = FROZEN
          - Risk_manager/executor with old heartbeats and NO pending signals = IDLE
        - If scanner is frozen (> 60s): System stopped
          - All modules = FROZEN (entire system halted)
        
        Args:
            heartbeats: Dict of module -> last_heartbeat_time
            pending_signals: Number of pending signals in last 5 minutes
            
        Returns:
            Dict of module -> status (OK/IDLE/FROZEN)
        """
        now = datetime.now()
        results = {}
        
        TIMEOUT_ACTIVE = 30    # seconds - module actively working
        TIMEOUT_FROZEN = 60    # seconds - system considered dead
        
        # Scanner is the system heartbeat (always runs)
        scanner_beat = heartbeats.get("scanner")
        system_running = False
        
        if scanner_beat:
            scanner_elapsed = (now - scanner_beat).total_seconds()
            system_running = (scanner_elapsed < TIMEOUT_FROZEN)
        
        # Get signal_factory elapsed time to detect if signals are being generated NOW
        signal_factory_beat = heartbeats.get("signal_factory")
        signals_active_now = False
        if signal_factory_beat:
            signal_factory_elapsed = (now - signal_factory_beat).total_seconds()
            signals_active_now = (signal_factory_elapsed < TIMEOUT_ACTIVE)
        
        # Check if there are ACTUAL pending signals that should be processed
        has_pending_signals = (pending_signals > 0)
        
        # Analyze each module based on system state
        for module, last_beat in heartbeats.items():
            elapsed = (now - last_beat).total_seconds()
            
            if module == "scanner" or module == "signal_factory":
                # Core modules that always run every cycle
                if elapsed < TIMEOUT_ACTIVE:
                    results[module] = "OK (active)"
                elif elapsed < TIMEOUT_FROZEN:
                    results[module] = f"WARNING (slow {int(elapsed)}s)"
                else:
                    results[module] = f"FROZEN (dead {int(elapsed)}s)"
            
            elif module == "risk_manager" or module == "executor":
                # Conditional modules (only work when signals exist)
                if not system_running:
                    # System down - modules are frozen
                    results[module] = f"FROZEN (system halted {int(elapsed)}s)"
                elif elapsed < TIMEOUT_ACTIVE:
                    # Module actively processing signals
                    results[module] = "OK (processing)"
                elif has_pending_signals and signals_active_now and elapsed > TIMEOUT_FROZEN:
                    # CRITICAL: Signals exist in DB and signal_factory is active
                    # but this module hasn't processed them → module is FROZEN
                    results[module] = f"FROZEN (signals pending {int(elapsed)}s)"
                else:
                    # Module idle (no signals to process, system is running)
                    # These modules only update when they have work
                    results[module] = f"IDLE (no signals {int(elapsed)}s)"
            
            else:
                # Unknown modules
                if elapsed < TIMEOUT_ACTIVE:
                    results[module] = "OK"
                elif elapsed < TIMEOUT_FROZEN:
                    results[module] = f"WARNING ({int(elapsed)}s)"
                else:
                    results[module] = f"FROZEN ({int(elapsed)}s)"
        
        return results
    
    @staticmethod
    def check_database_locks(db_path: str) -> Dict:
        """
        Check if database is locked or has write-ahead log issues.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Dict with lock status
        """
        results = {
            "locked": False,
            "wal_mode": False,
            "pending_writes": 0
        }
        
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            
            # Check journal mode
            cursor = conn.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            results["wal_mode"] = (journal_mode == "wal")
            
            # Check if there are pending WAL writes
            if results["wal_mode"]:
                cursor = conn.execute("PRAGMA wal_checkpoint")
                checkpoint_result = cursor.fetchone()
                if checkpoint_result:
                    results["pending_writes"] = checkpoint_result[1] if len(checkpoint_result) > 1 else 0
            
            conn.close()
            
        except sqlite3.OperationalError as e:
            results["locked"] = True
            results["error"] = str(e)
        
        return results
    
    @staticmethod
    def check_database_clean(db_path: str) -> Dict[str, any]:
        """
        Verify database tables are clean (0 records for operational tables).
        
        Recent signals (<5 min) are considered normal operation, not dirty data.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Dict with status and details per table
        """
        results = {
            "clean": True,
            "tables": {},
            "warnings": [],
            "recent_signals": 0
        }
        
        try:
            conn = sqlite3.connect(db_path)
            
            # Check recent signals (last 5 minutes) - these are NORMAL
            cursor = conn.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE timestamp > datetime('now', 'localtime', '-5 minutes')
            """)
            recent_signals = cursor.fetchone()[0]
            results["recent_signals"] = recent_signals
            
            # Check old signals (>5 minutes) - these are DIRTY
            cursor = conn.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE timestamp <= datetime('now', 'localtime', '-5 minutes')
            """)
            old_signals = cursor.fetchone()[0]
            
            # Total signals
            cursor = conn.execute("SELECT COUNT(*) FROM signals")
            total_signals = cursor.fetchone()[0]
            results["tables"]["signals"] = total_signals
            
            # Only mark as dirty if there are OLD signals
            if old_signals > 0:
                results["clean"] = False
            
            # Check other operational tables
            operational_tables = ["trades", "trade_results"]
            
            for table in operational_tables:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    results["tables"][table] = count
                    
                    if count > 0:
                        results["clean"] = False
                        
                except sqlite3.OperationalError:
                    results["warnings"].append(f"Table {table} not found")
            
            # Check system tables (informational only)
            system_tables = ["edge_learning", "coherence_events"]
            for table in system_tables:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    results["tables"][table] = count
                except sqlite3.OperationalError:
                    pass
            
            conn.close()
            
        except Exception as e:
            results["clean"] = False
            results["error"] = str(e)
        
        return results
    
    @staticmethod
    def get_mt5_positions() -> Optional[List[Dict]]:
        """
        Query real MT5 positions from the broker.
        
        Returns:
            List of positions or None if MT5 unavailable
        """
        try:
            from connectors.mt5_connector import MT5Connector, MT5_AVAILABLE
            
            if not MT5_AVAILABLE:
                logger.warning("MetaTrader5 library not installed")
                return None
            
            connector = MT5Connector()
            
            # Attempt connection (synchronous for diagnostic)
            if not connector._connect_sync_once():
                logger.warning("Failed to connect to MT5")
                return None
            
            positions = connector.get_open_positions()
            
            if positions is None:
                logger.warning("MT5 query returned None (connection issue)")
                return []
            
            return positions
            
        except ImportError:
            logger.warning("Cannot import MT5Connector (missing dependencies)")
            return None
        except Exception as e:
            logger.error(f"Error querying MT5: {e}")
            return None
