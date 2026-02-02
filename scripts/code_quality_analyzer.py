#!/usr/bin/env python
"""
[SEARCH] CODE SIMILARITY & COMPLEXITY DETECTOR
Detecta: Código duplicado (copy-paste), Complejidad ciclomática alta
"""
import ast
import sys
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Dict, Tuple
from collections import defaultdict

class CodeAnalyzer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.functions: Dict[str, List[Tuple[str, str, int, str]]] = defaultdict(list)
        self.complexity_issues: List[Tuple[str, str, int, int]] = []
        
    def extract_functions(self):
        """Extract all function signatures and bodies"""
        key_files = [
            "data_vault/storage.py",
            "core_brain/scanner.py",
            "connectors/mt5_connector.py",
            "core_brain/executor.py",
            "core_brain/main_orchestrator.py"
        ]
        
        for filepath_str in key_files:
            filepath = self.workspace_root / filepath_str
            if not filepath.exists():
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_body = self._get_function_body(content, node)
                        func_source = ast.get_source_segment(content, node) or ""
                        
                        self.functions[node.name].append((
                            filepath_str,
                            node.name,
                            node.lineno,
                            func_source
                        ))
                        
                        # Calculate complexity
                        complexity = self._calculate_complexity(node)
                        if complexity > 10:  # High threshold
                            self.complexity_issues.append((
                                filepath_str,
                                node.name,
                                node.lineno,
                                complexity
                            ))
            except Exception as e:
                print(f"  [WARN]  Error parsing {filepath_str}: {e}")
    
    def _get_function_body(self, source: str, node: ast.FunctionDef) -> str:
        """Extract function body as string"""
        try:
            return ast.get_source_segment(source, node) or ""
        except:
            return ""
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """
        Calculate cyclomatic complexity for a function.
        High values indicate:
        - Too many if/elif/else
        - Too many loops (for, while)
        - Too many exception handlers
        - Potential code smell
        """
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # Count 'and'/'or' operators
                complexity += len(child.values) - 1
        
        return complexity
    
    def find_similar_functions(self, similarity_threshold: float = 0.80):
        """Find functions with similar logic (potential copy-paste)"""
        similar_pairs = []
        
        # Compare functions with same name but different files
        for func_name, locations in self.functions.items():
            if len(locations) > 1:
                # Calculate similarity between versions
                for i in range(len(locations)):
                    for j in range(i + 1, len(locations)):
                        file1, name1, line1, source1 = locations[i]
                        file2, name2, line2, source2 = locations[j]
                        
                        if source1 and source2:
                            similarity = SequenceMatcher(None, source1, source2).ratio()
                            if similarity >= similarity_threshold:
                                similar_pairs.append((
                                    func_name,
                                    file1, line1,
                                    file2, line2,
                                    similarity
                                ))
        
        return similar_pairs
    
    def report(self):
        """Generate comprehensive report"""
        print("\n[START] CODE QUALITY ANALYSIS")
        print("=" * 80)
        
        # Extract functions
        self.extract_functions()
        
        # Find duplicates
        print("\n[FAIL] COPY-PASTE DETECTION (>80% similitud)")
        print("-" * 80)
        similar = self.find_similar_functions()
        
        if similar:
            for func_name, file1, line1, file2, line2, similarity in similar:
                print(f"\n[WARN]  {func_name} ({int(similarity*100)}% similar)")
                print(f"   📄 {file1}:{line1}")
                print(f"   📄 {file2}:{line2}")
                print(f"   💡 Acción: Consolidar ambas implementaciones en UNA función")
        else:
            print("[OK] No se detectó código duplicado significativo")
        
        # Cyclomatic complexity
        print("\n\n[STATS] COMPLEJIDAD CICLOMÁTICA (>10 = ALERTA)")
        print("-" * 80)
        
        if self.complexity_issues:
            # Sort by complexity (descending)
            sorted_issues = sorted(self.complexity_issues, key=lambda x: x[3], reverse=True)
            
            for filepath, func_name, lineno, complexity in sorted_issues[:15]:  # Top 15
                bar = "█" * (complexity // 2)
                print(f"\n[WARN] {func_name} (CC: {complexity})")
                print(f"   📄 {filepath}:{lineno}")
                print(f"   {bar}")
                print(f"   💡 Refactorizar: Extraer condiciones a funciones pequeñas")
        else:
            print("[OK] Complejidad dentro de límites aceptables")
        
        # Summary
        print("\n" + "=" * 80)
        print("📈 RESUMEN")
        print(f"Total funciones analizadas: {len(self.functions)}")
        print(f"Funciones con HIGH complexity: {len(self.complexity_issues)}")
        print(f"Potencial copy-paste detectado: {len(similar)}")
        
        if similar or len(self.complexity_issues) > 5:
            print("\n[WARN]  ACCIÓN REQUERIDA: Refactorización necesaria")
            return 1
        else:
            print("\n[OK] Código limpio - Sin issues significativos")
            return 0

def main():
    workspace_root = Path(__file__).parent.parent
    analyzer = CodeAnalyzer(workspace_root)
    return analyzer.report()

if __name__ == "__main__":
    sys.exit(main())
