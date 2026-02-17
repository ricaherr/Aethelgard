
import sqlite3
import json
import os

DB_PATH = r"c:\Users\Jose Herrera\Documents\Proyectos\Aethelgard\data_vault\aethelgard.db"

def check_modules_state() -> None:
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT value FROM system_state WHERE key = 'modules_enabled'")
        row = cursor.fetchone()
        
        if row:
            value = row[0]
            try:
                modules = json.loads(value)
                print("Current 'modules_enabled' state in DB:")
                print(json.dumps(modules, indent=2))
                
                executor_status = modules.get('executor', 'Not Set (Default: True)')
                print(f"\nExecutor Status: {executor_status}")
                
            except json.JSONDecodeError:
                print(f"Raw value (not JSON): {value}")
        else:
            print("No 'modules_enabled' key found in system_state table. System using defaults.")
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_modules_state()
