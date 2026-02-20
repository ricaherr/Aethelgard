#!/usr/bin/env python
"""
[OK] COMPLETE VALIDATION SUITE - Aethelgard
Ejecuta: Architecture Audit + QA Guard + Code Quality Analysis
"""
import subprocess
import sys
from pathlib import Path

def run_command(cmd: str, description: str) -> int:
    """Run command and report result"""
    print(f"\n{'='*80}")
    print(f"[AUDIT] {description}")
    print(f"{'='*80}")
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print(f"[OK] {description} - PASSED")
        return 0
    else:
        print(f"[ERROR] {description} - FAILED")
        return 1

def main():
    workspace = Path(__file__).parent.parent
    
    print("\n" + "="*80)
    print("[START] AETHELGARD COMPLETE VALIDATION SUITE")
    print("="*80)
    
    results = {}
    
    # 1. Architecture Audit
    results['Architecture'] = run_command(
        f"cd {workspace} && python scripts/utilities/architecture_audit.py",
        "Architecture Audit (Duplicados + Context Manager)"
    )
    
    # 2. QA Guard
    results['QA Guard'] = run_command(
        f"cd {workspace} && python scripts/qa_guard.py",
        "QA Guard (Sintaxis + Tipos + Style)"
    )
    
    # 3. Code Quality
    results['Code Quality'] = run_command(
        f"cd {workspace} && python scripts/code_quality_analyzer.py",
        "Code Quality (Copy-Paste + Complejidad)"
    )
    
    # 4. UI QA Guard (TS/React)
    results['UI Quality'] = run_command(
        f"cd {workspace} && python scripts/ui_qa_guard.py",
        "UI QA Guard (TypeScript + Build Validation)"
    )
    
    # 4.5 Manifesto Enforcer (DI + SSOT Rules)
    results['Manifesto Enforcer'] = run_command(
        f"cd {workspace} && python scripts/manifesto_enforcer.py",
        "Manifesto Enforcer (Reglas Arquitectónicas DI & SSOT)"
    )

    # 4.8 Pattern Enforcer (Signature & Argument Safety)
    results['Pattern Enforcer'] = run_command(
        f"cd {workspace} && python scripts/enforce_patterns.py",
        "Pattern Enforcer (AST Signature Validation)"
    )
    
    # 5. Critical Tests (Deduplication + Risk)
    results['Tests'] = run_command(
        f"cd {workspace} && python -m pytest tests/test_signal_deduplication.py tests/test_dynamic_deduplication.py tests/test_risk_manager.py -q",
        "Critical Tests (23 tests de Deduplicación + Risk Manager)"
    )
    
    # 6. Integration Tests (No Mocks - Real DB) - 100% CONFIABLE
    results['Integration'] = run_command(
        f"cd {workspace} && python -m pytest tests/test_executor_metadata_integration.py -q",
        "Integration Tests (Executor + StorageManager REAL)"
    )
    
    # Summary
    print("\n" + "="*80)
    print("[STATS] VALIDATION SUMMARY")
    print("="*80)
    
    for tool, result in results.items():
        status = "[OK] PASS" if result == 0 else "[ERROR] FAIL"
        print(f"{tool:.<40} {status}")
    
    total_failures = sum(1 for r in results.values() if r != 0)
    
    if total_failures == 0:
        print("\n" + "="*80)
        print("[SUCCESS] ALL VALIDATIONS PASSED - READY FOR DEPLOYMENT")
        print("="*80)
        return 0
    else:
        print(f"\n[ERROR] {total_failures} validation(s) failed - Review above for details")
        return 1

if __name__ == "__main__":
    sys.exit(main())
