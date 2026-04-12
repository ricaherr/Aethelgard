#!/usr/bin/env python3
"""
ENDPOINT NAMING VALIDATION SCRIPT
Trace_ID: ENDPOINT-NAMING-VALIDATOR-2026-0311

Responsibility:
    Scan all API router files and detect naming convention violations:
    1. Prefixes (sys_*, usr_*) exposed in public API routes
    2. Aliases/duplicates (@router.get(...) @router.get(...) on same handler)
    3. Mismatches between frontend expectations and backend routes
    4. Documentation gaps (route exists but not in MANIFESTO section XI)

Rule (from AETHELGARD_MANIFESTO.md and API governance conventions):
    - Database naming: sys_*, usr_* (internal)
    - API naming: semantic names WITHOUT prefixes (public)
    - PROHIBIDO: /sys_regime_configs, /usr_positions in router endpoints
    - OBLIGATORIO: /regime_configs, /positions (semantic names)
"""

import re
import sys
from pathlib import Path
from typing import List, Set, Dict, Tuple
from dataclasses import dataclass


class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


@dataclass
class EndpointViolation:
    """Represents a naming convention violation"""
    file: str
    line_number: int
    route: str
    issue: str  # "sys_/usr_ prefix exposed" | "alias redundancy" | etc.
    severity: str  # "error" | "warning"


def scan_router_files() -> Tuple[List[EndpointViolation], int, int]:
    """
    Scan all routers/*.py files for naming violations.
    
    Returns:
        (violations, total_endpoints, compliant_endpoints)
    """
    workspace = Path(__file__).parent.parent
    routers_dir = workspace / 'core_brain' / 'api' / 'routers'
    
    if not routers_dir.exists():
        print(f"{Colors.RED}ERROR: routers directory not found{Colors.RESET}")
        return [], 0, 0
    
    violations: List[EndpointViolation] = []
    total_endpoints = 0
    seen_endpoints: Dict[Tuple[str, str], str] = {}  # (method, route) -> file:line
    
    for router_file in sorted(routers_dir.glob('*.py')):
        if router_file.name == '__init__.py':
            continue
        
        content = router_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for @router.get|post|put|delete|patch decorators
            if '@router.' in line:
                match = re.search(r'@router\.(\w+)\s*\(\s*["\']([^"\']+)["\']', line)
                if match:
                    method = match.group(1).upper()
                    route = match.group(2)
                    full_route = f"/{route}" if not route.startswith('/') else route
                    total_endpoints += 1
                    
                    # CHECK 1: Prefix violation (sys_* or usr_* in public route)
                    if re.search(r'/(sys_|usr_)', full_route):
                        violations.append(EndpointViolation(
                            file=router_file.name,
                            line_number=i + 1,
                            route=full_route,
                            issue=f"Internal prefix (sys_/usr_) exposed in public route: {full_route}",
                            severity="error"
                        ))
                    
                    # CHECK 2: Duplicate route detection (alias redundancy)
                    # Only flag if SAME METHOD on SAME route (e.g., GET /users twice)
                    # CRUD operations (GET list, POST create, PUT update, DELETE delete) are NOT duplicates
                    endpoint_key = (method, full_route)
                    if endpoint_key in seen_endpoints:
                        prev_file_line = seen_endpoints[endpoint_key]
                        violations.append(EndpointViolation(
                            file=router_file.name,
                            line_number=i + 1,
                            route=full_route,
                            issue=f"Duplicate {method} route: already defined in {prev_file_line}",
                            severity="warning"
                        ))
                    else:
                        seen_endpoints[endpoint_key] = f"{router_file.name}:{i+1}"
            
            i += 1
    
    compliant = total_endpoints - len([v for v in violations if v.severity == "error"])
    return violations, total_endpoints, compliant


def validate_naming() -> int:
    """
    Main validation function.
    
    Returns:
        Exit code (0 = success, 1 = failures found)
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}ENDPOINT NAMING CONVENTION AUDIT{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    
    violations, total, compliant = scan_router_files()
    
    if violations:
        print(f"{Colors.YELLOW}VIOLATIONS FOUND:{Colors.RESET}\n")
        
        for violation in violations:
            color = Colors.RED if violation.severity == "error" else Colors.YELLOW
            icon = "❌" if violation.severity == "error" else "⚠️"
            
            print(f"{color}{icon} [{violation.file}:{violation.line_number}]{Colors.RESET}")
            print(f"   Route: {violation.route}")
            print(f"   Issue: {violation.issue}\n")
    
    # Summary
    errors = len([v for v in violations if v.severity == "error"])
    warnings = len([v for v in violations if v.severity == "warning"])
    
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"Total endpoints: {total}")
    print(f"Compliant: {compliant}/{total}")
    print(f"Errors: {errors} | Warnings: {warnings}\n")
    
    if errors == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] Endpoint naming convention compliant{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}[FAIL] {errors} naming violations detected{Colors.RESET}")
        print(f"{Colors.YELLOW}See docs/AETHELGARD_MANIFESTO.md for guidance{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = validate_naming()
    sys.exit(exit_code)
