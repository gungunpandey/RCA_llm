"""
AI-Generated Reliability Review — PowerPoint builder.

Produces an 8-slide management deck (+ cover) from:
  * the verified analysis bundle (insights_engine)  — numbers
  * the historical analytics rollup                 — trends / tables
  * an LLM-written narrative (with deterministic fallback)

Design principle carries over from the insights engine: every number printed on
a slide comes from the verified bundle/analytics. The LLM only writes prose
(executive summary, recommendations, decisions) and never invents figures.
"""
import io
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE


# ── palette (matches the ProdAI teal theme) ──────────────────────────────────
TEAL = RGBColor(0x33, 0xB1, 0xB0)
TEAL_DARK = RGBColor(0x2B, 0x8C, 0x8B)
DARK = RGBColor(0x1F, 0x2D, 0x3D)
GREY = RGBColor(0x64, 0x74, 0x8B)
RED = RGBColor(0xDC, 0x26, 0x26)
GREEN = RGBColor(0x16, 0xA3, 0x4A)
AMBER = RGBColor(0xB4, 0x7A, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF1, 0xF6, 0xF6)


# ── low-level helpers ────────────────────────────────────────────────────────
def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, left, top, width, height, color):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _text(slide, left, top, width, height, text, size=14, color=DARK,
          bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return box


def _header(slide, prs, idx, title):
    """Teal title band with a slide number badge."""
    _rect(slide, 0, 0, prs.slide_width, Inches(0.95), TEAL)
    _text(slide, Inches(0.55), Inches(0.18), prs.slide_width - Inches(1.6),
          Inches(0.6), title, size=26, color=WHITE, bold=True)
    _text(slide, prs.slide_width - Inches(1.0), Inches(0.25), Inches(0.7),
          Inches(0.5), str(idx), size=18, color=WHITE, bold=True, align=PP_ALIGN.RIGHT)


def _bullets(slide, items, left, top, width, height, size=15, color=DARK):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        run = p.add_run()
        run.text = f"•  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return box


def _table(slide, headers, rows, left, top, width, row_h=Inches(0.34)):
    n_rows = len(rows) + 1
    n_cols = len(headers)
    height = row_h * n_rows
    tbl = slide.shapes.add_table(n_rows, n_cols, left, top, width, height).table
    for c, h in enumerate(headers):
        cell = tbl.cell(0, c)
        cell.text = str(h)
        cell.fill.solid()
        cell.fill.fore_color.rgb = TEAL
        para = cell.text_frame.paragraphs[0]
        para.runs[0].font.size = Pt(11)
        para.runs[0].font.bold = True
        para.runs[0].font.color.rgb = WHITE
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if r % 2 else LIGHT
            para = cell.text_frame.paragraphs[0]
            para.runs[0].font.size = Pt(10.5)
            para.runs[0].font.color.rgb = DARK
    return tbl


def _metric_tiles(slide, metrics, left, top, total_width, prs):
    """Render exec-summary metric tiles in a row."""
    n = min(len(metrics), 4)
    if n == 0:
        return
    gap = Inches(0.2)
    tile_w = (total_width - gap * (n - 1)) / n
    tile_h = Inches(1.25)
    for i, m in enumerate(metrics[:n]):
        x = left + i * (tile_w + gap)
        accent = RED if m.get("good") is False else GREEN
        _rect(slide, x, top, tile_w, tile_h, LIGHT)
        _rect(slide, x, top, Inches(0.08), tile_h, accent)
        _text(slide, x + Inches(0.18), top + Inches(0.12), tile_w - Inches(0.3),
              Inches(0.4), m["label"].upper(), size=9.5, color=GREY, bold=True)
        _text(slide, x + Inches(0.18), top + Inches(0.45), tile_w - Inches(0.3),
              Inches(0.55), str(m["value"]), size=24, color=DARK, bold=True)
        if m.get("trend"):
            arrow = "▲" if m.get("direction") == "up" else "▼" if m.get("direction") == "down" else ""
            _text(slide, x + Inches(0.18), top + Inches(0.95), tile_w - Inches(0.3),
                  Inches(0.3), f"{arrow} {m['trend']}", size=11, color=accent, bold=True)


# ── deterministic narrative (fallback when LLM is unavailable) ────────────────
def deterministic_narrative(bundle: dict, analytics: dict) -> dict:
    es = bundle.get("executive_summary", {}) or {}

    exec_bullets = []
    for m in es.get("metrics", []):
        line = f"{m['label']}: {m['value']}"
        if m.get("trend"):
            line += f" ({m['trend']})"
        exec_bullets.append(line)

    rca_bullets = [f"{r['category']}: {r['count']} failures"
                   for r in (analytics.get("rootCause") or [])[:6]]

    rec = list(es.get("recommended_focus", []))
    if not rec:
        rec = ["Maintain current preventive-maintenance cadence; no critical focus areas flagged."]

    mgmt = []
    for c in bundle.get("unimplemented_capa_recurrence", [])[:3]:
        mgmt.append(f"Assign owner and deadline to close CAPA #{c['capa_id']} on "
                    f"{c['machine']} — failures are recurring while it stays open.")
    if bundle.get("capa_stats", {}).get("overdue"):
        mgmt.append(f"Review {bundle['capa_stats']['overdue']} overdue CAPA(s) for re-prioritization.")
    if not mgmt:
        mgmt = ["No critical management decisions flagged for this period."]

    return {
        "executive_summary": exec_bullets or ["No significant maintenance activity in this period."],
        "root_cause_analysis": rca_bullets or ["No failure-type data recorded for this period."],
        "recommended_actions": rec,
        "management_decisions": mgmt,
    }


# ── slide builders ───────────────────────────────────────────────────────────
def _cover(prs, meta):
    slide = _blank(prs)
    _rect(slide, 0, 0, prs.slide_width, prs.slide_height, DARK)
    _rect(slide, 0, Inches(2.55), prs.slide_width, Inches(0.06), TEAL)
    _text(slide, Inches(0.8), Inches(1.5), prs.slide_width - Inches(1.6),
          Inches(1.0), "Reliability Review", size=44, color=WHITE, bold=True)
    _text(slide, Inches(0.8), Inches(2.7), prs.slide_width - Inches(1.6),
          Inches(0.6), meta["scope"], size=20, color=TEAL, bold=True)
    _text(slide, Inches(0.8), Inches(3.4), prs.slide_width - Inches(1.6),
          Inches(0.5), f"Period: {meta['period']}", size=15, color=LIGHT)
    _text(slide, Inches(0.8), Inches(3.85), prs.slide_width - Inches(1.6),
          Inches(0.5), f"Generated by ProdAI · {meta['generated']}", size=12, color=GREY)


def _slide_exec(prs, bundle, narrative):
    slide = _blank(prs)
    _header(slide, prs, 1, "Executive Summary")
    es = bundle.get("executive_summary", {}) or {}
    _metric_tiles(slide, es.get("metrics", []), Inches(0.55), Inches(1.2),
                  prs.slide_width - Inches(1.1), prs)
    _bullets(slide, narrative.get("executive_summary", []),
             Inches(0.55), Inches(2.75), prs.slide_width - Inches(1.1), Inches(4.0), size=15)


def _slide_trends(prs, analytics):
    slide = _blank(prs)
    _header(slide, prs, 2, "Breakdown Trends")
    d = analytics.get("direction") or {}
    pct = d.get("pct")
    trend_txt = ("Stable failure rate" if pct is None
                 else f"Failures {'increasing' if d.get('direction') == 'up' else 'decreasing'} "
                      f"{'+' if d.get('direction') == 'up' else ''}{pct}% (recent half: "
                      f"{d.get('recent', 0)} vs prior half: {d.get('previous', 0)})")
    _text(slide, Inches(0.55), Inches(1.2), prs.slide_width - Inches(1.1),
          Inches(0.5), trend_txt, size=16, color=DARK, bold=True)

    rows = [[t.get("period", "—"), t.get("failures", 0),
             f"{t.get('avg_mttr', 0)} h"] for t in (analytics.get("trend") or [])]
    if rows:
        _table(slide, ["Period", "Failures", "Avg MTTR"], rows,
               Inches(0.55), Inches(1.9), Inches(6.0))
    else:
        _text(slide, Inches(0.55), Inches(1.9), Inches(6), Inches(0.5),
              "No trend data for this period.", size=13, color=GREY)


def _slide_top_equipment(prs, analytics):
    slide = _blank(prs)
    _header(slide, prs, 3, "Top Problem Equipment")
    top = analytics.get("top")
    if top:
        _text(slide, Inches(0.55), Inches(1.2), Inches(8), Inches(0.5),
              f"{top['equipment_name']}  —  {top['failure_count']} failures",
              size=18, color=RED, bold=True)
        _text(slide, Inches(0.55), Inches(1.75), Inches(9), Inches(0.4),
              f"Plant: {top.get('category', '—')}    |    Criticality: "
              f"{top.get('criticality', '—')}    |    Avg MTTR: {top.get('avg_mttr', 0)} h",
              size=12, color=GREY)
    rows = [[f["equipment_name"], f["failure_count"], f.get("category", "—")]
            for f in (analytics.get("freq") or [])[:10]]
    if rows:
        _table(slide, ["Equipment", "Failures", "Plant"], rows,
               Inches(0.55), Inches(2.4), Inches(8.5))


def _slide_rca(prs, analytics, narrative):
    slide = _blank(prs)
    _header(slide, prs, 4, "Root Cause Analysis")
    rows = [[r["category"], r["count"]] for r in (analytics.get("rootCause") or [])[:8]]
    if rows:
        _table(slide, ["Failure Category", "Count"], rows,
               Inches(0.55), Inches(1.2), Inches(4.5))
    _bullets(slide, narrative.get("root_cause_analysis", []),
             Inches(5.4), Inches(1.2), prs.slide_width - Inches(6.0), Inches(4.5), size=14)


def _slide_capa(prs, bundle):
    slide = _blank(prs)
    _header(slide, prs, 5, "CAPA Effectiveness")
    eff = bundle.get("capa_effectiveness") or []
    if eff:
        rows = [[e["machine"], f"#{e['capa_id']}", e["before"], e["after"],
                 f"{e['change_pct']}%", "Improved" if e["improved"] else "No change"]
                for e in eff]
        _table(slide, ["Equipment", "CAPA", "Before", "After", "Change", "Result"],
               rows, Inches(0.55), Inches(1.3), Inches(9.0))
    else:
        _text(slide, Inches(0.55), Inches(1.4), Inches(9), Inches(1.0),
              "No completed CAPAs with a fully-elapsed comparison window yet. "
              "Effectiveness will populate as CAPAs are closed and time passes.",
              size=14, color=GREY)
    stats = bundle.get("capa_stats") or {}
    if stats.get("total"):
        _text(slide, Inches(0.55), Inches(5.4), Inches(9), Inches(0.5),
              f"CAPA compliance this period: {stats.get('compliance_pct', 0)}%  "
              f"({stats.get('completed', 0)}/{stats.get('total', 0)} completed, "
              f"{stats.get('overdue', 0)} overdue)", size=13, color=DARK, bold=True)


def _slide_risks(prs, bundle):
    slide = _blank(prs)
    _header(slide, prs, 6, "Predicted Risks")
    _text(slide, Inches(0.55), Inches(1.1), prs.slide_width - Inches(1.1), Inches(0.4),
          "Elevated risk based on recent activity — not a guaranteed forecast.",
          size=11, color=GREY)
    risks = bundle.get("risk_alerts") or []
    if risks:
        rows = [[r["machine"], r["risk_level"], r["failures"],
                 r.get("criticality") or "—", "; ".join(r["reasons"][:2])]
                for r in risks]
        _table(slide, ["Equipment", "Risk", "Failures", "Criticality", "Why"],
               rows, Inches(0.55), Inches(1.65), Inches(9.2))
    else:
        _text(slide, Inches(0.55), Inches(1.8), Inches(9), Inches(0.5),
              "No elevated-risk assets detected this period.", size=14, color=GREEN, bold=True)


def _slide_actions(prs, narrative):
    slide = _blank(prs)
    _header(slide, prs, 7, "Recommended Actions")
    _bullets(slide, narrative.get("recommended_actions", []),
             Inches(0.6), Inches(1.3), prs.slide_width - Inches(1.2), Inches(5.0), size=16)


def _slide_decisions(prs, narrative):
    slide = _blank(prs)
    _header(slide, prs, 8, "Management Decisions Required")
    _bullets(slide, narrative.get("management_decisions", []),
             Inches(0.6), Inches(1.3), prs.slide_width - Inches(1.2), Inches(5.0), size=16)


# ── public API ───────────────────────────────────────────────────────────────
def build_deck(meta: dict, analytics: dict, bundle: dict, narrative: dict) -> io.BytesIO:
    """Assemble the full reliability-review deck and return it as a BytesIO."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    _cover(prs, meta)
    _slide_exec(prs, bundle, narrative)
    _slide_trends(prs, analytics)
    _slide_top_equipment(prs, analytics)
    _slide_rca(prs, analytics, narrative)
    _slide_capa(prs, bundle)
    _slide_risks(prs, bundle)
    _slide_actions(prs, narrative)
    _slide_decisions(prs, narrative)

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf
