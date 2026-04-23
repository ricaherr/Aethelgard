"""
Force initialization of DB schema and verify persistence
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager
from data_vault.schema import initialize_schema
import sqlite3
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("="*80)
print("FORCING BD INITIALIZATION")
print("="*80)

# Create StorageManager (this should initialize schema)
print("\n1. Creating StorageManager...")
try:
    storage = StorageManager()
    print("✅ StorageManager created")
except Exception as e:
    print(f"❌ Error creating StorageManager: {e}")
    import traceback
    traceback.print_exc()

# Check if tables exist NOW
print("\n2. Checking tables in aethelgard.db...")
db_path = Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db"
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()

        print(f"Tables found: {len(tables)}")
        for table in tables[:10]:  # Show first 10
            print(f"  - {table[0]}")
        if len(tables) > 10:
            print(f"  ... and {len(tables) - 10} more")
    finally:
        conn.close()
else:
    print(f"❌ Database file not found at {db_path}")

# Try to read instruments_config from system state
print("\n3. Trying to read instruments_config via StorageManager...")
try:
    state = storage.get_system_state()
    if "instruments_config" in state:
        config = state["instruments_config"]
        print(f"✅ instruments_config found")
        print(f"   Type: {type(config).__name__}")
        if isinstance(config, dict):
            markets = [k for k in config.keys() if not k.startswith("_")]
            print(f"   Markets: {markets}")
    else:
        print(f"⚠️  instruments_config NOT in system_state")
        print(f"   Available keys: {list(state.keys())}")
except Exception as e:
    print(f"❌ Error reading system_state: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
