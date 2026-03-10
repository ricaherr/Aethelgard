#!/usr/bin/env python3
"""
TENANT ISOLATION AUDIT SCRIPT
Trace_ID: TENANT-VALIDATION-SCANNER-2026-001

Responsibility:
    Scan all routers/*.py files and verify that endpoints with authentication
    (token: TokenPayload parameter) use TenantDBFactory.get_storage(token.sub)
    and NOT _get_storage() for data access (except for global endpoints like /config/).

Rule:
    If endpoint has @router.get|post|put|patch|delete(...) with token parameter
    THEN it must use TenantDBFactory.get_storage(token.sub) for any DB access
    
    Exception: Endpoints that are explicitly GLOBAL (system-wide data not tenant-bound)
    like /config/{category} which access sys_config (global data)
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ANSI Colors
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

@dataclass
class TenantedEndpoint:
    """Represents an endpoint that should be tenant-isolated"""
    file: str
    line_num: int
    endpoint_def: str  # @router.get("/path")
    function_name: str
    has_token_param: bool
    uses_tenantdbfactory: bool
    uses_generic_storage: bool
    is_compliant: bool
    reason: str = ""


def scan_router_file(filepath: Path) -> List[TenantedEndpoint]:
    """
    Scan a router file for tenanted endpoints compliance.
    """
    endpoints = []
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for @router decorators
        if '@router.' in line and ('get' in line or 'post' in line or 'put' in line or 'patch' in line or 'delete' in line):
            endpoint_line = i
            endpoint_def = line.strip()
            
            # Check next line for function definition
            if i + 1 < len(lines):
                func_line = lines[i + 1]
                
                # Extract function name
                if 'async def ' in func_line or 'def ' in func_line:
                    func_match = re.search(r'(?:async\s+)?def\s+(\w+)\s*\(', func_line)
                    func_name = func_match.group(1) if func_match else "unknown"
                    
                    # Check for token parameter
                    has_token = 'token:' in func_line or 'token :' in func_line
                    
                    # Build endpoint context (function body)
                    body_lines = []
                    j = i + 2
                    indent_level = len(func_line) - len(func_line.lstrip())
                    
                    while j < len(lines) and j < i + 50:  # Scan next 50 lines for storage access
                        body_line = lines[j]
                        
                        # Stop if we hit another @router or function def at same/lower indent
                        if body_line.strip().startswith('@router') or (
                            body_line.strip().startswith('def ') or body_line.strip().startswith('async def ')
                        ):
                            break
                        
                        body_lines.append(body_line)
                        j += 1
                    
                    body_text = '\n'.join(body_lines)
                    
                    # Check for storage access patterns
                    uses_tenantdbfactory = 'TenantDBFactory.get_storage' in body_text
                    uses_generic_storage = '_get_storage()' in body_text
                    
                    # Compliance logic
                    # Global endpoints (like /config/{category}, /health) can use _get_storage()
                    is_global_endpoint = any(
                        pattern in endpoint_def 
                        for pattern in ['/config/', '/health', '/system/', '/audit/']
                    )
                    
                    if not has_token:
                        # Endpoint doesn't require auth - might be public
                        is_compliant = True
                        reason = "No token required (possibly public endpoint)"
                    elif is_global_endpoint and uses_generic_storage:
                        # Global endpoints like /config/ can use _get_storage()
                        is_compliant = True
                        reason = "[OK] Global endpoint correctly uses _get_storage()"
                    elif has_token and uses_tenantdbfactory:
                        is_compliant = True
                        reason = "[OK] Uses TenantDBFactory correctly"
                    elif has_token and not uses_generic_storage and not uses_tenantdbfactory:
                        is_compliant = True
                        reason = "No direct storage access (might delegate to service)"
                    elif has_token and uses_generic_storage and not is_global_endpoint:
                        is_compliant = False
                        reason = "[FAIL] Uses _get_storage() instead of TenantDBFactory"
                    else:
                        is_compliant = True
                        reason = "[?] Unknown pattern"
                    
                    endpoints.append(TenantedEndpoint(
                        file=str(filepath),
                        line_num=endpoint_line + 1,  # 1-based
                        endpoint_def=endpoint_def,
                        function_name=func_name,
                        has_token_param=has_token,
                        uses_tenantdbfactory=uses_tenantdbfactory,
                        uses_generic_storage=uses_generic_storage,
                        is_compliant=is_compliant,
                        reason=reason
                    ))
        
        i += 1
    
    return endpoints


def audit_all_routers() -> Tuple[int, int]:
    """
    Scan all routers and return (compliant_count, total_count)
    """
    workspace = Path(__file__).parent.parent
    routers_dir = workspace / 'core_brain' / 'api' / 'routers'
    
    if not routers_dir.exists():
        print(f"{Colors.RED}ERROR: routers directory not found{Colors.RESET}")
        return 0, 0
    
    all_endpoints = []
    router_files = sorted(routers_dir.glob('*.py'))
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}TENANT ISOLATION AUDIT{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    
    for router_file in router_files:
        if router_file.name == '__init__.py':
            continue
        
        endpoints = scan_router_file(router_file)
        
        if endpoints:
            print(f"{Colors.BOLD}File: {router_file.name}{Colors.RESET}")
            
            for ep in endpoints:
                status_color = Colors.GREEN if ep.is_compliant else Colors.RED
                status_icon = "[OK]" if ep.is_compliant else "[FAIL]"
                
                print(f"  {status_icon} {status_color}L{ep.line_num}: {ep.function_name}(){Colors.RESET}")
                print(f"     Endpoint: {ep.endpoint_def}")
                print(f"     Auth: {'Token required' if ep.has_token_param else 'No token'}")
                print(f"     Storage: ", end="")
                
                storage_usage = []
                if ep.uses_tenantdbfactory:
                    storage_usage.append(f"{Colors.GREEN}TenantDBFactory{Colors.RESET}")
                if ep.uses_generic_storage:
                    storage_usage.append(f"{Colors.RED}_get_storage(){Colors.RESET}")
                
                if storage_usage:
                    print(" + ".join(storage_usage))
                else:
                    print("(Service delegate)")
                
                print(f"     Status: {ep.reason}\n")
            
            all_endpoints.extend(endpoints)
    
    # Summary
    compliant = sum(1 for ep in all_endpoints if ep.is_compliant)
    total = len(all_endpoints)
    
    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}")
    print(f"SUMMARY: {compliant}/{total} endpoints compliant")
    
    if compliant == total:
        print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] All endpoints are tenant-isolated{Colors.RESET}")
        return 0  # Success exit code
    else:
        non_compliant = total - compliant
        print(f"{Colors.RED}{Colors.BOLD}[FAIL] {non_compliant} endpoints need remediation{Colors.RESET}")
        print(f"{Colors.YELLOW}Affected endpoints should use:  TenantDBFactory.get_storage(token.sub){Colors.RESET}")
        return 1  # Failure exit code


if __name__ == "__main__":
    exit_code = audit_all_routers()
    sys.exit(exit_code)
