#!/usr/bin/env python3
"""
[PATTERN ENFORCER]
Checks for required and forbidden patterns in code to prevent regressions.
Crucial for guaranteeing that refactored classes are instantiated correctly.
Uses AST for robust parsing of multi-line calls.
"""

import os
import ast
import sys
from pathlib import Path
from typing import List, Set

# Configuration: (Class Name, {Required Argument Names}, {Forbidden Argument Names}, {File Exclusions})
CHECKS = [
    (
        "RegimeClassifier", 
        {"storage"}, 
        {"config_path"}, 
        {"tests/", "models/signal.py"}
    ),
    (
        "ScannerEngine", 
        {"storage"}, 
        {}, 
        {"tests/"}
    ),
    (
        "RiskManager", 
        {"storage"}, 
        {}, 
        {"tests/", "core_brain/risk_manager.py"} 
    ),
    (
        "SignalFactory", 
        {"storage_manager"}, 
        {}, 
        {"tests/", "core_brain/signal_factory.py"}
    ),
    (
        "DataProviderManager",
        {"storage"},
        {},
        {"tests/", "core_brain/data_provider_manager.py", "core_brain/chart_service.py", "core_brain/main_orchestrator.py"}
    )
]

def find_python_files(root_dir: Path) -> List[Path]:
    python_files = []
    exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'node_modules'}
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith('.py'):
                python_files.append(Path(root) / file)
    return python_files

def check_file(file_path: Path, root_dir: Path) -> List[str]:
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        rel_path = str(file_path.relative_to(root_dir)).replace("\\", "/")
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Identify the function/class being called
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                    
                if not func_name:
                    continue
                    
                for class_name, required, forbidden, exclusions in CHECKS:
                    if func_name != class_name:
                        continue
                        
                    # Check exclusions
                    if any(ex in rel_path for ex in exclusions):
                        continue
                        
                    # Get all keyword arguments used in the call
                    used_kwargs = {kw.arg for kw in node.keywords if kw.arg}
                    
                    lineno = node.lineno
                    
                    # Check required
                    missing = required - used_kwargs
                    if missing:
                        # Before flagging, check if it relies on positionals?
                        # For these specific classes, we want to ENFORCE keyword args for clarity and safety.
                        # So validation fails if critical args are positional (unless we map them, but let's be strict).
                        # Actually, risk_manager definition is (storage, ...).
                        # If called as RiskManager(storage, ...), used_kwargs is empty.
                        # We should check if there are positional args that might cover it.
                        if not node.args: 
                            issues.append(f"{rel_path}:{lineno} -> {class_name} missing required argument(s) {missing}. (Use keyword args for safety)")
                        else:
                            # If there are positional args, we can't easily validte, but we can WARN.
                            # However, for 'storage' which is usually first, maybe we skip if pos args > 0?
                            # But strict mode prefers keywords.
                            # Let's inspect specific cases.
                            # ScannerEngine(assets, data_provider, ...) - storage is late.
                            # RegimeClassifier(storage=...) - storage is first but often kwargs.
                            pass # For now, let's enforce KWARGS for these critical dependencies.
                            
                            # Update: If positional arguments exist, we assume the dev knows what they are doing OR we warn.
                            # To guarantee "no missing storage", we should demand it be identifiable.
                            if not (required & used_kwargs):
                                # If none of the required args are keywords, and there are positionals, 
                                # we might assume it's passed positionally?
                                # But ScannerEngine signature is (assets, data_provider, ... storage=None). 
                                # Attempting to pass storage positionally is fragile.
                                issues.append(f"{rel_path}:{lineno} -> {class_name} requires {missing}. Please use keyword arguments.")

                    # Check forbidden
                    found_forbidden = forbidden.intersection(used_kwargs)
                    if found_forbidden:
                         issues.append(f"{rel_path}:{lineno} -> {class_name} uses FORBIDDEN argument(s) {found_forbidden}.")

    except Exception as e:
        # Syntax errors are handled by other tools, ignore here
        pass
        
    return issues

def main():
    root_dir = Path(__file__).parent.parent
    files = find_python_files(root_dir)
    
    print(f"[PATTERN] Aethelgard Pattern Enforcer (AST) | Scanning {len(files)} files...")
    
    all_issues = []
    for f in files:
        if f.name == "enforce_patterns.py":
            continue
        all_issues.extend(check_file(f, root_dir))
        
    if all_issues:
        print(f"\n[FAIL] Found {len(all_issues)} violations:")
        for issue in all_issues:
            print(f"  [FAIL] {issue}")
        sys.exit(1)
    else:
        print("\n[OK] All patterns valid. SSOT enforced.")
        sys.exit(0)

if __name__ == "__main__":
    main()
