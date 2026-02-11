#!/usr/bin/env python3
"""
FASE 1 Validation Runner
Ejecuta tests y validate_all.py de forma autónoma
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

def run_command(cmd, description):
    """Ejecuta comando y captura output"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}\n")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        print(f"\nExit Code: {result.returncode}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT - Command took too long")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("="*60)
    print("FASE 1 VALIDATION - Position Manager")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60)
    
    # Change to repo directory
    repo_dir = Path(__file__).parent
    print(f"\nWorking Directory: {repo_dir}\n")
    
    results = {}
    
    # 1. Git Status
    results['git_status'] = run_command(
        "git status --short",
        "[1/3] Git Status"
    )
    
    # 2. Run Tests
    results['pytest'] = run_command(
        "python -m pytest tests/test_position_manager_regime.py -v --tb=short",
        "[2/3] Running pytest - Position Manager Tests"
    )
    
    # 3. Run validate_all
    results['validate_all'] = run_command(
        "python scripts/validate_all.py",
        "[3/3] Running validate_all.py - Architecture Validation"
    )
    
    # Summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    
    all_passed = True
    for key, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{key:20s}: {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("✅ ALL VALIDATIONS PASSED - FASE 1 READY")
        return 0
    else:
        print("❌ SOME VALIDATIONS FAILED - REVIEW OUTPUT ABOVE")
        return 1

if __name__ == "__main__":
    sys.exit(main())
