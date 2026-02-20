"""
EMERGENCY STOP - Aethelgard System
===================================
Detiene TODOS los procesos y hilos del sistema de forma INMEDIATA.

Mata:
1. Procesos de Python ejecutando start.py (incluye FastAPI/Uvicorn integrado)
2. Procesos en puerto 8000 (FastAPI + React UI)
3. Conexiones MT5 activas
4. Todos los hilos daemon (Scanner, Monitor, Tuner, etc.)

Architecture (2026):
- FastAPI (uvicorn) ejecutado como módulo Python por start.py
- React UI servido por FastAPI desde ui/dist
- NO usa Streamlit (eliminado en favor de React)

Usage:
    python stop.py
    
WARNING: Este comando es destructivo. Mata procesos sin esperar graceful shutdown.
"""

import sys
import subprocess
import time
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def kill_processes_by_name(process_names: list) -> int:
    """
    Mata procesos por nombre (Windows).
    
    Args:
        process_names: Lista de nombres de procesos a matar
        
    Returns:
        Número de procesos matados
    """
    killed_count = 0
    
    for proc_name in process_names:
        try:
            # Intentar matar el proceso
            result = subprocess.run(
                ["taskkill", "/F", "/IM", proc_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ Proceso {proc_name} detenido")
                killed_count += 1
            elif "not found" not in result.stderr.lower():
                # Si hubo otro error que no sea "proceso no encontrado"
                print(f"⚠️  {proc_name}: {result.stderr.strip()}")
                
        except Exception as e:
            print(f"❌ Error matando {proc_name}: {e}")
    
    return killed_count


def kill_processes_by_port(ports: list) -> int:
    """
    Mata procesos que ocupan puertos específicos (Windows).
    
    Args:
        ports: Lista de puertos (8000, 8503, 8504, etc.)
        
    Returns:
        Número de procesos matados
    """
    killed_count = 0
    
    for port in ports:
        try:
            # Encontrar PID del proceso que usa el puerto
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                continue
            
            # Parsear salida de netstat
            for line in result.stdout.split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        
                        # Matar el proceso por PID
                        kill_result = subprocess.run(
                            ["taskkill", "/PID", pid, "/F"],
                            capture_output=True,
                            text=True
                        )
                        
                        if kill_result.returncode == 0:
                            print(f"✅ Proceso en puerto {port} (PID {pid}) detenido")
                            killed_count += 1
                        else:
                            print(f"⚠️  No se pudo matar PID {pid}: {kill_result.stderr.strip()}")
                        
                        break  # Solo un proceso por puerto
                        
        except Exception as e:
            print(f"❌ Error matando proceso en puerto {port}: {e}")
    
    return killed_count


def close_mt5_connections() -> bool:
    """
    Intenta cerrar conexiones MT5 de forma limpia usando el conector.
    
    Returns:
        True si se cerraron exitosamente
    """
    try:
        from connectors.mt5_connector import MT5Connector
        return MT5Connector.shutdown_broker()
        
    except Exception as e:
        print(f"⚠️  No se pudo cerrar MT5: {e}")
        return False


def main() -> None:
    """Ejecuta parada de emergencia."""
    print("\n" + "=" * 70)
    print("  🚨 EMERGENCY STOP - AETHELGARD SYSTEM")
    print("=" * 70)
    print()
    
    total_killed = 0
    
    # Step 1: Intentar cerrar MT5 de forma limpia (ELIMINADO - Causa apertura de terminales inactivas)
    # print("🔌 Cerrando conexiones MT5...")
    # close_mt5_connections()
    
    # Step 2: Matar procesos por puerto (FastAPI + React UI)
    print("\n🔴 Matando procesos por puerto...")
    ports_to_kill = [
        8000,  # FastAPI Server (Uvicorn + React UI)
    ]
    
    total_killed += kill_processes_by_port(ports_to_kill)
    
    # Step 3: Matar procesos de Node (solo si quedó colgado durante desarrollo)
    print("\n🔴 Verificando procesos de Node...")
    processes_to_kill = [
        "node.exe",  # Matar procesos de Node si el build en watch quedó colgado
    ]
    
    total_killed += kill_processes_by_name(processes_to_kill)
    
    # Step 4: Matar procesos Python ejecutando start.py (incluye FastAPI/Uvicorn)
    print("\n🔴 Buscando procesos de Aethelgard (start.py)...")
    try:
        # Listar todos los procesos de Python
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "processid,commandline"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            
            for line in lines[1:]:  # Skip header
                if not line.strip():
                    continue
                
                # Buscar start.py en el comando (incluye uvicorn como módulo)
                if "start.py" in line or "core_brain.server" in line:
                    # Extraer PID (último número en la línea)
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        
                        # Verificar que sea un número
                        try:
                            int(pid)
                            
                            # Matar el proceso
                            kill_result = subprocess.run(
                                ["taskkill", "/PID", pid, "/F"],
                                capture_output=True,
                                text=True
                            )
                            
                            if kill_result.returncode == 0:
                                print(f"✅ Proceso Aethelgard (PID {pid}) detenido")
                                total_killed += 1
                        except ValueError:
                            continue
                            
    except Exception as e:
        print(f"⚠️  Error buscando procesos de Aethelgard: {e}")
    
    # Step 5: Limpiar cache de Python
    print("\n🧹 Limpiando cache de Python (.pyc y __pycache__)...")
    try:
        import shutil
        cache_count = 0
        
        # Eliminar archivos .pyc
        for pyc_file in project_root.rglob("*.pyc"):
            try:
                pyc_file.unlink()
                cache_count += 1
            except Exception as e:
                print(f"⚠️  No se pudo eliminar {pyc_file}: {e}")
        
        # Eliminar directorios __pycache__
        for pycache_dir in project_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache_dir)
                cache_count += 1
            except Exception as e:
                print(f"⚠️  No se pudo eliminar {pycache_dir}: {e}")
        
        if cache_count > 0:
            print(f"✅ Cache limpiado: {cache_count} archivo(s)/directorio(s) eliminados")
        else:
            print("ℹ️  No se encontró cache para limpiar")
            
    except Exception as e:
        print(f"❌ Error limpiando cache: {e}")
    
    # Step 6: Resumen
    print("\n" + "=" * 70)
    if total_killed > 0:
        print(f"✅ SISTEMA DETENIDO: {total_killed} proceso(s) matados")
    else:
        print("ℹ️  No se encontraron procesos activos del sistema")
    print("=" * 70)
    print()
    
    # Nota importante
    print("⚠️  NOTA: Los hilos daemon (Scanner, Monitor) mueren automáticamente")
    print("          cuando el proceso principal termina.")
    print()


if __name__ == "__main__":
    main()
