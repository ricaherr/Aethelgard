import sqlite3
from pathlib import Path

# Correct DB path
db_path = Path("data_vault/aethelgard.db")
print(f"DB Path: {db_path}")
print(f"DB Exists: {db_path.exists()}")
print()

if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get instruments_config value directly
    cursor.execute("SELECT length(value), substr(value, 1, 200) FROM system_state WHERE key = 'instruments_config'")
    row = cursor.fetchone()
    
    if row:
        length, sample = row
        print(f"✅ instruments_config FOUND in BD")
        print(f"Length of value: {length} characters")
        print(f"First 200 chars:\n{sample}\n")
        
        # Get full value  
        cursor.execute("SELECT value FROM system_state WHERE key = 'instruments_config'")
        full_value = cursor.fetchone()[0]
        
        # Try to parse
        import json
        try:
            config = json.loads(full_value)
            print(f"✅ JSON parsed successfully")
            print(f"Top-level keys: {list(config.keys())}")
            
            # Check METALS specifically
            if "METALS" in config and "spot" in config["METALS"]:
                metals_spot = config["METALS"]["spot"]
                print(f"\nMETALS/spot in DB:")
                print(f"  enabled: {metals_spot.get('enabled')}")
                print(f"  instruments: {metals_spot.get('instruments')}")
                print(f"  actives: {metals_spot.get('actives')}")
        except Exception as e:
            print(f"❌ JSON parse error: {e}")
    else:
        print(f"❌ instruments_config NOT found in system_state")
    
    conn.close()
else:
    print(f"❌ DB not found at {db_path}")
