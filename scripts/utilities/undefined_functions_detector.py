#!/usr/bin/env python
"""
UNDEFINED FUNCTIONS DETECTOR - Análisis Estático AST

Detecta llamadas a métodos/funciones que NO están implementados.
Previene bugs como el Issue #123 (update_position_metadata faltante).

PRINCIPLES:
- Análisis estático completo (sin ejecutar código)
- Detecta method calls en clases conocidas
- Reporta funciones faltantes ANTES de runtime
- Integrado en validate_all.py (CI/CD)

CÓMO FUNCIONA:
1. Escanea TODOS los archivos Python del proyecto
2. Construye mapas de: clases → métodos implementados
3. Analiza TODAS las llamadas a métodos (ast.Call + ast.Attribute)
4. Verifica que el método existe en la clase destino
5. Reporta llamadas a métodos INEXISTENTES

EJEMPLO DE DETECCIÓN:
```python
# En executor.py:
self.storage.update_position_metadata(ticket, metadata)

# Si StorageManager NO tiene update_position_metadata:
# [ERROR] UNDEFINED METHOD CALL
#   File: core_brain/executor.py:263
#   Call: storage.update_position_metadata()
#   Target Class: StorageManager
#   Status: METHOD NOT FOUND
```

REGRESSION: Issue #123 - 2026-02-12
- BUG: Executor llamaba storage.update_position_metadata() INEXISTENTE
- CAUSA: Tests con Mocks permitieron pasar sin detectar
- SOLUCIÓN: Este script detecta PROACTIVAMENTE antes de tests
"""

import ast
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


