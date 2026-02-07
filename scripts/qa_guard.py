#!/usr/bin/env python3
"""
QA Guard - Análisis Estático Profesional para Aethelgard
------------------------------------------------------
Verificaciones:
1. Sintaxis: Errores de compilación.
2. Type Hints: Obligatorios en argumentos y retorno (excepto tests/scripts).
3. Agnosticismo: MetaTrader5 solo permitido en /connectors.
"""

import os
import ast
import sys
from pathlib import Path
from typing import List, Tuple, Optional

def find_python_files(root_dir: Path) -> List[Path]:
    """Encuentra archivos .py excluyendo entornos virtuales y basura."""
    python_files = []
    exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'node_modules', 'build', 'dist', 'ui/node_modules', 'ui/dist'}
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith('.py'):
                python_files.append(Path(root) / file)
    return python_files

def check_syntax(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Verifica si el archivo es sintácticamente válido."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            ast.parse(f.read(), filename=str(file_path))
        return True, None
    except SyntaxError as e:
        return False, f"Línea {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Error de lectura: {e}"

def check_type_hints(file_path: Path) -> List[str]:
    """Verifica la presencia de Type Hints en funciones y métodos."""
    # Excluir carpetas que no requieren tipado estricto
    if any(part in file_path.parts for part in ['tests', 'scripts']):
        return []

    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Ignorar constructor si no tiene hints (es común)
                if node.name == '__init__': continue
                
                # Verificar argumentos (excluyendo 'self' y 'cls')
                args_missing = [
                    arg.arg for arg in node.args.args 
                    if arg.annotation is None and arg.arg not in ['self', 'cls']
                ]
                # Verificar retorno
                ret_missing = node.returns is None
                
                if args_missing or ret_missing:
                    detail = f"Faltan hints en: {node.name}"
                    if args_missing: detail += f" (args: {args_missing})"
                    if ret_missing: detail += " (retorno -> None o Type)"
                    issues.append(f"{file_path.name}: {detail}")
    except Exception:
        pass # Los errores de parseo se capturan en check_syntax
    return issues

def check_agnosticism(file_path: Path) -> List[str]:
    """Asegura que MetaTrader5 solo se use en /connectors."""
    if 'connectors' in file_path.parts or file_path.name == 'qa_guard.py':
        return []

    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            # Check 'import MetaTrader5'
            if isinstance(node, ast.Import):
                for name in node.names:
                    if 'MetaTrader5' in name.name:
                        issues.append(f"Import prohibido: '{name.name}'")
            # Check 'from MetaTrader5 import ...'
            if isinstance(node, ast.ImportFrom) and node.module and 'MetaTrader5' in node.module:
                issues.append(f"ImportFrom prohibido: '{node.module}'")
    except Exception:
        pass
    return issues

def main():
    project_root = Path(__file__).parent.parent
    files = find_python_files(project_root)
    
    all_passed = True
    print(f"🚀 Aethelgard QA Guard | Analizando {len(files)} archivos...\n")

    for f in files:
        rel_path = f.relative_to(project_root)
        
        # 1. Sintaxis (Crítico)
        syn_ok, syn_err = check_syntax(f)
        if not syn_ok:
            print(f"❌ SINTAXIS: {rel_path} -> {syn_err}")
            all_passed = False
            continue # Si no compila, no seguimos con este archivo

        # 2. Agnosticismo (Crítico)
        ag_issues = check_agnosticism(f)
        for issue in ag_issues:
            print(f"🚫 ESTRUCTURA: {rel_path} -> {issue}")
            all_passed = False

        # 3. Type Hints (Obligatorio)
        hint_issues = check_type_hints(f)
        for issue in hint_issues:
            print(f"❌ TYPE HINT: {rel_path} -> {issue}")
            all_passed = False 

    print("\n" + "="*40)
    if all_passed:
        print("✅ PROYECTO LIMPIO: Listo para producción.")
        sys.exit(0)
    else:
        print("❌ FALLÓ: Revisa los errores arriba antes de continuar.")
        sys.exit(1)

if __name__ == "__main__":
    main()