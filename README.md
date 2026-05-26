# ProdAI — Plant RCA System

An end-to-end Root Cause Analysis platform for industrial plant breakdowns. Combines a **server-rendered web dashboard + React SPA** (FastAPI + Jinja2 + Vite) with a **multi-agent AI pipeline** (LLM + RAG + knowledge graph + vision) to guide engineers from a single breakdown report through to a structured root cause and actionable CAPA plan.

---

## Architecture

```
rca/
├── app/                Web dashboard (port 8080) — auth, breakdown logging, RCA UI, SPA host
├── llm/                AI engine     (port 8000) — multi-agent pipeline, RAG, history matcher
├── data_ingestion/     Offline pipelines — PDFs → Weaviate, RCA records → Neo4j
└── docker-compose.yml  3 services: neo4j + llm + app
```

Three external systems are integrated:

| System | What it stores | How it's used |
|---|---|---|
| **SQLite** (in `app/`) | Users, breakdown logs, RCAs, CAPAs, equipment master | All operational data |
| **Weaviate Cloud** | OEM manual chunks (vector + BM25) | RAG retrieval for every domain agent and 5 Whys / Fishbone / CAPA step |
| **Neo4j 5** | Historical incidents + CAPAs + investigators (knowledge graph) | Similarity search for "have we seen this before?" + grounding CAPA generation |

The browser talks directly to **both** the dashboard and the AI engine:
- Page navigation → `http://localhost:8080`
- SSE AI streaming → `http://localhost:8000/analyze-prepare-stream` then `/analyze-finalize-stream`

---

## What the system does

End-to-end flow for one breakdown:

```
1. Engineer logs the breakdown      → SQLite (BreakdownLog)
2. Clicks "RCA AI Assist"
3. Phase 1 of AI pipeline runs:
       ├─ History matcher (Neo4j cosine similarity)  → past similar incidents
       ├─ Domain agents in parallel                  → mechanical / electrical / process
       ├─ Image analysis (vision LLM)                → if image was uploaded
       └─ Clarification generator                    → 3 targeted follow-up questions
4. Chatbot modal opens (MANDATORY)
       3 questions, per-format inputs (number, yes/no, free text), "I don't know" allowed
5. Phase 2 of AI pipeline runs:
       ├─ 5 Whys                                     → root cause + chain
       ├─ Fishbone (Ishikawa, 6 categories)          → contributing causes
       └─ CAPA tool                                  → structured corrective + preventive plan
                                                       grounded in past CAPAs from Neo4j
6. Report renders on screen (with all sections collapsible)
7. Engineer edits the CAPA rows, sets target dates, hits Save → JSON in BreakdownLog.rca_data
8. CSV / PDF export available
```

---

## Quick Start (Docker)

```bash
# 1. Add your API keys
cp llm/.env.example llm/.env
# Edit llm/.env:
#   LLM_PROVIDER=openrouter (or gemini)
#   OPENROUTER_API_KEY=...
#   WEAVIATE_URL=...
#   WEAVIATE_API_KEY=...

# 2. Bring up all 3 services
docker-compose up --build

# 3. Open the dashboard
# http://localhost:8080
```

Default login (seeded by `app/main.py` on first startup):
- `admin@plant.com` / `admin123` — Admin (sees all divisions)
- `bnfc@plant.com`, `pellet1@plant.com`, … / `pass123` — Per-division accounts

---

## Quick Start (Local Dev)

**Terminal 1 — AI Backend**
```bash
cd llm
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — Web Dashboard**
```bash
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

**Terminal 3 — SPA dev server** (only if editing React code)
```bash
cd app/frontend
npm install
npm run dev          # vite dev server
# When ready to ship:
npm run build        # outputs to app/static/spa/ (served by the deployed app)
```

**Optional — Neo4j** (history matcher is graceful if absent):
```bash
docker run -d --name neo4j-rca -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/rcapassword neo4j:5-community
# Then ingest your historical incidents:
cd data_ingestion/history
python build_knowledge_graph.py
```

---

## Key features

### AI pipeline (`llm/`)

