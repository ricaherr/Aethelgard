#!/usr/bin/env python3
import sqlite3
import os

db_path = "data_vault/aethelgard.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print("=" * 60)
    print("TABLAS EN aethelgard.db:")
    print("=" * 60)
    for table in tables:
        print(f"  - {table[0]}")
    
    # Verificar específicamente si existe system_settings
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'")
    system_settings_exists = cursor.fetchone() is not None
    
    print("\n" + "=" * 60)
    print(f"¿Existe tabla 'system_settings'? {('✅ SÍ' if system_settings_exists else '❌ NO')}")
    print("=" * 60)
    
    conn.close()
else:
    print(f"❌ BD no encontrada en {db_path}")
