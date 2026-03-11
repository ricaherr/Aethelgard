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

    # ═══════════════════════════════════════════════════════════════════════════
    # AUDIT STRUCTURE BY DOMAIN
    # ═══════════════════════════════════════════════════════════════════════════
    # Domain 01: IDENTITY_SECURITY
    domain_01_identity = [
        run_audit_module("Architecture", ["python", "scripts/utilities/architecture_audit.py"], workspace),
        run_audit_module("Tenant Isolation Scanner", ["python", "scripts/tenant_isolation_audit.py"], workspace),
        run_audit_module("Credentials & Seeds", ["python", "scripts/utilities/credentials_seeds_audit.py"], workspace),
        run_audit_module("User Management Quality", ["python", "scripts/user_management_quality_audit.py"], workspace),
    ]
    
    # Domain 02-03: CONTEXT_INTEL & ALPHA_ENGINE (Core Signal Generation)
    domain_02_03_signal_gen = [
        run_audit_module("Core Tests", ["python", "-m", "pytest", "tests/test_signal_deduplication.py", "tests/test_risk_manager.py", "-q"], workspace),
    ]
    
    # Domain 04: RISK_GOVERNANCE
    domain_04_risk = [
        run_audit_module("FASE B: NewsValidator", ["python", "-m", "pytest", "tests/test_news_sanitizer.py", "tests/test_economic_calendar_consolidation.py", "-q"], workspace),
    ]
    
    # Domain 05: UNIVERSAL_EXECUTION
    domain_05_execution = [
        run_audit_module("SPRINT S007", ["python", "-m", "pytest", "tests/test_strategy_ranker.py", "tests/test_strategy_engine_factory_phase3.py", "tests/test_main_orchestrator_phase4.py", "tests/test_circuit_breaker_phase5.py", "tests/test_executor_circuit_breaker_integration.py", "tests/test_qa_phase_integration.py", "tests/test_strategy_monitor_service.py", "tests/test_strategy_ws.py", "tests/test_degradation_alert_service.py", "-q"], workspace),
        run_audit_module("Integration", ["python", "-m", "pytest", "tests/test_executor_metadata_integration.py", "-q"], workspace),
    ]
    
    # INTELLIGENT SIGNAL DEDUPLICATION (Multi-module system)
    # ├─ Module 1: Dynamic Windows + Storage (Phase 1-2)
    # ├─ Module 2: Autonomous Learning (Phase 3)
    # ├─ Module 3: Signal Quality Validation (THIS - Signal Quality Scoring)
    intelligent_dedup = [
        run_audit_module("ISD: Signal Quality Validation", ["python", "-m", "pytest", "tests/test_signal_quality_scorer_phase4.py", "-v"], workspace),
    ]
    
    # Domain 08: DATA_SOVEREIGNTY
    domain_08_data = [
        run_audit_module("System DB", ["python", "scripts/utilities/verify_sync_fidelity.py"], workspace),
        run_audit_module("DB Integrity", ["python", "scripts/utilities/db_uniqueness_audit.py"], workspace),
    ]
    
    # Domain 09: INSTITUTIONAL_UI
    domain_09_ui = [
        run_audit_module("UI Quality", ["python", "scripts/utilities/ui_health_check.py"], workspace),
        run_audit_module("UI Build", ["npm.cmd", "run", "build"], workspace / "ui"),
    ]
    
    # CROSS-CUTTING CONCERNS (Governance, Quality, Infrastructure)
    cross_cutting = [
        run_audit_module("QA Guard", ["python", "scripts/qa_guard.py"], workspace),
        run_audit_module("Code Quality", ["python", "scripts/code_quality_analyzer.py"], workspace),
        run_audit_module("Manifesto", ["python", "scripts/manifesto_enforcer.py"], workspace),
        run_audit_module("Patterns", ["python", "scripts/enforce_patterns.py"], workspace),
        run_audit_module("Duplicate Methods", ["python", "scripts/detect_duplicate_methods.py"], workspace),
        run_audit_module("Interface Contracts", ["python", "scripts/validate_interface_contracts.py"], workspace),
        run_audit_module("Connectivity", ["python", "scripts/utilities/check_connectivity_health.py"], workspace),
        run_audit_module("Documentation", ["python", "scripts/utilities/documentation_audit.py"], workspace),
    ]
    
    # SPECIALIZED DOMAINS
    specialized = [
        run_audit_module("PHASE 8: Economic Veto", ["python", "scripts/utilities/economic_veto_audit.py"], workspace),
        run_audit_module("FASE 5: Tenant-Aware", ["python", "-m", "pytest", "tests/test_fase5_tenant_aware_orchestrator.py", "tests/test_fase5_mixin_tenant_aware.py", "-v"], workspace),
        run_audit_module("Tenant Security", ["python", "-m", "pytest", "tests/test_tenant_isolation_edge_history.py", "-q"], workspace),
        run_audit_module("Seeds Tests", ["python", "-m", "pytest", "tests/test_seed_demo_data.py", "-q"], workspace),
    ]
    
    # AGGREGATE ALL AUDIT TASKS
    audit_tasks = (
        cross_cutting +      # First: governance & quality baseline
        domain_01_identity +
        domain_02_03_signal_gen +
        domain_04_risk +
        domain_05_execution +
        intelligent_dedup +
        domain_08_data +
        domain_09_ui +
        specialized
    )

    # Ejecución paralela masiva
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} Desplegando agentes de integridad en paralelo...")
    results = await asyncio.gather(*audit_tasks)
    
    total_duration = time.monotonic() - start_total
    
    # Interfaz de resumen sofisticada, categorizada por DOMINIO
    print(f"\n{Colors.BOLD}{Colors.CYAN}AETHELGARD: DOMAIN-BY-DOMAIN INTEGRITY REPORT{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*100}{Colors.RESET}")
    
    # Categorizar resultados por dominio
    domain_results = {
        "CROSS-CUTTING (Governance & Quality)": [],
        "DOMAIN 01: Identity & Security": [],
        "DOMAIN 02-03: Context Intelligence & Signal Generation": [],
        "DOMAIN 04: Risk Governance": [],
        "DOMAIN 05: Universal Execution": [],
        "INTELLIGENT SIGNAL DEDUP: Quality Validation": [],
        "DOMAIN 08: Data Sovereignty": [],
        "DOMAIN 09: Institutional UI": [],
        "SPECIALIZED (Multidomain Integration)": [],
    }
    
    # Mapear resultados a dominios
    for res in results:
        if res['name'] in ["Architecture", "QA Guard", "Code Quality", "Manifesto", "Patterns", "Duplicate Methods", "Interface Contracts", "Documentation"]:
            domain_results["CROSS-CUTTING (Governance & Quality)"].append(res)
        elif res['name'] in ["Tenant Isolation Scanner", "Credentials & Seeds", "User Management Quality"]:
            domain_results["DOMAIN 01: Identity & Security"].append(res)
        elif res['name'] == "Core Tests":
            domain_results["DOMAIN 02-03: Context Intelligence & Signal Generation"].append(res)
        elif res['name'] == "FASE B: NewsValidator":
            domain_results["DOMAIN 04: Risk Governance"].append(res)
        elif res['name'] in ["SPRINT S007", "Integration"]:
            domain_results["DOMAIN 05: Universal Execution"].append(res)
        elif res['name'] == "ISD: Signal Quality Validation":
            domain_results["INTELLIGENT SIGNAL DEDUP: Quality Validation"].append(res)
        elif res['name'] in ["System DB", "DB Integrity"]:
            domain_results["DOMAIN 08: Data Sovereignty"].append(res)
        elif res['name'] in ["UI Quality", "UI Build"]:
            domain_results["DOMAIN 09: Institutional UI"].append(res)
        else:
            domain_results["SPECIALIZED (Multidomain Integration)"].append(res)
    
    failures = 0
    passed = 0
    for domain, tests in domain_results.items():
        if not tests:
            continue
        domain_pass = sum(1 for t in tests if t["success"])
        domain_total = len(tests)
        domain_color = Colors.GREEN if domain_pass == domain_total else Colors.GOLD if domain_pass > 0 else Colors.RED
        if domain_pass < domain_total: failures += domain_total - domain_pass
        passed += domain_pass
        
        print(f"\n{Colors.BOLD}{domain_color}[{domain_pass}/{domain_total}] {domain}{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*100}{Colors.RESET}")
        for test in tests:
            t_color = Colors.GREEN if test["success"] else Colors.RED
            t_status = "[PASS]" if test["success"] else "[FAIL]"
            print(f"  {t_color}{test['name']:<40} {t_status:<10}{Colors.RESET} [{test['duration']:.2f}s]")
    
    print(f"\n{Colors.BLUE}{'='*100}{Colors.RESET}")
    print(f"{Colors.BOLD}TOTAL EXECUTION TIME: {total_duration:.2f}s | TOTAL: {passed}/{len(results)} PASSED{Colors.RESET}")

    if failures == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*100}")
        print(f"[SUCCESS] SYSTEM INTEGRITY GUARANTEED - ALL DOMAINS COMPLIANT - READY FOR EXECUTION")
        print(f"{'='*100}{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}{'='*100}")
        print(f"[FAIL] {failures} TEST(S) FAILED - REVIEW LOGS AND FIX BEFORE DEPLOYING")
        print(f"{'='*100}{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
