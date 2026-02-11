#!/usr/bin/env python3
"""
Backfill Trade Metadata - Retrieve SL/TP/Lots from MT5 and update DB
Fixes missing metadata in existing EXECUTED signals
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not installed")
    sys.exit(1)

def backfill_metadata():
    """Retrieve SL/TP/Lots from MT5 and update DB for existing trades"""
    
    print("\n" + "="*80)
    print("BACKFILL TRADE METADATA FROM MT5")
    print("="*80)
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ ERROR: Cannot initialize MT5: {mt5.last_error()}")
        return
    
    storage = StorageManager()
    conn = storage._get_conn()
    
    try:
        # Get all EXECUTED signals with missing metadata
        signals = conn.execute("""
            SELECT id, symbol, order_id, metadata
            FROM signals
            WHERE UPPER(status) = 'EXECUTED'
            AND order_id IS NOT NULL
        """).fetchall()
        
        if not signals:
            print("\n⚠️  No EXECUTED signals found\n")
            return
        
        print(f"\n📊 Found {len(signals)} EXECUTED signals")
        
        # Get all MT5 positions
        positions = mt5.positions_get()
        if positions is None:
            print(f"❌ ERROR getting positions: {mt5.last_error()}")
            return
        
        # Create ticket -> position mapping
        mt5_positions = {str(pos.ticket): pos for pos in positions}
        
        print(f"📊 Found {len(mt5_positions)} open positions in MT5\n")
        print("Processing...\n")
        
        updated_count = 0
        missing_count = 0
        
        for signal in signals:
            signal_id = signal[0]
            symbol = signal[1]
            order_id = str(signal[2])
            metadata_str = signal[3] or "{}"
            
            # Parse current metadata
            try:
                metadata = json.loads(metadata_str)
            except:
                metadata = {}
            
            # Check if already has SL/TP/Lots
            has_sl = metadata.get('stop_loss') is not None
            has_tp = metadata.get('take_profit') is not None
            has_lots = metadata.get('lot_size') is not None
            
            if has_sl and has_tp and has_lots:
                continue  # Already complete
            
            # Find matching MT5 position
            if order_id not in mt5_positions:
                missing_count += 1
                print(f"⚠️  Signal {signal_id[:8]}... Order {order_id} not found in MT5 (closed?)")
                continue
            
            pos = mt5_positions[order_id]
            
            # Update metadata with MT5 data
            metadata.update({
                'stop_loss': pos.sl if pos.sl != 0.0 else None,
                'take_profit': pos.tp if pos.tp != 0.0 else None,
                'lot_size': pos.volume
            })
            
            # Save updated metadata
            conn.execute("""
                UPDATE signals
                SET metadata = ?
                WHERE id = ?
            """, (json.dumps(metadata), signal_id))
            
            updated_count += 1
            print(f"✅ Updated {symbol} ({order_id}): SL={pos.sl:.5f}, TP={pos.tp:.5f}, Lots={pos.volume:.2f}")
        
        conn.commit()
        
        print("\n" + "="*80)
        print(f"✅ Updated: {updated_count} signals")
        print(f"⚠️  Not found in MT5: {missing_count} signals (likely closed)")
        print("="*80 + "\n")
        
    finally:
        storage._close_conn(conn)
        mt5.shutdown()

if __name__ == "__main__":
    backfill_metadata()
