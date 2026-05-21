"""
CAPA (Corrective + Preventive Action) Tool

Runs AFTER 5 Whys + Fishbone, once the root cause has been confirmed.
Synthesises a structured CAPA plan from:
  - The confirmed root cause
  - The full 5 Whys causal chain
  - The Fishbone categories (breadth of contributing causes)
  - Domain expert findings + recommended checks
  - OEM documentation (RAG)
  - CAPAs that were applied to similar past incidents (from Neo4j history matcher)

Categories: corrective (fix the immediate problem) and preventive (stop recurrence).
"""

import json
import re
import time
import inspect
import logging
from typing import List, Dict, Any, Optional, Callable

from tools.base_tool import BaseTool
from models.tool_results import (
    ToolResult,
    CAPAAction,
    CAPAResult,
    DomainInsightsSummary,
    FishboneResult,
    WhyStep,
)

logger = logging.getLogger(__name__)

VALID_TYPES      = {"corrective", "preventive"}
VALID_PRIORITIES = {"immediate", "short_term", "long_term"}
DEFAULT_PRIORITY = "short_term"


class CAPATool(BaseTool):
    """Generates a structured CAPA plan from a confirmed root cause."""

    def __init__(self, llm_adapter: Any, rag_manager: Any):
        super().__init__(llm_adapter, rag_manager, tool_name="capa")

    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        root_cause: str,
        why_steps: Optional[List[Dict[str, Any]]] = None,
        fishbone_result: Optional[Dict[str, Any]] = None,
        domain_insights: Optional[DomainInsightsSummary] = None,
        historical_capas: Optional[List[Dict[str, Any]]] = None,
        user_clarifications: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Build a CAPA plan.

        Args:
            failure_description: Original failure description (post-clarifications)
            equipment_name: Equipment that failed
            symptoms: Observed symptoms
            root_cause: Root cause confirmed by 5 Whys
            why_steps: 5 Whys causal chain as a list of WhyStep dicts
            fishbone_result: FishboneResult.model_dump() — may be None if Fishbone failed
            domain_insights: Aggregated domain expert insights
            historical_capas: Past incidents (from history matcher) carrying a 'capa' list
            user_clarifications: List of ClarificationAnswer dicts from the chatbot step
            status_callback: Optional async callback for SSE status messages

        Returns:
            ToolResult containing CAPAResult.
        """
        status_callback: Optional[Callable] = kwargs.get("status_callback")
        start_time = time.time()

        async def _send(msg: str):
            if status_callback:
                await status_callback(msg)

        # Empty / missing root cause → degraded mode, single placeholder action
        if not root_cause or not root_cause.strip():
            await _send("⚠ CAPA skipped — no confirmed root cause to act on")
            return self._degraded_result(
                reason="No confirmed root cause provided to CAPA generator.",
                elapsed=round(time.time() - start_time, 2),
            )

        try:
            await _send("🛠 Generating CAPA plan (corrective + preventive)...")

            # 1. RAG context for the action wording (procedures, thresholds)
            await _send("📚 Retrieving equipment documentation for action wording...")
            rag_docs = await self.rag.retrieve_equipment_context(
                equipment_name=equipment_name,
                failure_symptoms=symptoms if symptoms else [root_cause[:120]],
                top_k=6,
            )
            rag_context = self._format_rag_context(rag_docs)
            docs_used = [
                doc.source if hasattr(doc, "source") else doc.get("source", "")
                for doc in rag_docs
            ]

            # 2. Build the prompt
            prompt = self._build_prompt(
                failure_description=failure_description,
                equipment_name=equipment_name,
                root_cause=root_cause,
                why_steps=why_steps or [],
                fishbone_result=fishbone_result,
                domain_insights=domain_insights,
                historical_capas=historical_capas or [],
                user_clarifications=user_clarifications or [],
                rag_context=rag_context,
            )

            # 3. Call LLM (json_mode when available; matches FishboneTool's pattern)
            await _send("🤖 Drafting actions across corrective + preventive categories...")
            gen_sig = inspect.signature(self.llm_adapter.generate)
            call_kwargs: Dict[str, Any] = {}
            if "json_mode" in gen_sig.parameters:
                call_kwargs["json_mode"] = True
            if "max_tokens" in gen_sig.parameters:
                # 4-6 structured actions can run long — give it headroom
                call_kwargs["max_tokens"] = 6000

            raw = await self.llm_adapter.generate(prompt, **call_kwargs)

            # 4. Parse + validate
            capa_result = self._parse_response(raw, docs_used, historical_capas or [])

            await _send(
                f"✓ CAPA plan ready — {len(capa_result.corrective)} corrective, "
                f"{len(capa_result.preventive)} preventive action(s)"
            )

            elapsed = round(time.time() - start_time, 2)
            return ToolResult(
                tool_name="capa",
                success=True,
                result=capa_result.model_dump(),
                execution_time_seconds=elapsed,
            )

        except Exception as e:
            logger.error(f"CAPATool failed: {e}", exc_info=True)
            elapsed = round(time.time() - start_time, 2)
            return ToolResult(
                tool_name="capa",
                success=False,
                result={},
                error=str(e),
                execution_time_seconds=elapsed,
            )

    # ── Prompt construction ─────────────────────────────────────────────────

    def _build_prompt(
        self,
        failure_description: str,
        equipment_name: str,
        root_cause: str,
        why_steps: List[Dict[str, Any]],
        fishbone_result: Optional[Dict[str, Any]],
        domain_insights: Optional[DomainInsightsSummary],
        historical_capas: List[Dict[str, Any]],
        user_clarifications: List[Dict[str, Any]],
        rag_context: str,
    ) -> str:
        why_chain = self._format_why_chain(why_steps)
        fishbone_block = self._format_fishbone(fishbone_result)
        domain_block = self._format_domain(domain_insights)
        historical_block = self._format_historical_capas(historical_capas)
        clarif_block = self._format_clarifications(user_clarifications)

        return f"""You are a senior plant reliability engineer producing a CAPA (Corrective + Preventive Action) plan for an industrial equipment failure.

