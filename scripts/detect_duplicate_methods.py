#!/usr/bin/env python
"""
DUPLICATE METHODS DETECTOR
Audita métodos con lógica duplicada en StorageManager y otros módulos.

Problema detectado: get_economic_calendar() y get_economic_events() tenían
código casi idéntico → violación DRY principle.

Solución: Consolida en SSOT method, hace el otro wrapper.
"""
import sys
import re
from pathlib import Path
from typing import Dict, Set, List

def detect_duplicate_economic_methods() -> bool:
    """
    Verifica que get_economic_events() sea wrapper de get_economic_calendar().
    
    Returns: True si está consolidado correctamente
    """
    storage_file = Path(__file__).parent.parent / "data_vault" / "storage.py"
    
    if not storage_file.exists():
        print(f"ERROR: File not found: {storage_file}")
        return False
    
    with open(storage_file, "r") as f:
        content = f.read()
    
    # Check 1: get_economic_calendar() debe tener la lógica principal
    has_main_logic = bool(re.search(
        r'def get_economic_calendar\([^)]*?\)\s*->\s*List.*?'
        r'SELECT event_id.*?FROM economic_calendar',
        content,
        re.DOTALL
    ))
    
    # Check 2: get_economic_events() debe ser wrapper (deprecated + delegate)
    is_wrapper = bool(re.search(
        r'def get_economic_events\([^)]*?\).*?DEPRECATED.*?'
        r'return self\.get_economic_calendar',
        content,
        re.DOTALL
    ))
    
    if not has_main_logic:
        print("FAIL: get_economic_calendar() must have SELECT logic")
        return False
    
    if not is_wrapper:
        print("FAIL: get_economic_events() must delegate to get_economic_calendar()")
        return False
    
    print("PASS: Economic methods consolidated (DRY principle)")
    return True


def detect_provider_source_hardcoding() -> bool:
    """
    Verifica que no haya "INVESTING" hardcodeado en tests.
    Debe usarse TEST_PROVIDER_SOURCE desde conftest.py.
    """
    test_file = Path(__file__).parent.parent / "tests" / "test_news_sanitizer.py"
    
    if not test_file.exists():
        print(f"WARNING: Test file not found: {test_file}")
        return True  # No fallar si no existe
    
    with open(test_file, "r") as f:
        content = f.read()
    
    # Buscar hardcoded "INVESTING" en parámetro de función
    hardcoded = re.findall(
        r'_validate_schema\([^)]*,\s*["\']INVESTING["\']',
        content
    )
    
    if hardcoded:
        print(f"FAIL: Found {len(hardcoded)} hardcoded 'INVESTING' in tests")
        print(f"  Use TEST_PROVIDER_SOURCE from conftest instead")
        return False
    
    # Buscar hardcoded country codes
    hardcoded_codes = re.findall(
        r'valid_codes\s*=\s*\[["\']USA["\'],',
        content
    )
    
    if hardcoded_codes:
        print(f"FAIL: Found hardcoded country codes in tests")
        print(f"  Use VALID_COUNTRY_CODES from conftest instead")
        return False
    
    print("PASS: No hardcoded provider/country values in tests")
    return True


def main() -> int:
    """Main audit function"""
    
    print("[DUPLICATE METHODS AUDIT]")
    print("=" * 80)
    
    checks = [
        ("Economic Methods Consolidation", detect_duplicate_economic_methods),
        ("Provider Source Hardcoding", detect_provider_source_hardcoding),
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
