import sqlite3
from pathlib import Path

db_path = Path("aethelgard.db")
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("Tables in aethelgard.db:")
for table in tables:
    print(f"  - {table[0]}")

# Check if system_state exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_state'")
exists = cursor.fetchone() is not None
print(f"\nsystem_state exists: {exists}")

conn.close()
