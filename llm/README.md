# LLM Backend

FastAPI server powering the AI RCA pipeline. Orchestrates a multi-agent flow that combines historical incident retrieval (Neo4j), domain-expert agents, a mandatory clarification chatbot, 5 Whys, Fishbone (Ishikawa), and structured CAPA generation — all grounded in OEM manuals via RAG.

> **Integration note:** This backend runs on port **8000**. The web dashboard (`app/`) runs on port **8080**. The browser connects directly to this service for SSE streaming via two endpoints: `/analyze-prepare-stream` (Phase 1) then `/analyze-finalize-stream` (Phase 2). No server-side proxy is involved.

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Directory Structure](#directory-structure)
- [API Endpoints](#api-endpoints)
- [Two-Phase Pipeline (with Chatbot)](#two-phase-pipeline-with-chatbot)
- [5 Whys — Early Stop Logic](#5-whys--early-stop-logic)
- [CAPA Generation](#capa-generation)
- [Evidence Validation System](#evidence-validation-system)
- [RAG Manager](#rag-manager)
- [History Matcher (Neo4j)](#history-matcher-neo4j)
- [Configuration Reference](#configuration-reference)
- [Running Tests](#running-tests)

---

## Quick Start

```bash
cd llm
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Add a `.env` file in the `llm/` directory (see [Configuration Reference](#configuration-reference) below).

---

## LLM Provider Configuration

The backend supports two providers, switched via a single env variable.

### Option A — OpenRouter (GPT-5, default)

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-5
```

Common GPT-5 models on OpenRouter:

| Model ID | Input | Output | Notes |
|----------|-------|--------|-------|
| `openai/gpt-5` | $1.25/M | $10.00/M | Recommended |
| `openai/gpt-5-mini-2025-08-07` | $0.25/M | $2.00/M | Cheapest, good for testing |
| `openai/gpt-5.2` | $1.75/M | $14.00/M | Strongest reasoning |

### Option B — Google Gemini (fallback)

```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-gemini-api-key
```

Active provider is reported on `/health` as `llm_model`.

---

## Directory Structure

```
llm/
├── api/
│   ├── main.py                  # FastAPI app — endpoints + SSE streaming
│   └── session_cache.py         # In-memory SessionCache (15-min TTL) — bridges
│                                #   /analyze-prepare-stream ↔ /analyze-finalize-stream
├── tools/
│   ├── base_tool.py             # Abstract base: timing, ToolResult wrapping
│   ├── tool_registry.py         # Name-based dispatcher
│   ├── five_whys_tool.py        # 5 Whys + causal sufficiency early stop
│   ├── fishbone_tool.py         # Ishikawa diagram (6 categories, JSON mode)
│   ├── capa_tool.py             # Corrective + Preventive Action generator
│   ├── clarification_generator.py # Chatbot question producer (deterministic + LLM ranker)
│   ├── integrated_rca_tool.py   # Two-phase orchestrator (run_prepare + run_finalize)
│   ├── history_matcher.py       # Neo4j incident similarity search
│   ├── image_analysis_tool.py   # Vision-model damage assessment
│   ├── evidence_validator.py    # ConfidenceCalibrator + PlantFailureModeValidator
│   │                            #   + CausalSufficiencyEvaluator
│   └── README.md
├── domain_agents/
│   ├── base_agent.py            # Shared agent logic (RAG, prompt, parsing)
│   ├── mechanical_agent.py
│   ├── electrical_agent.py
│   ├── process_agent.py
│   └── README.md
├── models/
│   └── tool_results.py          # Pydantic schemas (WhyStep, FiveWhysResult,
│                                #   FishboneResult, CAPAAction, CAPAResult,
│                                #   ClarifyingQuestion, ClarificationAnswer, …)
├── model_comparison/
│   ├── openrouter_adapter.py
│   ├── gemini_adapter.py
│   └── test_scenarios.json
├── rag_manager.py               # Weaviate vector search w/ gRPC timeout fix
├── rca_orchestrator.py          # Legacy stub — real orchestration is in IntegratedRCATool
├── chatbot plan.txt             # Design doc (gitignored locally)
├── test_fishbone.py             # Standalone fishbone test
└── test_five_whys.py            # 5 Whys scenario tests
```

---

## API Endpoints

### `POST /analyze-prepare-stream` (Phase 1)

Starts an RCA. Runs history lookup, domain agents, image analysis, and clarification question generation. Caches the intermediate state and emits a `session_id` for the frontend to resume with.

**Request body** (same as `AnalyzeRequest`):
```json
{
  "equipment_name": "Electrostatic Precipitator (ESP)",
  "failure_description": "TR Set 1 tripped on under-voltage...",
  "symptoms": ["TR Set 1 under-voltage trip", "Hopper high level alarm"],
  "occurrence_from": "2026-02-18T08:30:00",
  "department": "Pellet 1",
  "total_downtime": "240 minutes",
  "operator_observations": "Opacity increased on Stack monitor",
  "image_path": "/app/static/uploads/esp_1.jpg",
  "image_desc": "Visible ash deposit on TR set casing"
}
```

**SSE events** (in order):
```
event: status                → {"message": "..."}
event: history_matches       → {"history_matches": [...]}
event: domain_insights       → {"domain_insights": {...}}
event: image_analysis        → {"image_analysis": {...}}     # if applicable
event: clarifying_questions  → {"questions": [...]}          # 3 questions
event: prepare_complete      → {"session_id": "...", "expires_at": ...}
event: error                 → {"detail": "..."}
```

### `POST /analyze-finalize-stream` (Phase 2)

Resumes a prepared session with the user's chatbot answers. Validates that every issued question has an answer (server-side enforcement of the mandatory chatbot), then runs 5 Whys → Fishbone → CAPA.

**Request body**:
```json
{
  "session_id": "9f8d2c1b0a...",
  "clarifications": [
    {"question_id": "q1", "question": "...", "answer": "..."},
    {"question_id": "q2", "question": "...", "answer": "I don't know"},
    {"question_id": "q3", "question": "...", "answer": "12.4"}
  ]
}
```

**Errors**:
- `400` — clarifications missing or incomplete
- `404` — session_id not in cache
- `410` — session expired (>15 min)

**SSE events**:
```
event: status   → {"message": "..."}
event: capa     → {"capa": {...}}     # emitted just before the final 'result'
event: result   → {"status":"success", "result": {...}}
event: error    → {"detail": "..."}
```

### Other endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Server status + active LLM model + registered tools |
| `POST` | `/analyze` | Standalone 5 Whys (no chatbot, JSON response) |
| `POST` | `/analyze-stream` | Standalone 5 Whys SSE (no chatbot) |
| `POST` | `/analyze-domain` | Domain agents only (JSON) |
| `POST` | `/analyze-domain-stream` | Domain agents only (SSE) |
| `POST` | `/analyze-image` | Single image analysis (multipart upload) |

The legacy `POST /analyze-integrated-stream` has been **removed**. Any caller hitting that route now gets a 404; use the two-phase flow.

---

## Two-Phase Pipeline (with Chatbot)

The integrated RCA runs in two phases to support a mandatory user-clarification step:

```
                      Phase 1: /analyze-prepare-stream
                  ┌──────────────────────────────────────┐
                  │ 0. History matcher (Neo4j)           │  → emits history_matches
                  │ 1. Route → which domain agents       │
                  │ 2. Domain agents (parallel) + Image  │  → emits domain_insights
                  │ 3. Aggregate to DomainInsightsSummary│
                  │ 4. ClarificationGenerator            │  → emits clarifying_questions
                  │ 5. SessionCache.create(...)          │  → emits prepare_complete
                  └──────────────────────────────────────┘
                                  ▼
                  [Frontend chatbot modal — MANDATORY]
                  User answers all 3 questions
                                  ▼
                      Phase 2: /analyze-finalize-stream
                  ┌──────────────────────────────────────┐
                  │ Validate clarifications              │
                  │ SessionCache.get(session_id)         │
                  │ Append answers to failure_text       │
                  │ 5 Whys (with early stop)             │
                  │ Fishbone (Ishikawa, JSON mode)       │
                  │ CAPA (corrective + preventive)       │  → emits capa
                  │ Build final result                   │  → emits result
                  │ SessionCache.evict(session_id)       │
                  └──────────────────────────────────────┘
```

**Agent routing** (keyword-based, picks which agents run in parallel):

| Agent | Triggered by keywords |
|-------|-----------------------|
| `mechanical_agent` | bearing, vibration, shaft, lubrication, gearbox, coupling, wear, fatigue, … |
| `electrical_agent` | motor, voltage, current, interlock, relay, trip, VFD, winding, fuse, … |
| `process_agent`    | temperature, pressure, flow, combustion, feed, flame, damper, draft, … |

Multiple agents run if multiple domains match; `mechanical_agent` is the default if none match.

**Clarification generator** (deterministic builders + optional LLM ranker):

| Builder | What it asks |
|---|---|
| `discriminating` | When ≥2 domain agents have hypotheses with confidence ≥0.6, asks the one fact that would decide between them |
| `missing_metric` | When agents reference a sensor class (vibration, current, temp, …) but the failure text has no value for it, asks for the reading + units |
| `historical` | When a Neo4j match has ≥0.80 similarity but a divergent root cause, asks if that historical pattern is present here |
| `domain_check` | Top recommended_check from the highest-confidence agent |

If the deterministic pool is ≤3 candidates, the LLM ranker is **skipped** (saves cost + latency). Otherwise it ranks + rephrases the top 3 in JSON mode.

---

## 5 Whys — Early Stop Logic

The 5 Whys analysis implements a **Causal Sufficiency Stop Rule** to prevent over-escalation into speculative governance / design failures.

### How it works

1. Loop runs up to 5 iterations; minimum 2 are always completed.
2. From Why #2 onward, after each step `CausalSufficiencyEvaluator` calls the LLM with the current cause + observed symptoms:
   > *"Does this cause fully explain ALL the observed symptoms?"*
3. If sufficient → `stopped_early = True`, `stop_reason` recorded, loop breaks.
4. If insufficient → unexplained symptoms logged, next Why generated.

### Why this matters

Without this rule, LLMs over-escalate into vague systemic causes (*"inadequate maintenance policy"*, *"design flaw"*) even when the equipment-level failure already explains every observable symptom.

### Causal Boundary Rule

Every why step is prompted with:
> *"Identify the first equipment whose intended function failed. Do NOT move upstream beyond that unless a measurement or alarm explicitly confirms upstream failure."*

This prevents the analysis bypassing instrument-level failures and jumping to hypothetical upstream process deviations.

### Output fields

```json
{
  "why_steps": [...],
  "root_cause": "...",
  "root_cause_confidence": 0.82,
  "stopped_early": true,
  "stop_reason": "Causal sufficiency achieved at Why #3: ...",
  "next_investigation_paths": [...],
  "risk_assessment": "CRITICAL — Imminent risk of ...",
  "corrective_actions": [...]    // backfilled from CAPATool corrective list
}
```

---

## CAPA Generation

`tools/capa_tool.py` runs **after** 5 Whys + Fishbone. Produces a structured Corrective + Preventive Action plan grounded in:

- Confirmed root cause (from 5 Whys)
- Full 5 Whys chain
- Fishbone contributing causes per category
- Domain expert findings + recommended checks
- OEM documentation (RAG)
- **Past CAPAs from similar incidents** (Neo4j matches) — labelled as "what was actually applied"
- User clarifications from the chatbot

### Output schema

```python
{
  "corrective": [
    {
      "type": "corrective",
      "action": "Replace damaged bearing on Drum 2 and re-balance",
      "rationale": "Direct repair of the failed component...",
      "responsibility": "Mechanical Maintenance",
      "priority": "immediate",            # immediate | short_term | long_term
      "target_date_hint": "Within 24h",
      "related_category": "Machine",      # Fishbone category
      "references": ["Rotary Kiln_Hongda_OEM Manual section 4.2"]
    },
    # ...
  ],
  "preventive": [...],
  "summary": "One-line synthesis of the CAPA strategy",
  "documents_used": [...]
}
```

### Anti-fluff rules in the prompt

- No vague items like *"monitor regularly"*, *"check periodically"*, *"improve maintenance"*
- Every action must connect to either the root cause or a Fishbone category (via `related_category`)
- `responsibility` constrained to 6 values: Mechanical/Electrical Maintenance, Operations, Instrumentation, Process Engineering, Reliability
- `priority` semantically tied to timing: immediate=24h, short_term=1w, long_term=next PM cycle

### Degraded mode

If `root_cause` is missing/empty (5 Whys failed), CAPA returns a single placeholder action ("Investigation incomplete...") so the final result always carries a CAPA field.

---

## Evidence Validation System

`tools/evidence_validator.py` contains three classes keeping the RCA grounded in plant-credible evidence.

### `ConfidenceCalibrator`

Caps LLM confidence based on evidence quality:

| Evidence Type | Max Confidence | Description |
|---|---|---|
| `MEASURED` | 95% | Sensor data, alarm logs, trend data |
| `DOCUMENTED` | 85% | OEM manual explicitly states causality |
| `INFERRED` | 70% | Logical deduction, no direct evidence |
| `NONE` | 50% | Speculative — no supporting evidence |

Evidence type is auto-detected from keyword scanning of the answer text (e.g. "alarm", "sensor", "trend" → `MEASURED`; "likely", "probably" → `INFERRED`).

### `PlantFailureModeValidator`

Detects and sanitizes AI/system errors leaking into plant RCA answers:
- Patterns like `503 UNAVAILABLE`, `404 NOT FOUND`, `CONNECTION TIMEOUT` are flagged as invalid plant failure modes
- Auto-rewrites them to plant-credible signal failures: `Bad Quality`, `Comm Fail`, `Signal Unhealthy`, `Input Forced`, `Loss of Signal`

### `CausalSufficiencyEvaluator`

Drives the 5 Whys early stop logic. On any exception it returns `False` so the pipeline continues rather than block.

---

## RAG Manager

`rag_manager.py` connects to a self-hosted Weaviate instance (e.g. on AWS EC2, REST + gRPC, API-key auth) and retrieves OEM manual chunks for each query. Retrieval is **BM25 keyword search only** — the collection stores no vectors, so no embedding/HuggingFace key is needed for RAG.

**Key method:**
```python
await rag.retrieve_equipment_context(
    equipment_name="ESP",
    failure_symptoms=["under-voltage trip", "high spark rate"],
    top_k=8
)
# Returns: List[Document(content, source, score, metadata)]
```

**Search strategy:** BM25 keyword search against the `Rca` collection. Query is built by combining equipment name + symptoms into a single search string.

### gRPC Timeout Handling

Weaviate queries use gRPC, which can hang up to 60s on a stale connection. The RAG manager has a two-layer defence:

1. **Client-level timeout:** `query=8s` — gRPC raises `DEADLINE_EXCEEDED` quickly
2. **`asyncio.wait_for` guard (10s):** outer safety net
3. **Auto-reconnect on failure:** close client, reconnect, retry once
4. **Graceful degradation:** if retry also fails, returns `[]` — pipeline continues without RAG context

```python
rag = RAGManager()
rag.connect()    # call at startup
rag.disconnect() # call at shutdown
```

---

## History Matcher (Neo4j)

`tools/history_matcher.py` runs at the very start of the integrated pipeline. Queries Neo4j for past incidents whose embedding is semantically similar to the current failure.

```python
matches, prompt_text = await history_matcher.find_and_format(
    equipment_name="ESP",
    problem_description="TR Set 1 tripped on under-voltage..."
)
# Returns:
#   matches      — list of up to top_k (default 3) dicts: equipment, plant, downtime,
#                  problem_statement, root_cause, capa, team_members, similarity_score
#   prompt_text  — pre-formatted "HISTORICAL REFERENCE" block, injected into 5 Whys
```

- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (loaded once on first call, cached in HuggingFace cache volume in Docker)
- Default top_k=3, min similarity=0.65 (cosine)
- **Fully graceful**: if Neo4j is unreachable, returns `([], "")` and the rest of the pipeline runs as if no history existed. RCA never crashes due to history matcher.

The `capa` field on each match is what gets injected into the CAPA generator — past CAPAs that were actually applied to similar failures.

---

## Configuration Reference

| Variable | Purpose | Required |
|---|---|---|
| `LLM_PROVIDER` | `openrouter` (default) or `gemini` | Yes |
| `OPENROUTER_API_KEY` | OpenRouter key | When `LLM_PROVIDER=openrouter` |
| `OPENROUTER_MODEL` | Model id, e.g. `openai/gpt-5` | No (defaults to `openai/gpt-5`) |
| `GOOGLE_API_KEY` | Gemini key | When `LLM_PROVIDER=gemini` |
| `WEAVIATE_URL` | Self-hosted Weaviate REST endpoint, e.g. `http://<ec2-ip>:8080` | Yes |
| `WEAVIATE_API_KEY` | Weaviate API key | Yes |
| `WEAVIATE_GRPC_HOST` | gRPC host (default: same host as `WEAVIATE_URL`) | No |
| `WEAVIATE_GRPC_PORT` | gRPC port (default `50051`) | No |
| `WEAVIATE_GRPC_SECURE` | `true`/`false` (default: matches URL scheme) | No |
| `NEO4J_URI` | Bolt URI (default `bolt://localhost:7687`) | No |
| `NEO4J_USER` | Neo4j user (default `neo4j`) | No |
| `NEO4J_PASSWORD` | Neo4j password (default `rcapassword`) | No |
| `HUGGINGFACE_API_KEY` | Not used by RAG (BM25-only). History matcher loads a public sentence-transformers model with no key. | No |

Weaviate collection / embedding settings live in `data_ingestion/weaviate_config.json`. `.env` values override the JSON config.

**Minimal `.env`:**
```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-5
WEAVIATE_URL=https://your-cluster.weaviate.cloud
WEAVIATE_API_KEY=your-weaviate-key
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=rcapassword
```

---

## Running Tests

### Fishbone tool in isolation (~30s)
```bash
cd llm
python test_fishbone.py
```

### 5 Whys with scenario files (~2 min per scenario)
```bash
python test_five_whys.py
# Results saved to: test_results/five_whys_test_<timestamp>.json
```

### Full integrated pipeline
Start the server, then drive the two-phase flow from the frontend (or curl):
```bash
# Phase 1
curl -N -X POST http://localhost:8000/analyze-prepare-stream \
  -H "Content-Type: application/json" -d @request.json
# Extract session_id from the prepare_complete event, then:
# Phase 2
curl -N -X POST http://localhost:8000/analyze-finalize-stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "clarifications": [...]}'
```
