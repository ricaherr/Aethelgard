#!/usr/bin/env python3
"""
UI QA Guard - Validation for Aethelgard Next-Gen UI (TypeScript/React)
---------------------------------------------------------------------
Verificaciones:
1. TypeScript Linting/Type Checking (tsc --noEmit)
2. Build Validation (npm run build)
"""

import os
import subprocess
import sys
from pathlib import Path

def run_ui_check():
    ui_dir = Path(__file__).parent.parent / "ui"
    
    if not ui_dir.exists():
        print("❌ Error: Carpeta 'ui' no encontrada.")
        return 1

    print(f"🚀 Ejecutando validación de UI en {ui_dir}...\n")

    # 1. Type Checking (TSC)
    print("💎 Verificando tipos TypeScript (tsc)...")
    try:
        # Usamos npx para asegurar que tsc esté disponible
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=ui_dir,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ TypeScript: OK")
        else:
            print("❌ TypeScript: FAILED")
            print(result.stdout)
            print(result.stderr)
            return 1
    except Exception as e:
        print(f"⚠️ Error ejecutando TSC: {e}")
        return 1

    # 2. Build Validation
    print("\n🏗️  Validando Build de producción...")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=ui_dir,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Build: OK")
        else:
            print("❌ Build: FAILED")
            # Mostrar solo errores
            print(result.stderr)
            return 1
    except Exception as e:
        print(f"⚠️ Error ejecutando build: {e}")
        return 1

    print("\n✨ UI QA GUARD: TODOS LOS CHEQUEOS PASADOS")
    return 0

if __name__ == "__main__":
    sys.exit(run_ui_check())
