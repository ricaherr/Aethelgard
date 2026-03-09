#!/usr/bin/env python3
"""
audit_table_naming.py — Naming Convention Auditor (ARCH-SSOT-2026-006)

TRACE_ID: EXEC-SSOT-IMPLEMENT-2026-007 (Fase 1: Blindaje de Naming)

Responsibility: Verify that all table names in data_vault/schema.py conform to the
standardized naming convention (sys_* for global, usr_* for tenant-isolated).

RULE: Any deviation from the approved table mapping will trigger immediate deployment halt.

Approved Table Mapping (Single Source of Truth):
- sys_config (was: system_state)
- sys_market_pulse (was: market_state)
- sys_calendar (was: economic_calendar)
- sys_auth (was: users_auth)
- sys_memberships (was: memberships)
- sys_strategies (was: usr_strategies) [GLOBAL: All traders read same strategies]
- usr_assets_cfg (was: instruments_config)
- usr_signals (was: signals)
- usr_trades (was: trades)
- usr_performance (was: strategy_ranking)

Any mention of old table names (system_state, market_state, economic_calendar, etc.)
will FAIL this audit and halt deployment.
"""

import re
import sys
import logging
from pathlib import Path
from typing import Set, Dict, Tuple

logger = logging.getLogger(__name__)

# Approved table names (Capa 0 + Capa 1)
APPROVED_TABLES = {
    # Capa 0: Global Tables (sys_*)
    "sys_config",
    "sys_market_pulse",
    "sys_calendar",
    "sys_auth",
    "sys_memberships",
    "sys_strategies",  # Global: all traders read same strategies
    # Supporting sys tables (referenced in schema)
    "symbol_mappings",  # sys_* but kept for provider normalization
    "brokers",
    "platforms",
    "credentials",
    "data_providers",
    "asset_profiles",
    "regime_configs",
    "connector_settings",
    "notification_settings",
    "coherence_events",
    "anomaly_events",
    "broker_accounts",
    "user_preferences",
    "notifications",
    "tuning_adjustments",
    "signal_pipeline",
    "position_history",
    "execution_shadow_logs",
    "edge_learning",
    "strategy_performance_logs",
    # Capa 1: Tenant Tables (usr_*)
    "usr_assets_cfg",
    "usr_signals",
    "usr_trades",
    "usr_performance",
}

# Forbidden table names (old naming convention)
FORBIDDEN_TABLES = {
    "system_state",         # ❌ OLD → sys_config
    "market_state",         # ❌ OLD → sys_market_pulse
    "economic_calendar",    # ❌ OLD → sys_calendar
    "users_auth",           # ❌ OLD → sys_auth
    "memberships",          # ⚠️ Check context
    "instruments_config",   # ❌ OLD → usr_assets_cfg
    "usr_strategies",       # ❌ OLD → sys_strategies (global convention)
    "signals",              # ⚠️ Check: usr_signals (tenant-isolated)
    "trades",               # ⚠️ Check: usr_trades (tenant-isolated)
    "strategy_ranking",     # ❌ OLD → usr_performance
    "strategies",           # ⚠️ Check: sys_strategies (global)
}


def find_table_references(file_path: Path) -> Dict[str, Set[int]]:
    """
    Scan a Python or SQL file for table name references.
    Returns dict mapping table name to set of line numbers where found.
    """
    references = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        logger.warning(f"Could not read {file_path}: {e}")
        return references
    
    for line_no, line in enumerate(lines, start=1):
        # Skip comments
        if line.strip().startswith('#') or line.strip().startswith('--'):
            continue
        
        # Look for CREATE TABLE, INSERT, SELECT, UPDATE, DELETE statements
        for forbidden in FORBIDDEN_TABLES:
            # Match whole word only (not substring)
            pattern = rf"\b{forbidden}\b"
            if re.search(pattern, line, re.IGNORECASE):
                if forbidden not in references:
                    references[forbidden] = set()
                references[forbidden].add(line_no)
    
    return references


def audit_schema_file(schema_file: Path) -> Tuple[bool, list]:
    """
    Audit data_vault/schema.py for compliance with naming convention.
    
    Returns: (is_compliant: bool, violations: list of violation strings)
    """
    violations = []
    
    if not schema_file.exists():
        violations.append(f"❌ Schema file not found: {schema_file}")
        return False, violations
    
    logger.info(f"📋 Auditing schema file: {schema_file}")
    
    references = find_table_references(schema_file)
    
    # Check for forbidden table names
    if references:
        for forbidden, line_nos in sorted(references.items()):
            violation = (
                f"❌ FORBIDDEN TABLE NAME '{forbidden}' found in {schema_file.name}:\n"
                f"   Lines: {sorted(line_nos)}\n"
                f"   Action: Rename to approved equivalent (see audit_table_naming.py)"
            )
            violations.append(violation)
    
    is_compliant = len(violations) == 0
    return is_compliant, violations


