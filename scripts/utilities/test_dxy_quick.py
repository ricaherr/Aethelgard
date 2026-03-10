#!/usr/bin/env python3
"""Quick DXY validation test"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from connectors.generic_data_provider import get_provider
import logging

logging.basicConfig(level=logging.WARNING)

print("\n" + "="*60)
print("🧪 DXY Data Retrieval Test")
print("="*60)

try:
    provider = get_provider()
    print("\n📥 Fetching DXY from Yahoo Finance...")
    df = provider.fetch_ohlc('DXY', 'D1', 20)
    
    if df is not None and not df.empty:
        print(f"\n✅ SUCCESS!")
        print(f"   Candles obtained: {len(df)}")
        print(f"   Latest Close: {df.iloc[-1]['close']:.2f}")
        print(f"   20-day MA: {df['close'].rolling(20).mean().iloc[-1]:.2f}")
        print(f"   Date range: {df.index[0]} to {df.index[-1]}")
    else:
        print("\n⚠️  WARNING: No DXY data received from Yahoo Finance")
        print("   This is expected if Yahoo is rate-limited")
        print("   Ensure fallback providers are configured (Alpha Vantage, Twelve Data)")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("   Stack trace:")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
