#!/usr/bin/env python3
"""
UI QA Guard - Validation for Aethelgard Next-Gen UI (TypeScript/React)
---------------------------------------------------------------------
Verificaciones:
1. JSX/TSX Syntax Validation (Detección de comentarios mal formados)
2. TypeScript Type Checking (tsc --noEmit)
3. Build Validation (npm run build)
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Configure UTF-8 encoding for Windows terminal (fix emoji display)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def check_jsx_syntax_errors(ui_dir: Path) -> List[Tuple[Path, int, str]]:
    """
    Detect common JSX syntax errors:
    - Malformed JSX comments: {/* ... */}
    - Unclosed tags
    - Invalid comment patterns
    """
    errors = []
    jsx_files = list((ui_dir / "src").rglob("*.tsx")) + list((ui_dir / "src").rglob("*.jsx"))
    
    for file_path in jsx_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, start=1):
                # Detect malformed JSX comments
                # Pattern: {/* ... broken ... */} or {/* ... 'string ... */}
                if re.search(r"\{/\*.*?['\"].*?\*/\}", line):
                    errors.append((file_path, line_num, f"Possible malformed JSX comment: {line.strip()[:80]}"))
                
                # Detect unterminated JSX comment blocks
                if line.strip().startswith("{/*") and not "*/" in line:
                    # Check if closing is in next lines (multi-line comment)
                    is_multiline = False
                    for check_line in lines[line_num:min(line_num+5, len(lines))]:
                        if "*/" in check_line:
                            is_multiline = True
                            break
                    if not is_multiline:
                        errors.append((file_path, line_num, f"Unclosed JSX comment: {line.strip()[:80]}"))
        
        except Exception as e:
            errors.append((file_path, 0, f"Error reading file: {e}"))
    
    return errors

def run_ui_check():
    ui_dir = Path(__file__).parent.parent / "ui"
    
    if not ui_dir.exists():
        print("❌ Error: Carpeta 'ui' no encontrada.")
        return 1

    print(f"🚀 UI QA GUARD - Aethelgard Next-Gen UI Validation")
    print(f"📂 UI Directory: {ui_dir}\n")
    
    total_errors = 0

    # 1. JSX Syntax Validation (Custom Checks)
    print("="*80)
    print("📝 [1/3] JSX/TSX Syntax Validation")
    print("="*80)
    jsx_errors = check_jsx_syntax_errors(ui_dir)
    if jsx_errors:
        print(f"❌ Found {len(jsx_errors)} JSX syntax issue(s):")
        for file_path, line_num, error in jsx_errors:
            rel_path = file_path.relative_to(ui_dir)
            print(f"  • {rel_path}:{line_num} - {error}")
        total_errors += len(jsx_errors)
    else:
        print("✅ JSX Syntax: CLEAN")

    # 2. Type Checking (TSC)
    print("\n" + "="*80)
    print("💎 [2/3] TypeScript Type Checking (tsc --noEmit)")
    print("="*80)
    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--pretty"],
            cwd=ui_dir,
            shell=True,
            capture_output=False,  # Show output in real-time
            text=True
        )
        if result.returncode == 0:
            print("✅ TypeScript Types: OK")
        else:
            print(f"❌ TypeScript: FAILED (exit code {result.returncode})")
            total_errors += 1
    except Exception as e:
        print(f"⚠️ Error ejecutando TSC: {e}")
        total_errors += 1

    # 3. Build Validation
    print("\n" + "="*80)
    print("🏗️  [3/3] Production Build Validation")
    print("="*80)
    try:
        # Use PIPE and communicate() to avoid blocking
        process = subprocess.Popen(
            ["npm", "run", "build"],
            cwd=ui_dir,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=45)  # 45s timeout
        
        if process.returncode == 0:
            print("✅ Build: SUCCESS")
            # Show build stats
            for line in stdout.split('\n'):
                if 'dist/' in line or 'built in' in line:
                    print(f"   {line.strip()}")
        else:
            print("❌ Build: FAILED")
            print("\n--- Build Errors ---")
            if stderr:
                print(stderr)
            if stdout:
                print(stdout)
            total_errors += 1
    except subprocess.TimeoutExpired:
        print("❌ Build: TIMEOUT (>45s)")
        process.kill()
        total_errors += 1
    except Exception as e:
        print(f"⚠️ Error ejecutando build: {e}")
        total_errors += 1

    # Summary
    print("\n" + "="*80)
    if total_errors == 0:
        print("✨ UI QA GUARD: ALL CHECKS PASSED")
        print("="*80)
        return 0
    else:
        print(f"❌ UI QA GUARD: {total_errors} ERROR(S) DETECTED")
        print("="*80)
        return 1

if __name__ == "__main__":
    sys.exit(run_ui_check())
