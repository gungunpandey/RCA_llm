# Frontend — React UI

React single-page application for the RCA (Root Cause Analysis) system. Provides a structured form to submit equipment failures and displays a formal RCA report with full analysis results via Server-Sent Events (SSE).

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Component Architecture](#component-architecture)
- [Form Fields](#form-fields)
- [Output Layout](#output-layout)
- [SSE Streaming](#sse-streaming)
- [CSV Export](#csv-export)
- [Styling System](#styling-system)

---

## Quick Start

```bash
cd frontend
npm install
npm run dev        # Starts dev server at http://localhost:5173
```

**Requires:** Backend API running at `http://localhost:8000`

---

## Component Architecture

```
src/
├── main.jsx            # Entry point — mounts App
├── App.jsx             # Root layout: sidebar (form) + main panel (results)
├── RCAForm.jsx         # Input form + SSE stream controller
├── RCAReportTable.jsx  # Formal RCA report table (snapshot-style) + CSV download
├── RCAResult.jsx       # Fishbone + collapsible domain/5-whys details
├── FishboneCanvas.jsx  # Interactive SVG Ishikawa diagram
├── DomainResult.jsx    # Per-domain agent card (utility component)
└── index.css           # Global design system (~1800 lines)
```

### `App.jsx` — Layout & State

Two-panel shell: left sidebar (form) and right main panel (results).

- Holds top-level state: `result`, `domainInsights`, `analysisStatus`, `statusLog`
- **On success:** renders `RCAReportTable` first (upfront), then `RCAResult` (scroll down)
- **During analysis:** shows live SSE status spinner with completed-steps log

### `RCAForm.jsx` — Controller

Manages all form state and the SSE stream. On submit, connects to `/analyze-integrated-stream` (or `/analyze-stream` if domain toggle is off), parses events, and attaches `_formMeta` to the result payload so the report table has access to all user-entered fields.

**Key state:**

| State | Purpose |
|-------|---------|
| `form` | All input field values |
| `status` | `null` / `sending` / `success` / `error` |
| `statusMsg` | Current live status message (spinner) |
| `includeDomain` | Toggle for domain expert pipeline |

### `RCAReportTable.jsx` — Formal Report

Renders the snapshot-style tabular RCA report upfront as soon as analysis completes:

- **Header meta:** Department, Equipment, Occurrence From/To, Downtime, Production loss, Top-line impact
- **Problem statement:** From form input
- **5 Why Analysis table:** Why 1–5 (or fewer if causal sufficiency stops early)
- **Root Cause row:** Synthesized final root cause (distinct from any single why step)
- **CAPA table:** Editable rows for preventive action, responsibility, target date
- **CSV download:** Exports full report including CAPA rows

### `RCAResult.jsx` — Analysis Details

Shown below the report table. Contains two collapsible sections:

1. **Fishbone (Ishikawa)** — SVG canvas, always visible on load, can be collapsed
2. **Root Cause Reasoning Details** — two expand toggles:
   - 🔬 Domain Expert Insights (Mechanical / Electrical / Process findings)
   - 📋 Detailed 5 Whys Reasoning (question + answer + evidence badges per step)

### `FishboneCanvas.jsx` — Interactive SVG Diagram

- Fixed 1280 × 560 SVG canvas, scales with `viewBox`
- 6 Ishikawa categories: Machine, Material, Environment (top) + Method, Man, Measurement (bottom)
- Hover a bone branch to dim all others; click a leaf node to highlight it
- Evidence levels: `CONFIRMED` (green) / `SUPPORTED` (blue) / `POSSIBLE` (amber) / `EFFECT` (grey)
- Click root cause head to open the 5 Whys timeline modal

---

## Form Fields

| Field | Maps to |
|-------|---------|
| Department | `_formMeta.department` |
| Equipment name / Place of occurrence | `equipment_name` (API payload) |
| Occurrence — Date & time (From) | `occurrence_from` (API + `_formMeta`) |
| Occurrence — Date & time (To) | `occurrence_to` (API + `_formMeta`) |
| Total down time | `_formMeta.total_downtime` |
| Production loss | `_formMeta.production_loss` |
| Impact of top line | `_formMeta.impact_top_line` |
| Problem statement | `failure_description` (API payload) |
| Symptoms | `symptoms[]` (API payload) |
| Operator Observations | `operator_observations` (API payload) |
| Include Domain Expert Analysis | toggle — routes to integrated or 5-whys-only endpoint |

> `_formMeta` is a client-side object attached to the API result before passing it to the report component. It is not sent to the backend — it stays in the browser session.

---

## Output Layout

After analysis completes, the right panel renders in this order (top to bottom):

```
┌──────────────────────────────────────┐
│  RCA Report            ⬇ Download CSV │  ← always visible upfront
│  [meta table]                         │
│  [5 Why Analysis]                     │
│  [Root Cause] ← synthesized, distinct │
│  [CAPA table — editable]              │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  🦴 Fishbone Diagram  [Collapse ▼]   │  ← scroll down
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  🔬 Root Cause Reasoning Details     │
│  [ Show Domain Expert Insights ▶ ]   │  ← collapsed by default
│  [ Show 5 Whys Reasoning ▶ ]         │  ← collapsed by default
└──────────────────────────────────────┘
```

---

## SSE Streaming

The frontend connects to `/analyze-integrated-stream` and reads a continuous event stream:

```
event: status
data: {"message": "🔬 Domain experts analyzing failure..."}

event: domain_insights
data: {"domain_insights": { ... }}

event: result
data: {"status": "success", "result": { ... }}
```

**Event routing:**

| Event | Effect |
|-------|--------|
| `status` | Updates spinner text + appends to completed-steps log |
| `domain_insights` | Stored in state (used in RCAResult expand section) |
| `result` | Triggers report + result render; `_formMeta` is attached here |
| `error` | Shows error message in main panel |

---

## CSV Export

Clicking **⬇ Download CSV** in the report header exports a `.csv` file containing:

- All header meta fields (department, equipment, dates, downtime, etc.)
- Problem statement
- Why 1–5 answers
- Root cause
- CAPA table rows (including any edits made in the browser)

File is named: `RCA_Report_<equipment>_<date>.csv`

---

## Styling System

All styles live in `index.css` (~1800 lines). Key class groups:

| Class prefix | Purpose |
|---|---|
| `.app-*` | Two-panel shell layout |
| `.form-*` | Sidebar form and field styles |
| `.rca-report-*` | Formal report table (RCAReportTable) |
| `.fishbone-*` | Fishbone canvas section and SVG wrappers |
| `.domain-*` | Domain agent cards and findings |
| `.why-*` | 5 Whys timeline steps |
| `.evidence-badge` | Evidence level pill (From Alarm / From Manual / Inferred) |
| `.confidence-*` | Confidence bar track and fill |
| `.section-divider` | Section header between result blocks |
| `.expand-toggle` | Collapsible section toggle button |
| `.main-status-*` | Live status panel during analysis |

**Colour coding (confidence):**
- 🟢 `#34d399` — ≥ 85%
- 🟡 `#fbbf24` — 60–84%
- 🔴 `#f87171` — < 60%
