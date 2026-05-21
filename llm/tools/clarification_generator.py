"""
Clarification Generator — produces follow-up questions for the chatbot step.

Runs AFTER domain agents and BEFORE 5 Whys. Combines deterministic candidate
builders with an optional LLM ranker to produce exactly 3 ClarifyingQuestion
objects targeted at the gaps most likely to affect root cause accuracy.

Builders (priority order in the LLM ranker):
  1. discriminating  — competing hypotheses across domains (>=0.6 conf each)
  2. missing_metric  — sensor referenced by agents but no value in failure_text
  3. historical      — high-similarity past incident with divergent root cause
  4. domain_check    — top recommended_check from the strongest agent
"""

import re
import json
import logging
import inspect
from typing import List, Dict, Any, Optional

from models.tool_results import ClarifyingQuestion, DomainInsightsSummary

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3

# Numeric token: integer or decimal with at least one digit after the dot.
_NUM = r"\d+(?:\.\d+)?"

# ── Sensor classes the chatbot can ask about ────────────────────────────────
# Keyword → units + regex that detects an existing numeric value (so we don't
# re-ask). All regexes assume re.IGNORECASE.
SENSOR_SPECS: Dict[str, Dict[str, str]] = {
    "vibration":       {"units": "mm/s", "value_re": rf"{_NUM}\s*(mm/s|micron|g\b)"},
    "current":         {"units": "A",    "value_re": rf"{_NUM}\s*(amps?|ampere|A\b)"},
    "voltage":         {"units": "V",    "value_re": rf"{_NUM}\s*(volts?|V\b)"},
    "temperature":     {"units": "°C",   "value_re": rf"{_NUM}\s*(°c|deg\s*c|celsius)"},
    "pressure":        {"units": "bar",  "value_re": rf"{_NUM}\s*(bar|kpa|psi|mbar|mmhg)"},
    "flow":            {"units": "m³/h", "value_re": rf"{_NUM}\s*(m3/h|m³/h|l/min|l/s|gpm)"},
    "speed":           {"units": "rpm",  "value_re": rf"{_NUM}\s*(rpm|rev/min)"},
    "power":           {"units": "kW",   "value_re": rf"{_NUM}\s*(kw|mw)\b"},
    "torque":          {"units": "Nm",   "value_re": rf"{_NUM}\s*(nm|n\.m|ft-?lb)"},
    "oil temperature": {"units": "°C",   "value_re": rf"oil\s+temp.*?{_NUM}\s*°?c"},
}

_VALID_SOURCES = {"domain_check", "discriminating", "missing_metric", "historical"}
_VALID_FORMATS = {"number", "yes_no", "free_text"}


