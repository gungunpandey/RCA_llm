import os
import sys
import json
import sqlite3

# Add parent directory to path so we can import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import normalize_full_owner_string

def migrate():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plant_dashboard_v2.db")
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Migrate capas table
    print("Migrating 'capas' table...")
    cursor.execute("SELECT id, owner FROM capas")
    capas = cursor.fetchall()
    updated_capas = 0

    for capa_id, owner in capas:
        if owner:
            normalized = normalize_full_owner_string(owner)
            if normalized != owner:
                cursor.execute("UPDATE capas SET owner = ? WHERE id = ?", (normalized, capa_id))
                updated_capas += 1
                print(f"  CAPA {capa_id}: {repr(owner)} -> {repr(normalized)}")

    # 2. Migrate breakdown_logs table (rca_data field)
    print("Migrating 'breakdown_logs' table (rca_data field)...")
    cursor.execute("SELECT id, rca_data FROM breakdown_logs WHERE rca_data IS NOT NULL AND rca_data != ''")
    logs = cursor.fetchall()
    updated_logs = 0

    for log_id, rca_data in logs:
        try:
            parsed = json.loads(rca_data)
            changed = False
            
            # Format 1: dict with "capa" array
            if isinstance(parsed, dict) and "capa" in parsed and isinstance(parsed["capa"], list):
                for item in parsed["capa"]:
                    if isinstance(item, dict) and "responsibility" in item:
                        resp = item["responsibility"]
                        if resp:
                            normalized = normalize_full_owner_string(resp)
                            if normalized != resp:
                                item["responsibility"] = normalized
                                changed = True
                                print(f"  Log {log_id} (RCA CAPA): {repr(resp)} -> {repr(normalized)}")
            
            if changed:
                new_rca_data = json.dumps(parsed)
                cursor.execute("UPDATE breakdown_logs SET rca_data = ? WHERE id = ?", (new_rca_data, log_id))
                updated_logs += 1
        except Exception as e:
            print(f"  Error parsing/migrating rca_data for Log {log_id}: {e}")

    conn.commit()
    conn.close()
    
    print("\nMigration summary:")
    print(f"  - Updated {updated_capas} records in 'capas' table.")
    print(f"  - Updated {updated_logs} records in 'breakdown_logs' table.")

if __name__ == "__main__":
    migrate()
