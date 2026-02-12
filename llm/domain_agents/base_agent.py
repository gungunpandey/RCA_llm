"""
Base Agent for Domain-Specific RCA Analysis

Extends BaseTool to provide domain-specialized analysis capabilities.
Each domain agent (Mechanical, Electrical, Process) inherits from this
and provides its own prompt checklist and RAG search strategy.
"""

import re
import logging
from abc import abstractmethod
from typing import List, Dict, Any

from tools.base_tool import BaseTool
from models.tool_results import ToolResult, DomainAnalysisResult, DomainFinding
from tools.evidence_validator import (
    ConfidenceCalibrator,
    PlantFailureModeValidator,
    EvidenceType
)

logger = logging.getLogger(__name__)


class BaseAgent(BaseTool):
    """
    Abstract base for domain-specific RCA agents.

    Subclasses must implement:
        - domain (property)        : "mechanical" | "electrical" | "process"
        - domain_keywords (property): keywords for RAG search
        - checklist_areas (property): analysis areas for the domain
        - _build_domain_prompt()   : domain-specific LLM prompt
    """

    def __init__(self, llm_adapter: Any, rag_manager: Any):
        super().__init__(llm_adapter, rag_manager, tool_name=f"{self.domain}_agent")

    # ── Abstract properties (each subclass defines) ──

    @property
    @abstractmethod
    def domain(self) -> str:
        """Domain name: 'mechanical', 'electrical', or 'process'."""
        ...

    @property
    @abstractmethod
    def domain_keywords(self) -> List[str]:
        """Keywords used to enrich RAG queries for this domain."""
        ...

    @property
    @abstractmethod
    def checklist_areas(self) -> List[Dict[str, str]]:
        """
        Analysis checklist areas.
        Each dict has 'area' (name) and 'focus' (what to look for).
        """
        ...

    @abstractmethod
    def _build_domain_prompt(
        self,
        equipment_name: str,
        failure_description: str,
        symptoms: List[str],
        rag_context: str,
    ) -> str:
        """Build the domain-specific LLM prompt."""
        ...

    # ── Core analyze method (BaseTool interface) ──

    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs,
    ) -> ToolResult:
        status_callback = kwargs.get("status_callback")

        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)

        async def _perform_analysis():
            # 1. Domain-enriched RAG retrieval
            await _send_status(f"{self.domain.title()} agent: searching OEM manuals...")
            rag_docs = await self._get_domain_rag_context(equipment_name, symptoms)
            rag_context = self._format_context(rag_docs)
            doc_sources = [doc.source for doc in rag_docs if hasattr(doc, "source")]
            await _send_status(
                f"{self.domain.title()} agent: retrieved {len(rag_docs)} documents"
            )

            # 2. Build prompt and call LLM
            await _send_status(f"{self.domain.title()} agent: analyzing failure...")
            prompt = self._build_domain_prompt(
                equipment_name, failure_description, symptoms, rag_context
            )
            response = self._call_llm(prompt)

            # 3. Parse structured response
            findings, hypothesis, confidence, checks = self._parse_domain_response(
                response
            )

            # 4. Validate
            is_valid, error_msg = PlantFailureModeValidator.validate_failure_mode(
                hypothesis
            )
            if not is_valid:
                logger.warning(error_msg)
                hypothesis = PlantFailureModeValidator.sanitize_ai_errors(hypothesis)

            evidence_type = ConfidenceCalibrator.assess_evidence_from_answer(
                hypothesis, doc_sources
            )
            has_oem = any(
                kw in hypothesis.lower()
                for kw in ["manual states", "manual specifies", "according to"]
            )
            calibrated, _ = ConfidenceCalibrator.calibrate_confidence(
                raw_confidence=confidence,
                evidence_type=evidence_type,
                has_oem_rule=has_oem,
            )

            await _send_status(
                f"{self.domain.title()} agent: complete — confidence {calibrated*100:.0f}%"
            )

            result = DomainAnalysisResult(
                domain=self.domain,
                findings=findings,
                root_cause_hypothesis=hypothesis,
                confidence=calibrated,
                recommended_checks=checks,
                documents_used=list(set(doc_sources)),
            )
            return result.dict()

        return await self._execute_with_timing(_perform_analysis)

    # ── Domain-enriched RAG retrieval ──

    async def _get_domain_rag_context(
        self, equipment_name: str, symptoms: List[str], top_k: int = 5
    ):
        """Retrieve RAG docs using domain-specific keywords."""
        enriched_symptoms = list(symptoms) + self.domain_keywords
        return await self._retrieve_context(equipment_name, enriched_symptoms, top_k)

    # ── LLM call (same pattern as FiveWhysTool) ──

    def _call_llm(self, prompt: str) -> str:
        if hasattr(self.llm_adapter, "client"):
            if hasattr(self.llm_adapter.client, "models"):
                response = self.llm_adapter.client.models.generate_content(
                    model=self.llm_adapter.model_name, contents=prompt
                )
                return response.text

        result = self.llm_adapter.analyze_failure(
            failure_description=prompt,
            equipment_name="",
            symptoms=[],
            use_rag=False,
        )
        return result.get("raw_response", "")

    # ── Response parser ──

    def _parse_domain_response(self, response: str):
        """
        Parse LLM response into findings, hypothesis, confidence, checks.

        Expected LLM format:
            FINDINGS:
            [AREA] area_name | [SEVERITY] critical/warning/normal | observation | evidence
            ...
            HYPOTHESIS: ...
            RECOMMENDED_CHECKS:
            - check 1
            - check 2
            CONFIDENCE: 85
        """
        # Findings
        findings = []
        findings_match = re.search(
            r"FINDINGS:\s*(.+?)(?=\nHYPOTHESIS:|\Z)", response, re.DOTALL | re.IGNORECASE
        )
        if findings_match:
            for line in findings_match.group(1).strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    continue
                finding = self._parse_finding_line(line)
                if finding:
                    findings.append(finding)

        # If regex parsing got nothing, create a single generic finding
        if not findings:
            findings.append(
                DomainFinding(
                    area="General",
                    observation=response[:300].strip(),
                    severity="warning",
                    evidence="Based on inference",
                )
            )

        # Hypothesis
        hyp_match = re.search(
            r"HYPOTHESIS:\s*(.+?)(?=\nRECOMMENDED[_ ]CHECKS:|\nCONFIDENCE:|\Z)",
            response, re.DOTALL | re.IGNORECASE,
        )
        hypothesis = hyp_match.group(1).strip() if hyp_match else response[:300].strip()

        # Recommended checks
        checks = []
        checks_match = re.search(
            r"RECOMMENDED[_ ]CHECKS:\s*(.+?)(?=\nCONFIDENCE:|\Z)",
            response, re.DOTALL | re.IGNORECASE,
        )
        if checks_match:
            for line in checks_match.group(1).strip().split("\n"):
                line = re.sub(r"^[\-\d.)\s]+", "", line).strip()
                if line:
                    checks.append(line)

        # Confidence
        conf_match = re.search(r"CONFIDENCE:\s*(\d+)", response, re.IGNORECASE)
        confidence = float(conf_match.group(1)) / 100.0 if conf_match else 0.7

        return findings, hypothesis, confidence, checks

    def _parse_finding_line(self, line: str):
        """
        Parse a single finding line.
        Format: [AREA] name | [SEVERITY] level | observation | evidence
        Fallback: treat entire line as observation.
        """
        # Try structured format
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            area = re.sub(r"\[AREA\]\s*", "", parts[0], flags=re.IGNORECASE).strip()
            severity_raw = re.sub(r"\[SEVERITY\]\s*", "", parts[1], flags=re.IGNORECASE).strip().lower()
            severity = severity_raw if severity_raw in ("critical", "warning", "normal") else "warning"
            observation = parts[2].strip()
            evidence = parts[3].strip() if len(parts) > 3 else "Based on inference"
            if area and observation:
                return DomainFinding(
                    area=area, observation=observation,
                    severity=severity, evidence=evidence,
                )

        # Fallback: use checklist area names to guess
        line_lower = line.lower()
        for area_info in self.checklist_areas:
            if any(kw in line_lower for kw in area_info["area"].lower().split()):
                return DomainFinding(
                    area=area_info["area"],
                    observation=line,
                    severity="warning",
                    evidence="Based on inference",
                )

        return None
