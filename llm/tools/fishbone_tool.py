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
            # json_mode=True forces the model to return valid JSON (supported
            # by OpenRouter/GPT-5). Ignored silently by adapters that don't
            # support the parameter (e.g. GeminiAdapter).
            import inspect
            gen_sig = inspect.signature(self.llm_adapter.generate)
            supports_json = "json_mode" in gen_sig.parameters
            supports_max_tokens = "max_tokens" in gen_sig.parameters
            call_kwargs = {}
            if supports_json:
                call_kwargs["json_mode"] = True
            if supports_max_tokens:
                # Fishbone JSON (6 categories × multiple causes) can be verbose —
                # raise the cap well above the default 4096 so finish_reason never hits 'length'
                call_kwargs["max_tokens"] = 16384
            raw_response = await self.llm_adapter.generate(prompt, **call_kwargs)

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
Map ONLY the conditions that ENABLED the confirmed root cause to occur, across these 6 Ishikawa categories:
{categories_desc}

For each category, identify 1-2 specific contributing causes relevant to THIS failure.

CRITICAL RULES:
1. CAUSES ONLY — Do NOT include consequences or effects. Items that happened AFTER the root cause (electrical trips, emission exceedance, interlock activations, alarms triggered by the failure) are EFFECTS. Exclude them entirely.
2. CAUSAL BOUNDARY — Root cause = first equipment functional failure. Branches show conditions that enabled THAT failure only. Do NOT include upstream physics theories unless a sensor/alarm confirms them.
3. Each cause must be a SHORT phrase (5-10 words max, e.g. "Hopper heating element burnout"). NOT a full sentence.
4. Each sub_cause must also be SHORT (3-7 words max).
5. Evidence must be ONE sentence max (under 15 words).
6. Do NOT repeat the root cause itself — map what CONTRIBUTED to it.
7. The primary_category must contain ONLY CONFIRMED or SUPPORTED causes, never POSSIBLE.
8. If a category has no relevant causes, use an empty array []. EXCEPTION: "Environment" must ALWAYS have at least 1 cause — in industrial plants, environmental factors (dust, temperature, humidity, vibration from adjacent equipment) are always present. Even if not confirmed, include plausible environmental factors as SUPPORTED.
9. For Machine and Method categories: go BEYOND the symptom to the DESIGN or MAINTENANCE GAP. Example: Instead of "Mounting joint prone to vibration loosening", write "No locking mechanism (nylock/spring washer) on mounting bolts". Instead of "Bearing overheated", write "No vibration trending to detect progressive degradation".

EVIDENCE CLASSIFICATION — For each cause, assign an evidence_level:
- "CONFIRMED": Directly observed or logged (alarms, sensor data, operator report)
- "SUPPORTED": Required by physics but not directly measured
- "POSSIBLE": Plausible but unverified

Confidence scores: CONFIRMED → 0.90, SUPPORTED → 0.75, POSSIBLE → 0.50

SEVERITY CLASSIFICATION — For each cause, assign a severity:
- "CRITICAL": Directly caused or enabled the failure, must be addressed immediately
- "HIGH": Significantly contributed to the failure, should be addressed soon
- "MEDIUM": Contributed to conditions that enabled the failure
- "LOW": Minor contributing factor

Respond ONLY with valid JSON in this exact format:
{{
  "categories": {{
    "Man": [
      {{
        "cause": "Short cause phrase",
        "sub_causes": ["short sub-cause"],
        "confidence": 0.90,
        "evidence_level": "CONFIRMED",
        "evidence": "One sentence of evidence",
        "severity": "CRITICAL"
      }}
    ],
    "Machine": [...],
    "Material": [...],
    "Method": [...],
    "Measurement": [...],
    "Environment": [...]
  }},
  "primary_category": "Machine",
  "category_confidence": {{
    "Man": 0.60,
    "Machine": 0.90,
    "Material": 0.85,
    "Method": 0.70,
    "Measurement": 0.75,
    "Environment": 0.50
  }},
  "summary": "One sentence explaining the dominant causal pathway"
}}
"""

    def _parse_response(
        self, raw: str, root_cause: str, docs_used: List[str]
    ) -> FishboneResult:
        """Parse LLM JSON response into FishboneResult."""
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

        # Extract JSON block
        json_match = re.search(r'\{[\s\S]*\}', cleaned)
        if not json_match:
            logger.error(f"Raw LLM response (first 500 chars): {raw[:500]!r}")
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
                # Parse evidence_level, default to POSSIBLE
                evidence_level = c.get("evidence_level", "POSSIBLE").upper()
                if evidence_level not in ("CONFIRMED", "SUPPORTED", "POSSIBLE"):
                    evidence_level = "POSSIBLE"

                # Parse severity, default to MEDIUM
                severity = c.get("severity", "MEDIUM").upper()
                if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                    severity = "MEDIUM"

                causes.append(FishboneCause(
                    category=cat_name,
                    cause=cause_text,
                    sub_causes=c.get("sub_causes", []),
                    confidence=float(c.get("confidence", 0.5)),
                    evidence_level=evidence_level,
                    evidence=c.get("evidence", ""),
                    severity=severity,
                ))
            categories[cat_name] = causes

        # Validate primary_category
        if primary_category not in ISHIKAWA_CATEGORIES:
            # Pick the category with the most causes
            primary_category = max(
                categories, key=lambda k: len(categories[k]), default="Machine"
            )

        # Extract per-category confidence scores from LLM response
        raw_cat_conf = data.get("category_confidence", {})
        category_confidence = {}
        for cat_name in ISHIKAWA_CATEGORIES:
            if cat_name in raw_cat_conf:
                category_confidence[cat_name] = round(float(raw_cat_conf[cat_name]), 2)
            elif categories.get(cat_name):
                # Derive from average cause confidence
                avg_conf = sum(c.confidence for c in categories[cat_name]) / len(categories[cat_name])
                category_confidence[cat_name] = round(avg_conf, 2)
            else:
                category_confidence[cat_name] = 0.0

        return FishboneResult(
            categories=categories,
            root_cause_confirmed=root_cause,
            primary_category=primary_category,
            category_confidence=category_confidence,
            documents_used=list(set(docs_used)),
        )
