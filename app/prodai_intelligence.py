"""
ProdAI Intelligence — top-of-page analytics features for the Historical
Failure Analytics (ProdAI) page.

Three features, all computed deterministically from the verified analysis
bundle (insights_engine) + analytics rollup — same principle as the rest of
ProdAI: numbers are real, never model-invented.

  1. Reliability Score   — single 0-100 score + drivers + improvement opps
  2. Failure Pattern Explorer — hidden patterns as cards
  3. AI Action Prioritizer    — ranked "what to fix first" list
"""


def _grade(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "At Risk"


def _opportunity_for(label: str) -> str:
    l = label.lower()
    if "compliance" in l:
        return "Close out open CAPAs to lift compliance."
    if "overdue" in l:
        return "Clear overdue CAPAs — assign owners and deadlines."
    if "repeat" in l:
        return "Eliminate recurring root causes with targeted CAPA."
    if "rising" in l:
        return "Investigate the assets driving the failure increase."
    if "high-risk" in l:
        return "Prioritize inspection of high-risk assets."
    return "Maintain preventive-maintenance cadence."


def compute_reliability(analytics: dict, bundle: dict) -> dict:
    """0-100 reliability score with transparent, explainable deductions."""
    totals = bundle.get("totals", {}) or {}
    mttr = bundle.get("mttr_trend", {}) or {}
    capa = bundle.get("capa_stats", {}) or {}
    repeats = bundle.get("repeat_failures", []) or []
    risks = bundle.get("risk_alerts", []) or []

    score = 100.0
    components = []

    def deduct(label, amount):
        nonlocal score
        amount = round(amount)
        if amount > 0:
            score -= amount
            components.append({"label": label, "impact": -amount})

    def credit(label, amount):
        nonlocal score
        amount = round(amount)
        if amount > 0:
            score += amount
            components.append({"label": label, "impact": amount})

    pc = totals.get("pct_change")
    if totals.get("reliable") and pc is not None:
        if pc > 0:
            deduct(f"Failures rising {pc}%", min(25, pc * 0.5))
        elif pc < 0:
            credit(f"Failures falling {abs(pc)}%", min(10, abs(pc) * 0.2))

    comp = capa.get("compliance_pct")
    if comp is not None:
        deduct(f"CAPA compliance {comp}%", (100 - comp) * 0.25)

    overdue = capa.get("overdue", 0)
    if overdue:
        deduct(f"{overdue} overdue CAPA(s)", min(15, overdue * 5))

    if repeats:
        deduct(f"{len(repeats)} repeat-failure cluster(s)", min(15, len(repeats) * 5))

    high = [r for r in risks if r.get("risk_level") == "High"]
    if high:
        deduct(f"{len(high)} high-risk asset(s)", min(20, len(high) * 7))

    score = max(0, min(100, round(score)))

    drivers = sorted([c for c in components if c["impact"] < 0], key=lambda c: c["impact"])
    opportunities = []
    for c in drivers[:3]:
        opp = _opportunity_for(c["label"])
        if opp not in opportunities:
            opportunities.append(opp)

    return {
        "score": score,
        "grade": _grade(score),
        "components": components or [{"label": "Stable baseline", "impact": 0}],
        "drivers": [c["label"] for c in drivers] or ["No major negative drivers this period"],
        "opportunities": opportunities or ["Maintain current preventive-maintenance cadence"],
        "mttr_avg": mttr.get("current_avg"),
        "failures": totals.get("current"),
        "capa_compliance": comp,
    }


def compute_patterns(bundle: dict) -> list:
    """Failure Pattern Explorer — hidden patterns surfaced as cards."""
    cards = []

    for a in (bundle.get("equipment_anomalies") or [])[:3]:
        if a.get("reliable"):
            drv = f" — mostly {a['dominant_driver']['value']}" if a.get("dominant_driver") else ""
            cards.append({"icon": "📈", "type": "warning", "title": f"{a['equipment']} rising",
                          "text": f"Failures up {a['previous']} → {a['current']}{drv}."})

    for s in (bundle.get("plant_contribution_shifts") or [])[:2]:
        if s.get("reliable"):
            cards.append({"icon": "🏭", "type": "warning", "title": f"{s['plant']} share climbing",
                          "text": f"Now {s['current_pct']}% of failures (was {s['baseline_pct']}%)."})

    for c in (bundle.get("correlations") or [])[:2]:
        if c["type"] == "shift":
            cards.append({"icon": "🕒", "type": "info", "title": f"{c['shift']}-shift concentration",
                          "text": f"{c['pct']}% of failures on the {c['shift']} shift ({c['count']}/{c['total']})."})
        else:
            cards.append({"icon": "🕒", "type": "info", "title": f"{c['failure_type']} clusters at {c['shift']}",
                          "text": f"{c['pct']}% of {c['failure_type']} failures on the {c['shift']} shift."})

    for r in (bundle.get("repeat_failures") or [])[:2]:
        if r["type"] == "root_cause":
            cards.append({"icon": "🔁", "type": "danger", "title": "Recurring root cause",
                          "text": f"{r['count']} breakdowns share: \"{r['root_cause']}\"."})
        else:
            cards.append({"icon": "🔁", "type": "warning", "title": f"{r['equipment']} weak point",
                          "text": f"{r['component']} failed {r['count']}× this period."})

    if not cards:
        cards.append({"icon": "✅", "type": "success", "title": "No standout patterns",
                      "text": "No significant hidden patterns detected this period."})
    return cards[:6]


def compute_actions(bundle: dict) -> list:
    """AI Action Prioritizer — ranked 'what to fix first' list."""
    actions = []

    for c in (bundle.get("unimplemented_capa_recurrence") or []):
        actions.append({"priority": "Critical", "score": 100 + c.get("recurred_count", 0),
                        "title": f"Close CAPA #{c['capa_id']} on {c['machine']}",
                        "why": f"Failed again {c['recurred_count']}× while the CAPA is still {c['capa_status']}.",
                        "area": c["machine"]})

    for r in (bundle.get("risk_alerts") or []):
        high = r.get("risk_level") == "High"
        actions.append({"priority": "High" if high else "Medium",
                        "score": r.get("score", 0) + (50 if high else 20),
                        "title": f"Inspect {r['machine']}",
                        "why": f"{r['failures']} failures this period; {r['reasons'][0]}.",
                        "area": r["machine"]})

    for r in (bundle.get("repeat_failures") or []):
        if r["type"] == "root_cause":
            actions.append({"priority": "High", "score": 40 + r["count"],
                            "title": "Eliminate recurring root cause",
                            "why": f"{r['count']} breakdowns share: \"{r['root_cause']}\".", "area": "Multiple"})
        else:
            actions.append({"priority": "Medium", "score": 25 + r["count"],
                            "title": f"Address {r['equipment']} — {r['component']}",
                            "why": f"Failed {r['count']}× this period.", "area": r["equipment"]})

    for a in (bundle.get("equipment_anomalies") or []):
        if a.get("reliable"):
            actions.append({"priority": "Medium", "score": 15 + a["delta"],
                            "title": f"Investigate rising {a['equipment']} failures",
                            "why": f"Up {a['previous']} → {a['current']} this period.", "area": a["equipment"]})

    seen, uniq = set(), []
    for a in sorted(actions, key=lambda x: x["score"], reverse=True):
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        uniq.append(a)

    if not uniq:
        uniq = [{"priority": "Low", "score": 0, "title": "No urgent actions",
                 "why": "No critical issues detected this period.", "area": "—"}]

    for i, a in enumerate(uniq[:8], 1):
        a["rank"] = i
    return uniq[:8]


def compute_all(analytics: dict, bundle: dict) -> dict:
    return {
        "reliability": compute_reliability(analytics, bundle),
        "patterns": compute_patterns(bundle),
        "actions": compute_actions(bundle),
    }
