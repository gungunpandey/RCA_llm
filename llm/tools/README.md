# Tools

RCA analysis tools implementing the core methodologies. Each tool is an async class that accepts a failure description, equipment name, and symptoms, then returns a structured `ToolResult`.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Tool Registry](#tool-registry)
- [BaseTool](#basetool)
- [5 Whys Tool](#5-whys-tool)
- [Fishbone Tool](#fishbone-tool)
- [Integrated RCA Tool](#integrated-rca-tool)
- [Evidence Validator](#evidence-validator)
- [Adding a New Tool](#adding-a-new-tool)

---

## Overview

```
tools/
├── base_tool.py            # Abstract base — timing, error handling, ToolResult wrapping
├── tool_registry.py        # Register and execute tools by name
├── five_whys_tool.py       # 5 Whys progressive root cause drilling
├── fishbone_tool.py        # Ishikawa (fishbone) cause categorisation
├── integrated_rca_tool.py  # Orchestrates: domain agents → 5 Whys → Fishbone
└── evidence_validator.py   # Confidence calibration and evidence gate
```

---

## Tool Registry

`ToolRegistry` is a name-based dispatcher. Tools are registered at startup and executed by name:

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

`execute_tool` passes all keyword arguments to the tool's `analyze()` method.

---

## BaseTool

All tools inherit from `BaseTool` (`base_tool.py`). It provides:

- **`self.llm_adapter`** — LLM interface (call `generate(prompt)` for text generation)
- **`self.rag`** — RAGManager instance (call `retrieve_equipment_context(...)`)
- **`_execute_with_timing(fn)`** — wraps an async function, catches all exceptions, and returns a `ToolResult` with `execution_time_seconds`, `tokens_used`, and `cost_usd` populated automatically

**Pattern every tool follows:**
```python
async def analyze(self, failure_description, equipment_name, symptoms, **kwargs):
    async def _perform_analysis():
        # ... do work, return a dict
        return {"root_cause": "...", "confidence": 0.85}

    return await self._execute_with_timing(_perform_analysis)
```

---

## 5 Whys Tool

**File:** `five_whys_tool.py`

Implements the [5 Whys methodology](https://en.wikipedia.org/wiki/Five_whys): iteratively asks "why?" to drill from symptom to systemic root cause.

### How It Works

1. **RAG retrieval** — fetches relevant OEM manual chunks for the equipment
2. **Domain context injection** — if domain insights are available, injects them into the first step's prompt
3. **5 iterative why steps** — each step uses the previous answer as the next question's context
4. **Final root cause synthesis** — the 5th step explicitly asks for the deepest systemic cause
5. **Corrective actions** — optional final LLM call to generate recommended fixes

### Key Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `failure_description` | str | Initial failure symptom |
| `equipment_name` | str | Used in RAG queries and prompts |
| `symptoms` | List[str] | Additional observed symptoms |
| `domain_insights` | DomainInsightsSummary | Optional — pre-computed domain analysis |

### Output Schema

```python
{
  "why_steps": [
    {
      "step_number": 1,
      "question": "Why did the ESP fail?",
      "answer": "TR Set tripped due to ash accumulation...",
      "supporting_documents": ["ESP_Thermax_OEM Manual"],
      "confidence": 0.95
    },
    # ... steps 2–5
  ],
  "root_cause": "Deficiency in preventive maintenance of hopper heaters...",
  "root_cause_confidence": 0.85,
  "corrective_actions": ["Verify hopper heater operation...", ...],
  "documents_used": ["ESP_Thermax_OEM Manual"]
}
```

---

## Fishbone Tool

**File:** `fishbone_tool.py`

Implements the [Ishikawa (fishbone) diagram](https://en.wikipedia.org/wiki/Ishikawa_diagram). Categorises contributing causes into 6 standard categories.

### Categories

| Category | What it covers |
|----------|---------------|
| **Man** | Human error, procedural non-compliance, training gaps |
| **Machine** | Equipment failures, mechanical problems |
| **Material** | Raw material issues, consumable quality |
| **Method** | Process methods, maintenance procedures |
| **Measurement** | Sensor errors, monitoring gaps |
| **Environment** | Ambient conditions, temperature, humidity |

### How It Works

1. Retrieves equipment context from RAG (8 documents)
2. Formats domain insights and 5 Whys root cause as context
3. Single LLM call with structured JSON output prompt
4. Returns category → causes list with per-cause confidence scores

### Output Schema

```python
{
  "primary_category": "Man",
  "categories": {
    "Man": [
      {
        "cause": "Operational non-compliance with pre-heating protocols",
        "confidence": 0.95,
        "sub_causes": ["Failure to enforce 4-hour pre-heating", ...]
      }
    ],
    "Machine": [...],
    # ...
  },
  "summary": "Primary root cause is human procedural failure..."
}
```

---

## Integrated RCA Tool

**File:** `integrated_rca_tool.py`

Orchestrates the full pipeline as a single tool call.

### Execution Flow

```python
result = await registry.execute_tool(
    name="integrated_rca",
    failure_description="...",
    equipment_name="...",
    symptoms=[...],
    status_callback=my_async_callback,
)
```

**`status_callback`** receives either:
- A `str` — plain status message for the UI spinner
- A `tuple` `("__DOMAIN_INSIGHTS__", dict)` — domain insights ready for progressive rendering

### Output Structure

```python
{
  "domain_insights": { ... },        # From domain agents
  "five_whys_analysis": { ... },     # From 5 Whys tool
  "fishbone_analysis": { ... },      # From Fishbone tool (or null if failed)
  "final_root_cause": "...",
  "final_confidence": 0.85,
  "analysis_method": "domain_enhanced_5_whys_fishbone",
  "agents_used": ["electrical_agent"]
}
```

---

## Evidence Validator

**File:** `evidence_validator.py`

Validates and calibrates confidence scores assigned by the LLM.

| Class | Purpose |
|-------|---------|
| `ConfidenceCalibrator` | Adjusts raw LLM confidence based on evidence quality |
| `PlantFailureModeValidator` | Cross-references findings against known failure modes |
| `EvidenceGate` | Enforces minimum evidence thresholds before accepting a hypothesis |

`EvidenceType` enum values: `RAG_DOCUMENT`, `SYMPTOM_MATCH`, `INTERLOCK_REFERENCE`, `INFERENCE`.

---

## Adding a New Tool

1. Create `tools/my_tool.py` — extend `BaseTool`
2. Implement `async def analyze(...)` using `_execute_with_timing`
3. Register in `api/main.py`:
   ```python
   registry.register_tool("my_tool", MyTool(gemini, rag))
   ```
4. Add an SSE endpoint or trigger from `IntegratedRCATool` as needed