class ClarificationGenerator:
    """Generate up to MAX_QUESTIONS clarifying questions for the chatbot step."""

    def __init__(self, llm_adapter: Any):
        self.llm_adapter = llm_adapter

    async def generate(
        self,
        failure_text: str,
        domain_insights: DomainInsightsSummary,
        history_matches: List[dict],
        image_analysis: Optional[dict] = None,
    ) -> List[ClarifyingQuestion]:
        """Run the deterministic-pool → optional LLM ranker pipeline."""

        # 1. Build candidate pool
        candidates: List[ClarifyingQuestion] = []
        candidates.extend(self._from_competing_hypotheses(domain_insights))
        candidates.extend(self._from_missing_metrics(failure_text, domain_insights))
        candidates.extend(self._from_history_divergence(history_matches, domain_insights))
        candidates.extend(self._from_top_checks(domain_insights))

        # 2. Deduplicate
        candidates = self._dedupe(candidates)

        # 3. Guarantee at least one question
        if not candidates:
            candidates.append(self._generic_fallback())

        # 4. Renumber so the LLM ranker sees q1, q2, ...
        candidates = self._renumber(candidates)

        # 5. Short-circuit when pool already fits
        if len(candidates) <= MAX_QUESTIONS:
            logger.info(
                f"ClarificationGenerator: {len(candidates)} candidate(s); skipping LLM ranker"
            )
            return candidates

        # 6. LLM ranks + rephrases top MAX_QUESTIONS
        try:
            ranked = await self._llm_rank(
                candidates=candidates,
                failure_text=failure_text,
                domain_insights=domain_insights,
            )
            if ranked:
                return self._renumber(ranked[:MAX_QUESTIONS])
        except Exception as e:
            logger.warning(f"LLM ranker failed, using deterministic order: {e}")

        # 7. Fallback: take first MAX_QUESTIONS in deterministic order
        return candidates[:MAX_QUESTIONS]

    # ── Deterministic builders ──────────────────────────────────────────────

    def _from_competing_hypotheses(self, di: DomainInsightsSummary) -> List[ClarifyingQuestion]:
        """Two domains with conf >= 0.6 in different hypotheses → discriminator."""
        strong = [
            rc for rc in di.suspected_root_causes
            if rc.get("confidence", 0) >= 0.6 and rc.get("hypothesis")
        ]
        if len(strong) < 2:
            return []

        strong.sort(key=lambda r: r["confidence"], reverse=True)
        h1, h2 = strong[0], strong[1]
        if h1["domain"] == h2["domain"]:
            return []

        hyp1 = h1["hypothesis"][:140].rstrip(". ")
        hyp2 = h2["hypothesis"][:140].rstrip(". ")
        question = (
            f"{h1['domain'].title()} analysis suspects: \"{hyp1}\". "
            f"{h2['domain'].title()} analysis suspects: \"{hyp2}\". "
            f"Which pattern better matches your field observations, and what evidence supports it?"
        )
        return [ClarifyingQuestion(
            id="q_disc",
            question=question,
            rationale=f"Decides between {h1['domain']} and {h2['domain']} root cause paths",
            source="discriminating",
            expected_format="free_text",
            related_hypothesis=hyp1,
            related_domain=h1["domain"],
        )]

    def _from_missing_metrics(
        self,
        failure_text: str,
        di: DomainInsightsSummary,
    ) -> List[ClarifyingQuestion]:
        """Sensor referenced by an agent but no numeric value in failure_text."""
        text_lower = failure_text.lower()

        # Everything the agents wrote about
        agent_text_parts = list(di.recommended_checks)
        for analysis in di.domain_analyses:
            agent_text_parts.append(analysis.root_cause_hypothesis or "")
            for finding in analysis.findings:
                agent_text_parts.append(finding.observation or "")
                agent_text_parts.append(finding.area or "")
            agent_text_parts.extend(analysis.recommended_checks or [])
        agent_text = " ".join(agent_text_parts).lower()

        out: List[ClarifyingQuestion] = []
        for sensor, spec in SENSOR_SPECS.items():
            if sensor not in agent_text:
                continue
            if re.search(spec["value_re"], text_lower, flags=re.IGNORECASE):
                continue  # user already provided a value

            # Find which agent referenced it (best effort, first match wins)
            related_dom: Optional[str] = None
            related_hyp: Optional[str] = None
            for analysis in di.domain_analyses:
                blob = " ".join(
                    [f.observation for f in analysis.findings]
                    + analysis.recommended_checks
                    + [analysis.root_cause_hypothesis or ""]
                ).lower()
                if sensor in blob:
                    related_dom = analysis.domain
                    related_hyp = analysis.root_cause_hypothesis
                    break

            out.append(ClarifyingQuestion(
                id=f"q_metric_{sensor.replace(' ', '_')}",
                question=(
                    f"What was the latest {sensor} reading before or at the time of failure? "
                    f"(in {spec['units']} if available)"
                ),
                rationale=f"{sensor.title()} data validates the current hypothesis",
                source="missing_metric",
                expected_format="number",
                units=spec["units"],
                related_hypothesis=related_hyp,
                related_domain=related_dom,
            ))
        return out

    def _from_history_divergence(
        self,
        history: List[dict],
        di: DomainInsightsSummary,
    ) -> List[ClarifyingQuestion]:
        """High-similarity past incident with a root cause unlike the current top hypothesis."""
        if not history:
            return []
        top = history[0]
        if top.get("similarity_score", 0) < 0.80:
            return []

        hist_rc = (top.get("root_cause") or "").strip()
        if not hist_rc:
            return []

        # Word-overlap divergence check (cheap, no LLM)
        current_blob = " ".join(
            rc.get("hypothesis", "")
            for rc in di.suspected_root_causes
        ).lower()
        hist_words = set(re.findall(r"[a-z]{5,}", hist_rc.lower()))
        current_words = set(re.findall(r"[a-z]{5,}", current_blob))
        if hist_words and len(hist_words & current_words) / max(len(hist_words), 1) > 0.5:
            return []  # too similar — not divergent, no value in asking

        equipment = top.get("equipment", "this equipment")
        capa_hint = ""
        capa_list = top.get("capa") or []
        if capa_list:
            first_action = (capa_list[0].get("action") or "")[:80]
            if first_action:
                capa_hint = f" (past CAPA: '{first_action}')"

        return [ClarifyingQuestion(
            id="q_hist",
            question=(
                f"A past incident on {equipment} was traced to: \"{hist_rc[:200]}\". "
                f"Are there any signs of that same failure pattern in the current case"
                f"{capa_hint}?"
            ),
            rationale="High-similarity past incident with a different root cause",
            source="historical",
            expected_format="free_text",
        )]

    def _from_top_checks(self, di: DomainInsightsSummary) -> List[ClarifyingQuestion]:
        """Top recommended check from the highest-confidence agent."""
        if not di.domain_analyses:
            return []
        top_agent = max(di.domain_analyses, key=lambda a: a.confidence)
        if not top_agent.recommended_checks:
            return []
        check = top_agent.recommended_checks[0]
        return [ClarifyingQuestion(
            id="q_check",
            question=(
                f"Has this been verified: \"{check}\"? "
                f"If yes, what did you find?"
            ),
            rationale=f"Top verification check from the {top_agent.domain} expert",
            source="domain_check",
            expected_format="free_text",
            related_domain=top_agent.domain,
            related_hypothesis=top_agent.root_cause_hypothesis,
        )]

    def _generic_fallback(self) -> ClarifyingQuestion:
        """Used only if every builder returned empty (very rare)."""
        return ClarifyingQuestion(
            id="q_fb",
            question=(
                "Are there any additional observations, sensor readings, or operator notes "
                "from the time of failure that weren't included in the initial report?"
            ),
            rationale="Catch-all to surface missing context before root cause synthesis",
            source="domain_check",
            expected_format="free_text",
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _dedupe(self, candidates: List[ClarifyingQuestion]) -> List[ClarifyingQuestion]:
        seen = set()
        out = []
        for c in candidates:
            key = (c.source, c.question.strip().lower()[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _renumber(self, qs: List[ClarifyingQuestion]) -> List[ClarifyingQuestion]:
        for i, q in enumerate(qs, 1):
            q.id = f"q{i}"
        return qs

    # ── LLM ranker ──────────────────────────────────────────────────────────

    async def _llm_rank(
        self,
        candidates: List[ClarifyingQuestion],
        failure_text: str,
        domain_insights: DomainInsightsSummary,
    ) -> List[ClarifyingQuestion]:
        """Single LLM call: rank candidates by impact, rephrase the top 3."""

        cand_lines = []
        for c in candidates:
            cand_lines.append(
                f"  - id={c.id} source={c.source} domain={c.related_domain or '-'} "
                f"format={c.expected_format} units={c.units or '-'}\n"
                f"    question: {c.question}\n"
                f"    rationale: {c.rationale}"
            )
        cand_block = "\n".join(cand_lines)

        hyp_block = "\n".join(
            f"  - [{rc['domain'].upper()}] {rc.get('hypothesis', '')} "
            f"(conf {rc.get('confidence', 0) * 100:.0f}%)"
            for rc in domain_insights.suspected_root_causes
        ) or "  (none)"

        prompt = f"""You are helping a plant engineer prepare follow-up questions for a Root Cause Analysis chatbot.

FAILURE CONTEXT:
{failure_text[:1500]}

DOMAIN HYPOTHESES SO FAR:
{hyp_block}

CANDIDATE QUESTIONS (deterministically generated, may contain more than 3):
{cand_block}

Select EXACTLY 3 questions and rephrase them for clarity. PRIORITIES (highest first):
  1. discriminating  — decides between competing hypotheses
  2. missing_metric  — numerical reading the top hypothesis depends on
  3. historical      — past-incident pattern not yet ruled out
  4. domain_check    — verification of a recommended check

RULES:
  - Output EXACTLY 3 questions.
  - Each question must be concise and answerable in one short reply.
  - Keep 'source', 'expected_format', 'units', 'related_domain', 'related_hypothesis'
    from the original candidate UNLESS rephrasing changes its type.
  - Generate a fresh, scannable 'rationale' (max 12 words).
  - Do NOT invent questions that aren't in the candidate list.
  - Number ids as q1, q2, q3 in priority order.

Respond ONLY with valid JSON:
{{
  "questions": [
    {{
      "id": "q1",
      "question": "...",
      "rationale": "...",
      "source": "discriminating|missing_metric|historical|domain_check",
      "expected_format": "number|yes_no|free_text",
      "units": "mm/s" or null,
      "related_domain": "mechanical|electrical|process" or null,
      "related_hypothesis": "..." or null
    }}
  ]
}}
"""

        gen_sig = inspect.signature(self.llm_adapter.generate)
        call_kwargs: Dict[str, Any] = {}
        if "json_mode" in gen_sig.parameters:
            call_kwargs["json_mode"] = True
        if "max_tokens" in gen_sig.parameters:
            call_kwargs["max_tokens"] = 2048

        raw = await self.llm_adapter.generate(prompt, **call_kwargs)
        return self._parse_ranker_response(raw)

    def _parse_ranker_response(self, raw: str) -> List[ClarifyingQuestion]:
        """Parse JSON; return [] on any failure (caller falls back to candidates)."""
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            logger.warning("LLM ranker returned no JSON block")
            return []

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"LLM ranker JSON parse failed: {e}")
            return []

        out: List[ClarifyingQuestion] = []
        for q in (data.get("questions") or [])[:MAX_QUESTIONS]:
            if not isinstance(q, dict):
                continue
            text = (q.get("question") or "").strip()
            if not text:
                continue
            source = q.get("source", "domain_check")
            if source not in _VALID_SOURCES:
                source = "domain_check"
            fmt = q.get("expected_format", "free_text")
            if fmt not in _VALID_FORMATS:
                fmt = "free_text"
            try:
                out.append(ClarifyingQuestion(
                    id=q.get("id") or f"q{len(out) + 1}",
                    question=text,
                    rationale=(q.get("rationale") or "Follow-up question").strip(),
                    source=source,
                    expected_format=fmt,
                    units=q.get("units"),
                    related_hypothesis=q.get("related_hypothesis"),
                    related_domain=q.get("related_domain"),
                ))
            except Exception as e:
                logger.warning(f"Could not build ClarifyingQuestion from LLM output: {e}")
                continue

        return out
