
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join("data_vault", "aethelgard.db")

def check_usdcad_signals() -> None:
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")
        print(f"Checking USDCAD signals for {today}...")
        
        # Query specific to USDCAD
        query = "SELECT * FROM signals WHERE timestamp LIKE ? AND symbol = 'USDCAD' ORDER BY timestamp DESC"
        cursor.execute(query, (f"{today}%",))
        
        rows = cursor.fetchall()
        
        if not rows:
            print("No USDCAD signal registered for today.")
        else:
            print(f"Found {len(rows)} USDCAD signals for today:")
            print("-" * 120)
            print(f"{'Time':<20} | {'ID':<36} | {'Type':<6} | {'Status':<10} | {'Score'} | {'Strategy'}")
            print("-" * 120)
            for row in rows:
                row_dict = dict(row)
                time_str = row_dict.get('timestamp', '')
                sig_id = row_dict.get('id', '')
                metadata_str = row_dict.get('metadata')
                strategy = "N/A"
                if metadata_str:
                    try:
                        meta = json.loads(metadata_str)
                        strategy = meta.get('strategy', 'N/A')
                    except:
                        pass
                
                sig_type = row_dict.get('signal_type', 'N/A')
                status = row_dict.get('status', 'N/A')
                score = row_dict.get('confidence', 0)
                
                print(f"{time_str:<20} | {sig_id:<36} | {sig_type:<6} | {status:<10} | {round(score,4):<5} | {strategy}")
                
        # Also, check for exact duplicates (timestamp + type)
        cursor.execute("SELECT timestamp, signal_type, COUNT(*) as count FROM signals WHERE symbol = 'USDCAD' AND timestamp LIKE ? GROUP BY timestamp, signal_type HAVING count > 1", (f"{today}%",))
        dupes = cursor.fetchall()
        if dupes:
            print("\nDUPLICATE GROUPS FOUND:")
            for d in dupes:
                print(f"Time: {d['timestamp']} | Type: {d['signal_type']} | Count: {d['count']}")
                
        conn.close()

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    check_usdcad_signals()
