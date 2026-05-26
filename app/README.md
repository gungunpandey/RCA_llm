# app/ — ProdAI Web Dashboard

FastAPI server-rendered web app that handles authentication, breakdown logging, the RCA workflow, and the dashboards. Talks to the `llm/` service for AI analysis and to Neo4j (via `llm/`) for historical incident matching.

## Stack

- **Backend**: FastAPI + Jinja2 + SQLAlchemy + SQLite
- **Auth**: JWT in HTTP-only cookie, bcrypt password hashing
- **Frontend**:
  - **Jinja2 templates** for login, log-breakdown, and the AI/manual RCA page (`create_rca.html`)
  - **React SPA** (Vite build, served from `static/spa/`) for the dashboard, CAPA tracking, equipment master, and analytics pages
- **AI integration**: SSE streams from `llm/api/main.py` (default `http://localhost:8000`)
- **Knowledge graph**: Neo4j (queried indirectly via `llm/tools/history_matcher.py`)
- **RAG**: Weaviate Cloud (managed externally, configured in `llm/`)

## Structure

```
app/
├── main.py                FastAPI app — routes, auth, SPA mounting
├── api_routes.py          JSON API endpoints consumed by the SPA
├── database.py            SQLAlchemy models (User, BreakdownLog, Equipment, CAPA)
├── requirements.txt
├── Dockerfile
├── templates/             Jinja2 server-rendered pages
│   ├── base.html          Layout, nav, glassmorphism theme
│   ├── login.html
│   ├── dashboard.html
│   ├── log_breakdown.html
│   └── create_rca.html    AI assist tab (with chatbot, CAPA) + manual tree tab
├── frontend/              React + Vite source for the SPA
│   └── src/
│       ├── pages/         DashboardPage, BreakdownLogPage, CAPATrackingBoard,
│       │                  CAPADetailPage, CAPACreationPage, EquipmentMasterPage,
│       │                  HistoricalAnalyticsPage, LoginPage
│       ├── components/    NavBar, BreakdownTable, FailuresPieChart, MTTRChart,
│       │                  KPICard, RCAList, FileUpload, TopEquipment, …
│       ├── api/           dashboard.js, breakdown.js, equipment.js, analytics.js
│       └── context/       AuthContext, ProtectedRoute
├── static/
│   ├── favicon.svg
│   ├── spa/               Vite production build (output of `npm run build`)
│   └── uploads/           User-uploaded images and PDFs
├── data/                  CSV seeds for bulk import
└── scripts/               DB migration / seed helpers
```

## Routes

### Server-rendered (Jinja2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Login page (redirects to `/dashboard` if authenticated) |
| POST | `/login` | Authenticate, set JWT cookie |
| GET | `/register` | Create-account page |
| POST | `/register` | Create user + auto-login |
| GET | `/logout` | Clear cookie, redirect to login |
| GET | `/log-breakdown` | Breakdown entry form |
| POST | `/log-breakdown` | Submit breakdown → redirect to `/create-rca/{id}?ai=true` or manual |
| GET | `/create-rca/{id}` | AI assist + manual 5 Whys tree (Jinja template) |
| POST | `/save-rca/{id}` | Persist RCA JSON (AI or manual) to DB |
| POST | `/update-status/{id}` | Change breakdown status inline |

### SPA-bound (React, served from `/`)

The React SPA mounts at `/dashboard`, `/breakdowns`, `/capa`, `/capa/{id}`, `/equipment`, `/analytics`, etc. and consumes the JSON endpoints in `api_routes.py`.

### JSON API (consumed by SPA)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/summary` | KPIs, recent breakdowns, failure mix |
| GET | `/api/dashboard/mttr-weekly?month=YYYY-MM` | Weekly MTTR series |
| GET | `/api/breakdowns` | List + filter breakdowns |
| GET | `/api/equipment` | Equipment master list (search + criticality filter) |
| GET | `/api/equipment/{id}` | Equipment detail |
| POST | `/api/equipment` | Create equipment |
| GET | `/api/analytics/historical` | Aggregations for the historical analytics page |
| GET | `/api/capa/*` | CAPA tracking endpoints |

(For the exact route surface, see `api_routes.py`.)

## SPA Pages — what each one does

| Page | Highlights |
|---|---|
| **Dashboard** | KPI cards (open / resolved / MTTR / production loss), failure-mix pie chart, MTTR trend (with reference line), recent breakdowns table |
| **Log Breakdown** | Multi-step form; "Plant" / equipment / downtime / observations / image upload; one-click hand-off to AI RCA |
| **Create RCA** (Jinja, not SPA) | The AI workflow lives here — see "AI RCA workflow" below |
| **CAPA Tracking Board** | Kanban-style board for CAPA actions across all RCAs |
| **CAPA Detail** | Drill-down for a single CAPA — responsibility, target date, status, evidence |
| **CAPA Creation** | Manual CAPA entry (separate from AI-generated CAPAs) |
| **Equipment Master** | Sortable + filterable table with sticky header, criticality badges, plant filter, add-equipment form |
| **Historical Analytics** | Trend cards (top recurring failures, MTTR by plant/equipment), criticality breakdowns |
| **Login** | Glassmorphism light theme, "ProdAI" branding |

## AI RCA workflow (`create_rca.html`)

The most feature-dense page in the system. Here is the full pipeline as of today:

