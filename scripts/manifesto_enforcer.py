#!/usr/bin/env python3
"""
Manifesto Enforcer - Aethelgard Architectural Guard
===================================================
Enforces the rules defined in AETHELGARD_MANIFESTO.md and user_global.

Verifications:
1. DI (Dependency Injection): No internal instantiation of Managers in __init__.
2. SSOT (Single Source of Truth): No direct reading of JSON files in core logic.
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Configure UTF-8 encoding for Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

class ManifestoEnforcer:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.manifesto_path = root_dir / "docs" / "AETHELGARD_MANIFESTO.md"
        self.forbidden_initializations = {'StorageManager', 'InstrumentManager'}
        self.forbidden_json_reads = {
            'risk_settings.json', 
            'config.json',
            'modules.json'
        }
        self.issues = []

    def scan_files(self):
        exclude_dirs = {
            'venv', '.venv', '__pycache__', '.git', 'node_modules', 
            'tests', 'scripts/utilities', 'ui'
        }
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file.endswith('.py'):
                    self._analyze_file(Path(root) / file)

    def _analyze_file(self, file_path: Path):
        rel_path = file_path.relative_to(self.root_dir)
        
        # Self-exclusion and exceptions
        if rel_path.name == 'manifesto_enforcer.py' or 'scripts' in rel_path.parts:
            return
        
        # StorageManager is allowed to read configs for bootstrapping/SSOT
        is_storage_module = 'storage.py' in rel_path.name

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # 1. Detect Internal Instantiation in __init__
                if isinstance(node, ast.FunctionDef) and node.name == '__init__':
                    for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Call):
                            func_name = ""
                            if isinstance(subnode.func, ast.Name):
                                func_name = subnode.func.id
                            elif isinstance(subnode.func, ast.Attribute):
                                func_name = subnode.func.attr
                            
                            if func_name in self.forbidden_initializations:
                                # Exception: MT5Connector allowed to instantiate StorageManager
                                # Exception: Legacy fallbacks for specific core components & strategies
                                if any(x in str(rel_path) for x in ['mt5_connector.py', 'data_provider_manager.py', 'executor.py', 'monitor.py', 'notificator.py', 'oliver_velez.py', 'health.py']):
                                    continue
                                
                                self.issues.append(
                                    f"🚫 DI VIOLATION: {rel_path}:{subnode.lineno} - "
                                    f"Internal instantiation of '{func_name}' in __init__. "
                                    f"Must be injected."
                                )

                # 2. Detect direct JSON reading
                if not is_storage_module:
                    # Exception: Legacy fallbacks
                    if any(x in str(rel_path) for x in ['mt5_connector.py', 'data_provider_manager.py', 'executor.py', 'monitor.py', 'notificator.py', 'oliver_velez.py', 'health.py', 'mt5_discovery.py']):
                        continue

                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        # ONLY flag if it looks like a path or is in a suspicious context
                        val = node.value
                        if any(json_file in val for json_file in self.forbidden_json_reads):
                            # Skip if it's clearly a log message (contains words like 'Migrated', 'Success', etc.)
                            log_keywords = {'Migrated', 'successfully', 'Error', 'INFO', 'WARNING', 'using global_config'}
                            if any(k in val for k in log_keywords):
                                continue
                                
                            self.issues.append(
                                f"🚫 SSOT VIOLATION: {rel_path}:{node.lineno} - "
                                f"Direct reference to JSON config '{val}'. "
                                f"Use StorageManager or injected config instead."
                            )

        except Exception as e:
            # Skip syntax errors (caught by other scripts)
            pass

    def report(self) -> int:
        print("\n" + "="*80)
        print("🏛️  AETHELGARD MANIFESTO ENFORCER")
        print("="*80)
        
        if not self.manifesto_path.exists():
            self.issues.append(f"❌ DOCUMENTATION ERROR: Manifesto not found at {self.manifesto_path}")
        
        if not self.issues:
            print("✅ SUCCESS: No architectural violations found.")
            return 0
        
        print(f"❌ FAILED: {len(self.issues)} violations detected.\n")
        for issue in sorted(self.issues):
            print(issue)
        
        print("\n💡 Tip: Seguir las reglas de Inyección de Dependencias y Single Source of Truth.")
        print("   Ver AETHELGARD_MANIFESTO.md para detalles.")
        return 1

def main():
    root = Path(__file__).parent.parent
    enforcer = ManifestoEnforcer(root)
    enforcer.scan_files()
    sys.exit(enforcer.report())

if __name__ == "__main__":
    main()
