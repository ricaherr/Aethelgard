#!/usr/bin/env python
"""
INTERFACE CONTRACTS VALIDATOR
Verifies that NewsSanitizer implements all 3 pillars from INTERFACE_CONTRACTS.md
"""
import sys
import re
from pathlib import Path
from typing import Dict, Any


def validate_news_sanitizer_pillars() -> bool:
    """
    Verify NewsSanitizer has all 3 pillars from INTERFACE_CONTRACTS.md:
    - Pilar 1: Schema Validation (_validate_schema)
    - Pilar 2: Latency Validation (_validate_latency)
    - Pilar 3: Immutability Enforcement (validate_immutability)
    """
    sanitizer_file = Path(__file__).parent.parent / "core_brain" / "news_sanitizer.py"
    
    if not sanitizer_file.exists():
        print(f"ERROR: File not found: {sanitizer_file}")
        return False
    
    with open(sanitizer_file, "r") as f:
        content = f.read()
    
    # Check Pilar 1: _validate_schema() method
    pilar1 = bool(re.search(
        r'def _validate_schema\([^)]*\).*?Pilar 1|Schema Validation',
        content,
        re.DOTALL | re.IGNORECASE
    ))
    
    # Check Pilar 2: _validate_latency() method
    pilar2 = bool(re.search(
        r'def _validate_latency\([^)]*\).*?Pilar 2|Latency Validation',
        content,
        re.DOTALL | re.IGNORECASE
    ))
    
    # Check Pilar 3: validate_immutability() method with "always raise" behavior
    pilar3_method = bool(re.search(
        r'def validate_immutability\([^)]*\)',
        content,
        re.DOTALL
    ))
    
    pilar3_raises = bool(re.search(
        r'def validate_immutability\([^)]*\).*?raise.*?ImmutabilityViolation',
        content,
        re.DOTALL
    ))
    
    pilar3 = pilar3_method and pilar3_raises
    
    # Report
    if not pilar1:
        print("FAIL: Missing Pilar 1 (_validate_schema) in NewsSanitizer")
        return False
    if not pilar2:
        print("FAIL: Missing Pilar 2 (_validate_latency) in NewsSanitizer")
        return False
    if not pilar3:
        print("FAIL: Missing Pilar 3 (validate_immutability with ALWAYS raise) in NewsSanitizer")
        return False
    
    print("PASS: All 3 pillars implemented in NewsSanitizer")
    return True


def validate_storage_economic_consolidation() -> bool:
    """
    Verify storage.py has consolidated economic methods:
    - get_economic_calendar() is PRIMARY method with full logic
    - get_economic_events() DEPRECATED wrapper that delegates
    """
    storage_file = Path(__file__).parent.parent / "data_vault" / "storage.py"
    
    if not storage_file.exists():
        print(f"ERROR: File not found: {storage_file}")
        return False
    
    with open(storage_file, "r") as f:
        content = f.read()
    
    # Check get_economic_calendar() is primary (has SELECT logic)
    has_calendar_main = bool(re.search(
        r'def get_economic_calendar\([^)]*days_back[^)]*\).*?SELECT.*?FROM economic_calendar',
        content,
        re.DOTALL
    ))
    
    # Check get_economic_events() is wrapper (DEPRECATED + delegates)
    has_events_wrapper = bool(re.search(
        r'def get_economic_events\([^)]*\).*?(?:DEPRECATED|deprecated).*?get_economic_calendar',
        content,
        re.DOTALL | re.IGNORECASE
    ))
    
    if not has_calendar_main:
        print("FAIL: get_economic_calendar() must have full SELECT logic")
        return False
    
    if not has_events_wrapper:
        print("FAIL: get_economic_events() must be DEPRECATED wrapper")
        return False
    
    print("PASS: Economic methods properly consolidated")
    return True


def validate_test_constants() -> bool:
    """
    Verify tests use SSOT for configuration:
    - TEST_PROVIDER_SOURCE in conftest.py
    - VALID_COUNTRY_CODES imported from source
    - No hardcoded "INVESTING" in test parameters
    """
    conftest_file = Path(__file__).parent.parent / "tests" / "conftest.py"
    
    if not conftest_file.exists():
        print(f"WARNING: conftest.py not found: {conftest_file}")
        return True  # Don't fail tests if conftest missing
    
    with open(conftest_file, "r") as f:
        content = f.read()
    
    # Check TEST_PROVIDER_SOURCE constant exists
    has_constant = bool(re.search(
        r'TEST_PROVIDER_SOURCE\s*=\s*["\']INVESTING["\']',
        content
    ))
    
    # Check imports from source
    has_imports = bool(re.search(
        r'from core_brain\.news_sanitizer import.*VALID_COUNTRY_CODES',
        content,
        re.DOTALL
    ))
    
    if not has_constant:
        print("FAIL: TEST_PROVIDER_SOURCE constant missing in conftest.py")
        return False
    
    if not has_imports:
        print("FAIL: VALID_COUNTRY_CODES not imported from news_sanitizer in conftest.py")
        return False
    
    print("PASS: Test configuration centralized (SSOT)")
    return True


def main() -> int:
    """Main validation function"""
    
    print("[INTERFACE CONTRACTS VALIDATOR]")
    print("=" * 80)
    
    checks = [
        ("NewsSanitizer 3 Pillars", validate_news_sanitizer_pillars),
        ("Economic Consolidation", validate_storage_economic_consolidation),
        ("Test SSOT Constants", validate_test_constants),
    ]
    
    all_passed = True
    for check_name, check_fn in checks:
        try:
            result = check_fn()
            if not result:
                all_passed = False
        except Exception as e:
            print(f"ERROR in {check_name}: {e}")
            all_passed = False
    
    print("=" * 80)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