EQUIPMENT: {equipment_name}
FAILURE DESCRIPTION: {failure_description[:1200]}

CONFIRMED ROOT CAUSE (from 5 Whys analysis):
{root_cause}

5 WHYS CAUSAL CHAIN:
{why_chain}

FISHBONE CONTRIBUTING CAUSES (by Ishikawa category):
{fishbone_block}

DOMAIN EXPERT FINDINGS:
{domain_block}

USER CLARIFICATIONS (additional context provided by the engineer):
{clarif_block}

OEM DOCUMENTATION CONTEXT:
{rag_context}

HISTORICAL CAPAs FROM SIMILAR PAST INCIDENTS (reference only — these were actually applied):
{historical_block}

TASK:
Produce a CAPA plan with:
  - 2-3 CORRECTIVE actions (fix the immediate problem and restore safe operation)
  - 2-3 PREVENTIVE actions (prevent the same failure from recurring)

RULES:
1. Each action MUST be specific and verifiable. NEVER write generic items like "monitor regularly", "check periodically", or "improve maintenance". Always include WHAT to do, ON WHICH component, with WHAT acceptance criterion (numeric threshold, document reference, or measurable outcome).
2. Each action MUST connect either to the confirmed root cause OR to a Fishbone contributing cause. Use 'related_category' to declare which Ishikawa category it addresses (Man | Machine | Material | Method | Measurement | Environment).
3. Reference OEM manual sections by document name in 'references' when the action follows a documented procedure.
4. When a historical CAPA from a past similar incident is relevant, build on it (cite it by quoting its action in 'references') rather than just copying.
5. Use only these 'responsibility' values: "Mechanical Maintenance", "Electrical Maintenance", "Operations", "Instrumentation", "Process Engineering", "Reliability".
6. Priority guidance:
   - "immediate"   → within 24h; safety or availability critical
   - "short_term"  → within 1 week; before next production cycle
   - "long_term"   → next PM cycle or planned shutdown
7. 'target_date_hint' must be a human-readable string consistent with priority (e.g. "Within 24h", "Within 1 week", "Next PM cycle"). May be null only if truly indeterminate.
8. Do NOT use markdown formatting (no **, *, _) in any field.
9. 'summary' is ONE sentence describing the overall CAPA strategy in plain language.

