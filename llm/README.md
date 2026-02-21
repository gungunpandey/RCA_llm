# LLM Backend

FastAPI server powering the RCA (Root Cause Analysis) system. Orchestrates a multi-agent pipeline that combines domain-expert analysis, 5 Whys methodology, and Fishbone (Ishikawa) diagramming — all grounded in OEM manual content via RAG.

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Directory Structure](#directory-structure)
- [API Endpoints](#api-endpoints)
- [Pipeline Architecture](#pipeline-architecture)
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
```

---

## Directory Structure

```
llm/
├── api/
│   └── main.py               # FastAPI app — all endpoints + SSE streaming
├── tools/
│   ├── base_tool.py          # Abstract base for all analysis tools
│   ├── five_whys_tool.py     # 5 Whys RCA methodology
│   ├── fishbone_tool.py      # Ishikawa diagram analysis
│   ├── integrated_rca_tool.py # Full pipeline orchestrator
│   ├── evidence_validator.py # Confidence calibration + evidence validation
│   └── tool_registry.py      # Tool registration and execution
├── domain_agents/
│   ├── base_agent.py         # Shared agent logic (RAG, prompt, parsing)
│   ├── mechanical_agent.py   # Mechanical failure analysis
│   ├── electrical_agent.py   # Electrical/power failure analysis
│   └── process_agent.py      # Process/operational failure analysis
├── models/
│   └── tool_results.py       # Pydantic schemas for all tool outputs
├── model_comparison/
│   └── gemini_adapter.py     # Google Gemini API adapter
├── rag_manager.py            # Weaviate vector search for OEM docs
├── test_fishbone.py          # Standalone fishbone test (direct tool call)
└── test_five_whys.py         # 5 Whys test with scenario JSON files
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
  ├─ 3. 5 Whys → uses domain insights as context (2–5 "why" steps with early stop)
  │
  ├─ 4. Fishbone → categorizes causes into 6 Ishikawa categories
  │
  └─ 5. Return combined result → result SSE event
```

### Causal Sufficiency Stop Rule

The 5 Whys analysis can stop before 5 steps (minimum 2). After each step from Why #2 onward, the system evaluates whether the current cause **fully explains all observed symptoms**. If it does, escalation stops — the root cause is declared at that level.

**Why?** Industrial failures usually terminate at the equipment level. Without this rule the LLM tends to keep escalating into speculative governance/design causes that add no diagnostic value (e.g. "inadequate maintenance policy") even when the equipment-level cause already covers every symptom.

The response includes `stopped_early: true` and a `stop_reason` when this triggers.

**Agent routing** (keyword-based):

| Agent | Triggered by keywords |
|-------|-----------------------|
| `mechanical_agent` | bearing, vibration, shaft, lubrication, gearbox... |
| `electrical_agent` | motor, voltage, current, interlock, relay, trip... |
| `process_agent` | temperature, pressure, flow, combustion, feed... |

---

## RAG Manager

`rag_manager.py` connects to Weaviate and retrieves relevant OEM manual chunks for each query.

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

**Connection:**
```python
rag = RAGManager()
rag.connect()   # Call at startup
rag.disconnect() # Call at shutdown
```

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
