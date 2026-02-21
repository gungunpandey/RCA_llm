"""
Fishbone (Ishikawa) Diagram Tool

Analyzes a failure across 6 Ishikawa categories after the root cause
has been identified by the 5 Whys tool. Produces a structured causal map.

Categories: Man, Machine, Material, Method, Measurement, Environment
"""

import json
import logging
import re
import time
from typing import List, Dict, Any, Optional, Callable

from tools.base_tool import BaseTool
from models.tool_results import (
    ToolResult, FishboneCause, FishboneResult, DomainInsightsSummary
)

logger = logging.getLogger(__name__)

# The 6 Ishikawa categories with plant-specific focus hints
ISHIKAWA_CATEGORIES = {
    "Man": "operator actions, human error, training gaps, shift handover issues, procedural non-compliance",
    "Machine": "equipment wear, mechanical failure, design flaws, maintenance state, component degradation",
    "Material": "raw material quality, feed properties, contamination, material specification deviations",
    "Method": "SOP deviations, process parameter settings, operating procedures, control strategy",
    "Measurement": "sensor drift, calibration errors, signal quality issues, instrumentation failures",
    "Environment": "ambient temperature, dust levels, humidity, vibration, external conditions",
}


class FishboneTool(BaseTool):
    """
    Fishbone (Ishikawa) Diagram Tool.

    Runs after 5 Whys to map contributing causes across 6 categories.
    Uses the identified root cause + RAG context to populate each category.
    """

    def __init__(self, llm_adapter: Any, rag_manager: Any):
        super().__init__(llm_adapter, rag_manager, tool_name="fishbone")

    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        root_cause: str,
        domain_insights: Optional[DomainInsightsSummary] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Perform Fishbone analysis using the confirmed root cause from 5 Whys.

        Args:
            failure_description: Original failure description
            equipment_name: Equipment that failed
            symptoms: Observed symptoms
            root_cause: Root cause already identified by 5 Whys tool
            domain_insights: Optional domain agent findings for extra context
            **kwargs: Optional status_callback for SSE streaming

        Returns:
            ToolResult containing FishboneResult
        """
        status_callback: Optional[Callable] = kwargs.get("status_callback")
        start_time = time.time()

        async def _send(msg: str):
            if status_callback:
                await status_callback(msg)

        try:
            await _send("🦴 Starting Fishbone (Ishikawa) analysis...")

            # ── 1. Fetch RAG context ──────────────────────────────────────
            await _send("📚 Retrieving equipment context for causal analysis...")
            rag_docs = await self.rag.retrieve_equipment_context(
                equipment_name=equipment_name,
                failure_symptoms=symptoms if symptoms else [failure_description[:100]],
                top_k=8,
            )
            rag_context = self._format_rag_context(rag_docs)
            docs_used = [
                doc.source if hasattr(doc, 'source') else doc.get('source', '')
                for doc in rag_docs
            ]

            # ── 2. Build domain context string ───────────────────────────
            domain_context = ""
            if domain_insights:
                domain_context = self._format_domain_context(domain_insights)

            # ── 3. Build LLM prompt ───────────────────────────────────────
            await _send("🤖 Analyzing contributing causes across 6 categories...")
            prompt = self._build_prompt(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                root_cause=root_cause,
                rag_context=rag_context,
                domain_context=domain_context,
            )

            # ── 4. Call LLM ───────────────────────────────────────────────
            raw_response = await self.llm_adapter.generate(prompt)

            # ── 5. Parse response ─────────────────────────────────────────
            fishbone_result = self._parse_response(raw_response, root_cause, docs_used)

            await _send(
                f"✓ Fishbone complete — primary cause category: "
                f"{fishbone_result.primary_category}"
            )

            elapsed = round(time.time() - start_time, 2)
            return ToolResult(
                tool_name="fishbone",
                success=True,
                result=fishbone_result.model_dump(),
                execution_time_seconds=elapsed,
            )

        except Exception as e:
            logger.error(f"FishboneTool failed: {e}", exc_info=True)
            elapsed = round(time.time() - start_time, 2)
            return ToolResult(
                tool_name="fishbone",
                success=False,
                result={},
                error=str(e),
                execution_time_seconds=elapsed,
            )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _format_rag_context(self, docs) -> str:
        if not docs:
            return "No additional context retrieved."
        parts = []
        for i, doc in enumerate(docs[:6], 1):
            # Handle both Document objects and plain dicts
            if hasattr(doc, 'source'):
                source = doc.source or 'Unknown'
                content = (doc.content or '')[:400]
            else:
                source = doc.get('source', 'Unknown')
                content = doc.get('content', doc.get('text', ''))[:400]
            parts.append(f"[Doc {i} — {source}]\n{content}")
        return "\n\n".join(parts)

    def _format_domain_context(self, insights: DomainInsightsSummary) -> str:
        lines = ["DOMAIN EXPERT FINDINGS:"]
        for finding in insights.key_findings[:5]:
            lines.append(f"  • {finding}")
        for hyp in insights.suspected_root_causes[:3]:
            # Handle both Pydantic objects and plain dicts
            if hasattr(hyp, 'domain'):
                domain = hyp.domain or ""
                hypothesis = hyp.hypothesis or ""
                conf = int((hyp.confidence or 0) * 100)
            else:
                domain = hyp.get("domain", "")
                hypothesis = hyp.get("hypothesis", "")
                conf = int(hyp.get("confidence", 0) * 100)
            lines.append(f"  [{domain.upper()}] {hypothesis} ({conf}% confidence)")
        return "\n".join(lines)


    def _build_prompt(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        root_cause: str,
        rag_context: str,
        domain_context: str,
    ) -> str:
        symptoms_str = "\n".join(f"  - {s}" for s in symptoms) if symptoms else "  - None provided"
        categories_desc = "\n".join(
            f"  - {cat}: {focus}" for cat, focus in ISHIKAWA_CATEGORIES.items()
        )

        return f"""You are an expert plant engineer performing a Fishbone (Ishikawa) Diagram analysis.

