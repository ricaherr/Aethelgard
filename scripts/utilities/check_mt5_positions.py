#!/usr/bin/env python3
"""
Check MT5 Positions - Verify if SL/TP are configured in MetaTrader 5
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not installed")
    sys.exit(1)

def check_mt5_positions():
    """Check MT5 open positions to verify SL/TP configuration"""
    
    print("\n" + "="*80)
    print("CHECKING MT5 OPEN POSITIONS")
    print("="*80)
    
    # Initialize MT5 connection
    if not mt5.initialize():
        print(f"❌ ERROR: Cannot initialize MT5: {mt5.last_error()}")
        return
    
    try:
        # Get account info
        account_info = mt5.account_info()
        if account_info:
            print(f"\n📊 Account: #{account_info.login} | Balance: ${account_info.balance:.2f}")
        
        # Get all open positions
        positions = mt5.positions_get()
        
        if positions is None:
            print(f"❌ ERROR getting positions: {mt5.last_error()}")
            return
        
        if len(positions) == 0:
            print("\n⚠️  NO OPEN POSITIONS IN MT5\n")
            return
        
        print(f"\n   TOTAL: {len(positions)} open positions\n")
        print(f"{'Ticket':<12} {'Symbol':<10} {'Type':<6} {'Volume':<8} {'Entry':<12} {'SL':<12} {'TP':<12} {'Profit':<12}")
        print("-" * 100)
        
        missing_sl = 0
        missing_tp = 0
        
        for pos in positions:
            ticket = pos.ticket
            symbol = pos.symbol
            pos_type = "BUY" if pos.type == 0 else "SELL"
            volume = f"{pos.volume:.2f}"
            entry = f"{pos.price_open:.5f}"
            sl = f"{pos.sl:.5f}" if pos.sl and pos.sl != 0.0 else "NONE"
            tp = f"{pos.tp:.5f}" if pos.tp and pos.tp != 0.0 else "NONE"
            profit = f"${pos.profit:.2f}"
            
            if not pos.sl or pos.sl == 0.0:
                missing_sl += 1
            if not pos.tp or pos.tp == 0.0:
                missing_tp += 1
            
            print(f"{ticket:<12} {symbol:<10} {pos_type:<6} {volume:<8} {entry:<12} {sl:<12} {tp:<12} {profit:<12}")
        
        print("\n" + "-" * 80)
        print(f"Positions without SL: {missing_sl} {'CRITICAL - UNLIMITED RISK' if missing_sl > 0 else 'OK'}")
        print(f"Positions without TP: {missing_tp} {'WARNING - NO EXIT PLAN' if missing_tp > 0 else 'OK'}")
        print("="*80 + "\n")
        
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    check_mt5_positions()
