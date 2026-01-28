"""
Aethelgard Health Core - Diagnostic and Monitoring System
Rules:
1. Pure Python (Agnostic logic).
2. Validates DB, Config, and Connectors.
"""
import json
import logging
import os
import sys
import psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Path configuration
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data_vault"

logger = logging.getLogger("HEALTH_CORE")

class HealthManager:
    def __init__(self):
        self.db_path = DATA_DIR / "aethelgard.db"
    
    def check_config_integrity(self) -> Dict[str, Any]:
        """Checks if critical JSON config files are present and valid."""
        results = {"status": "GREEN", "details": []}
        critical_files = ["modules.json", "dynamic_params.json", "data_providers.json"]
        
        for cf in critical_files:
            file_path = CONFIG_DIR / cf
            if not file_path.exists():
                results["status"] = "RED"
                results["details"].append(f"CRITICAL: {cf} is missing.")
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                results["details"].append(f"SUCCESS: {cf} is valid JSON.")
            except Exception as e:
                results["status"] = "RED"
                results["details"].append(f"CRITICAL: {cf} has invalid JSON format: {e}")
        
        return results

    def check_db_integrity(self) -> Dict[str, Any]:
        """Checks SQLite database health."""
        results = {"status": "GREEN", "details": []}
        
        if not self.db_path.exists():
            results["status"] = "RED"
            results["details"].append("CRITICAL: aethelgard.db is missing.")
            return results
            
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Simple check of critical tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            
            needed_tables = ['system_state', 'signals', 'executed_signals']
            for t in needed_tables:
                if t not in tables:
                    results["status"] = "YELLOW"
                    results["details"].append(f"WARNING: Table {t} missing (will be auto-created).")
                else:
                    results["details"].append(f"SUCCESS: Table {t} found.")
            
            conn.close()
        except Exception as e:
            results["status"] = "RED"
            results["details"].append(f"CRITICAL: DB Connection Error: {e}")
            
        return results

    def get_resource_usage(self) -> Dict[str, Any]:
        """Gets CPU and Memory usage of the current process group."""
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_mb": mem_info.rss / (1024 * 1024),
                "threads": process.num_threads(),
                "status": "GREEN"
            }
        except Exception as e:
            return {"status": "YELLOW", "error": str(e)}

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Runs all checks and returns a summary."""
        config = self.check_config_integrity()
        db = self.check_db_integrity()
        resources = self.get_resource_usage()
        
        # Overall status logic
        status = "GREEN"
        if config["status"] == "RED" or db["status"] == "RED":
            status = "RED"
        elif config["status"] == "YELLOW" or db["status"] == "YELLOW":
            status = "YELLOW"
            
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": status,
            "config": config,
            "db": db,
            "resources": resources
        }

if __name__ == "__main__":
    # Quick CLI test
    hm = HealthManager()
    summary = hm.run_full_diagnostic()
    print(json.dumps(summary, indent=2))
