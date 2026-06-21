"""
Migration: add `completed_at` column to the `capas` table.

Powers Phase-3 CAPA-effectiveness insights (before/after failure comparison).

Backfill policy: existing CAPAs already marked "Completed" have no recorded
completion time, so we best-effort set completed_at = created_at for them and
print a notice. This is approximate; CAPAs completed *after* this migration get
an accurate timestamp from the app. Safe to run multiple times (idempotent).

Run:  python app/scripts/add_capa_completed_at.py
"""
import os
import sqlite3


def migrate():
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "plant_dashboard_v2.db",
    )
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Add the column if it doesn't already exist (idempotent).
    cursor.execute("PRAGMA table_info(capas);")
    cols = {row[1] for row in cursor.fetchall()}
    if "completed_at" in cols:
        print("Column 'completed_at' already exists — nothing to add.")
    else:
        print("Adding 'completed_at' column to 'capas'...")
        cursor.execute("ALTER TABLE capas ADD COLUMN completed_at DATETIME")

    # 2. Best-effort backfill for already-completed CAPAs that have no timestamp.
    cursor.execute(
        "UPDATE capas SET completed_at = created_at "
        "WHERE status = 'Completed' AND completed_at IS NULL"
    )
    backfilled = cursor.rowcount
    if backfilled:
        print(f"  Backfilled completed_at = created_at for {backfilled} "
              "already-completed CAPA(s) (approximate).")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