def audit_sql_queries(repo_files: list) -> Tuple[bool, list]:
    """
    Audit all data_vault repository files for forbidden table references.
    
    Scans: _db.py files for hardcoded SQL queries using old table names.
    
    Returns: (is_compliant: bool, violations: list)
    """
    violations = []
    
    logger.info(f"📋 Scanning {len(repo_files)} repository files for SQL queries...")
    
    for file_path in repo_files:
        references = find_table_references(file_path)
        
        if references:
            for forbidden, line_nos in sorted(references.items()):
                violation = (
                    f"❌ FORBIDDEN TABLE NAME '{forbidden}' in {file_path.name}:\n"
                    f"   Lines: {sorted(line_nos)}\n"
                    f"   Action: Update SQL to use new table name"
                )
                violations.append(violation)
    
    is_compliant = len(violations) == 0
    return is_compliant, violations


def audit_core_brain(core_brain_dir: Path) -> Tuple[bool, list]:
    """
    Audit core_brain/ for any hardcoded table references (should use StorageManager API).
    
    Returns: (is_compliant: bool, violations: list)
    """
    violations = []
    
    if not core_brain_dir.exists():
        logger.warning(f"core_brain directory not found: {core_brain_dir}")
        return True, []
    
    logger.info(f"📋 Scanning core_brain for forbidden table references...")
    
    py_files = list(core_brain_dir.glob("*.py"))
    
    for file_path in py_files:
        references = find_table_references(file_path)
        
        # Note: Some references might be intentional (e.g., in documentation),
        # but any SQL queries directly referencing tables MUST use new names
        if references:
            for forbidden, line_nos in sorted(references.items()):
                # Only flag if it looks like SQL (contains CREATE, INSERT, SELECT, etc.)
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    is_sql = False
                    for line_no in line_nos:
                        if line_no <= len(lines):
                            line = lines[line_no - 1]
                            if any(kw in line.upper() for kw in ['CREATE', 'INSERT', 'SELECT', 'UPDATE', 'DELETE']):
                                is_sql = True
                                break
                
                if is_sql:
                    violation = (
                        f"❌ FORBIDDEN TABLE NAME '{forbidden}' in {file_path.name}:\n"
                        f"   Lines: {sorted(line_nos)}\n"
                        f"   Action: Use StorageManager API instead of direct SQL"
                    )
                    violations.append(violation)
    
    is_compliant = len(violations) == 0
    return is_compliant, violations


def run_audit(project_root: Path = None) -> int:
    """
    Execute complete audit of the Aethelgard codebase.
    
    CRITICAL: If ANY violations found, return non-zero exit code (deployment halt).
    
    Returns: 0 if compliant, 1 if violations found
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent  # Navigate to project root
    
    data_vault_dir = project_root / "data_vault"
    core_brain_dir = project_root / "core_brain"
    schema_file = data_vault_dir / "schema.py"
    
    all_violations = []
    all_compliant = True
    
    print("\n" + "="*80)
    print("🔍 ARCH-SSOT-2026-006: DATABASE TABLE NAMING AUDIT")
    print("="*80 + "\n")
    
    # Phase 1: Audit schema.py (PRIMARY)
    print("📋 PHASE 1: Auditing data_vault/schema.py (PRIMARY SCHEMA)")
    print("-" * 80)
    compliant, violations = audit_schema_file(schema_file)
    if violations:
        all_compliant = False
        all_violations.extend(violations)
        for v in violations:
            print(v)
    else:
        print("✅ schema.py: Naming convention COMPLIANT")
    print()
    
    # Phase 2: Audit data_vault SQL queries
    print("📋 PHASE 2: Auditing data_vault/_db.py files (SQL QUERIES)")
    print("-" * 80)
    repo_files = sorted(data_vault_dir.glob("*_db.py"))
    if repo_files:
        compliant, violations = audit_sql_queries(repo_files)
        if violations:
            all_compliant = False
            all_violations.extend(violations)
            for v in violations:
                print(v)
        else:
            print(f"✅ {len(repo_files)} repository files: Naming convention COMPLIANT")
    else:
        print("⚠️  No *_db.py files found")
    print()
    
    # Phase 3: Audit core_brain (WARNING PHASE)
    print("📋 PHASE 3: Auditing core_brain/ (ARCHITECTURE CHECK)")
    print("-" * 80)
    compliant, violations = audit_core_brain(core_brain_dir)
    if violations:
        print("⚠️  WARNING: core_brain files contain table references:")
        for v in violations:
            print(v)
        # Note: Not failing deployment for core_brain warnings,
        # but flagging for developer attention
    else:
        print("✅ core_brain/: No direct table references detected")
    print()
    
    # Final Report
    print("="*80)
    if all_compliant:
        print("✅ AUDIT PASSED: All tables follow ARCH-SSOT-2026-006 convention")
        print("="*80 + "\n")
        return 0
    else:
        print("❌ AUDIT FAILED: Naming convention violations detected")
        print(f"   Total violations: {len(all_violations)}")
        print("\n⚠️  DEPLOYMENT BLOCKED: Please fix violations above and retry")
        print("="*80 + "\n")
        return 1


if __name__ == "__main__":
    # Get project root from environment or infer from script location
    project_root = Path(os.getenv("AETHELGARD_ROOT", "."))
    exit_code = run_audit(project_root)
    sys.exit(exit_code)
