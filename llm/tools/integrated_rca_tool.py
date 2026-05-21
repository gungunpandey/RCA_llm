"""
Integrated RCA Tool — split into two phases for the chatbot pipeline.

Phase 1: run_prepare()
    Historical lookup → domain agents (+ image analysis in parallel)
    → clarification question generation. Returns all state needed to resume
    after the user answers the chatbot.

Phase 2: run_finalize(session_fields, clarifications)
    Appends user clarifications to failure_text → 5 Whys → Fishbone →
    returns the final comprehensive result (same shape the old analyze()
    produced).

The original analyze() method is kept as a convenience wrapper that runs
both phases back-to-back with empty clarifications — useful for tests and
any programmatic caller that doesn't need the chatbot step.
"""

from typing import List, Dict, Any, Optional
import asyncio
import logging

from tools.base_tool import BaseTool
from models.tool_results import (
    ToolResult,
    DomainInsightsSummary,
    DomainAnalysisResult,
    ClarifyingQuestion,
    ClarificationAnswer,
)
from domain_agents import MechanicalAgent, ElectricalAgent, ProcessAgent
from tools.five_whys_tool import FiveWhysTool
from tools.fishbone_tool import FishboneTool
from tools.capa_tool import CAPATool
from tools.clarification_generator import ClarificationGenerator
from tools import history_matcher

logger = logging.getLogger(__name__)


