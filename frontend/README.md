# Frontend — React UI

React single-page application for the RCA (Root Cause Analysis) system. Provides a form to submit equipment failures and displays progressive, real-time analysis results via Server-Sent Events (SSE).

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Component Architecture](#component-architecture)
- [SSE Streaming](#sse-streaming)
- [Progressive Result Display](#progressive-result-display)
- [Confidence Score UI](#confidence-score-ui)
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
├── main.jsx          # Entry point — mounts App
├── App.jsx           # Root component
├── RCAForm.jsx       # Main form + SSE stream controller
├── RCAResult.jsx     # Final analysis results display
├── DomainSummary.jsx # Progressive domain insights card
├── DomainResult.jsx  # Legacy per-domain result card
└── index.css         # Global design system
```

### `RCAForm.jsx` — The Controller

The heart of the UI. Manages all state and orchestrates the SSE stream:

- Builds and submits the analysis request
- Parses incoming SSE events (`status`, `domain_insights`, `result`, `error`)
- Progressively renders components as events arrive

**Key state:**
| State | Purpose |
|-------|---------|
| `statusMsg` | Current live status message (spinner) |
| `statusLog` | Previously completed steps (✓ list) |
| `domainInsights` | Domain agent findings — rendered immediately on arrival |
| `result` | Final full analysis result |

### `RCAResult.jsx` — The Results Card

Displays the full RCA output once the pipeline completes:

- **MOST LIKELY CAUSE** — root cause text + INFERRED/RAG-BACKED badge + confidence bar
- **5 Why Steps** — collapsible chain of why questions and answers
- **Corrective Actions** — ordered list of recommended fixes
- **Documents Referenced** — source OEM manuals used

### `DomainSummary.jsx` — Progressive Card

Rendered **immediately** when domain agents finish (before 5 Whys starts). Shows:

- Agents that analyzed the failure (Mechanical / Electrical / Process)
- Key findings with severity badges (CRITICAL / WARNING)
- Suspected root cause hypothesis per domain
- Recommended physical checks

---

## SSE Streaming

The frontend connects to `/analyze-integrated-stream` and reads a continuous stream of events:

```
event: status
data: {"message": "🔬 Domain experts analyzing failure..."}

event: domain_insights
data: {"domain_insights": { ... }}

event: result
data: {"status": "success", "result": { ... }}
```

**Parsing logic** (`readSSEStream` in `RCAForm.jsx`):

```javascript
// Each SSE chunk is split on "\n\n" (double-newline = event separator)
// Lines starting with "event:" set the event type
// Lines starting with "data:" contain the JSON payload
```

**Event routing:**

| Event | Handler | Effect |
|-------|---------|--------|
| `status` | `onStatus` | Updates spinner + appends to completed log |
| `domain_insights` | `onDomainInsights` | Renders `DomainSummary` immediately |
| `result` | `onResult` | Renders full `RCAResult` |
| `error` | `onError` | Shows error message |

---

## Progressive Result Display

The UI renders results in **two waves** — not all at once:

```
[Spinner: "🔬 Domain experts analyzing..."]
         ↓ ~30-45s
[DomainSummary card appears]
[Spinner: "🎯 Running 5 Whys..."]
         ↓ ~60-90s more
[RCAResult card appears]
```

**Why this matters:** The pipeline takes 2–3 minutes total. Showing domain insights early gives the user actionable information while the slower 5 Whys + Fishbone analysis runs.

**Render conditions:**
```jsx
{/* Shown as soon as domain_insights SSE event arrives */}
{domainInsights && <DomainSummary insights={domainInsights} />}

{/* Shows while 5 Whys is still running */}
{domainInsights && status === 'sending' && (
  <div className="section-divider">🎯 Main Root Cause Analysis (5 Whys)</div>
)}

{/* Final result after pipeline completes */}
{status === 'success' && result && <RCAResult data={result} />}
```

---

## Confidence Score UI

Each root cause is displayed with a compact inline confidence bar:

```
[INFERRED]  ▓▓▓▓▓▓▓░░░  85%
```

- **Badge** (`EvidenceBadge`): `INFERRED` (LLM-only) or `RAG-BACKED` (supported by OEM docs)
- **Bar track**: 80px wide, 5px tall — compact and non-intrusive
- **Colour coding:**
  - 🟢 Green: ≥ 80% confidence
  - 🟡 Amber: 60–79%
  - 🔴 Red: < 60%

---

## Styling System

All styles live in `index.css`. Key CSS classes:

| Class | Purpose |
|-------|---------|
| `.form-container` | Outer page wrapper with max-width |
| `.status-panel` | Live spinner panel during analysis |
| `.status-log` | Completed-steps log with ✓ bullets |
| `.result-card` | Main results container |
| `.most-likely-cause` | Highlighted root cause section |
| `.badge-confidence-row` | Flex row: badge left, bar right |
| `.confidence-bar-track` | Bar background track (80px wide) |
| `.confidence-bar-fill` | Animated coloured fill |
| `.section-divider` | Header between domain summary and RCA result |

**Design tokens (CSS variables):**
```css
--bg-primary: #0f1117       /* Dark background */
--bg-card: #161b27          /* Card surface */
--accent: #6366f1           /* Primary purple accent */
--text-primary: #e2e8f0     /* Main text */
--text-muted: #a0a8c0       /* Secondary text */
```
