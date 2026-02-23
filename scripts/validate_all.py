#!/usr/bin/env python
"""
[OK] HIGH-PERFORMANCE PARALLEL AUDITOR - Aethelgard
Evolución profesional: Ejecución paralela + Interfaz sofisticada + Cobertura total
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

import re
from typing import Dict, List, Any, Tuple

# Colores ANSI para terminal profesional
class Colors:
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    GOLD = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def extract_error_detail(stdout: str, stderr: str) -> str:
    """Extrae el detalle técnico más relevante del error (Fichero, Línea, Mensaje)"""
    combined = stderr + "\n" + stdout
    
    # 1. Buscar Tracebacks de Python
    # Patrón: File "path", line line_num, in ...\n ...\n ErrorType: ErrorMessage
    python_traceback = re.search(r'File "(.+?)", line (\d+), in .+?\n(.+?)\n(\w+:.+)', combined, re.DOTALL)
    if python_traceback:
        file, line, context, error = python_traceback.groups()
        return f"{error.strip()} at {Path(file).name}:{line}"

    # 2. Buscar errores de TypeScript/React
    # Patrón: path/file.tsx:10:15 - error TS1234: Message
    ts_error = re.search(r'(.+?\.tsx?):(\d+):(\d+) - error .+?: (.+)', combined)
    if ts_error:
        file, line, col, msg = ts_error.groups()
        return f"{msg.strip()} at {Path(file).name}:{line}"

    # 3. Fallback: buscar la línea que contenga "Error" o "Exception" o "FAIL"
    for line in combined.split('\n'):
        if any(keyword in line.upper() for keyword in ["ERROR", "EXCEPTION", "FAIL", "FATAL"]):
            # Limpiar ruidos típicos de logs (timestamps, niveles)
            clean_line = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - \w+ - ', '', line)
            return clean_line.strip()[:100]

    # 4. Segundo Fallback: primera línea que no sea INFO o WARNING
    for line in stderr.split('\n'):
        if line.strip() and " - INFO - " not in line and " - WARNING - " not in line:
            return line.strip()[:100]

    return "Consistencia de integridad comprometida (Ver logs detallados)."

async def run_audit_module(name: str, cmd_parts: List[str], workspace: Path) -> Dict[str, Any]:
    """Ejecuta un módulo de auditoría de forma asíncrona"""
    start_time = time.monotonic()
    
    # Notificar inicio al backend vía stdout
    print(f"STAGE_START:{name}")
    sys.stdout.flush()
    
    try:
        # Usar el ejecutable de python actual para consistencia
        executable = sys.executable
        
        args = []
        if cmd_parts[0] == "python":
            args = [executable] + cmd_parts[1:]
        else:
            args = cmd_parts

        # Configurar environment con PYTHONPATH para que encuentren los módulos locales
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workspace) + os.pathsep + env.get("PYTHONPATH", "")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
            env=env
        )
        stdout, stderr = await process.communicate()
        duration = time.monotonic() - start_time
        
        # Usar errors='replace' para evitar crashes por codificación de consola en Windows
        decoded_stdout = stdout.decode(errors='replace').strip()
        decoded_stderr = stderr.decode(errors='replace').strip()
        
        success = process.returncode == 0
        
        if not success:
            error_detail = extract_error_detail(decoded_stdout, decoded_stderr)
            # Notificar detalle específico para el backend y la UI
            print(f"DEBUG_FAIL:{name}:{error_detail}")
            
            # Imprimir errores COMPLETOS si falla para debugging en terminal
            print(f"\n{Colors.RED}{'='*80}{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.RED}[FAIL] {name}: {error_detail}{Colors.RESET}")
            print(f"{Colors.RED}{'='*80}{Colors.RESET}")
            if decoded_stderr:
                print(f"{Colors.BOLD}STDERR:{Colors.RESET}\n{decoded_stderr}")
            if decoded_stdout:
                print(f"{Colors.BOLD}STDOUT:{Colors.RESET}\n{decoded_stdout}")
            print(f"{Colors.RED}{'='*80}{Colors.RESET}\n")
            sys.stdout.flush()

        print(f"STAGE_END:{name}:{'OK' if success else 'FAIL'}:{duration:.2f}")
        sys.stdout.flush()
        
        return {
            "name": name,
            "success": success,
            "duration": duration,
            "stdout": decoded_stdout,
            "stderr": decoded_stderr
        }
    except Exception as e:
        duration = time.monotonic() - start_time
        print(f"DEBUG_FAIL:{name}:{str(e)}")
        print(f"STAGE_END:{name}:FAIL:{duration:.2f}")
        sys.stdout.flush()
        return {
            "name": name,
            "success": False,
            "duration": duration,
            "error": str(e)
        }

async def main():
    workspace = Path(__file__).parent.parent
    start_total = time.monotonic()
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}AETHELGARD SYSTEM INTEGRITY AUDIT - PARALLEL EVOLUTION{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}\n")

    # Definición de hilos de validación (Paralelización estratégica)
    # Formato: [ejecutable, script, args...]
    audit_tasks = [
        run_audit_module("Architecture", ["python", "scripts/utilities/architecture_audit.py"], workspace),
        run_audit_module("QA Guard", ["python", "scripts/qa_guard.py"], workspace),
        run_audit_module("Code Quality", ["python", "scripts/code_quality_analyzer.py"], workspace),
        run_audit_module("UI Quality", ["python", "scripts/utilities/ui_health_check.py"], workspace),
        run_audit_module("Manifesto", ["python", "scripts/manifesto_enforcer.py"], workspace),
        run_audit_module("Patterns", ["python", "scripts/enforce_patterns.py"], workspace),
        run_audit_module("Core Tests", ["python", "-m", "pytest", "tests/test_signal_deduplication.py", "tests/test_risk_manager.py", "-q"], workspace),
        run_audit_module("Integration", ["python", "-m", "pytest", "tests/test_executor_metadata_integration.py", "-q"], workspace),
        run_audit_module("Connectivity", ["python", "scripts/utilities/check_connectivity_health.py"], workspace),
        run_audit_module("System DB", ["python", "scripts/utilities/verify_sync_fidelity.py"], workspace),
        run_audit_module("DB Integrity", ["python", "scripts/utilities/db_uniqueness_audit.py"], workspace),
    ]

    # Ejecución paralela masiva
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} Desplegando agentes de integridad en paralelo...")
    results = await asyncio.gather(*audit_tasks)
    
    total_duration = time.monotonic() - start_total
    
    # Interfaz de resumen sofisticada
    print(f"\n{Colors.BOLD}{Colors.CYAN}SYSTEM INTEGRITY MATRIX{Colors.RESET}")
    print(f"{Colors.BLUE}{'-'*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{'MODULO':<30} {'ESTADO':<15} {'DURACION':<15}{Colors.RESET}")
    
    failures = 0
    for res in results:
        status_color = Colors.GREEN if res["success"] else Colors.RED
        status_text = "PASSED" if res["success"] else "FAILED"
        if not res["success"]: failures += 1
        
        print(f"{res['name']:<30} {status_color}{status_text:<15}{Colors.RESET} {res['duration']:.2f}s")

    print(f"{Colors.BLUE}{'-'*80}{Colors.RESET}")
    print(f"{Colors.BOLD}TOTAL TIME: {total_duration:.2f}s{Colors.RESET}")

    if failures == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}================================================================================{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] SYSTEM INTEGRITY GUARANTEED - READY FOR EXECUTION{Colors.RESET}")
        print(f"{Colors.GREEN}{Colors.BOLD}================================================================================{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}[FAIL] {failures} VECTORS COMPROMISED - REVIEW LOGS IMMEDIATELY{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
