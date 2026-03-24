"""
JSON API routes for the React SPA frontend.
All endpoints use cookie-based JWT auth (same cookie set by /login).
"""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from dateutil import parser as dateparser

from database import SessionLocal, User, BreakdownLog, CAPA, CAPATask, CAPAComment

# ── Config ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "your-very-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

_EQUIPMENT_JSON = os.path.join(
    os.path.dirname(__file__), "..", "data_ingestion", "equipment_by_division.json"
)
try:
    with open(_EQUIPMENT_JSON, encoding="utf-8") as _f:
        EQUIPMENT_CATALOGUE: dict = json.load(_f)
except FileNotFoundError:
    EQUIPMENT_CATALOGUE = {}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api")


# ── Helpers ────────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Extract user from the HttpOnly access_token cookie. Raises 401 if invalid."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        if token.startswith("Bearer "):
            token = token.split(" ", 1)[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Auth ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
async def api_login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        return JSONResponse({"message": "Incorrect email or password"}, status_code=401)

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode({"sub": user.email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

    resp = JSONResponse({
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.division,  # division serves as role
            "name": user.name,
        }
    })
    resp.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=86400,
        samesite="lax",
    )
    return resp


@router.get("/auth/me")
async def api_me(user: User = Depends(get_current_user)):
    """Return current user from cookie. Used by React AuthContext on mount."""
    return {
        "id": user.id,
        "email": user.email,
        "role": user.division,
        "name": user.name,
    }


@router.get("/auth/logout")
async def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key="access_token")
    return resp


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/dashboard/summary")
async def api_dashboard_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BreakdownLog)
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.all()

    open_count = len([l for l in logs if l.status in ("Open", "In Progress")])

    capa_overdue = db.query(CAPA).filter(
        CAPA.status.notin_(["Completed"]),
        CAPA.due_date != None,
        CAPA.due_date != "",
        CAPA.due_date < datetime.utcnow().strftime("%Y-%m-%d"),
    ).count()

    # MTTR trend (monthly, last 12 months)
    monthly_mttr = defaultdict(list)
    for log in logs:
        if log.logged_at:
            mk = log.logged_at.strftime("%b %Y")
            mttr_val = None
            if log.mttr_hours is not None:
                mttr_val = float(log.mttr_hours)
            elif log.downtime_minutes and log.downtime_minutes > 0:
                mttr_val = round(log.downtime_minutes / 60, 1)
            if mttr_val is not None:
                monthly_mttr[mk].append(mttr_val)

    now = datetime.utcnow()
    mttr_trend = []
    for i in range(11, -1, -1):
        d = now - timedelta(days=i * 30)
        mk = d.strftime("%b %Y")
        if mk in monthly_mttr:
            vals = monthly_mttr[mk]
            mttr_trend.append({"month": mk, "avgMttr": round(sum(vals) / len(vals), 1)})

    return {
        "openBreakdowns": open_count,
        "capaOverdue": capa_overdue,
        "mttrTrend": mttr_trend,
    }


@router.get("/dashboard/top-equipment")
async def api_top_equipment(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BreakdownLog)
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.all()

    machine_counts = Counter(log.machine_name for log in logs if log.machine_name)
    result = []
    for equip_name, count in machine_counts.most_common(5):
        sample = next((l for l in logs if l.machine_name == equip_name), None)
        result.append({
            "equipment_name": equip_name,
            "asset_tag": equip_name[:6].upper().replace(" ", ""),
            "category": sample.division if sample else "Unknown",
            "breakdown_count": count,
        })
    return result


@router.get("/dashboard/breakdowns")
async def api_breakdowns(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BreakdownLog)
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.order_by(BreakdownLog.logged_at.desc()).limit(20).all()

    return [
        {
            "id": log.id,
            "equipment_name": log.machine_name,
            "asset_tag": log.division[:4].upper() if log.division else "N/A",
            "description": log.description,
            "status": log.status,
            "reported_at": log.logged_at.isoformat() if log.logged_at else None,
            "mttr_hours": float(log.mttr_hours) if log.mttr_hours else (
                round(log.downtime_minutes / 60, 1) if log.downtime_minutes else None
            ),
        }
        for log in logs
    ]


@router.get("/dashboard/failures-by-asset")
async def api_failures_by_asset(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BreakdownLog)
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.all()

    division_counts = Counter(log.division for log in logs if log.division)
    return [
        {"category": div, "count": cnt}
        for div, cnt in division_counts.most_common(8)
    ]


@router.get("/dashboard/rca-reports")
async def api_rca_reports(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BreakdownLog).filter(
        BreakdownLog.rca_data != None,
        BreakdownLog.rca_data != "",
        BreakdownLog.rca_data != "[]",
        BreakdownLog.rca_data != "null",
    )
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.order_by(BreakdownLog.logged_at.desc()).limit(10).all()

    results = []
    for log in logs:
        try:
            parsed = json.loads(log.rca_data)
            root_cause = ""
            corrective_action = ""
            if isinstance(parsed, dict):
                root_cause = parsed.get("final_root_cause", "")
                capa_list = parsed.get("capa", [])
                if capa_list and isinstance(capa_list, list) and len(capa_list) > 0:
                    corrective_action = capa_list[0].get("action", "")
            if root_cause:
                results.append({
                    "id": log.id,
                    "equipment_name": log.machine_name,
                    "root_cause": root_cause,
                    "corrective_action": corrective_action,
                    "author_email": log.author.email if log.author else "unknown",
                    "created_at": log.logged_at.isoformat() if log.logged_at else None,
                })
        except (json.JSONDecodeError, AttributeError):
            pass
    return results


