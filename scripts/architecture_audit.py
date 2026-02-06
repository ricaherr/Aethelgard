#!/usr/bin/env python
"""
[AUDIT] ARQUITECTURA AUDIT: Detectar métodos duplicados, código muerto, y problemas de diseño
Resuelve: https://github.com/issues/arquitectura-duplicados
"""
import ast
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set

class CodeAudit:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.duplicates: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.orphan_functions: List[Tuple[str, str, int]] = []
        self.context_manager_abuse: List[Tuple[str, str, int]] = []
        self.circular_imports: Set[str] = set()
        self.all_methods: Dict[str, Dict] = {}  # {class_name: {method_name: [(file, line)]}}
        
    def scan_python_files(self):
        """Scan all Python files in workspace"""
        py_files = list(self.workspace_root.rglob("*.py"))
        py_files = [f for f in py_files if "venv" not in str(f) and "__pycache__" not in str(f)]
        
        print(f"[DIR] Escaneando {len(py_files)} archivos Python...")
        for py_file in py_files:
            try:
                self._analyze_file(py_file)
            except Exception as e:
                print(f"  [WARN]  Error analizando {py_file}: {e}")
    
    def _analyze_file(self, filepath: Path):
        """Analyze single Python file for duplicates and issues"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            print(f"  [ERROR] Syntax error en {filepath}: {e}")
            return
        
        # Extract class and function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                self.all_methods[class_name] = {}
                
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name
                        line_no = item.lineno

                        is_property_setter = any(
                            isinstance(dec, ast.Attribute)
                            and isinstance(dec.value, ast.Name)
                            and dec.value.id == method_name
                            and dec.attr in {"setter", "deleter"}
                            for dec in item.decorator_list
                        )
                        
                        # Check if it's a typing overload (valid duplicate for type hints)
                        is_overload = any(
                            isinstance(dec, ast.Name) and dec.id == 'overload'
                            for dec in item.decorator_list
                        )

                        if not is_property_setter and not is_overload:
                            key = f"{class_name}.{method_name}"
                            self.duplicates[key].append((str(filepath.relative_to(self.workspace_root)), line_no))

                            if key not in self.all_methods[class_name]:
                                self.all_methods[class_name][method_name] = []
                            self.all_methods[class_name][method_name].append((str(filepath), line_no))
                    
                    # Check for context manager abuse on _get_conn
                    if isinstance(item, ast.FunctionDef):
                        for subnode in ast.walk(item):
                            if isinstance(subnode, ast.With):
                                for context_expr in subnode.items:
                                    if hasattr(context_expr, 'context_expr'):
                                        if isinstance(context_expr.context_expr, ast.Call):
                                            if isinstance(context_expr.context_expr.func, ast.Attribute):
                                                if context_expr.context_expr.func.attr == '_get_conn':
                                                    self.context_manager_abuse.append(
                                                        (class_name, item.name, item.lineno)
                                                    )
    
    def report_duplicates(self):
        """Report all duplicate method definitions (excluding valid overloads)"""
        duplicates_found = {k: v for k, v in self.duplicates.items() if len(v) > 1}
        
        if not duplicates_found:
            print("\n[OK] No se encontraron métodos duplicados")
            return duplicates_found
        
        print(f"\n[ERROR] ¡¡¡ {len(duplicates_found)} MÉTODOS DUPLICADOS ENCONTRADOS !!!")
        print("=" * 80)
        
        for method_key in sorted(duplicates_found.keys()):
            locations = duplicates_found[method_key]
            print(f"\n[FAIL] {method_key}")
            print(f"   Definido {len(locations)} veces:")
            for filepath, lineno in locations:
                print(f"     📄 {filepath}:{lineno}")
        
        return duplicates_found
    
    def report_context_manager_abuse(self):
        """Report uses of context manager with _get_conn()"""
        if not self.context_manager_abuse:
            print("\n[OK] No se encontró abuso de context managers en _get_conn()")
            return []
        
        print(f"\n[WARN]  {len(self.context_manager_abuse)} USOS DE CONTEXT MANAGER CON _get_conn()")
        print("=" * 80)
        
        for class_name, method_name, lineno in sorted(self.context_manager_abuse):
            print(f"\n[WARN] {class_name}.{method_name} (línea {lineno})")
            print(f"   [ERROR] Problema: 'with self._get_conn() as conn' - Connection objects no son context managers")
            print(f"   [OK] Solución: conn = self._get_conn(); try: ...; finally: conn.close()")
        
        return self.context_manager_abuse
    
    def analyze_method_signatures(self):
        """Check for methods with same signature but different implementations"""
        print(f"\n[SEARCH] Analizando {len(self.all_methods)} clases...")
        
        issues = []
        for class_name, methods in sorted(self.all_methods.items()):
            for method_name, locations in methods.items():
                if len(locations) > 1:
                    issues.append((class_name, method_name, locations))
        
        return issues

def main():
    workspace_root = Path(__file__).parent.parent  # Go up from scripts/ to root
    audit = CodeAudit(workspace_root)
    
    print("\n[START] AETHELGARD ARCHITECTURE AUDIT")
    print("=" * 80)
    print(f"Workspace: {workspace_root}\n")
    
    # Run scans
    audit.scan_python_files()
    
    # Generate reports
    duplicates = audit.report_duplicates()
    context_abuse = audit.report_context_manager_abuse()
    method_issues = audit.analyze_method_signatures()
    
    # Summary
    print("\n" + "=" * 80)
    print("[STATS] RESUMEN DE AUDITORÍA")
    print("=" * 80)
    print(f"[OK] Archivos escaneados: {sum(1 for _ in workspace_root.rglob('*.py') if 'venv' not in str(_))}")
    print(f"[ERROR] Métodos duplicados: {len(duplicates)}")
    print(f"[WARN]  Abuso de context managers: {len(context_abuse)}")
    print(f"[FAIL] Problemas de método: {len(method_issues)}")
    
    if duplicates or context_abuse:
        print("\n[WARN]  ACCIÓN REQUERIDA: Revisa los problemas identificados arriba")
        return 1
    else:
        print("\n[OK] Audit limpio - No se encontraron problemas")
        return 0

if __name__ == "__main__":
    sys.exit(main())
