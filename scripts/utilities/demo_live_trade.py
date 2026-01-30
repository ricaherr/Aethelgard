"""
End-to-End Trading Demo
Executes a complete trading cycle to demonstrate the feedback loop
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import logging
from datetime import datetime
import time

from models.signal import Signal, SignalType, ConnectorType
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from core_brain.monitor import ClosingMonitor
from data_vault.storage import StorageManager
from connectors.mt5_connector import get_mt5_connector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def demo_complete_trade():
    """Execute a complete trading cycle from signal to dashboard"""
    
    print("\n" + "=" * 70)
    print("🎯 AETHELGARD - End-to-End Trading Demo")
    print("=" * 70)
    print()
    
    # Step 1: Initialize components
    print("📦 Step 1: Initializing components...")
    storage = StorageManager()
    risk_manager = RiskManager(initial_capital=10000.0)
    
    # Try to connect MT5
    print()
    print("🔌 Step 2: Connecting to MT5...")
    mt5_connector = get_mt5_connector()
    
    if not mt5_connector:
        print("❌ MT5 not configured or connection failed")
        print("   Run: python scripts/setup_mt5_demo.py")
        return
    
    connectors_executor = {ConnectorType.METATRADER5: mt5_connector}
    connectors_monitor = {"MT5": mt5_connector}
    
    # Initialize executor and monitor
    executor = OrderExecutor(
        risk_manager=risk_manager,
        storage=storage,
        connectors=connectors_executor
    )
    
    monitor = ClosingMonitor(
        storage=storage,
        connectors=connectors_monitor,
        interval_seconds=30  # Check every 30s for demo
    )
    
    print()
    print("=" * 70)
    print("✅ System Ready!")
    print("=" * 70)
    print()
    
    # Step 3: Create a test signal
    print("⚡ Step 3: Creating test signal...")
    print()
    print("   Symbol: EURUSD")
    print("   Type: BUY")
    print("   Volume: 0.01 (micro lot)")
    print()
    
    # Get current price from MT5
    import MetaTrader5 as mt5
    from typing import Any, cast
    mt5 = cast(Any, mt5)
    tick = mt5.symbol_info_tick("EURUSD")
    
    if tick is None:
        print("❌ Could not get EURUSD price. Make sure symbol is in Market Watch.")
        return
    
    entry_price = tick.ask
    stop_loss = entry_price - 0.0020  # 20 pips stop loss
    take_profit = entry_price + 0.0030  # 30 pips take profit
    
    signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence=0.75,
        connector_type=ConnectorType.METATRADER5
    )
    
    print(f"   Entry: {entry_price:.5f}")
    print(f"   Stop Loss: {stop_loss:.5f} (-20 pips)")
    print(f"   Take Profit: {take_profit:.5f} (+30 pips)")
    print()
    
    # Step 4: Execute the signal
    print("🚀 Step 4: Executing signal on MT5 demo account...")
    
    success = executor.execute_signal(signal)
    
    if not success:
        print("❌ Signal execution failed!")
        return
    
    print()
    print("=" * 70)
    print("✅ TRADE EXECUTED SUCCESSFULLY!")
    print("=" * 70)
    print()
    print("The trade is now OPEN on your MT5 demo account.")
    print()
    
    # Step 5: Monitor the position
    print("👀 Step 5: Monitoring position...")
    print()
    print("Options:")
    print("   [1] Wait for automatic close (TP/SL)")
    print("   [2] Close manually now")
    print("   [3] Skip monitoring (close manually in MT5)")
    print()
    
    choice = input("Your choice [1-3]: ").strip()
    
    if choice == '2':
        # Close manually via code
        print()
        print("🔄 Closing position manually...")
        
        open_positions = mt5_connector.get_open_positions()
        
        if open_positions:
            ticket = open_positions[0]['ticket']
            if mt5_connector.close_position(ticket):
                print(f"✅ Position {ticket} closed successfully!")
                
                # Wait a moment for MT5 to register the close
                time.sleep(2)
            else:
                print("❌ Failed to close position")
        else:
            print("⚠️  No open positions found")
    
    elif choice == '1':
        # Monitor until closed
        print()
        print("⏳ Monitoring... (Press Ctrl+C to stop)")
        print()
        
        try:
            monitoring_task = asyncio.create_task(monitor.start())
            
            # Check periodically
            while True:
                open_positions = mt5_connector.get_open_positions()
                
                if not open_positions:
                    print("✅ Position closed!")
                    await monitor.stop()
                    break
                
                # Show current P&L
                pos = open_positions[0]
                print(f"   Current P&L: ${pos['profit']:+.2f}    ", end='\r')
                
                await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitoring stopped by user")
            await monitor.stop()
    
    else:
        print()
        print("⏭️  Skipped monitoring. Close the position manually in MT5.")
    
    # Step 6: Check results
    print()
    print("=" * 70)
    print("📊 Step 6: Checking for closed positions...")
    
    closed_positions = mt5_connector.get_closed_positions(hours=1)
    
    if closed_positions:
        print(f"✅ Found {len(closed_positions)} closed position(s)")
        print()
        
        for pos in closed_positions:
            print(f"   Ticket: {pos['ticket']}")
            print(f"   Symbol: {pos['symbol']}")
            print(f"   Entry: {pos['entry_price']:.5f}")
            print(f"   Exit: {pos['exit_price']:.5f}")
            print(f"   Profit: ${pos['profit']:+.2f}")
            print(f"   Reason: {pos['exit_reason']}")
            print()
        
        # Trigger monitor to update database
        print("🔄 Updating database with results...")
        updates = monitor.check_closed_positions()
        print(f"✅ Updated {updates} trade(s) in database")
    else:
        print("⚠️  No closed positions found yet")
        print("   The position might still be open, or it was closed very recently.")
    
    # Step 7: Show dashboard instructions
    print()
    print("=" * 70)
    print("📈 NEXT STEPS")
    print("=" * 70)
    print()
    print("1. Start the dashboard:")
    print("   streamlit run ui/dashboard.py --server.port 8504")
    print()
    print("2. Open in browser:")
    print("   http://localhost:8504")
    print()
    print("3. Navigate to tab:")
    print("   💰 Análisis de Activos")
    print()
    print("4. You will see:")
    print("   ✓ Real profit/loss from your trade")
    print("   ✓ Win rate statistics")
    print("   ✓ Profit by symbol")
    print("   ✓ Trade history with results")
    print()
    print("=" * 70)
    print("✅ DEMO COMPLETE!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    try:
        asyncio.run(demo_complete_trade())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