class UndefinedFunctionDetector:
    """
    Detecta llamadas a funciones/métodos que no están implementados.
    SOLO valida clases PROPIAS del proyecto (no librerías externas).
    """
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        
        # Maps: class_name → set of method names
        self.class_methods: Dict[str, Set[str]] = defaultdict(set)
        
        # Maps: class_name → list of base class names
        self.class_bases: Dict[str, List[str]] = {}
        
        # Maps: variable_name → class_name (for type inference)
        self.variable_types: Dict[str, str] = {}
        
        # Undefined method calls found
        self.undefined_calls: List[Dict] = []
        
        # Files to skip (external dependencies)
        self.skip_patterns = {'venv', '__pycache__', 'node_modules', '.git'}
        
        # WHITELIST: Solo clases propias del proyecto (código que controlamos)
        self.project_classes = {
            # core_brain/
            'StorageManager',
            'RiskManager',
            'OrderExecutor',
            'MainOrchestrator',
            'EdgeMonitor',
            'RegimeClassifier',
            'SignalFactory',
            'PositionManager',
            'TradeClosureListener',
            'ScannerEngine',
            'EdgeTuner',
            'CoherenceMonitor',
            'PositionSizeMonitor',
            'SignalExpirationManager',
            'MultiTimeframeLimiter',
            'DataProviderManager',
            'InstrumentManager',
            'ModuleManager',
            
            # connectors/
            'MT5Connector',
            'PaperConnector',
            'GenericDataProvider',
            'AlphaVantageProvider',
            'FinnhubProvider',
            'IEXCloudProvider',
            'PolygonProvider',
            'TwelveDataProvider',
            'CCXTProvider',
            'MT5DataProvider',
            
            # data_vault/
            'SignalsMixin',
            'TradesMixin',
            'AccountsMixin',
            'SystemMixin',
            'BaseRepository',
            'MarketDB',
            'SignalsDB',
            'SystemDB',
            'TradesDB',
            'AccountsDB',
            
            # models/
            'Signal',
            'BrokerEvent',
        }
        
    def scan_workspace(self):
        """Scan all Python files and build method maps"""
        py_files = list(self.workspace_root.rglob("*.py"))
        py_files = [
            f for f in py_files 
            if not any(skip in str(f) for skip in self.skip_patterns)
        ]
        
        print(f"[SCAN] Analizando {len(py_files)} archivos Python...")
        
        # PHASE 1: Build method maps (what exists)
        for py_file in py_files:
            self._extract_class_methods(py_file)
        
        print(f"[MAP] Encontradas {len(self.class_methods)} clases con métodos definidos")
        
        # PHASE 2: Analyze method calls (what's being used)
        for py_file in py_files:
            self._analyze_method_calls(py_file)
        
        return self.undefined_calls
    
    def _extract_class_methods(self, filepath: Path):
        """Extract all methods from classes in file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=str(filepath))
        except (SyntaxError, UnicodeDecodeError):
            return
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                
                # Track base classes for inheritance resolution
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(base.attr)
                self.class_bases[class_name] = bases
                
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name
                        self.class_methods[class_name].add(method_name)
    
    def _analyze_method_calls(self, filepath: Path):
        """Analyze all method calls and verify they exist"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content, filename=str(filepath))
        except (SyntaxError, UnicodeDecodeError):
            return
        
        # Track variable assignments for type inference
        local_vars: Dict[str, str] = {}
        
        for node in ast.walk(tree):
            # Track assignments: self.storage = storage
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Name):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute):
                            # self.storage = storage
                            attr_name = target.attr
                            var_name = node.value.id
                            # Try to infer type from context
                            if 'storage' in var_name.lower():
                                local_vars[attr_name] = 'StorageManager'
                            elif 'risk' in var_name.lower():
                                local_vars[attr_name] = 'RiskManager'
                            elif 'connector' in var_name.lower():
                                local_vars[attr_name] = 'MT5Connector'
            
            # Analyze method calls: obj.method()
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Get method name
                    method_name = node.func.attr
                    
                    # Try to infer object class
                    obj = node.func.value
                    class_name = self._infer_class_name(obj, local_vars)
                    
                    # CRITICAL: Solo validar clases propias del proyecto
                    if class_name and class_name in self.project_classes:
                        # Verificar si la clase está mapeada (existe en codebase)
                        if class_name in self.class_methods:
                            # Check if method exists (recursive inheritance check)
                            if not self._method_exists(class_name, method_name):
                                # UNDEFINED METHOD CALL DETECTED
                                self.undefined_calls.append({
                                    'file': str(filepath.relative_to(self.workspace_root)),
                                    'line': node.lineno,
                                    'call': f"{class_name}.{method_name}()",
                                    'class': class_name,
                                    'method': method_name,
                                    'severity': 'CRITICAL'
                                })
    
    def _method_exists(self, class_name: str, method_name: str, visited: Set[str] = None) -> bool:
        """Check if method exists in class or its bases (recursive)"""
        if visited is None:
            visited = set()
            
        if class_name in visited:
            return False
        visited.add(class_name)
        
        # Check in current class
        if method_name in self.class_methods.get(class_name, set()):
            return True
            
        # Check in bases
        for base in self.class_bases.get(class_name, []):
            if self._method_exists(base, method_name, visited):
                return True
                
        return False
    
    def _infer_class_name(self, obj_node: ast.AST, local_vars: Dict[str, str]) -> Optional[str]:
        """
        Infer class name from object node.
        
        Examples:
        - self.storage.method() → StorageManager
        - storage.method() → StorageManager
        - mt5.method() → MT5Connector
        """
        if isinstance(obj_node, ast.Attribute):
            # self.storage → 'storage'
            attr_name = obj_node.attr
            
            # Check local variable tracking
            if attr_name in local_vars:
                return local_vars[attr_name]
            
            # Heuristic inference
            if 'storage' in attr_name.lower():
                return 'StorageManager'
            elif 'risk' in attr_name.lower():
                return 'RiskManager'
            elif 'executor' in attr_name.lower():
                return 'OrderExecutor'
            elif 'connector' in attr_name.lower() or 'mt5' in attr_name.lower():
                return 'MT5Connector'
            elif 'monitor' in attr_name.lower():
                return 'EdgeMonitor'
            
        elif isinstance(obj_node, ast.Name):
            # Direct variable: storage.method()
            var_name = obj_node.id
            
            if var_name in local_vars:
                return local_vars[var_name]
            
            # Heuristic inference
            if 'storage' in var_name.lower():
                return 'StorageManager'
            elif 'risk' in var_name.lower():
                return 'RiskManager'
            elif 'executor' in var_name.lower():
                return 'OrderExecutor'
        
        return None
    
    def report(self) -> int:
        """Print report and return exit code (0=OK, 1=CRITICAL ERROR)"""
        if not self.undefined_calls:
            print("\n[OK] No se encontraron llamadas a metodos indefinidos en clases del proyecto")
            return 0
        
        print(f"\n[CRITICAL ERROR] {len(self.undefined_calls)} METODOS INDEFINIDOS EN CODIGO PROPIO")
        print("=" * 80)
        print("ESTO BLOQUEARA EL DEPLOYMENT - Debe corregirse ANTES de continuar")
        print("=" * 80)
        
        # Group by file
        by_file = defaultdict(list)
        for call in self.undefined_calls:
            by_file[call['file']].append(call)
        
        for file, calls in sorted(by_file.items()):
            print(f"\nFILE: {file}")
            for call in calls:
                print(f"   Linea {call['line']:>4}: {call['call']}")
                print(f"          Clase: {call['class']}")
                print(f"          Metodo NO EXISTE: {call['method']}()")
                print(f"          Severidad: {call['severity']}")
        
        print("\n" + "=" * 80)
        print("SOLUCION OBLIGATORIA:")
        print("   1. Crear STUB del metodo primero:")
        print("      def {method}(self, ...): raise NotImplementedError()")
        print("   2. Crear TEST que use el metodo")
        print("   3. Implementar logica REAL del metodo")
        print("   4. Ejecutar: python scripts/validate_all.py")
        print("\n   NO HACER COMMIT hasta que validate_all.py pase 100%")
        print("=" * 80)
        
        return 1


def main():
    """Run undefined functions detector"""
    workspace = Path(__file__).parent.parent
    
    print("\n" + "=" * 80)
    print("[START] DETECTOR DE METODOS INDEFINIDOS (CRITICO)")
    print("=" * 80)
    print("SCOPE: Solo clases propias del proyecto (StorageManager, RiskManager, etc.)")
    print("IGNORA: Librerias externas (dict, Path, Mock, pandas, etc.)")
    print("=" * 80)
    
    detector = UndefinedFunctionDetector(workspace)
    detector.scan_workspace()
    exit_code = detector.report()
    
    if exit_code == 0:
        print("\n[OK] VALIDACION EXITOSA - No hay metodos indefinidos")
    else:
        print("\n[CRITICAL] VALIDACION FALLIDA - Corregir metodos faltantes ANTES de deployment")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