class IntegratedRCATool(BaseTool):
    """
    Two-phase integrated RCA pipeline.

    Phase 1 (run_prepare): history → domain agents → image analysis →
                           clarification questions
    Phase 2 (run_finalize): apply user clarifications → 5 Whys → Fishbone
    """

    def __init__(self, llm_adapter: Any, rag_manager: Any):
        super().__init__(llm_adapter, rag_manager, tool_name="integrated_rca")

        # Domain agents
        self.mechanical_agent = MechanicalAgent(llm_adapter, rag_manager)
        self.electrical_agent = ElectricalAgent(llm_adapter, rag_manager)
        self.process_agent = ProcessAgent(llm_adapter, rag_manager)

        # Downstream tools
        self.five_whys = FiveWhysTool(llm_adapter, rag_manager)
        self.fishbone = FishboneTool(llm_adapter, rag_manager)
        self.capa = CAPATool(llm_adapter, rag_manager)

        # Clarification chatbot
        self.clarification_generator = ClarificationGenerator(llm_adapter)

        # Agent routing keywords
        self.agent_routing = {
            "mechanical_agent": [
                "bearing", "vibration", "mechanical", "wear", "alignment",
                "shaft", "coupling", "lubrication", "fatigue", "corrosion",
                "gearbox", "impeller", "belt", "chain", "girth gear"
            ],
            "electrical_agent": [
                "motor", "electrical", "power", "current", "voltage",
                "interlock", "relay", "trip", "overcurrent", "VFD",
                "winding", "insulation", "contactor", "circuit", "fuse"
            ],
            "process_agent": [
                "temperature", "pressure", "flow", "process", "combustion",
                "emission", "feed", "composition", "setpoint", "heat",
                "flame", "damper", "draft", "kiln speed"
            ]
        }

    # ── Phase 1: prepare ────────────────────────────────────────────────────

    async def run_prepare(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs,
    ) -> ToolResult:
        """
        Phase 1 — history + domain agents + image + clarification questions.

        Returns:
            ToolResult whose .result is a dict carrying:
              failure_text, equipment_name, symptoms, domain_insights,
              history_context, history_matches, image_analysis,
              selected_agents, questions
        """
        status_callback = kwargs.get("status_callback")
        image_path = kwargs.get("image_path")
        image_desc = kwargs.get("image_desc")

        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)

        async def _analyze_image_async():
            if not image_path:
                return None
            try:
                from tools.image_analysis_tool import analyze_image
                await _send_status("📷 Analyzing uploaded equipment image...")
                result = await asyncio.to_thread(analyze_image, image_path, image_desc)
                await _send_status(
                    f"✓ Image analyzed — {result.get('component', '?')}: "
                    f"{result.get('damage_type', '?')} ({result.get('severity', '?')})"
                )
                return result
            except Exception as e:
                logger.error(f"Image analysis failed: {e}", exc_info=True)
                await _send_status(f"⚠ Image analysis failed: {e}")
                return None

        async def _perform():
            # 0. Historical lookup
            await _send_status("📜 Searching historical incident database...")
            history_matches, history_context = await history_matcher.find_and_format(
                equipment_name=equipment_name,
                problem_description=failure_description,
            )
            if history_matches:
                await _send_status(f"✓ Found {len(history_matches)} similar past incident(s)")
                if status_callback:
                    await status_callback(("__HISTORY_MATCHES__", history_matches))
            else:
                await _send_status("No similar historical incidents found")

            # 1. Route to domain agents
            await _send_status("🔍 Routing to domain experts...")
            selected_agents = self._route_agents(failure_description, symptoms)
            await _send_status(
                "✓ Selected experts: "
                + ", ".join(a.replace("_agent", "").title() for a in selected_agents)
            )

            # 2. Domain agents + image analysis in parallel
            await _send_status("🔬 Domain experts + Image analysis running in parallel...")
            domain_results, image_analysis = await asyncio.gather(
                self._run_domain_agents(
                    selected_agents,
                    failure_description,
                    equipment_name,
                    symptoms,
                    status_callback,
                ),
                _analyze_image_async(),
            )

            # 3. Aggregate domain insights
            await _send_status("📊 Aggregating domain expert insights...")
            domain_insights = self._aggregate_domain_insights(domain_results)
            await _send_status(
                f"✓ Domain analysis complete — {len(domain_insights.key_findings)} "
                f"key findings (avg confidence: {domain_insights.overall_confidence*100:.0f}%)"
            )

            if status_callback:
                await status_callback(
                    ("__DOMAIN_INSIGHTS__", domain_insights.model_dump(mode="json"))
                )
            if image_analysis and status_callback:
                await status_callback(("__IMAGE_ANALYSIS__", image_analysis))

            # 4. Generate clarifying questions
            await _send_status("💬 Preparing follow-up questions for the chatbot...")
            questions = await self.clarification_generator.generate(
                failure_text=failure_description,
                domain_insights=domain_insights,
                history_matches=history_matches,
                image_analysis=image_analysis,
            )
            await _send_status(f"✓ Prepared {len(questions)} clarifying question(s)")

            if status_callback:
                await status_callback(
                    ("__CLARIFYING_QUESTIONS__", [q.model_dump() for q in questions])
                )

            return {
                "failure_text": failure_description,
                "equipment_name": equipment_name,
                "symptoms": symptoms,
                "domain_insights": domain_insights,      # Pydantic object, kept as-is
                "history_context": history_context,
                "history_matches": history_matches,
                "image_analysis": image_analysis,
                "selected_agents": selected_agents,
                "questions": questions,                  # List[ClarifyingQuestion]
            }

        return await self._execute_with_timing(_perform)

    # ── Phase 2: finalize ───────────────────────────────────────────────────

    async def run_finalize(
        self,
        equipment_name: str,
        failure_text: str,
        symptoms: List[str],
        domain_insights: DomainInsightsSummary,
        history_context: str,
        image_analysis: Optional[dict],
        selected_agents: List[str],
        clarifications: List[ClarificationAnswer],
        history_matches: Optional[List[dict]] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Phase 2 — apply clarifications, then run 5 Whys → Fishbone → CAPA.

        `history_matches` is the raw output from history_matcher (top similar
        past incidents with their CAPAs). Used to ground the CAPA generation
        in actions that were actually applied to similar failures.

        Returns the same final-result shape as the legacy analyze() method,
        plus a `capa_actions` field.
        """
        status_callback = kwargs.get("status_callback")

        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)

        async def _perform():
            # Append clarifications into a structured block on failure_text
            enriched_failure_text = self._append_clarifications(failure_text, clarifications)
            if clarifications:
                await _send_status(
                    f"✓ Applied {len(clarifications)} user clarification(s) to the analysis"
                )

            # 5 Whys
            await _send_status("🎯 Starting main root cause analysis (5 Whys)...")
            await _send_status("Using domain expert insights as foundation...")
            five_whys_result = await self.five_whys.analyze(
                failure_description=enriched_failure_text,
                equipment_name=equipment_name,
                symptoms=symptoms,
                domain_insights=domain_insights,
                image_analysis=image_analysis,
                historical_context=history_context,
                status_callback=status_callback,
            )

            # Fishbone using confirmed root cause
            root_cause = five_whys_result.result.get("root_cause", enriched_failure_text)
            fishbone_result = await self.fishbone.analyze(
                failure_description=enriched_failure_text,
                equipment_name=equipment_name,
                symptoms=symptoms,
                root_cause=root_cause,
                domain_insights=domain_insights,
                status_callback=status_callback,
            )

            fishbone_data = None
            if fishbone_result.success:
                fishbone_data = fishbone_result.result
            else:
                logger.error(f"Fishbone analysis failed: {fishbone_result.error}")

            # CAPA — corrective + preventive plan from the confirmed root cause
            await _send_status("🛠 Generating corrective + preventive action plan...")
            capa_result = await self.capa.analyze(
                failure_description=enriched_failure_text,
                equipment_name=equipment_name,
                symptoms=symptoms,
                root_cause=root_cause,
                why_steps=five_whys_result.result.get("why_steps", []),
                fishbone_result=fishbone_data,
                domain_insights=domain_insights,
                historical_capas=history_matches or [],
                user_clarifications=[c.model_dump() for c in clarifications],
                status_callback=status_callback,
            )

            capa_data: Optional[Dict[str, Any]] = None
            if capa_result.success:
                capa_data = capa_result.result
                # Stream CAPA to the frontend as an early event so cards can
                # render before the final 'result' event.
                if status_callback:
                    await status_callback(("__CAPA__", capa_data))
                # Backfill the legacy FiveWhysResult.corrective_actions field
                # so older callers (tests, manual UI) still find a list there.
                try:
                    five_whys_result.result["corrective_actions"] = [
                        a["action"] for a in capa_data.get("corrective", []) if a.get("action")
                    ]
                except Exception as e:
                    logger.warning(f"Could not backfill corrective_actions: {e}")
            else:
                logger.error(f"CAPA generation failed: {capa_result.error}")

            method = (
                "domain_enhanced_5_whys_fishbone_capa_with_clarifications"
                if clarifications
                else "domain_enhanced_5_whys_fishbone_capa"
            )

            result_dict: Dict[str, Any] = {
                "domain_insights": domain_insights.model_dump(),
                "five_whys_analysis": five_whys_result.result,
                "fishbone_analysis": fishbone_data,
                "capa_actions": capa_data,
                "final_root_cause": root_cause,
                "final_confidence": five_whys_result.result["root_cause_confidence"],
                "analysis_method": method,
                "agents_used": selected_agents,
                "user_clarifications": [c.model_dump() for c in clarifications],
            }
            if image_analysis:
                result_dict["image_analysis"] = image_analysis
            return result_dict

        return await self._execute_with_timing(_perform)

    # ── Legacy convenience wrapper ──────────────────────────────────────────

    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs,
    ) -> ToolResult:
        """
        Run both phases back-to-back with NO user clarifications.

        Kept for: legacy callers, tests, and any programmatic use that
        bypasses the chatbot. The HTTP API uses run_prepare and run_finalize
        directly so that the chatbot step is mandatory.
        """
        prep = await self.run_prepare(
            failure_description=failure_description,
            equipment_name=equipment_name,
            symptoms=symptoms,
            **kwargs,
        )
        if not prep.success:
            return prep

        p = prep.result
        return await self.run_finalize(
            equipment_name=equipment_name,
            failure_text=p["failure_text"],
            symptoms=symptoms,
            domain_insights=p["domain_insights"],
            history_context=p["history_context"],
            image_analysis=p["image_analysis"],
            selected_agents=p["selected_agents"],
            clarifications=[],
            history_matches=p.get("history_matches") or [],
            **kwargs,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _append_clarifications(
        self,
        failure_text: str,
        clarifications: List[ClarificationAnswer],
    ) -> str:
        """Append a structured USER CLARIFICATIONS block to failure_text."""
        if not clarifications:
            return failure_text

        lines = ["", "━━━ USER CLARIFICATIONS (Round 1) ━━━"]
        for c in clarifications:
            lines.append(f"Q: {c.question}")
            lines.append(f"A: {c.answer}")
            lines.append("")
        lines.append("━━━ END USER CLARIFICATIONS ━━━")
        return failure_text + "\n" + "\n".join(lines)

    def _route_agents(self, failure_description: str, symptoms: List[str]) -> List[str]:
        text = f"{failure_description} {' '.join(symptoms)}".lower()
        selected = [
            name for name, keywords in self.agent_routing.items()
            if any(kw in text for kw in keywords)
        ]
        if not selected:
            selected.append("mechanical_agent")
        return selected

    async def _run_domain_agents(
        self,
        agent_names: List[str],
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        status_callback,
    ) -> List[ToolResult]:
        async def _run_one(agent_name: str):
            agent = getattr(self, agent_name)
            return await agent.analyze(
                failure_description=failure_description,
                equipment_name=equipment_name,
                symptoms=symptoms,
                status_callback=status_callback,
            )

        tasks = [_run_one(name) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = [r for r in results if isinstance(r, ToolResult) and r.success]
        if not valid_results:
            self.logger.warning("All domain agents failed, will fall back to RAG-only 5 Whys")
        return valid_results

    def _aggregate_domain_insights(self, results: List[ToolResult]) -> DomainInsightsSummary:
        if not results:
            return DomainInsightsSummary(
                agents_analyzed=[],
                domain_analyses=[],
                key_findings=["No domain analysis available - using RAG-only mode"],
                suspected_root_causes=[],
                recommended_checks=[],
                documents_used=[],
                overall_confidence=0.5,
            )

        agents_analyzed: List[str] = []
        domain_analyses: List[DomainAnalysisResult] = []
        all_findings: List[str] = []
        suspected_causes: List[Dict[str, Any]] = []
        all_checks: List[str] = []
        all_docs: List[str] = []
        confidences: List[float] = []

        for result in results:
            analysis = result.result
            agents_analyzed.append(analysis["domain"])
            domain_analyses.append(DomainAnalysisResult(**analysis))

            for finding in analysis["findings"]:
                if finding["severity"] == "critical":
                    all_findings.append(
                        f"[{analysis['domain'].upper()}] {finding['observation']} (CRITICAL)"
                    )
                elif finding["severity"] == "warning" and len(all_findings) < 10:
                    all_findings.append(
                        f"[{analysis['domain'].upper()}] {finding['observation']} (WARNING)"
                    )

            suspected_causes.append({
                "domain": analysis["domain"],
                "hypothesis": analysis["root_cause_hypothesis"],
                "confidence": analysis["confidence"],
            })

            all_checks.extend(analysis.get("recommended_checks", []))
            all_docs.extend(analysis.get("documents_used", []))
            confidences.append(analysis["confidence"])

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        return DomainInsightsSummary(
            agents_analyzed=agents_analyzed,
            domain_analyses=domain_analyses,
            key_findings=all_findings[:10],
            suspected_root_causes=suspected_causes,
            recommended_checks=list(set(all_checks))[:10],
            documents_used=list(set(all_docs)),
            overall_confidence=overall_confidence,
        )
