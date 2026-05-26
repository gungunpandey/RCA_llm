# Tools

RCA analysis tools implementing the core methodologies + supporting modules. Each tool is an async class that accepts a failure description, equipment name, and symptoms (plus tool-specific kwargs), then returns a structured `ToolResult`.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Tool Registry](#tool-registry)
- [BaseTool](#basetool)
- [5 Whys Tool](#5-whys-tool)
- [Fishbone Tool](#fishbone-tool)
- [CAPA Tool](#capa-tool)
- [Clarification Generator](#clarification-generator)
- [History Matcher](#history-matcher)
- [Image Analysis Tool](#image-analysis-tool)
- [Integrated RCA Tool (two-phase)](#integrated-rca-tool-two-phase)
- [Evidence Validator](#evidence-validator)
- [Adding a New Tool](#adding-a-new-tool)

---

## Overview

```
tools/
├── base_tool.py                  # Abstract base — timing, ToolResult wrapping
├── tool_registry.py              # Register and execute tools by name
├── five_whys_tool.py             # Progressive root cause drilling (up to 5 whys + early stop)
├── fishbone_tool.py              # Ishikawa diagram across 6 categories (JSON mode)
├── capa_tool.py                  # Corrective + Preventive Action generator (NEW)
├── clarification_generator.py    # Chatbot question producer (NEW)
├── history_matcher.py            # Neo4j semantic search for similar past incidents
├── image_analysis_tool.py        # Vision-model damage assessment
├── integrated_rca_tool.py        # Two-phase orchestrator (run_prepare + run_finalize)
├── evidence_validator.py         # Confidence calibration + plant failure-mode validator +
│                                 #   causal sufficiency evaluator
└── README.md
```

---

## Tool Registry

Name-based dispatcher. Tools are registered at startup (`api/main.py` `lifespan`) and executed by name:

```python
registry = ToolRegistry()
registry.register_tool("5_whys", FiveWhysTool(llm, rag))
registry.register_tool("fishbone", FishboneTool(llm, rag))

result = await registry.execute_tool(
    name="5_whys",
    failure_description="...",
    equipment_name="...",
    symptoms=[...],
)
```

`execute_tool` forwards all keyword arguments to the tool's `analyze()` method.

**Note:** The HTTP endpoints `/analyze-prepare-stream` and `/analyze-finalize-stream` bypass the registry and call `IntegratedRCATool.run_prepare()` / `run_finalize()` directly (the registry's single-call shape doesn't fit a two-phase flow). The registry is still used for the standalone `/analyze`, `/analyze-stream`, `/analyze-domain[-stream]` endpoints.

---

## BaseTool

All tools inherit from `BaseTool` (`base_tool.py`). It provides:

- **`self.llm_adapter`** — LLM interface (`generate(prompt, …)` for text, `generate_sync(prompt)` for blocking calls)
- **`self.rag`** — `RAGManager` instance (`retrieve_equipment_context(...)`)
- **`_execute_with_timing(fn)`** — wraps an async function, catches exceptions, returns a `ToolResult` with `execution_time_seconds`, `tokens_used`, `cost_usd` populated

**Pattern every tool follows:**
```python
async def analyze(self, failure_description, equipment_name, symptoms, **kwargs):
    async def _perform_analysis():
        # ... do work, return a dict
        return {"root_cause": "...", "confidence": 0.85}

    return await self._execute_with_timing(_perform_analysis)
```

`FishboneTool`, `CAPATool`, and `IntegratedRCATool` build the `ToolResult` manually instead of via `_execute_with_timing` because they need finer success/failure semantics, but the contract is the same.

---

## 5 Whys Tool

**File:** `five_whys_tool.py`

Implements the [5 Whys methodology](https://en.wikipedia.org/wiki/Five_whys) — iteratively asks "why?" to drill from symptom to systemic root cause. Augmented with a **causal sufficiency early-stop rule** (see [llm/README.md](../README.md) for details).

### How it works

1. **RAG retrieval** — top-5 OEM manual chunks for the equipment
2. **Domain + historical + image context injection** — if available, all three are spliced into the Step-1 prompt
3. **Iterative why steps** (up to 5) — each step uses the previous answer as context
4. **Causal sufficiency check** after step ≥2 — early-exits when the cause explains every symptom
5. **Root cause synthesis** — separate LLM call that turns the chain into ONE crisp statement (favours system/process gap framing over single-component blame)
6. **Per-step summary** — each `WhyStep` also gets a concise `answer_summary` (≤20 words) for the formal report table

### Key Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `failure_description` | str | Initial failure symptom (with appended clarifications block) |
| `equipment_name` | str | Used in RAG queries + prompts |
| `symptoms` | List[str] | Additional observed symptoms |
| `domain_insights` | DomainInsightsSummary | Optional — pre-computed domain analysis |
| `image_analysis` | dict | Optional — vision output (injected on Step 1 only) |
| `historical_context` | str | Optional — preformatted HISTORICAL REFERENCE block |
| `status_callback` | async fn | Optional — receives status messages |

### Output Schema (`FiveWhysResult.model_dump()`)

```python
{
  "why_steps": [
    {
      "step_number": 1,
      "question": "Why did the ESP fail?",
      "answer": "TR Set tripped due to ash accumulation...",
      "answer_summary": "Ash hopper level breach triggered TR Set protection trip.",
      "supporting_documents": ["ESP_Thermax_OEM Manual"],
      "confidence": 0.95
    },
    # ...
  ],
  "root_cause": "Absence of vibration trending and oil analysis programme to detect ...",
  "root_cause_confidence": 0.82,
  "stopped_early": true,
  "stop_reason": "Causal sufficiency achieved at Why #3: ...",
  "next_investigation_paths": ["Verify Level Switch High-High signal", ...],
  "risk_assessment": "CRITICAL — Imminent risk of...",
  "corrective_actions": [...],          # backfilled from CAPATool corrective list
  "documents_used": ["ESP_Thermax_OEM Manual"]
}
```

---

## Fishbone Tool

**File:** `fishbone_tool.py`

Implements the [Ishikawa diagram](https://en.wikipedia.org/wiki/Ishikawa_diagram) — categorises contributing causes into 6 standard categories. Runs **after** 5 Whys, using the confirmed root cause as anchor.

### Categories

| Category | Focus |
|---|---|
| **Man** | Operator actions, training gaps, procedural non-compliance |
| **Machine** | Equipment wear, mechanical failure, design flaws, maintenance state |
| **Material** | Raw material quality, feed properties, contamination |
| **Method** | SOP deviations, process parameter settings, control strategy |
| **Measurement** | Sensor drift, calibration errors, signal quality issues |
| **Environment** | Ambient temperature, dust, humidity, vibration from adjacent equipment |

### How it works

1. Retrieves equipment context from RAG (8 documents)
2. Formats domain insights + 5 Whys root cause as context
3. **Single LLM call with `json_mode=True`** (when supported by the adapter) and `max_tokens=16384`
4. Returns category → causes with per-cause confidence + severity + evidence level

### Key prompt rules

- Map **only the conditions that enabled the confirmed root cause** — exclude downstream effects (alarms triggered by the failure, electrical trips, etc.)
- Causes must be short phrases (5–10 words), sub-causes shorter still
- Each cause gets `evidence_level`: `CONFIRMED` (observed/logged) / `SUPPORTED` (physics requires) / `POSSIBLE` (plausible)
- Each cause gets `severity`: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`
- Machine and Method causes are forced to go beyond the symptom to the **design or maintenance gap** (e.g., "No locking mechanism on mounting bolts" instead of "Mounting joint prone to loosening")
- Environment category must always have ≥1 cause (industrial settings always have ambient factors)

### Output Schema

```python
{
  "primary_category": "Machine",
  "categories": {
    "Man": [...],
    "Machine": [
      {
        "category": "Machine",
        "cause": "Bearing housing without vibration sensor",
        "sub_causes": ["No predictive monitoring installed"],
        "confidence": 0.85,
        "evidence_level": "SUPPORTED",
        "evidence": "Failure occurred without prior warning",
        "severity": "HIGH"
      }
    ],
    # ...
  },
  "category_confidence": {"Machine": 0.90, "Material": 0.85, ...},
  "root_cause_confirmed": "...",
  "documents_used": [...]
}
```

---

## CAPA Tool

**File:** `capa_tool.py`

Generates a structured **Corrective + Preventive Action plan** from a confirmed root cause. Runs **after** Fishbone in the integrated pipeline.

### Inputs

| Input | Source |
|---|---|
| `root_cause` | 5 Whys `root_cause` |
| `why_steps` | full 5 Whys chain |
| `fishbone_result` | Fishbone categories — for breadth via `related_category` |
| `domain_insights` | domain expert findings + recommended_checks |
| `historical_capas` | top-3 Neo4j history matches — past CAPAs that were actually applied |
| `user_clarifications` | answers from the chatbot |
| RAG (own retrieval) | top-6 OEM docs for procedure wording / thresholds |

### Prompt design

Single LLM call with `json_mode=True` and `max_tokens=6000`. Demands 2–3 corrective + 2–3 preventive actions, each with:

- `action` — specific + verifiable phrasing (numeric threshold, component name, document reference)
- `rationale` — 1–2 sentence justification tying back to the root cause
- `responsibility` — constrained to **6 values**: `Mechanical Maintenance` / `Electrical Maintenance` / `Operations` / `Instrumentation` / `Process Engineering` / `Reliability`
- `priority` — `immediate` (24h) / `short_term` (1 week) / `long_term` (next PM cycle)
- `target_date_hint` — human-readable string consistent with priority
- `related_category` — Fishbone category this action addresses
- `references` — OEM manual sections + cited past CAPAs

### Anti-fluff guardrails in the prompt

- Generic phrases banned by name: *"monitor regularly"*, *"check periodically"*, *"improve maintenance"*
- Every action must connect to the root cause OR a Fishbone category
- Markdown bold/italic forbidden in any field
- Historical CAPAs are referenced ("what was applied"), not blindly copied

### Output Schema (`CAPAResult.model_dump()`)

```python
{
  "corrective": [
    {
      "type": "corrective",
      "action": "Replace damaged bearing on Drum 2 and re-balance the rotor assembly",
      "rationale": "Direct repair of the failed component identified in the chain",
      "responsibility": "Mechanical Maintenance",
      "priority": "immediate",
      "target_date_hint": "Within 24h",
      "related_category": "Machine",
      "references": ["Rotary Kiln_Hongda_OEM Manual section 4.2"]
    },
    # ...
  ],
  "preventive": [...],
  "summary": "Replace the failed bearing and institute vibration trending to detect future degradation early.",
  "documents_used": [...]
}
```

### Degraded mode

If `root_cause` is empty/missing, CAPA returns a single placeholder corrective action (*"Investigation incomplete — gather more failure data before implementing corrective actions"*). The pipeline never crashes; downstream code always has a `capa_actions` field to render.

### Backfill into FiveWhysResult

After CAPA succeeds, `IntegratedRCATool.run_finalize` writes the top corrective action strings into `five_whys_analysis.corrective_actions` so legacy readers (tests, manual UI that reads that field) still find a list.

---

## Clarification Generator

**File:** `clarification_generator.py`

Produces the 3 chatbot questions emitted in Phase 1 (`/analyze-prepare-stream`). Runs **after** the domain agents aggregate and **before** the session is cached.

### Architecture: deterministic + optional LLM ranker

```
Build candidate pool from 4 deterministic builders
       │
       ├─ If pool ≤ 3 → return as-is (no LLM call, saves cost + latency)
       └─ If pool > 3 → single LLM call (json_mode) to RANK + REPHRASE the top 3
```

### The 4 builders

| Builder | Source | Trigger |
|---|---|---|
| `discriminating` | DomainInsightsSummary.suspected_root_causes | ≥2 domain agents with hypotheses, both confidence ≥0.6, different domains |
| `missing_metric` | DomainAnalysisResult.findings + recommended_checks | Sensor keyword (vibration / current / temperature / pressure / …) appears in agent text but no numeric value in failure_text |
| `historical` | history_matches[0] | Top match has similarity ≥0.80 AND word-overlap with current hypotheses ≤50% (i.e., divergent) |
| `domain_check` | DomainAnalysisResult.recommended_checks | Top check from highest-confidence agent (fallback) |

### Sensor detection table

```
vibration → mm/s     current → A     voltage → V     temperature → °C
pressure → bar       flow → m³/h     speed → rpm     power → kW
torque → Nm          oil temperature → °C
```

Each entry has a regex for "value already present in failure_text" — if the user already gave a number, the corresponding question is suppressed.

### Output Schema (`List[ClarifyingQuestion]`)

```python
[
  {
    "id": "q1",
    "question": "What was the latest vibration reading before or at the time of failure? (in mm/s if available)",
    "rationale": "Vibration data validates the current hypothesis",
    "source": "missing_metric",
    "expected_format": "number",       # number | yes_no | free_text
    "units": "mm/s",
    "related_hypothesis": "Bearing wear...",
    "related_domain": "mechanical"
  },
  # 2 more...
]
```

The LLM ranker prompt enforces priority order (`discriminating > missing_metric > historical > domain_check`) and renumbers IDs as `q1/q2/q3`.

---

## History Matcher

**File:** `history_matcher.py`

Neo4j semantic search over past RCA incidents. Runs at the very start of Phase 1.

```python
matches, prompt_text = await history_matcher.find_and_format(
    equipment_name="ESP",
    problem_description="TR Set 1 tripped on under-voltage..."
)
```

Returns:
- `matches` — up to top_k (default 3) dicts: `equipment`, `plant`, `department`, `occurrence_from`, `downtime_minutes`, `problem_statement`, `root_cause`, `capa` (list), `team_members`, `similarity_score`
- `prompt_text` — pre-formatted `HISTORICAL REFERENCE` block, injected into the 5 Whys Step-1 prompt

### How it works

1. Embeds the query `"Equipment: X. Problem: Y"` with `sentence-transformers/all-MiniLM-L6-v2` (singleton — loaded once on first call)
2. Pulls every `:Incident` node from Neo4j with its embedding + linked `:HAS_CAPA` / `:INVESTIGATED_BY` data
3. Computes cosine similarity (vectors are pre-normalised → dot product)
4. Returns top-k above `min_similarity` (default 0.65)

### Failure mode

If Neo4j is unreachable or any error occurs, returns `([], "")` and the pipeline continues. **RCA never crashes due to history matcher.**

---

## Image Analysis Tool

**File:** `image_analysis_tool.py`

Vision-model damage assessment. Triggered when an `image_path` is included in the request. Runs in parallel with the domain agents during Phase 1.

```python
result = await asyncio.to_thread(analyze_image, image_path, user_description)
# Returns: {
#   "component": "Bearing housing",
#   "damage_type": "Spalling",
#   "severity": "Severe",
#   "visual_symptoms": ["scoring", "discoloration"],
#   "possible_causes": ["misalignment", "lubrication starvation"],
#   "ai_description": "...",
#   "combined_observation": "...",
#   "image_filename": "..."
# }
```

Uses a vision-capable LLM (Qwen via OpenRouter by default). Supported extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.

Injected on **Step 1 only** of 5 Whys and folded into the final result as `image_analysis`.

---

## Integrated RCA Tool (two-phase)

**File:** `integrated_rca_tool.py`

Orchestrates the full pipeline. **Refactored into two phases** to support the mandatory chatbot step.

### `run_prepare(failure_description, equipment_name, symptoms, **kwargs)`

Phase 1 — runs everything that can happen *before* user input:

```
0. history_matcher.find_and_format()        → emits __HISTORY_MATCHES__
1. _route_agents()                          → keyword pick of domain agents
2. asyncio.gather(domain agents, image)     → parallel
3. _aggregate_domain_insights()             → DomainInsightsSummary
                                              → emits __DOMAIN_INSIGHTS__
                                              → emits __IMAGE_ANALYSIS__ if applicable
4. ClarificationGenerator.generate()        → emits __CLARIFYING_QUESTIONS__
5. Return all state needed to resume        (failure_text, equipment_name, symptoms,
                                              domain_insights, history_context,
                                              history_matches, image_analysis,
                                              selected_agents, questions)
```

### `run_finalize(equipment_name, failure_text, symptoms, domain_insights, history_context, image_analysis, selected_agents, clarifications, history_matches, **kwargs)`

Phase 2 — runs after user submits chatbot answers:

```
1. _append_clarifications(failure_text, …)  → user Q&A injected as structured block
2. self.five_whys.analyze(...)              → 5 Whys
3. self.fishbone.analyze(...)               → Fishbone (with confirmed root_cause)
4. self.capa.analyze(...)                   → CAPA (with historical CAPAs + clarifications)
                                              → emits __CAPA__
5. Backfill five_whys_analysis.corrective_actions from CAPA corrective list
6. Build final result dict (same shape as legacy analyze())
```

### Final result shape

```python
{
  "domain_insights": {...},
  "five_whys_analysis": {...},      # corrective_actions backfilled from CAPA
  "fishbone_analysis": {...},       # or null if Fishbone failed
  "capa_actions": {                 # NEW — full structured CAPA
    "corrective": [...],
    "preventive": [...],
    "summary": "...",
    "documents_used": [...]
  },
  "user_clarifications": [          # NEW — chatbot Q&A for the report
    {"question_id": "q1", "question": "...", "answer": "..."},
    ...
  ],
  "final_root_cause": "...",
  "final_confidence": 0.82,
  "analysis_method": "domain_enhanced_5_whys_fishbone_capa_with_clarifications",
  "agents_used": ["electrical_agent", "mechanical_agent"],
  "image_analysis": {...}           # if applicable
}
```

### `analyze(...)` — legacy convenience wrapper

Kept for tests and any programmatic caller that doesn't need the chatbot. Just calls `run_prepare` → `run_finalize` back-to-back with empty clarifications. Not used by any HTTP endpoint.

### SSE callback tuples

Both phases use the `status_callback` for both plain string messages and special event tuples:

| Tuple key | Endpoint emits |
|---|---|
| `("__HISTORY_MATCHES__", [...])` | `event: history_matches` |
| `("__DOMAIN_INSIGHTS__", {...})` | `event: domain_insights` |
| `("__IMAGE_ANALYSIS__", {...})`  | `event: image_analysis` |
| `("__CLARIFYING_QUESTIONS__", [...])` | `event: clarifying_questions` |
| `("__CAPA__", {...})` | `event: capa` |
| plain `str` | `event: status` |

---

## Evidence Validator

**File:** `evidence_validator.py`

Three classes that keep RCA grounded in plant-credible evidence.

| Class | Purpose |
|---|---|
| `ConfidenceCalibrator` | Caps LLM confidence by evidence quality (MEASURED 95% / DOCUMENTED 85% / INFERRED 70% / NONE 50%) |
| `PlantFailureModeValidator` | Detects + sanitizes AI-error patterns (`503 UNAVAILABLE`, `404 NOT FOUND`, …) that leak into plant RCA answers; rewrites them to plant-credible signal failures (`Bad Quality`, `Comm Fail`, `Loss of Signal`, …) |
| `CausalSufficiencyEvaluator` | Drives the 5 Whys early stop logic; on any exception returns `False` so the pipeline continues |

`EvidenceType` enum values: `MEASURED`, `DOCUMENTED`, `INFERRED`, `NONE`.

---

## Adding a New Tool

1. Create `tools/my_tool.py` extending `BaseTool`
2. Implement `async def analyze(...)` — return via `_execute_with_timing` or build the `ToolResult` manually
3. Register in `api/main.py` `lifespan`:
   ```python
   registry.register_tool("my_tool", MyTool(llm_adapter=gemini, rag_manager=rag))
   ```
4. If the tool should run inside the integrated pipeline, add a call site in `IntegratedRCATool.run_finalize` (or `run_prepare` for pre-chatbot steps) and emit a `__MY_TOOL__` status_callback tuple
5. If the SSE stream should carry its output, add an `event: my_tool` branch to the relevant endpoint's `_event_generator` in `api/main.py`