Respond ONLY with valid JSON in this exact format:
{{
  "corrective": [
    {{
      "type": "corrective",
      "action": "Replace damaged bearing on Drum 2 and re-balance the rotor assembly",
      "rationale": "Direct repair of the failed component identified in the 5 Whys chain",
      "responsibility": "Mechanical Maintenance",
      "priority": "immediate",
      "target_date_hint": "Within 24h",
      "related_category": "Machine",
      "references": ["Rotary Kiln_Hongda_OEM Manual section 4.2"]
    }}
  ],
  "preventive": [
    {{
      "type": "preventive",
      "action": "...",
      "rationale": "...",
      "responsibility": "Reliability",
      "priority": "short_term",
      "target_date_hint": "Within 1 week",
      "related_category": "Method",
      "references": []
    }}
  ],
  "summary": "Replace the failed bearing and institute vibration trending to detect future degradation early."
}}
"""

    # ── Block formatters ────────────────────────────────────────────────────

    def _format_why_chain(self, why_steps: List[Dict[str, Any]]) -> str:
        if not why_steps:
            return "  (no 5 Whys chain available)"
        lines = []
        for s in why_steps:
            step = s.get("step_number", "?")
            ans  = (s.get("answer") or "").strip().replace("\n", " ")
            lines.append(f"  Why #{step}: {ans[:240]}")
        return "\n".join(lines)

    def _format_fishbone(self, fishbone: Optional[Dict[str, Any]]) -> str:
        if not fishbone or not fishbone.get("categories"):
            return "  (no Fishbone analysis available)"
        lines = []
        primary = fishbone.get("primary_category", "")
        if primary:
            lines.append(f"  PRIMARY CATEGORY: {primary}")
        for cat, causes in (fishbone.get("categories") or {}).items():
            if not causes:
                continue
            top = causes[0] if isinstance(causes[0], dict) else {}
            cause_text = (top.get("cause") or "").strip()
            evidence_level = top.get("evidence_level", "")
            severity = top.get("severity", "")
            if cause_text:
                tag = f" [{evidence_level}/{severity}]" if (evidence_level or severity) else ""
                lines.append(f"  {cat}: {cause_text}{tag}")
        return "\n".join(lines) if lines else "  (no Fishbone causes captured)"

    def _format_domain(self, di: Optional[DomainInsightsSummary]) -> str:
        if not di:
            return "  (no domain analysis available)"
        lines = []
        for finding in (di.key_findings or [])[:5]:
            lines.append(f"  • {finding}")
        for hyp in (di.suspected_root_causes or [])[:3]:
            dom  = (hyp.get("domain") or "").upper()
            text = (hyp.get("hypothesis") or "")[:160]
            conf = int((hyp.get("confidence") or 0) * 100)
            lines.append(f"  [{dom}] {text} ({conf}% conf)")
        recommended = (di.recommended_checks or [])[:5]
        if recommended:
            lines.append("  RECOMMENDED CHECKS:")
            for c in recommended:
                lines.append(f"    - {c}")
        return "\n".join(lines) if lines else "  (no findings)"

    def _format_historical_capas(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "  (none — no similar past incidents found)"
        lines = []
        for i, m in enumerate(history[:3], 1):
            capa_list = m.get("capa") or []
            if not capa_list:
                continue
            equip = m.get("equipment", "?")
            sim   = round((m.get("similarity_score") or 0) * 100)
            rc    = (m.get("root_cause") or "").strip()[:140]
            lines.append(f"  Past incident on {equip} ({sim}% similar) — root cause: \"{rc}\"")
            for c in capa_list[:4]:
                action = (c.get("action") or "").strip()
                if not action:
                    continue
                resp = c.get("responsibility")
                resp_str = f" [{resp}]" if resp else ""
                lines.append(f"    - {action}{resp_str}")
            lines.append("")
        return "\n".join(lines).rstrip() or "  (no usable past CAPAs)"

    def _format_clarifications(self, clarifications: List[Dict[str, Any]]) -> str:
        if not clarifications:
            return "  (none provided)"
        lines = []
        for c in clarifications:
            q = (c.get("question") or "").strip()[:140]
            a = (c.get("answer")   or "").strip()[:200]
            if q and a:
                lines.append(f"  Q: {q}")
                lines.append(f"  A: {a}")
        return "\n".join(lines) if lines else "  (none provided)"

    def _format_rag_context(self, docs) -> str:
        if not docs:
            return "  (no additional documentation retrieved)"
        parts = []
        for i, doc in enumerate(docs[:5], 1):
            if hasattr(doc, "source"):
                source  = doc.source or "Unknown"
                content = (doc.content or "")[:350]
            else:
                source  = doc.get("source", "Unknown")
                content = doc.get("content", doc.get("text", ""))[:350]
            parts.append(f"  [Doc {i} — {source}]\n  {content}")
        return "\n\n".join(parts)

    # ── Response parsing ────────────────────────────────────────────────────

    def _parse_response(
        self,
        raw: str,
        docs_used: List[str],
        historical_capas: List[Dict[str, Any]],
    ) -> CAPAResult:
        """Parse the LLM JSON output into a validated CAPAResult."""
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            logger.error(f"CAPA: no JSON block in LLM response (first 400 chars): {raw[:400]!r}")
            raise ValueError("No JSON found in CAPA LLM response")

        data = json.loads(match.group())

        corrective = self._parse_actions(data.get("corrective"), expected_type="corrective")
        preventive = self._parse_actions(data.get("preventive"), expected_type="preventive")

        # Always produce a non-empty summary
        summary = (data.get("summary") or "").strip()
        if not summary:
            summary = (
                f"Generated {len(corrective)} corrective and {len(preventive)} preventive "
                f"action(s) to address the confirmed root cause."
            )

        # Merge historical doc references into documents_used for traceability
        all_docs = list(docs_used)
        for m in historical_capas[:3]:
            sf = m.get("source_file") or m.get("equipment")
            if sf and sf not in all_docs:
                all_docs.append(f"past_incident:{sf}")

        return CAPAResult(
            corrective=corrective,
            preventive=preventive,
            summary=summary,
            documents_used=list(dict.fromkeys(all_docs)),  # dedupe preserving order
        )

    def _parse_actions(
        self,
        raw_list: Any,
        expected_type: str,
    ) -> List[CAPAAction]:
        """Build CAPAAction objects from a raw list, applying defaults + validation."""
        if not isinstance(raw_list, list):
            return []

        actions: List[CAPAAction] = []
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            action_text = (raw.get("action") or "").strip()
            if not action_text:
                continue

            type_value = (raw.get("type") or expected_type).strip().lower()
            if type_value not in VALID_TYPES:
                type_value = expected_type

            priority = (raw.get("priority") or DEFAULT_PRIORITY).strip().lower()
            if priority not in VALID_PRIORITIES:
                priority = DEFAULT_PRIORITY

            rationale = (raw.get("rationale") or "").strip() or "Derived from root cause analysis"
            responsibility = (raw.get("responsibility") or "Reliability").strip()

            references = raw.get("references") or []
            if isinstance(references, str):
                references = [references]
            references = [r for r in references if isinstance(r, str) and r.strip()]

            try:
                actions.append(CAPAAction(
                    type=type_value,
                    action=action_text,
                    rationale=rationale,
                    responsibility=responsibility,
                    priority=priority,
                    target_date_hint=raw.get("target_date_hint"),
                    related_category=raw.get("related_category"),
                    references=references,
                ))
            except Exception as e:
                logger.warning(f"Could not build CAPAAction from LLM item ({expected_type}): {e}")
                continue

        return actions

    # ── Degraded path ───────────────────────────────────────────────────────

    def _degraded_result(self, reason: str, elapsed: float) -> ToolResult:
        """Return a single-action CAPA when there's no usable root cause."""
        placeholder = CAPAAction(
            type="corrective",
            action="Investigation incomplete — gather more failure data before implementing corrective actions",
            rationale=reason,
            responsibility="Reliability",
            priority="short_term",
            target_date_hint="Within 1 week",
            related_category=None,
            references=[],
        )
        result = CAPAResult(
            corrective=[placeholder],
            preventive=[],
            summary="CAPA could not be generated — investigation must complete first.",
            documents_used=[],
        )
        return ToolResult(
            tool_name="capa",
            success=True,
            result=result.model_dump(),
            execution_time_seconds=elapsed,
        )