@router.get("/dashboard/mttr-weekly")
async def api_mttr_weekly(
    month: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return weekly MTTR for a specific month (e.g. 'Mar 2026')."""
    query = db.query(BreakdownLog)
    if user.division != "Admin":
        query = query.filter(BreakdownLog.division == user.division)
    logs = query.all()

    weekly = defaultdict(list)
    for log in logs:
        if not log.logged_at:
            continue
        mk = log.logged_at.strftime("%b %Y")
        if mk != month:
            continue
        week_num = (log.logged_at.day - 1) // 7 + 1
        week_label = f"Week {week_num}"
        mttr_val = None
        if log.mttr_hours is not None:
            mttr_val = float(log.mttr_hours)
        elif log.downtime_minutes and log.downtime_minutes > 0:
            mttr_val = round(log.downtime_minutes / 60, 1)
        if mttr_val is not None:
            weekly[week_label].append(mttr_val)

    return [
        {"month": wk, "avgMttr": round(sum(vals) / len(vals), 1)}
        for wk, vals in sorted(weekly.items())
    ]


# ── Breakdowns (logging) ──────────────────────────────────────────────────

@router.get("/breakdowns/equipment")
async def api_equipment_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return equipment list grouped by division for the breakdown log form."""
    division_machines = {k: list(v) for k, v in EQUIPMENT_CATALOGUE.items()}

    rows = db.query(BreakdownLog.division, BreakdownLog.machine_name).filter(
        BreakdownLog.machine_name != None,
        BreakdownLog.machine_name != "",
    ).distinct().all()
    for div, machine in rows:
        if div and machine and machine.strip():
            division_machines.setdefault(div, [])
            if machine.strip() not in division_machines[div]:
                division_machines[div].append(machine.strip())

    # Flatten to list format expected by React
    equipment = []
    eq_id = 1
    for div, machines in sorted(division_machines.items()):
        for m in sorted(machines):
            equipment.append({
                "id": eq_id,
                "name": m,
                "asset_tag": f"EQ-{eq_id:03d}",
                "location": div,
                "category": div,
            })
            eq_id += 1
    return equipment


@router.post("/breakdowns")
async def api_submit_breakdown(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a new breakdown log. Accepts FormData (multipart) or JSON."""
    content_type = request.headers.get("content-type", "")

    if "multipart" in content_type:
        form = await request.form()
        equipment_id = form.get("equipment_id")
        description = form.get("description", "")
        division = form.get("division", "Unknown")
        machine_name = form.get("machine_name", "") or ""
        reported_at = form.get("reported_at")
        severity_level = form.get("severity_level")
        failure_type = form.get("failure_type")
        issue_end_at = form.get("issue_end_at")
        feed_loss = form.get("feed_loss_applicable", "").lower() in ("true", "yes", "y", "1")
        revenue_loss = float(form.get("revenue_loss") or 0)
        doc_description = form.get("doc_description", "")

        # If we got an equipment_id but no machine_name, look up from the equipment list
        if not machine_name and equipment_id:
            machine_name = f"Equipment-{equipment_id}"

        st_time = dateparser.parse(reported_at) if reported_at else None
        ed_time = dateparser.parse(issue_end_at) if issue_end_at else None

        downtime = 0
        if st_time and ed_time:
            downtime = int((ed_time - st_time).total_seconds() / 60)

        mttr_h = round(downtime / 60, 1) if downtime > 0 else None

        # Handle file attachment
        doc_path = None
        attachment = form.get("attachments")
        if attachment and hasattr(attachment, 'filename') and attachment.filename:
            os.makedirs("static/uploads", exist_ok=True)
            file_location = f"static/uploads/{attachment.filename}"
            content = await attachment.read()
            with open(file_location, "wb") as f:
                f.write(content)
            doc_path = file_location

        new_log = BreakdownLog(
            machine_name=machine_name,
            division=division,
            description=description,
            downtime_minutes=downtime,
            status="Open",
            author_id=user.id,
            start_time=st_time,
            end_time=ed_time,
            feed_loss=feed_loss,
            attached_doc=doc_path,
            doc_description=doc_description,
            revenue_loss=revenue_loss,
            mttr_hours=mttr_h,
            severity_level=severity_level,
            failure_type=failure_type,
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        return {"id": new_log.id, "message": "Breakdown logged successfully"}
    else:
        return JSONResponse({"message": "Expected multipart form data"}, status_code=400)


# ── CAPA ───────────────────────────────────────────────────────────────────

@router.get("/capa")
async def api_capa_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capas = db.query(CAPA).order_by(CAPA.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "title": (c.actions or "Untitled CAPA").split("\n")[0][:80],
            "status": c.status,
            "owner": c.owner or "Unassigned",
            "dueDate": c.due_date,
            "due_date": c.due_date,
            "priority": c.priority or "Medium",
            "impact_level": c.impact_level,
            "action_type": c.action_type,
            "actions": c.actions,
            "root_cause": c.root_cause,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in capas
    ]


@router.get("/capa/{capa_id}")
async def api_capa_get(
    capa_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capa = db.query(CAPA).filter(CAPA.id == capa_id).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    return {
        "capa": {
            "id": capa.id,
            "action_type": capa.action_type,
            "actions": capa.actions,
            "owner": capa.owner,
            "due_date": capa.due_date,
            "priority": capa.priority,
            "impact_level": capa.impact_level,
            "status": capa.status,
            "root_cause": capa.root_cause,
        }
    }


class CAPABody(BaseModel):
    action_type: str = "Corrective"
    actions: str = ""
    owner: str = ""
    due_date: str = ""
    priority: str = ""
    impact_level: str = ""
    status: str = "Open"
    root_cause: str = ""
    breakdown_id: Optional[int] = None


@router.post("/capa")
async def api_capa_create(
    body: CAPABody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capa = CAPA(
        breakdown_log_id=body.breakdown_id,
        action_type=body.action_type,
        actions=body.actions,
        owner=body.owner,
        due_date=body.due_date,
        priority=body.priority,
        impact_level=body.impact_level,
        status=body.status,
        root_cause=body.root_cause,
    )
    db.add(capa)
    db.commit()
    db.refresh(capa)
    return {"id": capa.id, "message": "CAPA created"}


@router.put("/capa/{capa_id}")
async def api_capa_update(
    capa_id: int,
    body: CAPABody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capa = db.query(CAPA).filter(CAPA.id == capa_id).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    capa.action_type = body.action_type
    capa.actions = body.actions
    capa.owner = body.owner
    capa.due_date = body.due_date
    capa.priority = body.priority
    capa.impact_level = body.impact_level
    capa.status = body.status
    capa.root_cause = body.root_cause
    db.commit()
    return {"id": capa.id, "message": "CAPA updated"}


class StatusBody(BaseModel):
    status: str


@router.patch("/capa/{capa_id}/status")
async def api_capa_patch_status(
    capa_id: int,
    body: StatusBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capa = db.query(CAPA).filter(CAPA.id == capa_id).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    capa.status = body.status
    db.commit()
    return {"message": "Status updated"}


# ── CAPA Detail ────────────────────────────────────────────────────────────

@router.get("/capa-detail/{capa_id}/details")
async def api_capa_detail(
    capa_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capa = db.query(CAPA).filter(CAPA.id == capa_id).first()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")

    tasks = db.query(CAPATask).filter(CAPATask.capa_id == capa_id).order_by(CAPATask.id).all()
    comments = db.query(CAPAComment).filter(CAPAComment.capa_id == capa_id).order_by(CAPAComment.created_at).all()

    return {
        "capa": {
            "id": capa.id,
            "title": (capa.actions or "Untitled").split("\n")[0][:80],
            "status": capa.status,
            "owner": capa.owner or "Unassigned",
            "dueDate": capa.due_date,
            "priority": capa.priority or "Medium",
            "rootCause": capa.root_cause or "",
            "action_type": capa.action_type,
            "impact_level": capa.impact_level,
        },
        "tasks": [
            {
                "id": t.id,
                "title": t.task_title,
                "done": t.is_completed,
                "comment": "",
                "file": None,
            }
            for t in tasks
        ],
        "comments": [
            {
                "id": c.id,
                "author": c.author_name or "Team",
                "time": c.created_at.strftime("%d %b %Y, %H:%M") if c.created_at else "",
                "text": c.comment_text,
            }
            for c in comments
        ],
    }


class TaskStatusBody(BaseModel):
    is_completed: bool


@router.patch("/capa-detail/tasks/{task_id}/status")
async def api_toggle_task(
    task_id: int,
    body: TaskStatusBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(CAPATask).filter(CAPATask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_completed = body.is_completed
    db.commit()
    return {"message": "Task updated"}


class NewTaskBody(BaseModel):
    capa_id: int
    task_title: str


@router.post("/capa-detail/tasks")
async def api_add_task(
    body: NewTaskBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = CAPATask(capa_id=body.capa_id, task_title=body.task_title)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "id": task.id,
        "title": task.task_title,
        "done": task.is_completed,
        "comment": "",
        "file": None,
    }


class NewCommentBody(BaseModel):
    capa_id: int
    comment_text: str


@router.post("/capa-detail/comments")
async def api_add_comment(
    body: NewCommentBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = CAPAComment(
        capa_id=body.capa_id,
        comment_text=body.comment_text,
        author_name=user.name,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id,
        "author": comment.author_name,
        "time": comment.created_at.strftime("%d %b %Y, %H:%M") if comment.created_at else "",
        "text": comment.comment_text,
    }
