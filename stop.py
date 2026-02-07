"""
EMERGENCY STOP - Aethelgard System
===================================
Detiene TODOS los procesos y hilos del sistema de forma INMEDIATA.

Mata:
1. Procesos de Python ejecutando start.py/main.py
2. Procesos de Streamlit (Dashboard)
3. Procesos de Uvicorn (API Server)
4. Conexiones MT5 activas
5. Todos los hilos daemon (Scanner, Monitor, Tuner, etc.)

Usage:
    python scripts/emergency_stop.py
    
WARNING: Este comando es destructivo. Mata procesos sin esperar graceful shutdown.
"""

import sys
import subprocess
import time
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
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
    Intenta cerrar conexiones MT5 de forma limpia.
    
    Returns:
        True si se cerraron exitosamente
    """
    try:
        from connectors.mt5_connector import MT5_AVAILABLE
        
        if not MT5_AVAILABLE:
            return False
        
        import MetaTrader5 as mt5
        
        # Intentar cerrar conexión
        if mt5.initialize():
            mt5.shutdown()
            print("✅ Conexión MT5 cerrada")
            return True
        
        return False
        
    except Exception as e:
        print(f"⚠️  No se pudo cerrar MT5: {e}")
        return False


def main():
    """Ejecuta parada de emergencia."""
    print("\n" + "=" * 70)
    print("  🚨 EMERGENCY STOP - AETHELGARD SYSTEM")
    print("=" * 70)
    print()
    
    total_killed = 0
    
    # Step 1: Intentar cerrar MT5 de forma limpia
    print("🔌 Cerrando conexiones MT5...")
    close_mt5_connections()
    
    # Step 2: Matar procesos por puerto (Dashboard, API)
    print("\n🔴 Matando procesos por puerto...")
    ports_to_kill = [
        8000,  # API Server (Uvicorn)
        8503,  # Dashboard Streamlit (old)
        8504,  # Dashboard Streamlit (new)
    ]
    
    total_killed += kill_processes_by_port(ports_to_kill)
    
    # Step 3: Matar procesos por nombre
    print("\n🔴 Matando procesos por nombre...")
    processes_to_kill = [
        "streamlit.exe",
        "uvicorn.exe",
    ]
    
    total_killed += kill_processes_by_name(processes_to_kill)
    
    # Step 4: Matar procesos de Python ejecutando start.py o main.py
    print("\n🔴 Buscando procesos de Aethelgard (start.py/main.py)...")
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
                
                # Buscar start.py o main.py en el comando
                if "start.py" in line or "main.py" in line or "Aethelgard" in line:
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
    
    # Step 5: Resumen
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