EQUIPMENT: {equipment_name}
FAILURE: {failure_description}
SYMPTOMS:
{symptoms_str}

CONFIRMED ROOT CAUSE (from 5 Whys analysis):
{root_cause}

{domain_context}

EQUIPMENT DOCUMENTATION CONTEXT:
{rag_context}

TASK:
Map ALL contributing causes to the failure across these 6 Ishikawa categories:
{categories_desc}

For each category, identify 1-3 specific contributing causes that are relevant to THIS failure.
Focus on causes that are realistic for a plant/industrial setting.
Use the equipment documentation and domain findings to support your causes.

IMPORTANT RULES:
- Every cause must be specific and actionable (not vague like "poor maintenance")
- Include sub-causes where relevant (e.g. "Bearing wear" → sub: "Lack of vibration monitoring")
- Assign a confidence score (0.0-1.0) based on evidence available
- The primary_category is the one with the strongest/most direct contributing causes
- Do NOT repeat the root cause itself — map what CONTRIBUTED to it

Respond ONLY with valid JSON in this exact format:
{{
  "categories": {{
    "Man": [
      {{
        "cause": "Specific cause description",
        "sub_causes": ["sub-cause 1", "sub-cause 2"],
        "confidence": 0.85,
        "evidence": "Evidence or document reference supporting this cause"
      }}
    ],
    "Machine": [...],
    "Material": [...],
    "Method": [...],
    "Measurement": [...],
    "Environment": [...]
  }},
  "primary_category": "Machine",
  "summary": "One sentence explaining the dominant causal pathway"
}}

If a category has no relevant causes for this specific failure, use an empty array [].
"""

    def _parse_response(
        self, raw: str, root_cause: str, docs_used: List[str]
    ) -> FishboneResult:
        """Parse LLM JSON response into FishboneResult."""
        # Extract JSON block
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if not json_match:
            raise ValueError("No JSON found in LLM response")

        data = json.loads(json_match.group())

        categories_raw = data.get("categories", {})
        primary_category = data.get("primary_category", "Machine")

        # Build FishboneCause objects per category
        categories: Dict[str, List[FishboneCause]] = {}
        for cat_name in ISHIKAWA_CATEGORIES:
            causes_raw = categories_raw.get(cat_name, [])
            causes = []
            for c in causes_raw:
                if not isinstance(c, dict):
                    continue
                cause_text = c.get("cause", "").strip()
                if not cause_text:
                    continue
                causes.append(FishboneCause(
                    category=cat_name,
                    cause=cause_text,
                    sub_causes=c.get("sub_causes", []),
                    confidence=float(c.get("confidence", 0.7)),
                    evidence=c.get("evidence", ""),
                ))
            categories[cat_name] = causes

        # Validate primary_category
        if primary_category not in ISHIKAWA_CATEGORIES:
            # Pick the category with the most causes
            primary_category = max(
                categories, key=lambda k: len(categories[k]), default="Machine"
            )

        return FishboneResult(
            categories=categories,
            root_cause_confirmed=root_cause,
            primary_category=primary_category,
            documents_used=list(set(docs_used)),
        )
