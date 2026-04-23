#!/usr/bin/env python3
"""
Diagnostic script: Compare what's in DB vs what the endpoint returns
"""
import json
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager
from data_vault.default_instruments import DEFAULT_INSTRUMENTS_CONFIG

# Initialize storage
storage = StorageManager()

print("="*80)
print("DIAGNOSIS: Instruments Config")
print("="*80)

# 1. READ RAW FROM DB
print("\n1. RAW DATA FROM system_state TABLE")
print("-" * 80)
db_path = Path(__file__).parent.parent / "data_vault" / "global" / "aethelgard.db"
print(f"DB Path: {db_path}")
print(f"DB Exists: {db_path.exists()}")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check if table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_state'")
table_exists = cursor.fetchone() is not None
print(f"system_state table exists: {table_exists}")

if table_exists:
    cursor.execute("SELECT key, value FROM system_state WHERE key = 'instruments_config'")
    row = cursor.fetchone()

    if row:
        raw_value = row['value']
        print(f"Type of value: {type(raw_value).__name__}")
        print(f"Length: {len(raw_value)} characters")
        print(f"First 200 chars: {raw_value[:200]}")
        
        # Try to parse
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
                print(f"\n✅ JSON Parsed successfully")
                print(f"Top-level keys: {list(parsed.keys())}")
            except Exception as e:
                print(f"\n❌ JSON Parse ERROR: {e}")
                parsed = None
        else:
            parsed = raw_value
    else:
        print("❌ instruments_config NOT found in DB!")
        parsed = None
else:
    print("❌ system_state table doesn't exist in DB!")
    parsed = None

conn.close()

# 2. READ VIA StorageManager
print("\n2. VIA StorageManager.get_system_state()")
print("-" * 80)
state = storage.get_system_state()
instruments_config = state.get("instruments_config")

if instruments_config:
    print(f"Type: {type(instruments_config).__name__}")
    print(f"Top-level keys: {list(instruments_config.keys())}")
    
    # Count symbols
    total_symbols = 0
    for market, categories in instruments_config.items():
        if market.startswith("_"):
            continue
        for cat, cat_data in categories.items():
            if isinstance(cat_data, dict):
                instruments = cat_data.get("instruments", [])
                enabled = cat_data.get("enabled", False)
                actives = cat_data.get("actives", {})
                print(f"  {market}/{cat}: enabled={enabled}, instruments={len(instruments)}, actives={len(actives)}")
                total_symbols += len(instruments)
    print(f"Total symbols: {total_symbols}")
else:
    print("❌ instruments_config is None!")

# 3. COMPARE with DEFAULT
print("\n3. COMPARE WITH DEFAULT_INSTRUMENTS_CONFIG")
print("-" * 80)
default_total = 0
for market, categories in DEFAULT_INSTRUMENTS_CONFIG.items():
    if market.startswith("_"):
        continue
    for cat, cat_data in categories.items():
        instruments = cat_data.get("instruments", [])
        default_total += len(instruments)

print(f"Default: {default_total} total symbols")
print(f"Current DB: {total_symbols} total symbols")

if total_symbols != default_total:
    print(f"⚠️  MISMATCH: DB has {total_symbols}, Default has {default_total}")

# 4. CHECK METALS/spot specifically
print("\n4. METALS/spot DEEP INSPECTION")
print("-" * 80)
if instruments_config and "METALS" in instruments_config and "spot" in instruments_config["METALS"]:
    metals_spot = instruments_config["METALS"]["spot"]
    print(f"METALS/spot data:")
    for key, val in metals_spot.items():
        if key == "instruments":
            print(f"  {key}: {val}")
        elif key == "actives":
            print(f"  {key}: {val}")
        else:
            print(f"  {key}: {val}")
else:
    print("❌ METALS/spot not found!")

# 5. SIMULATE ENDPOINT
print("\n5. SIMULATE GET /instruments ENDPOINT")
print("-" * 80)

def _build_markets_response(instruments_config, all):
    """Replica of endpoint's _build_markets_response"""
    result = {}
    for market, categories in instruments_config.items():
        if market.startswith("_"):
            continue
        if not isinstance(categories, dict):
            continue
        result[market] = {}
        for cat, cat_data in categories.items():
            if not isinstance(cat_data, dict):
                continue
            if not all and not cat_data.get("enabled", False):
                continue
            instruments = cat_data.get("instruments", [])
            if not all:
                actives = cat_data.get("actives", {})
                instruments = [sym for sym in instruments if actives.get(sym, True)]
            if instruments or all:
                result[market][cat] = {
                    "description": cat_data.get("description", ""),
                    "instruments": instruments,
                    "priority": cat_data.get("priority", 0),
                    "min_score": cat_data.get("min_score", None),
                    "risk_multiplier": cat_data.get("risk_multiplier", None),
                    "enabled": cat_data.get("enabled", False),
                    "actives": cat_data.get("actives", {}),
                }
    return result

if instruments_config:
    endpoint_response = _build_markets_response(instruments_config, all=True)
    print(f"Endpoint would return markets: {list(endpoint_response.keys())}")
    
    # Count what endpoint returns
    endpoint_total = 0
    for market, categories in endpoint_response.items():
        for cat, cat_data in categories.items():
            endpoint_total += len(cat_data.get("instruments", []))
    
    print(f"Endpoint total symbols: {endpoint_total}")
    
    # Check METALS specifically
    if "METALS" in endpoint_response:
        metals = endpoint_response["METALS"]
        if "spot" in metals:
            metals_spot_ep = metals["spot"]
            print(f"Endpoint METALS/spot:")
            print(f"  enabled: {metals_spot_ep.get('enabled')}")
            print(f"  instruments: {metals_spot_ep.get('instruments')}")
            print(f"  actives: {metals_spot_ep.get('actives')}")

print("\n" + "="*80)
print("END DIAGNOSIS")
print("="*80)
