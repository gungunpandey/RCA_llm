import sqlite3

def alter():
    conn = sqlite3.connect('plant_dashboard_v2.db')
    cursor = conn.cursor()
    columns = [
        "rca_data VARCHAR"
    ]
    for col in columns:
        try:
            cursor.execute(f"ALTER TABLE breakdown_logs ADD COLUMN {col}")
        except sqlite3.OperationalError as e:
            print(f"Skipping {col}, maybe already exists: {e}")
    conn.commit()
    conn.close()
    print("DB altered successfully with rca_data.")

if __name__ == '__main__':
    alter()
