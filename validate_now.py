import subprocess
import sys
import os

os.chdir(r'C:\Users\Jose Herrera\Documents\Proyectos\Aethelgard')

print("="*60)
print("FASE 1 VALIDATION - AUTONOMOUS EXECUTION")
print("="*60)

# Test imports
try:
    print("\n[VALIDATING IMPORTS...]")
    sys.path.insert(0, '.')
    from core_brain.position_manager import PositionManager
    print("✅ PositionManager imports OK")
except Exception as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

# Run pytest
print("\n[RUNNING TESTS...]")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_position_manager_regime.py", "-v"],
    capture_output=True,
    text=True
)
print(result.stdout)
print(result.stderr)
test_passed = result.returncode == 0

# Run validate_all
print("\n[RUNNING VALIDATE_ALL...]")
result = subprocess.run(
    [sys.executable, "scripts/validate_all.py"],
    capture_output=True,
    text=True
)
print(result.stdout)
print(result.stderr)
validate_passed = result.returncode == 0

# Summary
print("\n" + "="*60)
print("RESULTS:")
print(f"Tests: {'✅ PASS' if test_passed else '❌ FAIL'}")
print(f"Validate_all: {'✅ PASS' if validate_passed else '❌ FAIL'}")
print("="*60)

sys.exit(0 if (test_passed and validate_passed) else 1)
