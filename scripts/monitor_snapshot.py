import os
import sqlite3
import json
from datetime import datetime

# Configuración de rutas según .ai_rules.md
GLOBAL_DB = "data_vault/global/aethelgard.db"
LOG_DIR = "logs/"

def get_db_status():
    """Verifica salud de sys_state y últimas señales"""
    if not os.path.exists(GLOBAL_DB):
        return "ERROR: Global DB not found"
    try:
        conn = sqlite3.connect(GLOBAL_DB)
        cursor = conn.cursor()
        # Ejemplo: Buscar últimas señales y estado del sistema
        cursor.execute("SELECT * FROM sys_state ORDER BY timestamp DESC LIMIT 5")
        state = cursor.fetchall()
        conn.close()
        return state
    except Exception as e:
        return f"DB_ERROR: {str(e)}"

def get_recent_logs(lines=50):
    """Extrae logs sin saturar tokens"""
    summary = {}
    if not os.path.exists(LOG_DIR):
        return "No logs directory found."
    
    for log_file in os.listdir(LOG_DIR):
        if log_file.endswith(".log"):
            path = os.path.join(LOG_DIR, log_file)
            with open(path, "r") as f:
                summary[log_file] = f.readlines()[-lines:]
    return summary

def generate_snapshot():
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "db_health": get_db_status(),
        "log_tail": get_recent_logs(),
        "system_limits": "Checking vs .ai_rules.md 30KB limit" #
    }
    print(json.dumps(snapshot, indent=2))

if __name__ == "__main__":
    generate_snapshot()