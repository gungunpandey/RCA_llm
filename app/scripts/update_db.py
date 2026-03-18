from database import SessionLocal, BreakdownLog

def fix_status():
    db = SessionLocal()
    logs = db.query(BreakdownLog).all()
    count_updated = 0
    for log in logs:
        if log.extended_info:
            parts = log.extended_info.split(" | ")
            status_val = None
            for p in parts:
                if p.startswith("Status:"):
                    status_val = p.split("Status:", 1)[1].strip()
            
            if status_val:
                new_status = "Open"
                sv_lower = status_val.lower()
                
                if status_val:
                    new_status = status_val
                else:
                    new_status = "Open"
                    
                if log.status != new_status:
                    log.status = new_status
                    count_updated += 1
                    
    db.commit()
    print(f"Updated {count_updated} records.")
    db.close()

if __name__ == "__main__":
    fix_status()
