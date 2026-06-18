import os
import sys
import csv
import json
from datetime import datetime
from dateutil import parser as dateparser

# Ensure parent directory is in python path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal, BreakdownLog, CAPA, CAPATask, CAPAComment, User, Equipment
from utils import normalize_full_owner_string

def clean_downtime_minutes(val):
    if not val or val.strip() in ("", "-", "---", "N/A"):
        return 0
    cleaned = val.replace(",", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return 0

def determine_action_type(text):
    text_clean = text.strip().upper()
    if text_clean.startswith("CA") or "CORRECTIVE" in text_clean:
        return "Corrective"
    elif text_clean.startswith("PA") or "PREVENTIVE" in text_clean:
        return "Preventive"
    else:
        return "Corrective"

def parse_csv_date(val):
    if not val or val.strip() in ("", "-", "---"):
        return None
    try:
        return dateparser.parse(val.strip())
    except Exception:
        return None

def import_csv(csv_path):
    if not os.path.exists(csv_path):
        print(f"Error: File not found at {csv_path}")
        return

    db = SessionLocal()

    # Get default admin user in case
    admin_user = db.query(User).filter(User.division == "Admin").first()
    if not admin_user:
        admin_user = db.query(User).first()
    
    if not admin_user:
        print("Error: No users found in database to assign as author. Run the web app first to seed default users.")
        db.close()
        return

    print("Clearing previous data from database tables (BreakdownLog, CAPA, CAPATask, CAPAComment)...")
    db.query(CAPATask).delete()
    db.query(CAPAComment).delete()
    db.query(CAPA).delete()
    db.query(BreakdownLog).delete()
    db.commit()
    print("Database tables cleared.")

    print(f"Reading and importing data from {csv_path}...")

    current_bd = None
    current_capas = []

    imported_logs_count = 0
    imported_capas_count = 0

    def save_current_bd():
        nonlocal imported_logs_count, imported_capas_count
        if not current_bd:
            return

        # Fetch division user
        area_norm = current_bd["area"].replace("-", " ")
        division_user = db.query(User).filter(User.division == area_norm).first()
        author_id = division_user.id if division_user else admin_user.id

        # Normalize status
        rca_status = current_bd["rca_status"]
        bd_status = "Open"
        if rca_status == "Done":
            bd_status = "Completed"
        elif rca_status == "Not required":
            bd_status = "Resolved"
        elif rca_status == "Not done":
            bd_status = "Open"

        # Determine failure type from department
        dept = current_bd["department"].lower()
        if "e & i" in dept or "elec" in dept:
            failure_type = "Electrical"
        elif "mech" in dept:
            failure_type = "Mechanical"
        elif "process" in dept:
            failure_type = "Process"
        else:
            failure_type = "Other"

        # Format description with action taken if present
        desc = current_bd["description"]
        action_taken = current_bd["action_taken"]
        if action_taken:
            desc = f"{desc}\nAction taken: {action_taken}"

        # Construct rca_data JSON
        rca_json = {
            "type": "ai_generated",
            "timestamp": datetime.utcnow().isoformat(),
            "final_root_cause": current_bd["root_cause"],
            "five_whys_analysis": {
                "root_cause": current_bd["root_cause"],
                "steps": [current_bd["root_cause"]] if current_bd["root_cause"] else []
            },
            "domain_insights": {
                "mechanical": {"findings": "", "confidence": 1.0},
                "electrical": {"findings": "", "confidence": 1.0},
                "process": {"findings": "", "confidence": 1.0}
            },
            "final_confidence": 1.0,
            "team_list": "RCA Team",
            "capa": [
                {
                    "action": c["action"],
                    "responsibility": normalize_full_owner_string(c["responsible"]),
                    "targetDate": c["due_date"],
                    "status": "Completed" if c["status"].strip().lower() in ("done", "completed") else "Open"
                }
                for c in current_capas
            ]
        }

        # Create BreakdownLog record
        new_log = BreakdownLog(
            machine_name=current_bd["equipment"],
            division=area_norm,
            description=desc,
            downtime_minutes=current_bd["downtime"],
            status=bd_status,
            author_id=author_id,
            start_time=current_bd["date"],
            logged_at=current_bd["date"] or datetime.utcnow(),
            revenue_loss=0.0,
            mttr_hours=round(current_bd["downtime"] / 60, 1) if current_bd["downtime"] > 0 else 0.0,
            severity_level="Medium",
            failure_type=failure_type,
            feed_loss=current_bd["feed_loss"],
            attached_doc=current_bd["link"],
            rca_data=json.dumps(rca_json)
        )
        db.add(new_log)
        db.flush() # get new_log.id

        # Create CAPA table records
        for c in current_capas:
            c_action = c["action"]
            c_status = "Completed" if c["status"].strip().lower() in ("done", "completed") else "Open"
            c_type = determine_action_type(c_action)
            
            capa_record = CAPA(
                breakdown_log_id=new_log.id,
                action_type=c_type,
                actions=c_action,
                owner=normalize_full_owner_string(c["responsible"]),
                due_date=c["due_date"],
                priority="Medium",
                impact_level="Medium",
                status=c_status,
                root_cause=current_bd["root_cause"],
                created_at=datetime.utcnow()
            )
            db.add(capa_record)
            imported_capas_count += 1

        imported_logs_count += 1

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        
        for idx, row in enumerate(reader):
            sl_no = row.get("#", "").strip()
            date_str = row.get("Date of incident", "").strip()
            
            is_new = bool(sl_no or date_str)
            
            capa_action = row.get("CAPA", "").strip()
            if capa_action in ("-", "---", "Not required", "Not done", "N/A", "N.A", "N.A.", ""):
                capa_action = ""

            if is_new:
                save_current_bd()
                
                eq = row.get("Equipment", "").strip()
                desc = row.get("Description of Breakdown/Case", "").strip()
                
                if not eq and not desc:
                    current_bd = None
                    current_capas = []
                    continue

                downtime = clean_downtime_minutes(row.get("Effected time (Minute)", "0"))
                feed_loss_str = row.get("Impact on production", "").strip().lower()
                feed_loss = "stop" in feed_loss_str or "yes" in feed_loss_str
                
                link = row.get("Link", "").strip()
                if link in ("-", "---", "N/A", "N.A", "N.A.", ""):
                    link = None

                current_bd = {
                    "date": parse_csv_date(date_str) or datetime.utcnow(),
                    "area": row.get("Area", "").strip(),
                    "department": row.get("Department", "").strip(),
                    "equipment": eq if eq else "Unknown Equipment",
                    "description": desc if desc else "No description",
                    "downtime": downtime,
                    "action_taken": row.get("Action taken", "").strip(),
                    "rca_status": row.get(" RCA Status", "").strip(),
                    "root_cause": row.get("Root Cause", "").strip(),
                    "feed_loss": feed_loss,
                    "link": link
                }
                current_capas = []

                if capa_action:
                    current_capas.append({
                        "action": capa_action,
                        "responsible": row.get("Responsible", "").strip(),
                        "due_date": row.get("Due date", "").strip(),
                        "status": row.get("Status of CAPA", "").strip()
                    })
            else:
                if current_bd and capa_action:
                    current_capas.append({
                        "action": capa_action,
                        "responsible": row.get("Responsible", "").strip(),
                        "due_date": row.get("Due date", "").strip(),
                        "status": row.get("Status of CAPA", "").strip()
                    })

        save_current_bd()

    db.commit()
    db.close()
    print(f"Import process complete!")
    print(f"  Successfully imported: {imported_logs_count} breakdown logs")
    print(f"  Successfully imported: {imported_capas_count} CAPA items")

if __name__ == "__main__":
    csv_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "Pellet, BNFC, PGP - BD & RCA data.csv")
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    import_csv(csv_file)
