# Domain Agents

Specialised AI agents that analyse equipment failures from a domain-specific perspective — Mechanical, Electrical, or Process. Each agent queries relevant OEM documentation via RAG, builds a structured prompt, and returns findings with severity ratings and confidence-calibrated hypotheses.

---

## 📋 Table of Contents

- [Overview](#overview)
- [How Agents Are Selected](#how-agents-are-selected)
- [BaseAgent](#baseagent)
- [Mechanical Agent](#mechanical-agent)
- [Electrical Agent](#electrical-agent)
- [Process Agent](#process-agent)
- [Output Schema](#output-schema)
- [Adding a New Agent](#adding-a-new-agent)

---

## Overview

```
domain_agents/
├── __init__.py          # Exports: MechanicalAgent, ElectricalAgent, ProcessAgent
├── base_agent.py        # All shared logic: RAG, prompt building, response parsing
├── mechanical_agent.py  # Checklist for mechanical failures
├── electrical_agent.py  # Checklist for electrical/power failures
└── process_agent.py     # Checklist for process/operational failures
```

Domain agents run **in parallel** during the integrated RCA pipeline, then their findings are aggregated into a `DomainInsightsSummary` before being passed to the 5 Whys tool.

---

## How Agents Are Selected

The `IntegratedRCATool` routes to relevant agents based on keyword matching against `failure_description + symptoms`:

| Agent | Trigger keywords |
|-------|-----------------|
| `MechanicalAgent` | bearing, vibration, shaft, coupling, lubrication, gearbox, impeller, wear, fatigue... |
| `ElectricalAgent` | motor, voltage, current, interlock, relay, trip, VFD, winding, fuse, circuit... |
| `ProcessAgent` | temperature, pressure, flow, combustion, emission, feed, flame, damper, draft... |

Multiple agents can run simultaneously if the failure description spans domains. If no keywords match, `MechanicalAgent` is the default.

---

## BaseAgent

**File:** `base_agent.py`

Contains all the shared logic. Subclasses only need to define 3 properties:

```python
class MyNewAgent(BaseAgent):
    @property
    def domain(self) -> str:
        return "my_domain"

    @property
    def domain_keywords(self) -> List[str]:
        return ["keyword1", "keyword2"]   # Used to enrich RAG queries

    @property
    def checklist_areas(self) -> List[dict]:
        return [
            {"area": "Power Supply", "focus": "Check for voltage drops, fuse conditions"},
            {"area": "Controls", "focus": "Inspect PLC I/O, interlock status"},
        ]
```

### Analysis Flow (`analyze` method)

```
1. Build RAG query (equipment name + symptoms + domain keywords)
       ↓
2. Retrieve top-5 OEM manual chunks from Weaviate
       ↓
3. Build domain-specific prompt (checklist areas + RAG context)
       ↓
4. Call LLM → parse structured response
       ↓
5. Return DomainAnalysisResult (findings, hypothesis, confidence, checks)
```

### Prompt Format

The LLM is instructed to respond in this exact structure:

```
FINDINGS:
[AREA] Protection Systems | [SEVERITY] critical | observation text | evidence text
[AREA] Power Supply | [SEVERITY] warning | observation text | evidence text

HYPOTHESIS: The root cause is...

RECOMMENDED_CHECKS:
- Check RAV motor for thermal overload trip
- Verify Level Switch High-High signal

CONFIDENCE: 70
```

### Response Parsing

`_parse_domain_response` extracts:
- **Findings** — each line parsed into `DomainFinding(area, severity, observation, evidence)`
- **Hypothesis** — free-text root cause hypothesis for this domain
- **Confidence** — integer 0–100, converted to float 0.0–1.0
- **Recommended checks** — bullet-point list of physical checks

---

## Mechanical Agent

**File:** `mechanical_agent.py`

**Domain:** `"mechanical"`

**Checklist areas:**
| Area | Focus |
|------|-------|
| Bearings & Lubrication | Bearing temp, vibration, oil levels, bearing failures |
| Rotating Equipment | Shaft alignment, coupling condition, balance |
| Mechanical Seals | Seal condition, leakage, wear patterns |
| Drive Systems | Belt tension, gear mesh, coupling torque |
| Structural Integrity | Frame cracks, bolt loosening, foundation |

**RAG keywords:** `"bearing failure vibration mechanical wear shaft"`

---

## Electrical Agent

**File:** `electrical_agent.py`

**Domain:** `"electrical"`

**Checklist areas:**
| Area | Focus |
|------|-------|
| Protection Systems | Relay trips, interlock status, protection coordination |
| Power Supply Quality | Voltage levels, harmonics, power factor |
| Motor Conditions | Winding resistance, insulation IR values, thermal status |
| Control Circuits | PLC I/O, control logic faults, signal integrity |
| Earthing & Grounding | Earth faults, equipotential bonding |

**RAG keywords:** `"electrical motor failure voltage current interlock trip"`

---

## Process Agent

**File:** `process_agent.py`

**Domain:** `"process"`

**Checklist areas:**
| Area | Focus |
|------|-------|
| Process Parameters | Temperature, pressure, flow rate deviations |
| Feed Quality | Raw material composition, moisture, particle size |
| Combustion Systems | Flame stability, air-fuel ratio, draft pressure |
| Control Systems | Setpoint deviations, PID tuning, control loops |
| Environmental Conditions | Ambient temperature, humidity, dust levels |

**RAG keywords:** `"process failure temperature pressure flow combustion"`

---

## Output Schema

Each agent returns a `DomainAnalysisResult`:

```python
{
  "domain": "electrical",
  "findings": [
    {
      "area": "Protection Systems",
      "observation": "TR Set executed mandatory under-voltage trip per interlock SL NO 6",
      "severity": "critical",
      "evidence": "Evidence: TR Set 1 under-voltage trip symptom + OEM Manual SL NO 6"
    }
  ],
  "root_cause_hypothesis": "Ash evacuation system failure allowed hopper to fill...",
  "confidence": 0.70,
  "recommended_checks": [
    "Check RAV motor for thermal overload (Interlock 7i/7j)",
    "Verify Level Switch High-High signal in Field 1 hopper"
  ],
  "documents_used": ["ESP_Thermax_OEM Manual"],
  "analysis_timestamp": "2026-02-18T13:38:03"
}
```

Results from all agents are merged into `DomainInsightsSummary`:
- `key_findings` — top findings across all domains (severity-sorted)
- `suspected_root_causes` — one hypothesis per domain with confidence
- `overall_confidence` — weighted average across agents
- `recommended_checks` — deduplicated union of all agents' checks

---

## Adding a New Agent

1. Create `domain_agents/my_agent.py`:

```python
from domain_agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    @property
    def domain(self) -> str:
        return "my_domain"

    @property
    def domain_keywords(self) -> List[str]:
        return ["keyword1", "keyword2"]

    @property
    def checklist_areas(self) -> List[dict]:
        return [
            {"area": "Area Name", "focus": "What to look for in this area"},
        ]
```

2. Export it from `domain_agents/__init__.py`:
```python
from domain_agents.my_agent import MyAgent
```

3. Add routing keywords in `IntegratedRCATool.agent_routing`:
```python
"my_agent": ["keyword1", "keyword2"]
```

4. Register in `api/main.py` at startup:
```python
registry.register_tool("my_agent", MyAgent(llm_adapter=gemini, rag_manager=rag))
```
