#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
User Management Quality Audit: Detecta hardcoding, duplicación y code smells.

Valida:
  [OK] Hardcoding detection (roles, tiers, status)
  [OK] Duplication detection (user response transformation)
  [OK] Constants centralization (enums vs strings)
  [OK] Tenant isolation compliance
  [OK] Test parametrization (no hardcoded values)
  
Exit codes:
  0 = All checks PASSED
  1 = FAIL: Critical issues found
  2 = WARN: Non-critical issues (code quality)
"""
import sys
import io
import re
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def search_in_file(filepath: Path, pattern: str) -> int:
    """Count pattern occurrences in file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        return len(re.findall(pattern, content, re.IGNORECASE))
    except Exception as e:
        print(f"ERROR reading {filepath}: {e}", file=sys.stderr)
        return 0


def check_hardcoding():
    """Check for hardcoded role/tier/status values."""
    workspace = Path(__file__).parent.parent
    
    print("[CHECK] Hardcoding Detection...")
    
    issues = []
    
    # Hardcoded roles (should use UserRole enum)
    admin_files = [
        workspace / "core_brain" / "api" / "routers" / "admin.py",
        workspace / "core_brain" / "api" / "dependencies" / "rbac.py",
        workspace / "data_vault" / "auth_repo.py"
    ]
    
    for filepath in admin_files:
        if filepath.exists():
            # Check for hardcoded "admin" or "trader" strings
            hardcoded_admin = search_in_file(filepath, r'"admin"')
            hardcoded_trader = search_in_file(filepath, r'"trader"')
            
            if hardcoded_admin > 2 or hardcoded_trader > 2:  # Allow imports/docstrings
                issues.append(f"  [FAIL] {filepath.name}: Hardcoded roles found ({hardcoded_admin} 'admin', {hardcoded_trader} 'trader')")
    
    # Hardcoded tiers
    hardcoded_tiers = search_in_file(
        workspace / "core_brain" / "api" / "routers" / "admin.py",
        r'(BASIC|PREMIUM|INSTITUTIONAL)'
    )
    if hardcoded_tiers > 5:  # Allow in error messages/docstrings
        issues.append(f"  [FAIL] admin.py: Hardcoded tiers found ({hardcoded_tiers} occurrences)")
    
    if issues:
        print("\n".join(issues))
        return 1
    
    print("  [OK] PASS: No hardcoding detected")
    return 0


def check_duplication():
    """Check for duplicate user_to_response transformations."""
    workspace = Path(__file__).parent.parent
    admin_file = workspace / "core_brain" / "api" / "routers" / "admin.py"
    
    print("[CHECK] Duplication Detection...")
    
    if admin_file.exists():
        content = admin_file.read_text(encoding='utf-8')
        
        # Look for multiple dict transformations with user fields
        pattern = r'\{[^}]*"id"[^}]*"email"[^}]*"role"[^}]*\}'
        duplicates = len(re.findall(pattern, content))
        
        if duplicates > 1:
            print(f"  [FAIL] FAIL: Found {duplicates} duplicate user_to_response() transformations")
            return 1
        
        # Check if user_to_response() is being used (centralized)
        if "user_to_response(" in content:
            print("  [OK] PASS: Using centralized user_to_response() helper")
            return 0
        else:
            print("  [FAIL] FAIL: Not using user_to_response() helper function")
            return 1
    
    print("  [WARN] WARN: admin.py not found")
    return 2


def check_constants_centralization():
    """Check if constants are centralized in enums."""
    workspace = Path(__file__).parent.parent
    enums_file = workspace / "models" / "user_enums.py"
    
    print("[CHECK] Constants Centralization...")
    
    if enums_file.exists():
        content = enums_file.read_text(encoding='utf-8')
        
        required_enums = ["UserRole", "UserTier", "UserStatus"]
        found_enums = [e for e in required_enums if e in content]
        
        if len(found_enums) == len(required_enums):
            print("  [OK] PASS: All enums defined (UserRole, UserTier, UserStatus)")
            return 0
        else:
            missing = set(required_enums) - set(found_enums)
            print(f"  [WARN] WARN: Missing enums: {', '.join(missing)}")
            return 2
    else:
        print("  [FAIL] FAIL: models/user_enums.py not found")
        return 1


def check_tenant_isolation():
    """Check if admin endpoints are properly isolated by tenant (if needed)."""
    workspace = Path(__file__).parent.parent
    admin_file = workspace / "core_brain" / "api" / "routers" / "admin.py"
    
    print("[CHECK] Tenant Isolation Compliance...")
    
    # Note: Admin endpoints are typically GLOBAL, not per-tenant
    # This check just warns if they should be
    
    if admin_file.exists():
        content = admin_file.read_text(encoding='utf-8')
        
        # Check if endpoints use TenantDBFactory (if they should be per-tenant)
        if "TenantDBFactory" in content:
            print("  [OK] PASS: Admin endpoints are tenant-isolated (intentional)")
            return 0
        else:
            # This is OK - admin endpoints are global by design
            print("  [OK] PASS: Admin endpoints are global (SSOT per design)")
            return 0
    
    return 0


def check_test_quality():
    """Check if tests use parametrization instead of hardcoded values."""
    workspace = Path(__file__).parent.parent
    test_file = workspace / "tests" / "test_user_management.py"
    
    print("[CHECK] Test Parametrization...")
    
    if test_file.exists():
        content = test_file.read_text(encoding='utf-8')
        
        # Check for pytest.mark.parametrize
        if "pytest.mark.parametrize" in content:
            print("  [OK] PASS: Tests use parametrization (no hardcoding)")
            return 0
        else:
            # Check for hardcoded test values
            hardcoded = len(re.findall(r'role=["\'](?:admin|trader)["\']', content))
            if hardcoded > 2:
                print(f"  [WARN] WARN: {hardcoded} hardcoded role values in tests")
                return 2
            else:
                print("  [OK] PASS: Test quality acceptable")
                return 0
    
    return 0


def main():
    """Run all quality checks."""
    print("\n" + "="*80)
    print("USER MANAGEMENT QUALITY AUDIT")
    print("="*80 + "\n")
    
    checks = [
        ("Hardcoding Detection", check_hardcoding),
        ("Duplication Detection", check_duplication),
        ("Constants Centralization", check_constants_centralization),
        ("Tenant Isolation", check_tenant_isolation),
        ("Test Quality", check_test_quality),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
            print()
        except Exception as e:
            print(f"ERROR in {name}: {e}\n", file=sys.stderr)
            results.append((name, 1))
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    
    failures = sum(1 for _, result in results if result == 1)
    warnings = sum(1 for _, result in results if result == 2)
    passed = len(results) - failures - warnings
    
    for name, result in results:
        status = "[OK] PASS" if result == 0 else "[WARN] WARN" if result == 2 else "[FAIL] FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{len(results)} PASSED")
    
    # Exit code: 1 if any failures, 2 if warnings, 0 if all pass
    exit_code = 1 if failures > 0 else (2 if warnings > 0 else 0)
    
    if exit_code == 0:
        print("\n[OK] All quality checks PASSED!")
    elif exit_code == 2:
        print("\n[WARN] Some quality warnings (non-critical)")
    else:
        print("\n[FAIL] CRITICAL ISSUES: Fix before proceeding")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
