"""
Reset Circuit Breaker Utility

Use this script to manually reset the position size circuit breaker
after resolving the underlying issue (e.g., MT5 connection restored).

Usage:
    python scripts/utilities/reset_circuit_breaker.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager
from connectors.mt5_connector import MT5Connector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Reset circuit breaker and verify system health"""
    
    print("\n" + "="*80)
    print("AETHELGARD - Circuit Breaker Reset Utility")
    print("="*80 + "\n")
    
    # 1. Verify MT5 connection
    print("📡 Step 1: Verifying MT5 connection...")
    try:
        mt5 = MT5Connector()
        if mt5.connect_blocking():
            balance = mt5.get_account_balance()
            print(f"   ✅ MT5 Connected | Balance: ${balance:,.2f}")
        else:
            print("   ❌ MT5 Connection FAILED")
            print("   ⚠️  Circuit breaker reset aborted - fix MT5 connection first")
            return
    except Exception as e:
        print(f"   ❌ Error connecting to MT5: {e}")
        print("   ⚠️  Circuit breaker reset aborted")
        return
    
    # 2. Initialize RiskManager
    print("\n🧠 Step 2: Initializing RiskManager...")
    try:
        storage = StorageManager()
        risk_manager = RiskManager(storage=storage, initial_capital=10000.0)
        
        # Check current state
        monitor = risk_manager.monitor
        metrics = monitor.get_health_metrics()
        
        print(f"   Total Calculations: {metrics['total_calculations']}")
        print(f"   Success Rate: {metrics['success_rate']:.1f}%")
        print(f"   Consecutive Failures: {monitor.consecutive_failures}")
        print(f"   Circuit Breaker: {'ACTIVE ❌' if metrics['circuit_breaker_active'] else 'OK ✅'}")
        
        # 3. Reset circuit breaker if active
        if metrics['circuit_breaker_active']:
            print(f"\n🔧 Step 3: Resetting circuit breaker...")
            print(f"   Previous failures: {monitor.consecutive_failures}")
            
            monitor.force_reset_circuit_breaker()
            
            print(f"   ✅ Circuit breaker RESET successfully")
            print(f"   New consecutive failures: {monitor.consecutive_failures}")
            
            # Verify reset
            new_metrics = monitor.get_health_metrics()
            if not new_metrics['circuit_breaker_active']:
                print("\n✨ SUCCESS: System ready for trading")
                print("   Circuit breaker is now INACTIVE")
                print("   Trading operations will resume normally")
            else:
                print("\n⚠️  WARNING: Circuit breaker still active after reset")
        else:
            print(f"\n✅ Step 3: Circuit breaker not active - no reset needed")
        
        # 4. Display current statistics
        print("\n📊 Current System Statistics:")
        print(f"   - Total Calculations: {metrics['total_calculations']}")
        print(f"   - Successful: {metrics['successful']}")
        print(f"   - Failed: {metrics['failed']}")
        print(f"   - Success Rate: {metrics['success_rate']:.1f}%")
        
        print("\n" + "="*80)
        print("Reset complete. Restart the system to resume trading.")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Failed to reset circuit breaker", exc_info=True)


if __name__ == "__main__":
    main()
