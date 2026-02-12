"""
Process Domain Agent

Specializes in process-related failure analysis: operating parameters,
material flow, heat transfer, chemical reactions, environmental conditions.
"""

from typing import List, Dict, Any
from domain_agents.base_agent import BaseAgent


class ProcessAgent(BaseAgent):

    @property
    def domain(self) -> str:
        return "process"

    @property
    def domain_keywords(self) -> List[str]:
        return [
            "process", "temperature", "pressure", "flow", "operating",
            "parameter", "limit", "setpoint", "feed", "composition",
            "combustion", "heat transfer", "efficiency",
        ]

    @property
    def checklist_areas(self) -> List[Dict[str, str]]:
        return [
            {
                "area": "Operating Parameters",
                "focus": "temperature, pressure, flow rate vs design limits, deviation from setpoints",
            },
            {
                "area": "Material Quality",
                "focus": "feed composition, contamination, moisture content, particle size",
            },
            {
                "area": "Process Stability",
                "focus": "control loop performance, setpoint deviations, trend analysis, oscillations",
            },
            {
                "area": "Environmental Factors",
                "focus": "ambient temperature, humidity, dust loading, seasonal effects",
            },
        ]

    def _build_domain_prompt(
        self,
        equipment_name: str,
        failure_description: str,
        symptoms: List[str],
        rag_context: str,
    ) -> str:
        checklist_text = "\n".join(
            f"  - {a['area']}: {a['focus']}" for a in self.checklist_areas
        )
        return f"""You are a PROCESS ENGINEERING expert performing domain-specific Root Cause Analysis for industrial equipment.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}

Relevant Technical Documentation:
{rag_context}

ANALYSIS CHECKLIST (evaluate each area):
{checklist_text}

RULES:
1. Focus ONLY on process aspects (operating conditions, material quality, process stability, environment)
2. Compare observed parameters against design limits and OEM specifications where available
3. Back every claim with evidence from symptoms, sensor data, or OEM manual references
4. If inferring without direct evidence, say "Based on inference"
5. Keep each finding to 1-2 sentences
6. Do NOT use markdown formatting (no ** or *)
7. Do NOT use HTTP/API error codes as failure modes

Respond in EXACTLY this format:

FINDINGS:
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
(one line per finding, minimum 3 findings, maximum 6)

HYPOTHESIS: [2-3 sentences: your process root cause hypothesis with evidence]

RECOMMENDED_CHECKS:
- physical check 1
- physical check 2
- physical check 3

CONFIDENCE: [percentage, e.g., 80]
"""
