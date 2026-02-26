#!/usr/bin/env python3
"""
[AUDIT] DOCUMENTATION AUDIT: Verificar la existencia y ubicación de los documentos de gobernanza.
"""
import sys
from pathlib import Path
import io

# Fix encoding for Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def check_documentation():
    workspace_root = Path(__file__).parent.parent.parent
    
    required_files = [
        "governance/BACKLOG.md",
        "governance/ROADMAP.md",
        "governance/SPRINT.md",
        "docs/AETHELGARD_MANIFESTO.md",
        "docs/DEVELOPMENT_GUIDELINES.md",
        "docs/SYSTEM_LEDGER.md"
    ]
    
    issues = []
    
    print("\n" + "="*80)
    print("📋 AETHELGARD DOCUMENTATION AUDIT")
    print("="*80)
    
    for rel_path in required_files:
        full_path = workspace_root / rel_path
        if full_path.exists():
            print(f"✅ FOUND: {rel_path}")
        else:
            issues.append(f"❌ MISSING: {rel_path}")
            
    if not issues:
        print("\n✨ SUCCESS: All governance and engineering documents are in their correct locations.")
        return 0
    else:
        print(f"\n🛑 FAILED: {len(issues)} critical documents are missing or misplaced.")
        for issue in issues:
            print(f"  {issue}")
        return 1

if __name__ == "__main__":
    sys.exit(check_documentation())