```
User logs breakdown
       │
       ▼
POST /analyze-prepare-stream   (llm backend)
       │
       ▼
SSE events stream in real time:
  ├─ history_matches        Top-3 similar past incidents from Neo4j
  ├─ domain_insights        Parallel domain agents (mechanical / electrical / process)
  ├─ image_analysis         Vision model output (if an image was uploaded)
  ├─ clarifying_questions   3 follow-up questions from ClarificationGenerator
  └─ prepare_complete       { session_id, expires_at }
       │
       ▼
Chatbot modal opens (mandatory)
  - 3 questions, one per card
  - Per-format inputs: number+units, yes/no, free text
  - "I don't know" allowed but every question must be answered to continue
       │
       ▼
POST /analyze-finalize-stream   (llm backend, session_id + answers)
       │
       ▼
SSE events:
  ├─ status        5 Whys progress per step
  ├─ capa          Structured CAPA plan (corrective + preventive)
  └─ result        Final report payload
       │
       ▼
Report renders (collapsible sections):
  ├─ Formal RCA Table     Equipment / dates / downtime / root cause
  ├─ Historical Matches   Same incidents from Neo4j with CAPA hints
  ├─ Domain Insights      Per-domain findings, hypotheses, recommended checks
  ├─ Image Analysis       If applicable
  ├─ Detailed 5 Whys      Per-step answer, evidence, confidence
  ├─ Fishbone Diagram     6 Ishikawa categories with primary highlighted
  ├─ AI-Suggested CAPA    Corrective + preventive cards with priority,
  │                       responsibility, related Fishbone category, references
  ├─ Editable CAPA Table  Pre-filled from AI suggestions, fully editable
  ├─ Investigation Team   Free-text input
  └─ User Inputs          Chatbot Q&A printed at the end of the report
                          (screen-only — excluded from CSV/PDF exports)
```

### Manual mode

The page has a second tab — **Manual 5 Whys Tree** — for engineers who don't want AI assist. The tree is drag-rearrangeable, nodes are editable, and the result saves alongside AI runs in `BreakdownLog.rca_data`.

### Export

CSV + PDF buttons at the bottom of the AI report. Both pull from the editable CAPA table, so any edits the user makes to AI-suggested CAPAs are reflected in the export. The User Inputs section is intentionally **not** exported.

## Database

SQLite file: `plant_dashboard_v2.db` (auto-created on startup, mounted to `/app/data/` in Docker).

Key models in `database.py`:

| Model | Purpose |
|---|---|
| `User` | id, email, hashed_password, name, division, registered_at |
| `BreakdownLog` | machine, division, description, downtime, status, start/end times, **`rca_data` (Text)** |
| `Equipment` | name, asset_tag, category, criticality, plant, dates |
| `CAPA` | action, responsibility, target_date, status — tracked across RCAs |

`BreakdownLog.rca_data` stores JSON in one of three formats:
- `{"type": "ai_generated", ...}` — full AI result (`five_whys_analysis`, `fishbone_analysis`, `capa_actions`, `domain_insights`, `user_clarifications`, etc.) + the editable CAPA rows + team list
- `{"type": "manual_tree", "nodes": [...]}` — manual 5 Whys tree
- `[{id, parentId, text}, ...]` — legacy format (auto-migrated on read)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_API_URL` | `http://localhost:8000` | URL the browser uses to hit the `llm/` service (SSE streams) |
| `APP_PORT` | `8080` | Web server port |
| `SECRET_KEY` | (insecure default) | JWT signing key — **change in production** |
| `DATABASE_URL` | `sqlite:///./plant_dashboard_v2.db` | Override if migrating to Postgres |

## Running locally

```powershell
# Backend (RCA AI engine)
cd llm
uvicorn api.main:app --reload --port 8000

# In another shell — web app
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8080

# In a third shell — SPA (only when actively editing React code)
cd app/frontend
npm install
npm run dev          # vite dev server
# or
npm run build        # produces static/spa/ — used by the deployed app
```

Open `http://localhost:8080`. Default seeded users live in `main.py` (12 division admins). Neo4j is optional locally — if it's not running, the history matcher returns empty and the rest of the pipeline still works.

## Deployment

Three-container docker-compose at the repo root:

| Service | Purpose | Port |
|---|---|---|
| `neo4j` | Knowledge graph for historical incidents | 7474 (UI), 7687 (Bolt) |
| `llm` | AI pipeline (FastAPI on `:8000`) | 8000 |
| `app` | Web dashboard (FastAPI on `:8080`) | 8080 |

Current deployment: AWS EC2 (t2.small, 2 GB). See `data_ingestion/history/neo4j deployment plan.txt` for the EC2 checklist (data ingestion, EBS persistence, security group lockdown, memory tuning).

## Features added in the recent work cycle

- **Mandatory clarification chatbot** between the domain-agent stage and 5 Whys — generates 3 targeted questions per RCA (deterministic builders + optional LLM ranker), enforced server-side on `/analyze-finalize-stream`
- **Two-phase SSE pipeline** (`/analyze-prepare-stream` + `/analyze-finalize-stream`) with in-memory `SessionCache` (15 min TTL) holding intermediate state between phases
- **Structured CAPA generation** — `CAPATool` produces corrective + preventive actions with priority, responsibility, related Fishbone category, references; grounded in past CAPAs from Neo4j matches
- **AI-Suggested CAPA cards** above the editable table; editable table is pre-filled from the structured AI output (action + responsibility)
- **User Inputs section** at the end of the report (chatbot Q&A) — visible on-screen, excluded from CSV/PDF exports by design
- **Equipment Master upgrades** — sticky table header, sort modes, plant filter
- **Breakdown table upgrades** — sort fields, status filter dropdown, severity colors, `showAll` toggle
- **Dashboard upgrades** — `INSIGHT_STYLES`, multi-insight builder, configurable MTTR/breakdown range
- **Failures pie chart** — custom SVG implementation (no recharts dependency)
- **Terminology** — "Division" → "Plant" in user-facing labels (DB still uses `division` field for compatibility)
- **MTTR chart** — orange accent + reference line
- **NavBar** — buttons no longer wrap on narrow viewports
