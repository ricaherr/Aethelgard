"""
Check for duplicate data in database and show statistics.
"""
import sqlite3
from pathlib import Path

db_path = Path("data_vault/aethelgard.db")

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check signals
cursor.execute('SELECT COUNT(*) FROM signals')
total_signals = cursor.fetchone()[0]
print(f"📊 Total signals: {total_signals}")

# Check for exact duplicates (same symbol, type, timestamp)
cursor.execute('''
    SELECT symbol, signal_type, timestamp, COUNT(*) as count 
    FROM signals 
    GROUP BY symbol, signal_type, timestamp 
    HAVING count > 1
''')
exact_dups = cursor.fetchall()
print(f"🔍 Exact duplicate signals: {len(exact_dups)}")
for dup in exact_dups[:10]:
    print(f"  - {dup[0]} {dup[1]} @ {dup[2]} ({dup[3]} copies)")

# Check signals without connector info
cursor.execute('SELECT COUNT(*) FROM signals WHERE metadata NOT LIKE "%connector%"')
no_connector = cursor.fetchone()[0]
print(f"\n⚠️  Signals without connector info: {no_connector}")

# Check signals without account info
cursor.execute('SELECT COUNT(*) FROM signals WHERE metadata NOT LIKE "%account%"')
no_account = cursor.fetchone()[0]
print(f"⚠️  Signals without account info: {no_account}")

# Check trades
cursor.execute('SELECT COUNT(*) FROM trades')
total_trades = cursor.fetchone()[0]
print(f"\n📊 Total trades: {total_trades}")

# Check trades without platform info
cursor.execute('SELECT COUNT(*) FROM trades')
print(f"📊 Trades in database: {total_trades}")

conn.close()
