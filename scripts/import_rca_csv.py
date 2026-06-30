"""
scripts/import_rca_csv.py
=========================
One-time script to seed the SQLite database with historical RCA records
from the confidential CSV files.

Run ONCE on the production EC2 server after first deploy:

    python scripts/import_rca_csv.py --csv-dir /opt/rca_data/csv

The script is SAFE to re-run — it checks for existing serial numbers and
skips duplicates. No data will be overwritten.

Usage:
    python scripts/import_rca_csv.py                          # uses default paths
    python scripts/import_rca_csv.py --csv-dir /opt/rca_data/csv
    python scripts/import_rca_csv.py --db-path /opt/rca_data/db/plant_dashboard_v2.db
    python scripts/import_rca_csv.py --dry-run               # preview without writing
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Allow running from project root or scripts/ directory ──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Import app models ──────────────────────────────────────────────────────
try:
    from database import Base, BreakdownLog, User, init_db
except ImportError:
    print("ERROR: Could not import database.py. Make sure you're running from the project root.")
    print("       python scripts/import_rca_csv.py")
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────
DEFAULT_CSV_DIR = PROJECT_ROOT / "app" / "data"
DEFAULT_DB_PATH = PROJECT_ROOT / "app" / "plant_dashboard_v2.db"

# Map CSV division names → exact values used in the app
# (must match users.division values for access filtering to work)
DIVISION_MAP = {
    "BNFC": "BNFC",
    "CPP 2": "CPP 2",
    "CPP-2": "CPP 2",
    "CPP2": "CPP 2",
    "DRI": "DRI",
    "DRI-650": "DRI-650",
    "DRI650": "DRI-650",
    "FIRE SERVICE": "FIRE SERVICE",
    "Pellet 1": "Pellet 1",
    "P1": "Pellet 1",
    "Pellet 2": "Pellet 2",
    "P2": "Pellet 2",
    "PGP": "PGP",
    "POWER PLANT": "POWER PLANT",
    "PP": "POWER PLANT",
    "SMS-1": "SMS-1",
    "SMS-2": "SMS-2",
}

STATUS_MAP = {
    "Completed": "Completed",
    "completed": "Completed",
    "Incomplete": "Incomplete",
    "incomplete": "Incomplete",
    "Preventive": "Preventive",
    "preventive": "Preventive",
    "In Progress": "In Progress",
    "Open": "Open",
}


def clean_currency(value: str) -> float | None:
    """Parse '₹3,600,000' or '₹ 5184000 /year' → float or None."""
    if not value or value.strip() in ("-", "--", "---", ""):
        return None
    # Remove currency symbol, commas, spaces, and anything after /
    cleaned = re.sub(r"[₹,\s]", "", value.split("/")[0])
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def clean_float(value: str) -> float | None:
    """Parse downtime strings like '2.3', '288', '0.13', '-' → float or None."""
    if not value or value.strip() in ("-", "--", "---", "0", ""):
        return None
    # Extract first number found
    match = re.search(r"[\d.]+", value)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def parse_date(value: str) -> datetime | None:
    """Try multiple date formats used across the CSVs."""
    if not value or value.strip() in ("-", "--", ""):
        return None
    value = value.strip().split("\n")[0].strip()  # take first line if multiline
    formats = [
        "%d-%b-%Y",   # 20-Nov-2022
        "%d/%m/%Y",   # 20/11/2022
        "%d-%m-%Y",   # 20-11-2022
        "%Y-%m-%d",   # 2022-11-20
        "%b-%Y",      # Nov-2022
        "%d %b %Y",   # 20 Nov 2022
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def normalize_division(raw: str) -> str:
    """Map raw CSV division to canonical app division name."""
    raw = raw.strip()
    return DIVISION_MAP.get(raw, raw)  # return as-is if not in map


def normalize_status(raw: str) -> str:
    """Map raw CSV status to canonical app status."""
    raw = raw.strip() if raw else ""
    return STATUS_MAP.get(raw, "Completed")  # default completed for historical data


def import_rca_tracker(csv_path: Path, session, dry_run: bool, system_user_id: int) -> tuple[int, int]:
    """Import RCA_TRACKER.csv. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0

    print(f"\n📄 Processing: {csv_path.name}")

    with open(csv_path, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            serial_no = row.get("RCA Serial No.", "").strip()
            if not serial_no:
                continue

            # Skip if already exists (idempotency check on extended_info)
            existing = session.query(BreakdownLog).filter(
                BreakdownLog.extended_info.like(f'%"serial_no": "{serial_no}"%')
            ).first()
            if existing:
                skipped += 1
                continue

            division = normalize_division(row.get("Division", ""))
            equipment = row.get("Equipment", "").strip().replace("\n", " ")
            description = row.get("Event Description/ Problem Statement", "").strip().replace("\n", " ")
            root_cause = row.get("Root Cause", "").strip().replace("\n", " ")
            actions = row.get("Actions", "").strip().replace("\n", " ")
            capa_type = row.get("CAPA", "").strip()
            status = normalize_status(row.get("Status", ""))
            responsibility = row.get("Responsibility", "").strip().replace("\n", " ")
            remarks = row.get("Remarks", "").strip().replace("\n", " ")
            target_date = row.get("Target date", "").strip()

            revenue_loss = clean_currency(row.get("Impact on topline (Rs.)", ""))
            downtime = clean_float(row.get("Downtime (hrs)", ""))

            failure_date = parse_date(row.get("Failure Date", ""))
            rca_date = parse_date(row.get("RCA Date", ""))
            actual_complete = parse_date(row.get("Actual Complete Date", ""))

            # Build a lightweight RCA data blob from existing CSV fields
            rca_data = None
            if root_cause or actions:
                rca_data = json.dumps({
                    "type": "csv_import",
                    "source": "RCA_TRACKER.csv",
                    "serial_no": serial_no,
                    "root_cause": root_cause,
                    "actions": actions,
                    "capa_type": capa_type,
                    "responsibility": responsibility,
                    "target_date": target_date,
                    "remarks": remarks,
                })

            extended = json.dumps({
                "serial_no": serial_no,
                "rca_report_ref": row.get("RCA Report", "").strip(),
                "hd": row.get("HD  (Y/N)", "").strip(),
            })

            log = BreakdownLog(
                machine_name=equipment[:200] if equipment else "Unknown",
                component_name=None,
                division=division,
                description=description[:1000] if description else f"RCA {serial_no}",
                downtime_minutes=int(downtime * 60) if downtime else 0,
                mttr_hours=downtime,
                revenue_loss=revenue_loss,
                status=status,
                logged_at=rca_date or failure_date or datetime.utcnow(),
                start_time=failure_date,
                end_time=actual_complete,
                rca_data=rca_data,
                extended_info=extended,
                author_id=system_user_id,
            )

            if not dry_run:
                session.add(log)

            inserted += 1

            if row_num % 10 == 0:
                print(f"   ... processed row {row_num}")

    if not dry_run:
        session.commit()

    print(f"   ✅ {csv_path.name}: {inserted} inserted, {skipped} skipped (already exist)")
    return inserted, skipped


def import_bd_rca_data(csv_path: Path, session, dry_run: bool, system_user_id: int) -> tuple[int, int]:
    """Import 'Pellet, BNFC, PGP - BD & RCA data.csv'. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0

    print(f"\n📄 Processing: {csv_path.name}")

    with open(csv_path, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        print(f"   Detected columns: {headers[:8]}...")

        for row_num, row in enumerate(reader, start=2):
            # This CSV may have different column names — use flexible lookup
            serial = (
                row.get("Sl No.", "") or row.get("Sl No", "") or
                row.get("Serial No", "") or str(row_num)
            ).strip()

            description = (
                row.get("Event Description/ Problem Statement", "") or
                row.get("Problem Statement", "") or
                row.get("Description", "") or ""
            ).strip().replace("\n", " ")

            if not description:
                continue

            # Idempotency — check by description snippet + source marker
            snippet = description[:80]
            existing = session.query(BreakdownLog).filter(
                BreakdownLog.description.like(f"%{snippet[:40]}%"),
                BreakdownLog.extended_info.like('%"source": "BD_RCA_data.csv"%'),
            ).first()
            if existing:
                skipped += 1
                continue

            division_raw = (
                row.get("Division", "") or row.get("Plant", "") or ""
            ).strip()
            division = normalize_division(division_raw)

            equipment = (
                row.get("Equipment", "") or row.get("Machine", "") or ""
            ).strip().replace("\n", " ")

            revenue_loss = clean_currency(
                row.get("Impact on topline (Rs.)", "") or
                row.get("Revenue Loss", "") or ""
            )
            downtime = clean_float(
                row.get("Downtime (hrs)", "") or row.get("Downtime", "") or ""
            )
            root_cause = (
                row.get("Root Cause", "") or ""
            ).strip().replace("\n", " ")
            actions = (
                row.get("Actions", "") or row.get("CAPA", "") or ""
            ).strip().replace("\n", " ")
            status = normalize_status(row.get("Status", "Completed"))

            rca_data = None
            if root_cause or actions:
                rca_data = json.dumps({
                    "type": "csv_import",
                    "source": "BD_RCA_data.csv",
                    "root_cause": root_cause,
                    "actions": actions,
                })

            extended = json.dumps({
                "source": "BD_RCA_data.csv",
                "row": row_num,
                "serial": serial,
            })

            log = BreakdownLog(
                machine_name=equipment[:200] if equipment else "Unknown",
                division=division,
                description=description[:1000],
                downtime_minutes=int(downtime * 60) if downtime else 0,
                mttr_hours=downtime,
                revenue_loss=revenue_loss,
                status=status,
                logged_at=datetime.utcnow(),
                rca_data=rca_data,
                extended_info=extended,
                author_id=system_user_id,
            )

            if not dry_run:
                session.add(log)

            inserted += 1

    if not dry_run:
        session.commit()

    print(f"   ✅ {csv_path.name}: {inserted} inserted, {skipped} skipped (already exist)")
    return inserted, skipped


def get_or_create_system_user(session) -> int:
    """Return the ID of the system/admin user to assign imported records to."""
    # Try to find an existing Admin user
    admin = session.query(User).filter(User.division == "Admin").first()
    if admin:
        return admin.id

    # If no admin exists yet, create a placeholder system user
    # (this should not happen in practice — the app creates an admin on first run)
    print("   ℹ️  No Admin user found — creating placeholder system user for imports")
    system_user = User(
        email="system@import.local",
        hashed_password="!disabled",
        name="CSV Import System",
        division="Admin",
    )
    session.add(system_user)
    session.commit()
    return system_user.id


def main():
    parser = argparse.ArgumentParser(
        description="Seed SQLite database with historical RCA CSV data (one-time import)"
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help=f"Directory containing the CSV files (default: {DEFAULT_CSV_DIR})",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing to the database",
    )
    args = parser.parse_args()

    # ── Validate paths ──────────────────────────────────────────────────────
    if not args.csv_dir.exists():
        print(f"❌ CSV directory not found: {args.csv_dir}")
        print("   SCP the CSV files to the server first:")
        print('   scp -i key.pem "app/data/RCA_TRACKER.csv" ubuntu@<ec2-ip>:/opt/rca_data/csv/')
        sys.exit(1)

    mode = "DRY RUN (no writes)" if args.dry_run else "LIVE IMPORT"
    print(f"\n{'='*60}")
    print(f"  RCA Historical Data Import — {mode}")
    print(f"{'='*60}")
    print(f"  CSV directory : {args.csv_dir}")
    print(f"  Database      : {args.db_path}")
    print(f"{'='*60}\n")

    # ── Connect to DB ───────────────────────────────────────────────────────
    db_url = f"sqlite:///{args.db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)  # create tables if they don't exist
    Session = sessionmaker(bind=engine)
    session = Session()

    system_user_id = get_or_create_system_user(session)
    print(f"   Using author_id={system_user_id} for all imported records\n")

    total_inserted = 0
    total_skipped = 0

    # ── RCA_TRACKER.csv ─────────────────────────────────────────────────────
    rca_tracker = args.csv_dir / "RCA_TRACKER.csv"
    if rca_tracker.exists():
        ins, skp = import_rca_tracker(rca_tracker, session, args.dry_run, system_user_id)
        total_inserted += ins
        total_skipped += skp
    else:
        print(f"⚠️  Not found (skipping): {rca_tracker}")

    # ── Pellet, BNFC, PGP - BD & RCA data.csv ──────────────────────────────
    bd_csv = args.csv_dir / "Pellet, BNFC, PGP - BD & RCA data.csv"
    if bd_csv.exists():
        ins, skp = import_bd_rca_data(bd_csv, session, args.dry_run, system_user_id)
        total_inserted += ins
        total_skipped += skp
    else:
        print(f"⚠️  Not found (skipping): {bd_csv}")

    session.close()

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Total records inserted : {total_inserted}")
    print(f"  Total records skipped  : {total_skipped} (already existed)")
    if args.dry_run:
        print(f"\n  DRY RUN — nothing was written to the database.")
        print(f"  Re-run without --dry-run to actually import.")
    else:
        print(f"\n  ✅ Import complete. Database: {args.db_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
