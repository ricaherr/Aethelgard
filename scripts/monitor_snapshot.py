import os
import sqlite3
import json
from datetime import datetime

# Configuración de rutas según .ai_rules.md
GLOBAL_DB = "data_vault/global/aethelgard.db"
LOG_DIR = "logs/"

def get_db_snapshot():
    """
    Extrae el estado real de la base de datos.
    Sustituye la tabla obsoleta sys_state por sys_config [SSOT v2.x].
    """
    if not os.path.exists(GLOBAL_DB):
        return {"error": "GLOBAL_DB_NOT_FOUND", "path": GLOBAL_DB}
    
    snapshot = {}
    try:
        conn = sqlite3.connect(GLOBAL_DB)
        conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
        cursor = conn.cursor()
        
        # 1. VERIFICACIÓN DE TABLAS REALES (Anti-Alucinación)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        snapshot["active_tables"] = [row["name"] for row in cursor.fetchall()]
        
        # 2. ÚLTIMOS ESTADOS DEL SISTEMA (sys_config)
        # Verificamos si la tabla existe antes de consultar para evitar crash
        if "sys_config" in snapshot["active_tables"]:
            cursor.execute("SELECT key, value, updated_at FROM sys_config ORDER BY updated_at DESC LIMIT 10")
            snapshot["sys_config_tail"] = [dict(row) for row in cursor.fetchall()]
        
        # 3. AUDITORÍA DE ANOMALÍAS (Basado en Dominio 04/09)
        if "sys_audit_logs" in snapshot["active_tables"]:
            cursor.execute("SELECT * FROM sys_audit_logs ORDER BY timestamp DESC LIMIT 5")
            snapshot["recent_audit"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return snapshot
    except Exception as e:
        return {"error": f"DB_SNAPSHOT_FAILED: {str(e)}"}

def get_recent_logs(lines=50):
    """
    Extrae las últimas líneas de logs con manejo de encoding robusto.
    Evita el error UnicodeDecodeError en archivos con caracteres especiales.
    """
    summary = {}
    if not os.path.exists(LOG_DIR):
        return {"error": "LOG_DIR_NOT_FOUND", "path": LOG_DIR}
    
    try:
        for log_file in os.listdir(LOG_DIR):
            if log_file.endswith(".log"):
                path = os.path.join(LOG_DIR, log_file)
                # 'errors=replace' es clave para no romper el script con bytes inválidos
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    summary[log_file] = [line.strip() for line in f.readlines()[-lines:]]
        return summary
    except Exception as e:
        return {"error": f"LOG_READ_FAILED: {str(e)}"}

def check_file_mass_limits():
    """Verifica la Regla de Oro §4 (>30KB) en archivos clave"""
    alerts = []
    critical_paths = ["core_brain/", "connectors/", "data_vault/"]
    for folder in critical_paths:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith(".py"):
                    fpath = os.path.join(folder, f)
                    fsize = os.path.getsize(fpath) / 1024
                    if fsize > 30:
                        alerts.append({"file": fpath, "size_kb": round(fsize, 2)})
    return alerts

def generate_full_snapshot():
    """Genera el JSON final para el contexto de la IA"""
    full_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "standard": "Aethelegard Master SRE",
            "trace_id_context": "AUTO-GEN-AUDIT"
        },
        "db_state": get_db_snapshot(),
        "log_tails": get_recent_logs(),
        "mass_limit_violations": check_file_mass_limits()
    }
    
    # Salida en JSON puro para que Claude lo procese sin ruido
    print(json.dumps(full_data, indent=2))

if __name__ == "__main__":
    generate_full_snapshot()