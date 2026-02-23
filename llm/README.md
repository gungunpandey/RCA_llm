# LLM Backend

FastAPI server powering the RCA (Root Cause Analysis) system. Orchestrates a multi-agent pipeline that combines domain-expert analysis, 5 Whys methodology, and Fishbone (Ishikawa) diagramming — all grounded in OEM manual content via RAG.

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Directory Structure](#directory-structure)
- [API Endpoints](#api-endpoints)
- [Pipeline Architecture](#pipeline-architecture)
- [5 Whys — Early Stop Logic](#5-whys--early-stop-logic)
- [Evidence Validation System](#evidence-validation-system)
- [RAG Manager](#rag-manager)
- [Configuration](#configuration)
- [Running Tests](#running-tests)

---

## Quick Start

```bash
cd llm
pip install fastapi uvicorn python-dotenv google-genai weaviate-client pydantic

# Start the API server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Add a `.env` file in the `llm/` directory:
```
GOOGLE_API_KEY=your-gemini-api-key
WEAVIATE_URL=your-weaviate-cloud-url
WEAVIATE_API_KEY=your-weaviate-api-key
HUGGINGFACE_API_KEY=your-hf-api-key   # optional, for embedding
```

---

## Directory Structure

```
llm/
├── api/
│   └── main.py                  # FastAPI app — all endpoints + SSE streaming
├── tools/
│   ├── base_tool.py             # Abstract base for all analysis tools
│   ├── five_whys_tool.py        # 5 Whys RCA with causal sufficiency early stop
│   ├── fishbone_tool.py         # Ishikawa diagram analysis
│   ├── integrated_rca_tool.py   # Full pipeline orchestrator (domain → whys → fishbone)
│   ├── evidence_validator.py    # Confidence calibration, plant validator, causal evaluator
│   └── tool_registry.py         # Tool registration and execution
├── domain_agents/
│   ├── base_agent.py            # Shared agent logic (RAG, prompt, parsing)
│   ├── mechanical_agent.py      # Mechanical failure analysis
│   ├── electrical_agent.py      # Electrical/power failure analysis
│   └── process_agent.py         # Process/operational failure analysis
├── models/
│   └── tool_results.py          # Pydantic schemas for all tool outputs
├── model_comparison/
│   ├── run_comparison.py        # Multi-model comparison script
│   ├── gemini_adapter.py        # Google Gemini API adapter
│   └── test_scenarios_extended.json  # Test scenarios for model comparison
├── rag_manager.py               # Weaviate vector search for OEM docs (with gRPC timeout fix)
├── rca_orchestrator.py          # Legacy orchestrator (pre-integrated pipeline)
├── test_fishbone.py             # Standalone fishbone test (direct tool call)
└── test_five_whys.py            # 5 Whys test with scenario JSON files
```

---

## API Endpoints

### `POST /analyze-integrated-stream`

Main endpoint. Runs the full integrated pipeline and streams real-time progress via SSE.

**Request:**
```json
{
  "equipment_name": "Electrostatic Precipitator (ESP)",
  "failure_description": "TR Set 1 tripped on under-voltage. Hopper High Level Alarm active.",
  "symptoms": ["TR Set 1 under-voltage trip", "High spark rate", "Hopper high level alarm"],
  "failure_timestamp": "2026-02-18T08:30:00Z",
  "operator_observations": "Opacity increased on Stack monitor"
}
```

**SSE Event Stream:**
```
event: status
data: {"message": "🔬 Domain experts analyzing failure..."}

event: domain_insights
data: {"domain_insights": { "key_findings": [...], "overall_confidence": 0.7 }}

event: result
data: {"status": "success", "result": { "five_whys_analysis": {...}, "fishbone_analysis": {...} }}
```

### `POST /analyze-stream`

Lighter endpoint — runs standalone 5 Whys (no domain agents or fishbone).

### `GET /health`

Returns `{"status": "ok"}` — used for readiness checks.

---

## Pipeline Architecture

The integrated pipeline runs in **5 sequential stages:**

```
Request
  │
  ├─ 1. Route → select domain agents based on keywords
  │
  ├─ 2. Domain Agents (parallel) → Mechanical + Electrical + Process
  │        ↓ emits: domain_insights SSE event immediately
  │
  ├─ 3. 5 Whys → uses domain insights as context (2–5 why steps, with early stop)
  │
  ├─ 4. Fishbone → categorizes causes into 6 Ishikawa categories
  │
  └─ 5. Return combined result → result SSE event
```

**Agent routing** (keyword-based):

| Agent | Triggered by keywords |
|-------|-----------------------|
| `mechanical_agent` | bearing, vibration, shaft, lubrication, gearbox... |
| `electrical_agent` | motor, voltage, current, interlock, relay, trip... |
| `process_agent` | temperature, pressure, flow, combustion, feed... |

---

## 5 Whys — Early Stop Logic

The 5 Whys analysis implements a **Causal Sufficiency Stop Rule** to prevent over-escalation into speculative governance or design failures.

### How it works

1. The loop runs up to 5 iterations (minimum 2 whys are always completed).
2. **From Why #2 onward**, after each step, the system calls `CausalSufficiencyEvaluator` with the current candidate cause and the full list of observed symptoms.
3. The evaluator sends a dedicated prompt to the LLM asking:

   > *"Does this cause fully explain ALL of the observed symptoms? If yes for all → cause is SUFFICIENT. If any symptom is unexplained → INSUFFICIENT, continue digging."*

4. If the cause is **sufficient** → the loop breaks, `stopped_early = True` is recorded, and a `stop_reason` string is attached to the result.
5. If the cause is **insufficient** → the unexplained symptoms are logged and the next Why is generated.

### Why this matters

Without this rule, LLMs tend to over-escalate into vague systemic causes (e.g. *"inadequate maintenance policy"*, *"design flaw"*) even when the equipment-level failure already explains every observable symptom. This adds no diagnostic value and can mislead operators.

The rule anchors the analysis at the **lowest sufficient explanation** — i.e., the first equipment or component failure that fully accounts for all alarms and observations.

### Output fields

```json
{
  "why_steps": [...],
  "root_cause": "...",
  "root_cause_confidence": 0.82,
  "stopped_early": true,
  "stop_reason": "Causal sufficiency achieved at Why #3: cause explains all observed symptoms. ..."
}
```

### Causal Boundary Rule

Each why step is also prompted with an explicit **causal boundary constraint**:

> *"Identify the first equipment whose intended function failed. Do NOT move upstream beyond that unless a measurement or alarm explicitly confirms upstream failure."*

This prevents the analysis from bypassing instrument-level failures (signal quality, transmitter failure) and jumping straight to hypothetical upstream process deviations.

---

## Evidence Validation System

`tools/evidence_validator.py` contains three classes that keep the RCA grounded in plant-credible evidence.

### `ConfidenceCalibrator`

Caps LLM-generated confidence scores based on the quality of evidence:

| Evidence Type | Max Confidence | Description |
|---------------|----------------|-------------|
| `MEASURED` | 95% | Sensor data, alarm logs, trend data |
| `DOCUMENTED` | 85% | OEM manual explicitly states causality |
| `INFERRED` | 70% | Logical deduction, no direct evidence |
| `NONE` | 50% | Speculative — no supporting evidence |

Evidence type is auto-detected from keyword scanning of the answer text (e.g. presence of "alarm", "sensor", "trend" → `MEASURED`; "likely", "probably" → `INFERRED`).

### `PlantFailureModeValidator`

Detects and sanitizes AI/system errors that may leak into plant RCA answers:

- Patterns like `503 UNAVAILABLE`, `404 NOT FOUND`, `CONNECTION TIMEOUT` are flagged as invalid plant failure modes.
- Invalid answers are sanitized — e.g. `503 UNAVAILABLE` → `Loss of Signal (LOS)`.
- Plant-credible signal failures: `Bad Quality`, `Comm Fail`, `Signal Unhealthy`, `Input Forced`, `Loss of Signal`.

### `CausalSufficiencyEvaluator`

Drives the early stop logic (see [5 Whys — Early Stop Logic](#5-whys--early-stop-logic)). On any exception it fails safely — returning `False` to allow analysis to continue rather than block the pipeline.

---

## RAG Manager

`rag_manager.py` connects to Weaviate Cloud and retrieves relevant OEM manual chunks for each query.

**Key method:**
```python
await rag.retrieve_equipment_context(
    equipment_name="ESP",
    failure_symptoms=["under-voltage trip", "high spark rate"],
    top_k=8
)
# Returns: List[Document(content, source, score, metadata)]
```

**Search strategy:** BM25 keyword search against the `Rca` collection in Weaviate. Query is built by combining equipment name + symptoms into a single search string.

### gRPC Timeout Handling

Weaviate queries use gRPC, which can hang for up to 60 seconds when the connection is stale. The RAG manager implements a two-layer defence:

1. **Client-level timeout:** The Weaviate client is configured with `query=8s` — so the gRPC layer itself raises `DEADLINE_EXCEEDED` quickly rather than hanging.
2. **`asyncio.wait_for` guard (10s):** The BM25 call runs in a thread executor wrapped by `asyncio.wait_for` as an outer safety net in case the gRPC timeout doesn't fire.
3. **Auto-reconnect on failure:** If either timeout fires on the first attempt, the client is closed, a fresh connection is established, and the query is retried once.
4. **Graceful degradation:** If the retry also fails, `retrieve_equipment_context` returns `[]` and the pipeline continues without RAG context — analysis is not blocked.

```python
rag = RAGManager()
rag.connect()    # Call at startup
rag.disconnect() # Call at shutdown
```

**Connection timeout config:**
```python
Timeout(init=10, query=8, insert=120)
```

---

## Configuration

| Variable | Location | Purpose |
|----------|----------|---------|
| `GOOGLE_API_KEY` | `llm/.env` | Gemini API key for LLM calls |
| `WEAVIATE_URL` | `llm/.env` | Weaviate Cloud cluster URL |
| `WEAVIATE_API_KEY` | `llm/.env` | Weaviate API key |
| `HUGGINGFACE_API_KEY` | `llm/.env` | HuggingFace key for embeddings (optional) |

Weaviate collection and embedding settings are in `data_ingestion/weaviate_config.json`. `.env` values override the JSON config.

---

## Running Tests

### Fishbone tool in isolation (fast, ~30s)
```bash
cd llm
python test_fishbone.py
```
Uses hardcoded inputs — no domain agents needed. Prints full Ishikawa breakdown.

### 5 Whys with scenario files (~2 min per scenario)
```bash
python test_five_whys.py
# Results saved to: test_results/five_whys_test_<timestamp>.json
```

### Full integrated pipeline via API
Start the server, then submit a request to `/analyze-integrated-stream` (use the frontend or curl).

### Model comparison
```bash
python model_comparison/run_comparison.py
```
Runs multiple Gemini models against the scenarios defined in `model_comparison/test_scenarios_extended.json` and produces a side-by-side comparison of outputs.
