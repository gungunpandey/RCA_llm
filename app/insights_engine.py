"""
ProdAI Insights Engine — Phase 1 (Anomaly + Repeat Failure detection).

Core design principle
---------------------
ALL numbers are computed here, deterministically, from the database. The LLM
only *narrates* the verified facts in the returned `analysis_bundle`; it never
computes a statistic. This is what prevents the model from inventing
percentages or correlations.

Graceful handling of the risks called out in planning:
  * Hallucinated stats  -> every metric is pre-computed; a rule-based fallback
                           (`bundle_to_deterministic_insights`) can render the
                           panel with correct numbers even if the LLM fails.
  * Low-volume noise    -> MIN_PERIOD_EVENTS / threshold guards; each metric
                           carries sample sizes and a `reliable` flag, and a
                           `low_volume_warning` is raised for thin data.
  * Performance         -> a single windowed query feeds both periods; lists
                           are capped with MAX_ITEMS.
  * Data quality        -> free-text root causes are normalized before
                           clustering; `data_quality` reports RCA coverage.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database import BreakdownLog, CAPA, Equipment, User


# ── Tunable guards against statistical noise ─────────────────────────────────
MIN_PERIOD_EVENTS = 3       # both periods need >= this before a % change is trusted
REPEAT_THRESHOLD = 3        # occurrences of one root cause to call it a "repeat"
EQUIP_REPEAT_THRESHOLD = 3  # breakdowns on one machine+component to flag a repeat
LOW_VOLUME_TOTAL = 5        # fewer than this total -> blanket low-confidence note
MAX_ITEMS = 5               # cap each list so prompts / UI stay compact

# Phase 2 — risk scoring (heuristic, frequency-based; NOT a prediction model)
RISK_MIN_FAILURES = 3       # min failures this period before an asset can be "at risk"
RISK_HIGH_SCORE = 7         # composite score at/above which risk is labelled "High"

# Phase 3 — correlations (guarded hard against spurious low-N patterns)
CORRELATION_MIN_EVENTS = 8     # need a decent sample before claiming a correlation
CORRELATION_DOMINANCE_PCT = 50 # one bucket must hold >= this share to be notable

# Phase 3 — CAPA effectiveness (equal before/after windows)
CAPA_EFFECT_WINDOW = 90     # days on each side of a CAPA's completion date
CAPA_EFFECT_MIN_BEFORE = 2  # need a baseline of failures before to judge effect

_RANGE_DAYS = {
    "7d": 7, "7D": 7,
    "30d": 30, "30D": 30,
    "90d": 90, "90D": 90, "3m": 90, "3M": 90,
    "180d": 180, "180D": 180, "6m": 180, "6M": 180,
    "1y": 365, "1Y": 365, "365d": 365,
}
DEFAULT_WINDOW_DAYS = 30


# ── small pure helpers ───────────────────────────────────────────────────────
def _window_days(date_range: Optional[str]) -> int:
    return _RANGE_DAYS.get(date_range or "", DEFAULT_WINDOW_DAYS)


def _pct_change(cur: int, prev: int):
    """Rounded % change, or None when the previous period has no events."""
    if prev <= 0:
        return None
    return round((cur - prev) / prev * 100)


def _normalize_cause(s: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace so free-text root
    causes that are 'the same' cluster together."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_root_cause(log: BreakdownLog) -> str:
    """Pull `final_root_cause` out of the rca_data JSON, tolerating the legacy
    array / null / empty formats."""
    raw = (log.rca_data or "").strip()
    if not raw or raw in ("[]", "null"):
        return ""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    if isinstance(parsed, dict):
        return (parsed.get("final_root_cause") or "").strip()
    return ""


def _base_logs_query(db: Session, user: User, plant: Optional[str], equip_type: Optional[str]):
    """Access-controlled base query (mirrors get_filtered_breakdown_logs, minus
    the date filter which the engine applies itself). Kept here so the engine has
    no import dependency on api_routes."""
    q = db.query(BreakdownLog)
    if user.division != "Admin":
        q = q.filter(BreakdownLog.division == user.division)
    elif plant:
        q = q.filter(BreakdownLog.division == plant)
    if equip_type:
        q = q.filter(BreakdownLog.machine_name.ilike(f"%{equip_type}%"))
    return q


# ── metric computations ──────────────────────────────────────────────────────
def _totals(current: list, previous: list) -> dict:
    cur, prev = len(current), len(previous)
    reliable = cur >= MIN_PERIOD_EVENTS and prev >= MIN_PERIOD_EVENTS
    return {
        "current": cur,
        "previous": prev,
        "delta": cur - prev,
        "pct_change": _pct_change(cur, prev) if reliable else None,
        "reliable": reliable,
    }


def _dominant_driver(logs: list):
    """Name the sub-driver behind a group of failures: failure_type first,
    falling back to component_name. Returns None when neither is recorded."""
    ft = Counter(l.failure_type for l in logs if l.failure_type)
    if ft:
        value, count = ft.most_common(1)[0]
        return {"by": "failure_type", "value": value, "count": count}
    comp = Counter(l.component_name for l in logs if l.component_name)
    if comp:
        value, count = comp.most_common(1)[0]
        return {"by": "component", "value": value, "count": count}
    return None


def _equipment_anomalies(current: list, previous: list) -> list:
    cur_counts = Counter(l.machine_name for l in current if l.machine_name)
    prev_counts = Counter(l.machine_name for l in previous if l.machine_name)

    out = []
    for name, cur in cur_counts.items():
        prev = prev_counts.get(name, 0)
        delta = cur - prev
        if delta <= 0:
            continue
        out.append({
            "equipment": name,
            "current": cur,
            "previous": prev,
            "delta": delta,
            "pct_change": _pct_change(cur, prev),
            "dominant_driver": _dominant_driver(
                [l for l in current if l.machine_name == name]
            ),
            # a meaningful current count is required before we surface it as signal
            "reliable": cur >= MIN_PERIOD_EVENTS,
        })
    out.sort(key=lambda x: (x["reliable"], x["delta"]), reverse=True)
    return out[:MAX_ITEMS]


def _plant_contribution_shifts(current: list, previous: list) -> list:
    """How each plant's *share* of failures changed. Only meaningful in a
    multi-plant view with enough events."""
    cur_counts = Counter(l.division for l in current if l.division)
    prev_counts = Counter(l.division for l in previous if l.division)
    cur_total = sum(cur_counts.values())
    prev_total = sum(prev_counts.values())

    if cur_total < MIN_PERIOD_EVENTS or len(cur_counts) < 2 or prev_total == 0:
        return []

    out = []
    for div, cnt in cur_counts.items():
        cur_pct = round(cnt / cur_total * 100)
        base_pct = round(prev_counts.get(div, 0) / prev_total * 100)
        shift = cur_pct - base_pct
        if shift <= 0:
            continue
        out.append({
            "plant": div,
            "current_pct": cur_pct,
            "baseline_pct": base_pct,
            "shift_pts": shift,
            "current_count": cnt,
            "reliable": cnt >= MIN_PERIOD_EVENTS,
        })
    out.sort(key=lambda x: (x["reliable"], x["shift_pts"]), reverse=True)
    return out[:MAX_ITEMS]


def _repeat_failures(current: list) -> list:
    out = []

    # (a) cluster by normalized root-cause text
    cause_groups = defaultdict(list)
    for l in current:
        rc = _extract_root_cause(l)
        if rc:
            cause_groups[_normalize_cause(rc)].append(l)
    for _, logs in cause_groups.items():
        if len(logs) >= REPEAT_THRESHOLD:
            # display the most common original phrasing, not the normalized form
            original = Counter(_extract_root_cause(l) for l in logs).most_common(1)[0][0]
            out.append({
                "type": "root_cause",
                "root_cause": original[:200],
                "count": len(logs),
                "equipment": sorted({l.machine_name for l in logs if l.machine_name})[:5],
                "reliable": True,
            })

    # (b) cluster by machine + component (works even without RCA text)
    comp_groups = defaultdict(list)
    for l in current:
        if l.machine_name and l.component_name:
            comp_groups[(l.machine_name, l.component_name)].append(l)
    for (machine, comp), logs in comp_groups.items():
        if len(logs) >= EQUIP_REPEAT_THRESHOLD:
            out.append({
                "type": "equipment_component",
                "equipment": machine,
                "component": comp,
                "count": len(logs),
                "reliable": True,
            })

    out.sort(key=lambda x: x["count"], reverse=True)
    return out[:MAX_ITEMS]


def _capa_access_query(db: Session, user: User, plant: Optional[str], equip_type: Optional[str]):
    """Access-controlled CAPA⋈BreakdownLog query (shared by recurrence / stats)."""
    q = db.query(CAPA, BreakdownLog).join(
        BreakdownLog, CAPA.breakdown_log_id == BreakdownLog.id
    )
    if user.division != "Admin":
        q = q.filter(BreakdownLog.division == user.division)
    elif plant:
        q = q.filter(BreakdownLog.division == plant)
    if equip_type:
        q = q.filter(BreakdownLog.machine_name.ilike(f"%{equip_type}%"))
    return q


def _open_capa_by_machine(db: Session, user: User, plant: Optional[str],
                          equip_type: Optional[str]) -> dict:
    """Most recent still-open CAPA per machine: {machine: (capa, origin_log)}."""
    q = _capa_access_query(db, user, plant, equip_type).filter(
        CAPA.status.notin_(["Completed"])
    )
    out: dict = {}
    for capa, origin in q.all():
        if not origin.machine_name:
            continue
        existing = out.get(origin.machine_name)
        if existing is None or (
            capa.created_at and existing[0].created_at
            and capa.created_at > existing[0].created_at
        ):
            out[origin.machine_name] = (capa, origin)
    return out


def _capa_recurrence(open_capa_by_machine: dict, current: list) -> list:
    """Machines that failed again in the current window while a CAPA from an
    earlier breakdown is still not completed — i.e. an un-implemented or
    ineffective corrective action."""
    cur_by_machine = defaultdict(list)
    for l in current:
        if l.machine_name:
            cur_by_machine[l.machine_name].append(l)

    out = []
    for machine, (capa, origin) in open_capa_by_machine.items():
        recurrences = [
            l for l in cur_by_machine.get(machine, [])
            if l.id != origin.id
            and (not capa.created_at or (l.logged_at and l.logged_at >= capa.created_at))
        ]
        if not recurrences:
            continue
        dates = [l.logged_at for l in recurrences if l.logged_at]
        out.append({
            "machine": machine,
            "capa_id": capa.id,
            "capa_status": capa.status,
            "root_cause": (capa.root_cause or _extract_root_cause(origin) or "")[:200],
            "recurred_count": len(recurrences),
            "last_failure_date": max(dates).isoformat() if dates else None,
        })
    out.sort(key=lambda x: x["recurred_count"], reverse=True)
    return out[:MAX_ITEMS]


def _data_quality(current: list) -> dict:
    total = len(current)
    with_rca = sum(1 for l in current if _extract_root_cause(l))
    return {
        "total_logs_analyzed": total,
        "logs_with_rca": with_rca,
        "rca_coverage_pct": round(with_rca / total * 100) if total else 0,
        "low_volume_warning": total < LOW_VOLUME_TOTAL,
    }


# ── Phase 2/3 metrics ────────────────────────────────────────────────────────
def _mttr_val(log: BreakdownLog):
    if log.mttr_hours is not None:
        return float(log.mttr_hours)
    if log.downtime_minutes and log.downtime_minutes > 0:
        return round(log.downtime_minutes / 60, 1)
    return None


def _mttr_trend(current: list, previous: list) -> dict:
    cur = [v for v in (_mttr_val(l) for l in current) if v is not None]
    prev = [v for v in (_mttr_val(l) for l in previous) if v is not None]
    cur_avg = round(sum(cur) / len(cur), 1) if cur else None
    prev_avg = round(sum(prev) / len(prev), 1) if prev else None
    reliable = len(cur) >= MIN_PERIOD_EVENTS and len(prev) >= MIN_PERIOD_EVENTS
    pct = round((cur_avg - prev_avg) / prev_avg * 100) if (reliable and prev_avg) else None
    return {"current_avg": cur_avg, "previous_avg": prev_avg,
            "pct_change": pct, "reliable": reliable, "sample": len(cur)}


def _shift_of(dt: datetime) -> str:
    """Map an hour to a plant shift bucket."""
    h = dt.hour
    if 6 <= h < 14:
        return "Day"
    if 14 <= h < 22:
        return "Evening"
    return "Night"


def _correlations(current: list) -> list:
    """Time-of-day / shift correlations, heavily guarded against low-N noise.
    Cross-equipment sequencing (e.g. 'after kiln shutdown') is intentionally
    deferred — too noisy without an explicit event log."""
    out = []

    # (a) overall shift concentration
    shift_counts = Counter()
    for l in current:
        dt = l.start_time or l.logged_at
        if dt:
            shift_counts[_shift_of(dt)] += 1
    total = sum(shift_counts.values())
    if total >= CORRELATION_MIN_EVENTS and shift_counts:
        shift, cnt = shift_counts.most_common(1)[0]
        pct = round(cnt / total * 100)
        if pct >= CORRELATION_DOMINANCE_PCT and cnt >= MIN_PERIOD_EVENTS:
            out.append({"type": "shift", "shift": shift, "pct": pct,
                        "count": cnt, "total": total, "reliable": True})

    # (b) failure-type concentrated in a shift (e.g. hydraulic at night)
    ft_shift = defaultdict(Counter)
    for l in current:
        dt = l.start_time or l.logged_at
        if dt and l.failure_type:
            ft_shift[l.failure_type][_shift_of(dt)] += 1
    for ft, sc in ft_shift.items():
        tot = sum(sc.values())
        if tot < CORRELATION_MIN_EVENTS:
            continue
        sh, c = sc.most_common(1)[0]
        pct = round(c / tot * 100)
        if pct >= CORRELATION_DOMINANCE_PCT and c >= MIN_PERIOD_EVENTS:
            out.append({"type": "failure_type_shift", "failure_type": ft, "shift": sh,
                        "pct": pct, "count": c, "total": tot, "reliable": True})

    return out[:MAX_ITEMS]


def _capa_stats(db: Session, user: User, plant: Optional[str],
                equip_type: Optional[str], cur_start: datetime) -> dict:
    """CAPA compliance/overdue within the current window (for the exec summary)."""
    capas = [c for c, _ in _capa_access_query(db, user, plant, equip_type)
             .filter(BreakdownLog.logged_at >= cur_start).all()]
    total = len(capas)
    completed = sum(1 for c in capas if c.status == "Completed")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    overdue = sum(1 for c in capas
                  if c.status != "Completed" and c.due_date and c.due_date < today)
    return {
        "total": total,
        "completed": completed,
        "overdue": overdue,
        "compliance_pct": round(completed / total * 100) if total else None,
    }


def _equipment_index(db: Session) -> dict:
    """{normalized_equipment_name: {criticality, health}} — best-effort lookup."""
    idx = {}
    try:
        for e in db.query(Equipment).all():
            if e.name:
                idx[e.name.strip().lower()] = {
                    "criticality": e.criticality,
                    "health": e.asset_health_score,
                }
    except Exception:
        pass
    return idx


def _risk_alerts(current: list, previous: list, open_capa_by_machine: dict,
                 equip_index: dict) -> list:
    """Heuristic, frequency-based risk scoring. This is NOT a forecast — it
    flags assets whose RECENT behaviour is elevated, with explicit reasons."""
    cur_counts = Counter(l.machine_name for l in current if l.machine_name)
    prev_counts = Counter(l.machine_name for l in previous if l.machine_name)

    out = []
    for machine, cnt in cur_counts.items():
        if cnt < RISK_MIN_FAILURES:
            continue
        score = cnt
        reasons = [f"{cnt} failures in this period"]

        prev = prev_counts.get(machine, 0)
        if cnt > prev:
            score += (cnt - prev)
            reasons.append(f"up from {prev} in the previous period")

        if machine in open_capa_by_machine:
            score += 2
            reasons.append("an open CAPA is still unresolved")

        crit = equip_index.get(machine.strip().lower(), {}).get("criticality")
        if crit == "Critical":
            score += 3
            reasons.append("Critical asset")
        elif crit == "High":
            score += 1
            reasons.append("High-criticality asset")

        sev = Counter(l.severity_level for l in current
                      if l.machine_name == machine and l.severity_level)
        if sev.get("Critical") or sev.get("High"):
            score += 1
            reasons.append("recent high-severity failures")

        out.append({
            "machine": machine,
            "failures": cnt,
            "previous": prev,
            "risk_level": "High" if score >= RISK_HIGH_SCORE else "Medium",
            "score": score,
            "reasons": reasons,
            "criticality": crit,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:MAX_ITEMS]


def _capa_effectiveness(db: Session, user: User, plant: Optional[str],
                        equip_type: Optional[str], now: datetime) -> list:
    """Before/after failure comparison around each CAPA's completion date, using
    equal-length windows. Only CAPAs whose full 'after' window has elapsed are
    eligible, so the comparison is fair."""
    w = CAPA_EFFECT_WINDOW
    latest_eligible = now - timedelta(days=w)  # 'after' window must have fully elapsed

    q = (_capa_access_query(db, user, plant, equip_type)
         .filter(CAPA.completed_at != None)
         .filter(CAPA.completed_at <= latest_eligible)
         .order_by(CAPA.completed_at.desc()))

    base = _base_logs_query(db, user, plant, equip_type)
    seen = set()
    out = []
    for capa, origin in q.all():
        machine = origin.machine_name
        if not machine or machine in seen:
            continue
        comp = capa.completed_at
        before = base.filter(
            BreakdownLog.machine_name == machine,
            BreakdownLog.logged_at >= comp - timedelta(days=w),
            BreakdownLog.logged_at < comp,
        ).count()
        if before < CAPA_EFFECT_MIN_BEFORE:   # need a baseline to judge against
            continue
        after = base.filter(
            BreakdownLog.machine_name == machine,
            BreakdownLog.logged_at >= comp,
            BreakdownLog.logged_at < comp + timedelta(days=w),
        ).count()
        seen.add(machine)
        out.append({
            "machine": machine,
            "capa_id": capa.id,
            "window_days": w,
            "before": before,
            "after": after,
            "change_pct": round((after - before) / before * 100),
            "improved": after < before,
        })
    out.sort(key=lambda x: x["change_pct"])   # biggest reduction first
    return out[:MAX_ITEMS]


def build_executive_summary(bundle: dict) -> dict:
    """One-click management rollup. Pure aggregation of already-verified bundle
    facts — no new statistics, no LLM."""
    t = bundle["totals"]
    mttr = bundle["mttr_trend"]
    capa = bundle["capa_stats"]
    metrics = []

    metrics.append({
        "label": "Total failures",
        "value": str(t["current"]),
        "trend": (f"{'+' if t['delta'] > 0 else ''}{t['pct_change']}%"
                  if t["reliable"] and t["pct_change"] is not None else None),
        "direction": "up" if t["delta"] > 0 else "down" if t["delta"] < 0 else "flat",
        "good": t["delta"] <= 0,
    })

    if mttr["current_avg"] is not None:
        d = mttr["pct_change"] or 0
        metrics.append({
            "label": "Avg BD Hours (MTTR)",
            "value": f"{mttr['current_avg']} h",
            "trend": (f"{'+' if d > 0 else ''}{mttr['pct_change']}%"
                      if mttr["reliable"] and mttr["pct_change"] is not None else None),
            "direction": "up" if d > 0 else "down" if d < 0 else "flat",
            "good": d <= 0,
        })

    if capa["compliance_pct"] is not None:
        metrics.append({"label": "CAPA compliance",
                        "value": f"{capa['compliance_pct']}%",
                        "good": capa["compliance_pct"] >= 80})
    if capa["overdue"]:
        metrics.append({"label": "Overdue CAPAs", "value": str(capa["overdue"]), "good": False})

    risks = bundle["risk_alerts"]
    if risks:
        metrics.append({"label": "Highest-risk asset", "value": risks[0]["machine"], "good": False})
    if bundle["repeat_failures"]:
        metrics.append({"label": "Repeat-failure clusters",
                        "value": str(len(bundle["repeat_failures"])), "good": False})

    # Recommended focus — top decision-relevant actions, de-duplicated, max 3.
    focus = []
    if risks:
        focus.append(f"{risks[0]['machine']} — elevated risk "
                     f"({risks[0]['failures']} failures this period)")
    for rf in bundle["repeat_failures"][:1]:
        if rf["type"] == "root_cause":
            focus.append(f"Address recurring root cause: \"{rf['root_cause']}\"")
        else:
            focus.append(f"{rf['equipment']} — recurring {rf['component']} failures")
    for c in bundle["unimplemented_capa_recurrence"][:1]:
        focus.append(f"Close out CAPA #{c['capa_id']} on {c['machine']} (failures recurring)")
    for a in bundle["equipment_anomalies"][:1]:
        if a["reliable"]:
            focus.append(f"Investigate rising {a['equipment']} failures")
    seen = set()
    focus = [f for f in focus if not (f in seen or seen.add(f))][:3]

    return {
        "headline": "Plant Health Summary",
        "period": bundle["period"]["label"],
        "metrics": metrics,
        "recommended_focus": focus,
        "data_quality": bundle["data_quality"],
    }


# ── public API ───────────────────────────────────────────────────────────────
def compute_analysis_bundle(db: Session, user: User, plant: Optional[str] = None,
                            equip_type: Optional[str] = None,
                            date_range: Optional[str] = None,
                            now: Optional[datetime] = None) -> dict:
    """Compute the full, verified analysis bundle for Phase-1 insights.

    Compares the current window against the immediately preceding window of equal
    length (default 30 days). One DB fetch covers both periods.
    """
    now = now or datetime.utcnow()
    days = _window_days(date_range)
    cur_start = now - timedelta(days=days)
    prev_start = now - timedelta(days=2 * days)

    base = _base_logs_query(db, user, plant, equip_type)
    logs = base.filter(BreakdownLog.logged_at >= prev_start).all()

    current = [l for l in logs if l.logged_at and l.logged_at >= cur_start]
    previous = [l for l in logs if l.logged_at and prev_start <= l.logged_at < cur_start]

    # Shared lookups computed once.
    open_capa = _open_capa_by_machine(db, user, plant, equip_type)
    equip_index = _equipment_index(db)

    bundle = {
        "period": {
            "days": days,
            "label": f"last {days} days",
            "current_start": cur_start.isoformat(),
            "current_end": now.isoformat(),
            "previous_start": prev_start.isoformat(),
            "previous_end": cur_start.isoformat(),
        },
        "totals": _totals(current, previous),
        "mttr_trend": _mttr_trend(current, previous),
        "equipment_anomalies": _equipment_anomalies(current, previous),
        "plant_contribution_shifts": _plant_contribution_shifts(current, previous),
        "repeat_failures": _repeat_failures(current),
        "unimplemented_capa_recurrence": _capa_recurrence(open_capa, current),
        "risk_alerts": _risk_alerts(current, previous, open_capa, equip_index),
        "correlations": _correlations(current),
        "capa_effectiveness": _capa_effectiveness(db, user, plant, equip_type, now),
        "capa_stats": _capa_stats(db, user, plant, equip_type, cur_start),
        "data_quality": _data_quality(current),
    }
    bundle["executive_summary"] = build_executive_summary(bundle)
    return bundle


def bundle_to_deterministic_insights(bundle: dict) -> list:
    """Rule-based insight cards built straight from the bundle.

    Guaranteed-correct fallback used when the LLM is unreachable or returns
    invalid output. Same shape the frontend already renders: {icon, text, type}.
    """
    insights = []
    dq = bundle["data_quality"]

    if dq["total_logs_analyzed"] == 0:
        return [{
            "icon": "📭", "type": "info",
            "text": "No breakdowns logged in this period for the selected filters.",
        }]

    if dq["low_volume_warning"]:
        insights.append({
            "icon": "ℹ️", "type": "info",
            "text": (f"Only <strong>{dq['total_logs_analyzed']}</strong> breakdowns in this "
                     "period — insights are indicative; trends need more data to be conclusive."),
        })

    period_word = bundle["period"]["label"]

    t = bundle["totals"]
    if t["reliable"] and t["pct_change"] is not None and t["delta"] != 0:
        up = t["delta"] > 0
        insights.append({
            "icon": "📈" if up else "📉",
            "type": "danger" if up else "success",
            "text": (f"Breakdowns {'climbed' if up else 'dropped'} "
                     f"<strong>{abs(t['pct_change'])}%</strong> over the {period_word} — "
                     f"from <strong>{t['previous']}</strong> in the prior period to "
                     f"<strong>{t['current']}</strong> now."),
        })

    mt = bundle.get("mttr_trend", {})
    if mt.get("reliable") and mt.get("pct_change") is not None and mt.get("current_avg") is not None:
        up = mt["pct_change"] > 0
        insights.append({
            "icon": "🕒",
            "type": "warning" if up else "success",
            "text": (f"Average repair time {'rose' if up else 'improved'} "
                     f"<strong>{abs(mt['pct_change'])}%</strong> — from "
                     f"<strong>{mt['previous_avg']} h</strong> to "
                     f"<strong>{mt['current_avg']} h</strong> per breakdown."),
        })

    for a in bundle["equipment_anomalies"]:
        if not a["reliable"]:
            continue
        driver = f", mostly {a['dominant_driver']['value']} issues" if a["dominant_driver"] else ""
        insights.append({
            "icon": "📈", "type": "warning",
            "text": (f"<strong>{a['equipment']}</strong> had the sharpest rise — from "
                     f"<strong>{a['previous']}</strong> to <strong>{a['current']}</strong> "
                     f"breakdowns{driver}."),
        })

    for s in bundle["plant_contribution_shifts"]:
        if not s["reliable"]:
            continue
        insights.append({
            "icon": "🏭", "type": "warning",
            "text": (f"<strong>{s['plant']}</strong> now accounts for "
                     f"<strong>{s['current_pct']}%</strong> of all breakdowns — "
                     f"up from {s['baseline_pct']}% last period."),
        })

    for r in bundle["repeat_failures"]:
        if r["type"] == "root_cause":
            insights.append({
                "icon": "🔁", "type": "danger",
                "text": (f"Recurring problem: <strong>{r['count']} breakdowns</strong> trace back "
                         f"to the same root cause — \"{r['root_cause']}\"."),
            })
        else:
            insights.append({
                "icon": "🔁", "type": "warning",
                "text": (f"<strong>{r['equipment']}</strong>'s {r['component']} has failed "
                         f"<strong>{r['count']} times</strong> this period — a recurring weak point."),
            })

    for c in bundle["unimplemented_capa_recurrence"]:
        insights.append({
            "icon": "🚧", "type": "danger",
            "text": (f"<strong>{c['machine']}</strong> failed again "
                     f"({c['recurred_count']}×) while CAPA #{c['capa_id']} is still "
                     f"<strong>{c['capa_status']}</strong> — corrective action may be "
                     "overdue or ineffective."),
        })

    # Risk alerts (heuristic; framed as elevated risk, not a forecast)
    for r in bundle.get("risk_alerts", []):
        icon = "🟠" if r["risk_level"] == "High" else "🟡"
        insights.append({
            "icon": icon,
            "type": "danger" if r["risk_level"] == "High" else "warning",
            "text": (f"<strong>{r['risk_level']} risk — {r['machine']}</strong>: "
                     f"{r['reasons'][0]}"
                     + (f", {r['reasons'][1]}" if len(r["reasons"]) > 1 else "")
                     + ". Elevated risk based on recent activity (not a forecast)."),
        })

    # CAPA effectiveness (before/after)
    for e in bundle.get("capa_effectiveness", []):
        if e["improved"]:
            insights.append({
                "icon": "✅", "type": "success",
                "text": (f"After CAPA #{e['capa_id']}, <strong>{e['machine']}</strong> "
                         f"failures fell {e['before']} → {e['after']} "
                         f"({e['change_pct']}%) over {e['window_days']} days."),
            })
        else:
            insights.append({
                "icon": "🔧", "type": "warning",
                "text": (f"Despite CAPA #{e['capa_id']}, <strong>{e['machine']}</strong> "
                         f"failures did not improve ({e['before']} → {e['after']} "
                         f"over {e['window_days']} days) — review the action."),
            })

    # Time-of-day / shift correlations
    for c in bundle.get("correlations", []):
        if c["type"] == "shift":
            insights.append({
                "icon": "🕒", "type": "info",
                "text": (f"<strong>{c['pct']}% of breakdowns</strong> happen on the "
                         f"<strong>{c['shift']} shift</strong> ({c['count']} of {c['total']}) — "
                         "worth a shift-pattern review."),
            })
        else:
            insights.append({
                "icon": "🕒", "type": "info",
                "text": (f"<strong>{c['pct']}%</strong> of {c['failure_type']} failures cluster on "
                         f"the <strong>{c['shift']} shift</strong> ({c['count']} of {c['total']})."),
            })

    return insights[:12] or [{
        "icon": "✅", "type": "success",
        "text": "No significant anomalies or repeat failures detected this period.",
    }]