- **Mandatory clarification chatbot** between the domain-agent stage and 5 Whys — 3 follow-up questions generated from competing hypotheses, missing metrics, history divergence, or top domain checks
- **Two-phase SSE pipeline**: `POST /analyze-prepare-stream` runs history + domain + image + question gen; `POST /analyze-finalize-stream` resumes with user answers and runs 5 Whys → Fishbone → CAPA
- **In-memory session cache** (15-min TTL) holds the intermediate state between phases
- **Multi-agent domain analysis** runs mechanical, electrical, process agents in parallel based on keyword routing
- **Confidence calibration** caps LLM-stated confidence based on evidence quality (measured / documented / inferred / none)
- **Causal sufficiency stop rule** — 5 Whys halts early when the current cause explains all observed symptoms, preventing over-escalation into speculative governance causes
- **Image vision analysis** runs in parallel with domain agents when an equipment photo is attached
- **Historical CAPA grounding** — past CAPAs from similar incidents (Neo4j) get injected into the CAPA generation prompt
- **Structured CAPA output** — corrective + preventive actions with priority, responsibility, related Fishbone category, references, target-date hint

### Web dashboard (`app/`)

- **JWT cookie auth**, bcrypt passwords, per-division access control
- **Server-rendered Jinja2 pages** for login, log-breakdown, and the RCA workflow (`create_rca.html` — the most feature-dense page in the system)
- **React SPA** (Vite) for dashboard, CAPA tracking, equipment master, historical analytics
- **AI-Suggested CAPA cards** with priority/responsibility/category badges
- **Editable CAPA table** pre-filled from AI output but fully overridable before save
- **User Inputs section** prints chatbot Q&A at the end of the report (screen-only — excluded from CSV/PDF exports)
- **CSV + PDF exports** of the formal report
- **Manual 5 Whys tree** for engineers who don't want AI assist

### Knowledge & data layer (`data_ingestion/`)

- **PDF processing pipeline** — extracts text, tables, images (vector + raster), runs OCR on scanned pages, chunks and uploads to Weaviate
- **Historical incident knowledge graph** — `build_knowledge_graph.py` ingests past RCA records into Neo4j with sentence-transformer embeddings; idempotent re-runs use `MERGE` to update without duplicating

---

## Default Users (seeded)

| Email | Password | Division |
|---|---|---|
| admin@plant.com | admin123 | Admin (sees all) |
| bnfc@plant.com | pass123 | BNFC |
| pellet1@plant.com / pellet2@plant.com | pass123 | Pellet 1 / 2 |
| sms1@plant.com / sms2@plant.com | pass123 | SMS 1 / 2 |
| dri1@plant.com / dri2@plant.com | pass123 | DRI 1 / 2 |
| cpp@plant.com / cpp2@plant.com | pass123 | CPP / CPP 2 |
| pgp@plant.com | pass123 | PGP |
| fireservice@plant.com | pass123 | Fire Service |

---

## Deployment

Current deployment: AWS EC2 t2.small (2 GB) running `docker-compose up`. Three containers:

- `neo4j` — graph DB, ports 7474/7687, persisted in `neo4j_data` volume
- `llm` — AI engine, port 8000, talks to Weaviate Cloud
- `app` — web dashboard, port 8080, SQLite in `app_data` volume

See [data_ingestion/history/neo4j deployment plan.txt](data_ingestion/history/neo4j%20deployment%20plan.txt) for the EC2 checklist (history ingestion, EBS persistence, security group lockdown, memory tuning).

Postgres migration path documented separately — when the t2.small instance gets memory-constrained, move SQLite → RDS `db.t3.micro`.

---

## Sub-project READMEs

- [app/README.md](app/README.md) — Web dashboard + SPA details + RCA workflow
- [llm/README.md](llm/README.md) — AI backend, endpoints, pipeline architecture, evidence validation
- [llm/tools/README.md](llm/tools/README.md) — Individual analysis tools (5 Whys, Fishbone, CAPA, Clarification Generator, History Matcher, Evidence Validator)
- [llm/domain_agents/README.md](llm/domain_agents/README.md) — Mechanical / Electrical / Process domain agents
- [data_ingestion/README.md](data_ingestion/README.md) — PDF → Weaviate + historical RCA → Neo4j pipelines
