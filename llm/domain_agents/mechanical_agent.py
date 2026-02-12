"""
Mechanical Domain Agent

Specializes in mechanical failure analysis: vibration, alignment,
wear patterns, lubrication, bearing condition, structural integrity.
"""

from typing import List, Dict, Any
from domain_agents.base_agent import BaseAgent


class MechanicalAgent(BaseAgent):

    @property
    def domain(self) -> str:
        return "mechanical"

    @property
    def domain_keywords(self) -> List[str]:
        return [
            "vibration", "alignment", "bearing", "wear", "lubrication",
            "torque", "mechanical", "shaft", "coupling", "fatigue",
            "corrosion", "clearance", "balance",
        ]

    @property
    def checklist_areas(self) -> List[Dict[str, str]]:
        return [
            {
                "area": "Bearing Condition",
                "focus": "temperature, vibration spectrum, lubrication state, clearance",
            },
            {
                "area": "Alignment and Balance",
                "focus": "shaft alignment, coupling condition, impeller balance, runout",
            },
            {
                "area": "Wear and Fatigue",
                "focus": "material wear, fatigue cracks, service life, erosion patterns",
            },
            {
                "area": "Structural Integrity",
                "focus": "cracks, corrosion, deformation, foundation condition",
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
        return f"""You are a MECHANICAL ENGINEERING expert performing domain-specific Root Cause Analysis for industrial equipment.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}

Relevant Technical Documentation:
{rag_context}

ANALYSIS CHECKLIST (evaluate each area):
{checklist_text}

RULES:
1. Focus ONLY on mechanical aspects (vibration, wear, alignment, lubrication, structural)
2. Back every claim with evidence from symptoms, sensor data, or OEM manual references
3. If inferring without direct evidence, say "Based on inference"
4. Keep each finding to 1-2 sentences
5. Do NOT use markdown formatting (no ** or *)
6. Do NOT use HTTP/API error codes as failure modes

Respond in EXACTLY this format:

FINDINGS:
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
(one line per finding, minimum 3 findings, maximum 6)

HYPOTHESIS: [2-3 sentences: your mechanical root cause hypothesis with evidence]

RECOMMENDED_CHECKS:
- physical check 1
- physical check 2
- physical check 3

CONFIDENCE: [percentage, e.g., 80]
"""
