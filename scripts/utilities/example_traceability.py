"""
Example: Creating signals with full traceability
Demonstrates how to create signals for different platforms, accounts, and markets.
"""
from models.signal import Signal, SignalType, ConnectorType
from data_vault.storage import StorageManager
from datetime import datetime

# Initialize storage
storage = StorageManager()

print("📊 Creating signals with full traceability...\n")

# Example 1: MT5 DEMO - Forex
signal_mt5_demo = Signal(
    symbol="EURUSD",
    signal_type=SignalType.BUY,
    confidence=0.85,
    connector_type=ConnectorType.METATRADER5,
    entry_price=1.1050,
    stop_loss=1.1000,
    take_profit=1.1150,
    volume=0.01,
    timeframe="M5",
    # Traceability
    account_id="demo-mt5-001",
    account_type="DEMO",
    market_type="FOREX",
    platform="MT5",
    order_id=None  # Will be filled after execution
)

signal_id_1 = storage.save_signal(signal_mt5_demo)
print(f"✅ MT5 DEMO Forex: {signal_id_1[:8]}...")
print(f"   {signal_mt5_demo.symbol} {signal_mt5_demo.signal_type.value} @ {signal_mt5_demo.entry_price}")
print(f"   Platform: {signal_mt5_demo.platform} | Account: {signal_mt5_demo.account_type} | Market: {signal_mt5_demo.market_type}\n")

# Example 2: MT5 REAL - Forex
signal_mt5_real = Signal(
    symbol="GBPUSD",
    signal_type=SignalType.SELL,
    confidence=0.92,
    connector_type=ConnectorType.METATRADER5,
    entry_price=1.2500,
    stop_loss=1.2550,
    take_profit=1.2400,
    volume=0.02,
    timeframe="M15",
    # Traceability
    account_id="real-mt5-001",
    account_type="REAL",
    market_type="FOREX",
    platform="MT5",
    order_id="12345678"  # Broker order ID
)

signal_id_2 = storage.save_signal(signal_mt5_real)
print(f"✅ MT5 REAL Forex: {signal_id_2[:8]}...")
print(f"   {signal_mt5_real.symbol} {signal_mt5_real.signal_type.value} @ {signal_mt5_real.entry_price}")
print(f"   Platform: {signal_mt5_real.platform} | Account: {signal_mt5_real.account_type} | Market: {signal_mt5_real.market_type}")
print(f"   Order ID: {signal_mt5_real.order_id}\n")

# Example 3: PAPER (Simulation) - Crypto
signal_paper_crypto = Signal(
    symbol="BTCUSD",
    signal_type=SignalType.BUY,
    confidence=0.78,
    connector_type=ConnectorType.PAPER,
    entry_price=50000,
    stop_loss=48000,
    take_profit=55000,
    volume=0.1,
    timeframe="1h",
    # Traceability
    account_id="paper-sim-001",
    account_type="DEMO",
    market_type="CRYPTO",
    platform="PAPER",
    order_id="SIM-001"
)

signal_id_3 = storage.save_signal(signal_paper_crypto)
print(f"✅ PAPER Crypto: {signal_id_3[:8]}...")
print(f"   {signal_paper_crypto.symbol} {signal_paper_crypto.signal_type.value} @ {signal_paper_crypto.entry_price}")
print(f"   Platform: {signal_paper_crypto.platform} | Account: {signal_paper_crypto.account_type} | Market: {signal_paper_crypto.market_type}\n")

# Example 4: NinjaTrader - Futures
signal_nt8_futures = Signal(
    symbol="NQ",  # Nasdaq Futures
    signal_type=SignalType.BUY,
    confidence=0.88,
    connector_type=ConnectorType.NINJATRADER8,
    entry_price=15000,
    stop_loss=14950,
    take_profit=15100,
    volume=1,
    timeframe="M5",
    # Traceability
    account_id="nt8-demo-001",
    account_type="DEMO",
    market_type="FUTURES",
    platform="NT8",
    order_id="NT-987654"
)

signal_id_4 = storage.save_signal(signal_nt8_futures)
print(f"✅ NT8 Futures: {signal_id_4[:8]}...")
print(f"   {signal_nt8_futures.symbol} {signal_nt8_futures.signal_type.value} @ {signal_nt8_futures.entry_price}")
print(f"   Platform: {signal_nt8_futures.platform} | Account: {signal_nt8_futures.account_type} | Market: {signal_nt8_futures.market_type}\n")

# Query signals by platform
print("\n📊 Signals by platform:")
import sqlite3
conn = sqlite3.connect("data_vault/aethelgard.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT platform, market_type, account_type, COUNT(*) as count
    FROM signals
    WHERE platform IS NOT NULL
    GROUP BY platform, market_type, account_type
    ORDER BY platform, market_type
""")

for row in cursor.fetchall():
    platform, market, acc_type, count = row
    print(f"  {platform} | {market} | {acc_type}: {count} signals")

conn.close()

print("\n✅ All signals created with full traceability!")
print("Now you can:")
print("  - Track which operations are DEMO vs REAL")
print("  - Separate Forex from Crypto performance")
print("  - Monitor multiple platforms simultaneously")
print("  - Audit operations by account ID")
