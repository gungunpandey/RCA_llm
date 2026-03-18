# ProdAI — Plant RCA Dashboard

A web-based Root Cause Analysis system for industrial plant breakdowns.
Combines a **server-rendered dashboard** (FastAPI + Jinja2) with an **AI analysis engine** (LLM + RAG) to guide 5 Whys investigations.

---

## Architecture

```
rca/
├── app/          Web dashboard (port 8080) — auth, breakdown logging, RCA UI
├── llm/          AI backend    (port 8000) — LLM, RAG, domain agents, 5 Whys
└── docker-compose.yml
```

The browser talks directly to **both** services:
- Page navigation → `http://localhost:8080`
- SSE AI streaming → `http://localhost:8000/analyze-integrated-stream`

---

## Quick Start (Docker)

```bash
# 1. Add your API keys to llm/.env (copy from llm/.env.example)
cp llm/.env.example llm/.env
# edit llm/.env — set GEMINI_API_KEY or OPENROUTER_API_KEY

# 2. Start both services
docker-compose up --build

# 3. Open the dashboard
open http://localhost:8080
```

Default login: `admin@plant.com` / `admin123`

---

## Quick Start (Local Dev)

**Terminal 1 — AI Backend:**
```bash
cd llm
pip install -r requirements.txt
# set API key: export GEMINI_API_KEY=...
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — Web Dashboard:**
```bash
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

---

## User Flow

1. **Login** → division-specific or Admin access
2. **Log Issue** → fill in equipment, times, description → auto-calculates downtime + revenue loss
3. **Create RCA** → manual interactive 5 Whys tree
   — or —
   **RCA AI Assist** → AI streams analysis in real time → view domain insights → view root cause + CAPA → save & export

---

## Default Users

| Email | Password | Division |
|-------|----------|----------|
| admin@plant.com | admin123 | Admin (sees all) |
| bnfc@plant.com | pass123 | BNFC |
| pellet1@plant.com | pass123 | Pellet 1 |
| dri1@plant.com | pass123 | DRI 1 |
| ... | pass123 | ... |

---

## Sub-project READMEs

- [app/README.md](app/README.md) — web dashboard details
- [llm/README.md](llm/README.md) — AI backend details
