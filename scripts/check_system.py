"""
Aethelgard Pre-flight System Checker
CLI tool to verify system readiness before launch.
"""
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from core_brain.health import HealthManager

def run_check():
    print("=" * 50)
    print("🛡️  AETHELGARD PRE-FLIGHT CHECKER")
    print("=" * 50)
    
    hm = HealthManager()
    summary = hm.run_full_diagnostic()
    
    # 1. Configuration
    print(f"\n📂 CONFIGURATION: {summary['config']['status']}")
    for detail in summary['config']['details']:
        print(f"   • {detail}")
        
    # 2. Database
    print(f"\n🗄️  DATABASE: {summary['db']['status']}")
    for detail in summary['db']['details']:
        print(f"   • {detail}")
        
    # 3. Resources
    res = summary['resources']
    print(f"\n⚡ RESOURCES: {res['status']}")
    print(f"   • CPU: {res.get('cpu_percent', 'N/A')}%")
    print(f"   • Memory: {res.get('memory_mb', 'N/A'):.1f} MB")
    
    # Final Result
    print("\n" + "=" * 50)
    if summary['overall_status'] == "GREEN":
        print("✅ SYSTEM READY - LIFT OFF!")
        return 0
    elif summary['overall_status'] == "YELLOW":
        print("⚠️  SYSTEM READY WITH WARNINGS - PROCEED WITH CAUTION")
        return 0
    else:
        print("🚨 CRITICAL ERRORS DETECTED - ABORT LAUNCH")
        return 1

if __name__ == "__main__":
    sys.exit(run_check())
