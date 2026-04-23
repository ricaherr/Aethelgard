import sqlite3
from pathlib import Path

# Ruta oficial: data_vault/global/aethelgard.db
db_path = Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db"
conn = sqlite3.connect(str(db_path))
try:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    print("Tables in aethelgard.db:")
    for table in tables:
        print(f"  - {table[0]}")

    # Check if sys_config exists (current schema)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_config'")
    exists = cursor.fetchone() is not None
    print(f"\nsys_config exists: {exists}")
finally:
    conn.close()
