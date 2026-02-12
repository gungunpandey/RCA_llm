"""
Electrical Domain Agent

Specializes in electrical failure analysis: motor parameters, interlocks,
protection relays, power supply, insulation, wiring, VFD faults.
"""

from typing import List, Dict, Any
from domain_agents.base_agent import BaseAgent


class ElectricalAgent(BaseAgent):

    @property
    def domain(self) -> str:
        return "electrical"

    @property
    def domain_keywords(self) -> List[str]:
        return [
            "electrical", "motor", "interlock", "relay", "voltage",
            "current", "protection", "circuit", "winding", "insulation",
            "VFD", "contactor", "overcurrent", "trip",
        ]

    @property
    def checklist_areas(self) -> List[Dict[str, str]]:
        return [
            {
                "area": "Motor Condition",
                "focus": "current draw vs rated FLA, insulation resistance, winding temperature, starting current",
            },
            {
                "area": "Protection Systems",
                "focus": "relay settings, trip conditions, interlock logic, fuse condition",
            },
            {
                "area": "Power Supply Quality",
                "focus": "voltage levels, phase balance, harmonics, grounding integrity",
            },
            {
                "area": "Control Circuits",
                "focus": "wiring condition, contactor state, VFD parameters and fault codes, sensor signals",
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
        return f"""You are an ELECTRICAL ENGINEERING expert performing domain-specific Root Cause Analysis for industrial equipment.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}

Relevant Technical Documentation:
{rag_context}

ANALYSIS CHECKLIST (evaluate each area):
{checklist_text}

RULES:
1. Focus ONLY on electrical aspects (motor, protection, power supply, control circuits, interlocks)
2. Back every claim with evidence from symptoms, sensor data, or OEM manual references
3. If inferring without direct evidence, say "Based on inference"
4. Keep each finding to 1-2 sentences
5. Do NOT use markdown formatting (no ** or *)
6. Plant signal failures are: "Bad Quality", "Comm Fail", "Signal Unhealthy", "Input Forced", "Loss of Signal"
7. Do NOT use HTTP/API error codes (503, 404, etc.) as plant failure modes

Respond in EXACTLY this format:

FINDINGS:
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
[AREA] area_name | [SEVERITY] critical/warning/normal | observation text | evidence text
(one line per finding, minimum 3 findings, maximum 6)

HYPOTHESIS: [2-3 sentences: your electrical root cause hypothesis with evidence]

RECOMMENDED_CHECKS:
- physical check 1
- physical check 2
- physical check 3

CONFIDENCE: [percentage, e.g., 80]
"""
