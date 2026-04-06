# -*- coding: utf-8 -*-
"""
EMERGENCY STOP - Aethelgard System
===================================
Detiene TODOS los procesos del sistema de forma segura.
Limpia los bloqueos residuales (WAL) en las bases de datos SQLite.

Mata exclusivamente procesos de Aethelgard identificados por cmdline,
sin afectar otros procesos Python del sistema.

Pasos:
1. Matar procesos start.py + uvicorn core_brain.server (por cmdline)
2. Matar cualquier proceso en puerto 8000 que pertenezca al proyecto
3. Limpiar lockfile singleton (data_vault/aethelgard.lock)
4. Limpiar cache Python (.pyc / __pycache__)
5. Liberar DB Locks forzando WAL Checkpoint (TRUNCATE)

Usage:
    python stop.py
"""

import sys
import os
import shutil
import sqlite3
from pathlib import Path

# Force UTF-8 output on Windows to avoid encoding errors with accented chars
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

LOCK_PATH = project_root / "data_vault" / "aethelgard.lock"
PROJECT_MARKER = str(project_root).replace("\\", "/")  # path usado como firma de proceso


def _kill_aethelgard_processes() -> int:
    """
    Mata procesos start.py y uvicorn pertenecientes a este proyecto.
    Identifica por cmdline (contiene la ruta del proyecto), no por nombre genérico.
    Usa psutil para compatibilidad cross-platform y sin depender de wmic/taskkill.
    """
    import psutil

    killed = []
    project_lower = PROJECT_MARKER.lower()

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
            cmd_str = " ".join(cmdline).replace("\\", "/").lower()

            is_python = "python" in (proc.info["name"] or "").lower()
            is_aethelgard = project_lower in cmd_str
            is_relevant = any(k in cmd_str for k in ("start.py", "uvicorn", "core_brain.server"))

            if is_python and is_aethelgard and is_relevant:
                proc.kill()
                killed.append((proc.pid, " ".join(cmdline)[:100]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    for pid, cmd in killed:
        print(f"  [OK] PID {pid} detenido: {cmd}")

    return len(killed)


def _kill_port_8000() -> int:
    """
    Mata cualquier proceso del proyecto que tenga el puerto 8000 abierto.
    Fallback por si uvicorn no fue detectado por cmdline.
    """
    import psutil

    killed = []
    project_lower = PROJECT_MARKER.lower()

    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr and conn.laddr.port == 8000 and conn.pid:
            try:
                proc = psutil.Process(conn.pid)
                cmd_str = " ".join(proc.cmdline()).replace("\\", "/").lower()
                if project_lower in cmd_str:
                    proc.kill()
                    killed.append(conn.pid)
                    print(f"  [OK] PID {conn.pid} (puerto 8000) detenido")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return len(killed)


def _clean_lockfile() -> None:
    """Elimina el lockfile singleton para permitir reinicios limpios."""
    if LOCK_PATH.exists():
        try:
            pid = LOCK_PATH.read_text().strip()
            LOCK_PATH.unlink()
            print(f"  [OK] Lockfile eliminado (contenia PID {pid})")
        except Exception as e:
            print(f"  [WARN]  No se pudo eliminar lockfile: {e}")
    else:
        print("  [INFO]  Sin lockfile activo")


def _clean_pycache() -> int:
    """Elimina .pyc y __pycache__ del proyecto (excluye venv)."""
    count = 0
    for item in project_root.rglob("*.pyc"):
        if "venv" not in item.parts:
            try:
                item.unlink()
                count += 1
            except Exception:
                pass
    for item in project_root.rglob("__pycache__"):
        if "venv" not in item.parts:
            try:
                shutil.rmtree(item)
                count += 1
            except Exception:
                pass
    return count

def _clean_db_locks() -> int:
    """
    Busca todas las bases de datos de Aethelgard (Global y Tenants)
    y fuerza un checkpoint del WAL para liberar locks colgados por procesos asesinados.
    """
    cleaned = 0
    for db_path in project_root.rglob("aethelgard.db"):
        try:
            # Timeout corto: si está bloqueada por otro proceso legítimo fallará rápido
            conn = sqlite3.connect(db_path, timeout=3.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
            cleaned += 1
        except Exception as e:
            print(f"  [WARN] No se pudo limpiar DB lock en {db_path.parent.name}/{db_path.name}: {e}")
            
    return cleaned

def main() -> None:
    print("\n" + "=" * 70)
    print("  EMERGENCY STOP - AETHELGARD SYSTEM")
    print("=" * 70)

    try:
        import psutil
    except ImportError:
        print("[ERROR] psutil no disponible. Instalar con: pip install psutil")
        sys.exit(1)

    total_killed = 0

    print("\n[>] Deteniendo procesos Aethelgard (start.py / uvicorn)...")
    total_killed += _kill_aethelgard_processes()

    print("\n[>] Verificando puerto 8000...")
    total_killed += _kill_port_8000()

    print("\n[>] Limpiando lockfile...")
    _clean_lockfile()

    print("\n[>] Liberando DB Locks (SQLite WAL Checkpoints)...")
    dbs_cleaned = _clean_db_locks()
    if dbs_cleaned > 0:
        print(f"  [OK] {dbs_cleaned} base(s) de datos sincronizada(s) y liberada(s)")
    else:
        print("  [INFO] Sin bases de datos que requieran limpieza")

    print("\n[>] Limpiando cache Python...")
    cache_count = _clean_pycache()
    if cache_count:
        print(f"  [OK] {cache_count} archivo(s)/directorio(s) eliminados")
    else:
        print("  [INFO]  Sin cache que limpiar")

    print("\n" + "=" * 70)
    if total_killed > 0:
        print(f"[OK] SISTEMA DETENIDO: {total_killed} proceso(s) terminado(s)")
    else:
        print("[INFO]  No se encontraron procesos activos del sistema")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
