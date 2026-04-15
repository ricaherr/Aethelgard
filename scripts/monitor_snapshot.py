import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, List

# Configuración de rutas según .ai_rules.md
GLOBAL_DB = "data_vault/global/aethelgard.db"
LOG_DIR = "logs/"

# ── Tabla de legacies CONOCIDAS con plan de migración explícito ───────────────
# Estas tablas NO tienen prefijo sys_/usr_ pero son legacy-compatible durante
# la transición canónica. NO deben clasificarse como "violation".
# Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
KNOWN_LEGACY_TABLES: frozenset[str] = frozenset({
    "session_tokens",     # → canónica: sys_session_tokens  (HU 8.10)
    "position_metadata",  # → canónica: sys_position_metadata (HU 8.10)
})

# Tablas internas de SQLite — nunca son violations de negocio.
# sqlite_sequence aparece cuando alguna tabla usa AUTOINCREMENT.
_SQLITE_INTERNAL_TABLES: frozenset[str] = frozenset({
    "sqlite_sequence",
    "sqlite_stat1",
    "sqlite_stat2",
    "sqlite_stat3",
    "sqlite_stat4",
})


def classify_tables(table_names: List[str]) -> Dict[str, List[str]]:
    """
    Clasifica una lista de nombres de tablas SQLite en tres categorías SRE:

    - canonical       : tienen prefijo sys_  o usr_  (conforme a SSOT)
    - legacy_compatible: legacy conocidas con plan de migración (sin prefijo, permitidas transitoriamente)
    - violations      : sin prefijo y sin plan registrado → requieren remediación

    Args:
        table_names: Lista de nombres de tablas (e.g. de sqlite_master)

    Returns:
        Dict con listas separadas por categoría.
    """
    canonical: List[str] = []
    legacy_compatible: List[str] = []
    violations: List[str] = []

    for table in table_names:
        if table in _SQLITE_INTERNAL_TABLES:
            # SQLite internals are invisible to SRE classification — skip silently.
            continue
        if table.startswith("sys_") or table.startswith("usr_"):
            canonical.append(table)
        elif table in KNOWN_LEGACY_TABLES:
            legacy_compatible.append(table)
        else:
            violations.append(table)

    return {
        "canonical": canonical,
        "legacy_compatible": legacy_compatible,
        "violations": violations,
    }


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
        all_tables = [row["name"] for row in cursor.fetchall()]
        snapshot["active_tables"] = all_tables

        # 1.1 CLASIFICACIÓN SRE — canonical / legacy_compatible / violations
        # Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
        snapshot["table_classification"] = classify_tables(all_tables)
        
        # 2. ÚLTIMOS ESTADOS DEL SISTEMA (sys_config)
        # Verificamos si la tabla existe antes de consultar para evitar crash
        if "sys_config" in snapshot["active_tables"]:
            cursor.execute("SELECT key, value, updated_at FROM sys_config ORDER BY updated_at DESC LIMIT 10")
            snapshot["sys_config_tail"] = [dict(row) for row in cursor.fetchall()]
        
        # 3. EVIDENCIA CANÓNICA OEM (sys_audit_logs, UTC)
        if "sys_audit_logs" in snapshot["active_tables"]:
            cursor.execute(
                """
                SELECT timestamp, action, resource, status, reason, trace_id
                FROM sys_audit_logs
                WHERE action IN ('HEARTBEAT', 'SCAN_BACKPRESSURE', 'PHASE_TIMEOUT')
                ORDER BY timestamp DESC
                LIMIT 30
                """
            )
            recent_rows = [dict(row) for row in cursor.fetchall()]
            latest_by_component = {}
            for row in recent_rows:
                component = row.get("resource") or "unknown"
                if component not in latest_by_component:
                    latest_by_component[component] = row

            snapshot["audit_source"] = "sys_audit_logs_canonical_utc"
            snapshot["recent_audit"] = recent_rows[:10]
            snapshot["component_evidence"] = latest_by_component

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