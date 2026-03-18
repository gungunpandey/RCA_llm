"""
5 Whys Analysis Tool

Implements the 5 Whys RCA methodology with RAG-enhanced analysis.
"""

from typing import List, Dict, Any, Optional
import logging

from tools.base_tool import BaseTool
from models.tool_results import ToolResult, FiveWhysResult, WhyStep, DomainInsightsSummary
from tools.evidence_validator import (
    ConfidenceCalibrator,
    PlantFailureModeValidator,
    EvidenceGate,
    EvidenceType,
    CausalSufficiencyEvaluator
)

logger = logging.getLogger(__name__)


class FiveWhysTool(BaseTool):
    """
    5 Whys Root Cause Analysis Tool.
    
    Performs progressive "why" questioning to drill down to root cause,
    using RAG context from equipment manuals and troubleshooting guides.
    """
    
    def __init__(self, llm_adapter: Any, rag_manager: Any):
        """Initialize 5 Whys tool."""
        super().__init__(llm_adapter, rag_manager, tool_name="5_whys")
    
    async def analyze(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        domain_insights: Optional[DomainInsightsSummary] = None,
        **kwargs
    ) -> ToolResult:
        """
        Perform 5 Whys analysis with optional domain insights.
        
        Args:
            failure_description: Description of the failure
            equipment_name: Name of the equipment
            symptoms: List of observed symptoms
            domain_insights: Optional domain expert analysis results
            **kwargs: Additional parameters (status_callback, image_analysis, etc.)
            
        Returns:
            ToolResult containing FiveWhysResult
        """
        # Optional callback for live status updates (used by SSE endpoint)
        status_callback = kwargs.get('status_callback')
        image_analysis = kwargs.get('image_analysis')  # optional image analysis dict

        async def _send_status(msg: str):
            if status_callback:
                await status_callback(msg)

        async def _perform_analysis():
            # Step 1: Retrieve initial context from RAG
            self.logger.info(f"Starting 5 Whys analysis for {equipment_name}")
            
            # Check if domain insights are provided
            if domain_insights:
                self.logger.info("Using domain insights from expert analysis")
                await _send_status("Using domain expert analysis as foundation...")
            else:
                await _send_status("Searching OEM manuals for relevant context...")
            
            rag_docs = await self._retrieve_context(equipment_name, symptoms, top_k=5)
            rag_context = self._format_context(rag_docs)

            # Collect document sources
            doc_sources = [doc.source for doc in rag_docs if hasattr(doc, 'source')]
            
            if domain_insights:
                await _send_status(f"Retrieved {len(rag_docs)} OEM documents + domain expert insights")
            else:
                await _send_status(f"Retrieved {len(rag_docs)} relevant documents")

            # Step 2: Perform up to 5 progressive "why" iterations with causal sufficiency stop rule
            why_steps = []
            current_answer = failure_description
            stopped_early = False
            stop_reason = None

            for step_num in range(1, 6):
                self.logger.info(f"Generating Why #{step_num}")
                await _send_status(f"Analyzing Why #{step_num} of 5...")

                # Generate why question and answer
                why_result = await self._generate_why_step(
                    step_number=step_num,
                    equipment_name=equipment_name,
                    failure_description=failure_description,
                    symptoms=symptoms,
                    previous_answer=current_answer,
                    rag_context=rag_context,
                    domain_insights=domain_insights,
                    image_analysis=image_analysis if step_num == 1 else None,  # inject on step 1 only
                    is_final=False  # No longer force systemic escalation
                )

                why_steps.append(why_result)
                current_answer = why_result.answer
                await _send_status(f"Why #{step_num} complete — confidence {why_result.confidence*100:.0f}%")

                # Generate report-card summary (concise LLM-generated summary for the final report)
                await _send_status(f"Summarising Why #{step_num} for report...")
                why_result.answer_summary = await self._summarize_why_step(
                    step_number=step_num,
                    full_answer=why_result.answer
                )

                # Causal sufficiency check: after step 2+, evaluate if current cause explains all observations
                if step_num >= 2 and symptoms:
                    await _send_status(f"Evaluating causal sufficiency at Why #{step_num}...")
                    is_sufficient, unexplained, justification = CausalSufficiencyEvaluator.evaluate_sync(
                        llm_caller=self._call_llm,
                        current_cause=current_answer,
                        observations=symptoms,
                        rag_context=rag_context
                    )

                    if is_sufficient:
                        stopped_early = True
                        stop_reason = (
                            f"Causal sufficiency achieved at Why #{step_num}: "
                            f"cause explains all observed symptoms. {justification}"
                        )
                        self.logger.info(f"Stopping 5 Whys early: {stop_reason}")
                        await _send_status(f"Root cause isolated at Why #{step_num} — all symptoms explained")
                        break
                    else:
                        self.logger.info(
                            f"Why #{step_num} insufficient — unexplained: {unexplained}. Continuing..."
                        )

            # Step 3: Synthesize root cause from ALL why steps + domain insights
            await _send_status("Synthesizing final root cause from all findings...")
            root_cause, root_cause_confidence = await self._synthesize_root_cause(
                equipment_name=equipment_name,
                failure_description=failure_description,
                why_steps=why_steps,
                domain_insights=domain_insights,
                rag_context=rag_context
            )

            # Step 4: Generate corrective actions (COMMENTED OUT - not needed for now)
            # corrective_actions = await self._generate_corrective_actions(...)
            corrective_actions = []  # Empty for now

            # Build result
            result = FiveWhysResult(
                why_steps=why_steps,
                root_cause=root_cause,
                root_cause_confidence=root_cause_confidence,
                corrective_actions=corrective_actions,
                documents_used=list(set(doc_sources)),  # Remove duplicates, keep unique only
                stopped_early=stopped_early,
                stop_reason=stop_reason
            )

            return result.model_dump()

        # Execute with timing and error handling
        return await self._execute_with_timing(_perform_analysis)
    
    async def _synthesize_root_cause(
        self,
        equipment_name: str,
        failure_description: str,
        why_steps: list,
        domain_insights,
        rag_context: str
    ) -> tuple:
        """
        Synthesize a final root cause statement from all why steps and domain insights.

        This produces a DISTINCT, concise root cause — not a copy of any individual why step.
        The root cause should be the deepest, most fundamental cause that explains ALL symptoms.

        Returns:
            Tuple of (root_cause_str, confidence_float)
        """
        import re

        # Build the causal chain summary
        chain_lines = []
        for step in why_steps:
            chain_lines.append(f"  Why #{step.step_number}: {step.answer}")
        causal_chain = "\n".join(chain_lines)

        # Build domain hypotheses section
        domain_section = ""
        if domain_insights and domain_insights.suspected_root_causes:
            hyps = []
            for rc in domain_insights.suspected_root_causes:
                hyps.append(
                    f"  [{rc['domain'].upper()} agent] {rc['hypothesis']} "
                    f"(confidence {rc['confidence']*100:.0f}%)"
                )
            domain_section = "\nDOMAIN EXPERT HYPOTHESES:\n" + "\n".join(hyps)

        prompt = f"""You are the final reviewer of a 5 Whys Root Cause Analysis for an industrial equipment failure.

Equipment: {equipment_name}
Original Failure: {failure_description}
{domain_section}

COMPLETE CAUSAL CHAIN (5 Whys):
{causal_chain}

Your task: Synthesize ONE concise root cause statement that:
1. Is the deepest, most fundamental cause identified in the causal chain above
2. Is DIFFERENT from any single why step — it integrates the full chain into a single, clear statement
3. Explains WHY the failure occurred at its root, not just what happened
4. Is 1-3 sentences maximum — precise and actionable, not verbose
5. Is consistent with the domain expert hypotheses where relevant
6. Does NOT repeat the failure description or the symptom — it answers the fundamental "why"
7. Does NOT use markdown bold/italic formatting
8. Focuses on the equipment-level or process-level root cause, NOT IT/API/software failures

Respond in EXACTLY this format:
ROOT_CAUSE: [1-3 sentences — the synthesized root cause]
CONFIDENCE: [percentage, e.g., 82]
"""

        try:
            response = self._call_llm(prompt)

            # Parse ROOT_CAUSE
            rc_match = re.search(
                r'ROOT_CAUSE:\s*(.+?)(?=\nCONFIDENCE:|\Z)',
                response, re.DOTALL | re.IGNORECASE
            )
            root_cause = rc_match.group(1).strip() if rc_match else why_steps[-1].answer

            # Parse confidence
            conf_match = re.search(r'CONFIDENCE:\s*(\d+)', response, re.IGNORECASE)
            raw_conf = float(conf_match.group(1)) / 100.0 if conf_match else 0.75

            # Cap at max confidence seen across why steps
            max_step_conf = max((s.confidence for s in why_steps), default=0.75)
            confidence = min(raw_conf, max_step_conf + 0.05)  # allow slight boost for synthesis
            confidence = round(max(0.0, min(1.0, confidence)), 3)

            self.logger.info(f"Root cause synthesized: {root_cause[:120]}... (confidence {confidence:.0%})")
            return root_cause, confidence

        except Exception as e:
            self.logger.error(f"Root cause synthesis failed: {e}")
            # Graceful fallback: use last why step
            return why_steps[-1].answer, why_steps[-1].confidence

    async def _generate_why_step(
        self,
        step_number: int,
        equipment_name: str,
        failure_description: str,
        symptoms: List[str],
        previous_answer: str,
        rag_context: str,
        domain_insights: Optional[DomainInsightsSummary] = None,
        image_analysis: Optional[dict] = None,
        is_final: bool = False
    ) -> WhyStep:
        """
        Generate a single "why" step.
        
        Args:
            step_number: Current step number (1-5)
            equipment_name: Equipment name
            failure_description: Original failure description
            symptoms: Observed symptoms
            previous_answer: Answer from previous why (or failure description for step 1)
            rag_context: RAG context documents
            domain_insights: Optional domain expert analysis results
            image_analysis: Optional image analysis dict (injected on step 1)
            is_final: Whether this is the final step (step 5)
            
        Returns:
            WhyStep with question, answer, and supporting documents
        """
        # Build the question text ourselves (don't rely on LLM to generate it)
        if step_number == 1:
            why_question = f"Why did the {equipment_name} fail?"
        else:
            # Condense previous answer into a short "why" question
            prev_short = previous_answer.split('.')[0].strip()[:120]
            why_question = f"Why did {prev_short.rstrip('.')}?"

        # Build domain insights section if available
        # Build image analysis section if available (step 1 only)
        image_section = ""
        if image_analysis:
            symptoms_str = ", ".join(image_analysis.get("visual_symptoms", []))
            causes_str = ", ".join(image_analysis.get("possible_causes", []))
            image_section = (
                f"\n\nIMAGE ANALYSIS (Visual Inspection of {image_analysis.get('component', 'Unknown')}):"
                f"\n  Component: {image_analysis.get('component', 'Unknown')}"
                f"\n  Damage Type: {image_analysis.get('damage_type', 'Unknown')}"
                f"\n  Severity: {image_analysis.get('severity', 'Unknown')}"
                f"\n  Visual Symptoms: {symptoms_str}"
                f"\n  Possible Causes: {causes_str}"
                f"\n  Observation: {image_analysis.get('combined_observation', '')}"
                f"\n"
            )

        domain_section = ""
        if domain_insights and domain_insights.key_findings:
            domain_section = f"\n\nDOMAIN EXPERT ANALYSIS (Pre-Analysis):\nThe following domain experts have already analyzed this failure:\n\n{self._format_domain_insights(domain_insights)}\n"

                # Build prompt for this why step
        if step_number == 1:
            prompt = f"""You are performing a 5 Whys Root Cause Analysis for industrial equipment failure.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}
{domain_section}{image_section}
Relevant Technical Documentation:
{rag_context}

This is Why #1 of the 5 Whys analysis.

RULES:
1. NEVER use HTTP/API errors (503, 404, 500, etc.) as plant failure modes
2. Plant signal failures are: "Bad Quality", "Comm Fail", "Signal Unhealthy", "Input Forced", "Loss of Signal"
3. Back every claim with evidence (sensor data, OEM manual rules, or documented procedures)
4. If inferring without direct evidence, say "Based on inference"
5. Keep your answer CONCISE: 2-4 sentences. State the cause and the evidence. No lengthy explanations.
6. Do NOT use markdown formatting (no ** or * for bold/italic)
7. Do NOT escalate to governance, maintenance policy, or design failures unless there is direct evidence (alarm logs, maintenance records, design specifications) that these are causal. The goal is the LOWEST sufficient explanation, not the deepest.
8. CAUSAL BOUNDARY: Identify the first equipment whose intended function failed using alarms and observations. Do NOT move upstream beyond that equipment failure unless a measurement or alarm explicitly confirms upstream failure. Root cause = first functional failure, NOT the physical origin of material behavior.

Question: {why_question}

Respond in EXACTLY this format:
ANSWER: [2-4 concise sentences with evidence]
SUPPORTING_DOCUMENTS: [Only full document names, e.g., "Rotary Kiln_Hongda_OEM Manual, ID&HR Fan_TLT_OEM Manual"]
CONFIDENCE: [percentage, e.g., 85]
"""
        else:
            prompt = f"""You are performing a 5 Whys Root Cause Analysis for industrial equipment failure.

Equipment: {equipment_name}
Original Failure: {failure_description}

Relevant Technical Documentation:
{rag_context}

This is Why #{step_number} of the 5 Whys analysis.

Previous Answer (Why #{step_number-1}): {previous_answer}

RULES:
1. NEVER use HTTP/API errors (503, 404, 500, etc.) as plant failure modes
2. Plant signal failures are: "Bad Quality", "Comm Fail", "Signal Unhealthy", "Input Forced", "Loss of Signal"
3. Back every claim with evidence (sensor data, OEM manual rules, or documented procedures)
4. If inferring without direct evidence, say "Based on inference"
5. Keep your answer CONCISE: 2-4 sentences. State the cause and evidence only.
6. Do NOT use markdown formatting (no ** or * for bold/italic)
7. Do NOT repeat document names inside the ANSWER. Put them only in SUPPORTING_DOCUMENTS.
8. Only escalate to a deeper root cause if the current cause cannot explain at least one observed symptom. If all symptoms are explained, declare the current cause as the root cause. Do NOT infer governance, maintenance, or design failures without direct evidence such as alarms, logs, or sensor data.
9. CAUSAL BOUNDARY: Identify the first equipment whose intended function failed using alarms and observations. Do NOT move upstream beyond that equipment failure unless a measurement or alarm explicitly confirms upstream failure. Root cause = first functional failure, NOT the physical origin of material behavior.

Question: {why_question}

Respond in EXACTLY this format:
ANSWER: [2-4 concise sentences with evidence]
SUPPORTING_DOCUMENTS: [Only full document names, comma-separated]
CONFIDENCE: [percentage, e.g., 85]
"""
        
        # Call LLM
        try:
            response = self._call_llm(prompt)

            # Parse response (question is built above, not parsed from LLM)
            _, answer, docs, confidence = self._parse_why_response(response, step_number)
            question = why_question
            
            # VALIDATION 1: Check for AI errors leaked into plant RCA
            is_valid, error_msg = PlantFailureModeValidator.validate_failure_mode(answer)
            if not is_valid:
                self.logger.warning(error_msg)
                # Sanitize the answer
                answer = PlantFailureModeValidator.sanitize_ai_errors(answer)
                self.logger.info(f"Sanitized answer: {answer[:100]}...")
            
            # VALIDATION 2: Assess evidence type
            evidence_type = ConfidenceCalibrator.assess_evidence_from_answer(answer, docs)
            
            # VALIDATION 3: Calibrate confidence based on evidence
            has_oem_rule = any(
                keyword in answer.lower() 
                for keyword in ["manual states", "manual specifies", "according to table"]
            )
            
            calibrated_confidence, justification = ConfidenceCalibrator.calibrate_confidence(
                raw_confidence=confidence,
                evidence_type=evidence_type,
                has_oem_rule=has_oem_rule
            )
            
            # Log calibration
            if calibrated_confidence < confidence:
                self.logger.info(
                    f"Confidence calibrated: {confidence:.0%} → {calibrated_confidence:.0%} "
                    f"({justification})"
                )
            
            return WhyStep(
                step_number=step_number,
                question=question,
                answer=answer,
                supporting_documents=docs,
                confidence=calibrated_confidence  # Use calibrated confidence
            )
            
        except Exception as e:
            self.logger.error(f"Error generating why step {step_number}: {e}")
            return WhyStep(
                step_number=step_number,
                question=why_question,
                answer=f"Error: {str(e)}",
                supporting_documents=[],
                confidence=0.0
            )
    
    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM with the given prompt.

        Returns:
            LLM response text
        """
        # Preferred: adapter exposes a direct sync call (OpenRouter and future adapters)
        if hasattr(self.llm_adapter, "generate_sync"):
            return self.llm_adapter.generate_sync(prompt)
        # Gemini-specific path: client.models.generate_content
        if (
            hasattr(self.llm_adapter, "client")
            and hasattr(self.llm_adapter.client, "models")
            and hasattr(self.llm_adapter.client.models, "generate_content")
        ):
            response = self.llm_adapter.client.models.generate_content(
                model=self.llm_adapter.model_name,
                contents=prompt,
            )
            return response.text
        # Last-resort fallback
        result = self.llm_adapter.analyze_failure(
            failure_description=prompt,
            equipment_name="",
            symptoms=[],
            use_rag=False,
        )
        return result.get("raw_response", "")
    
    def _parse_why_response(self, response: str, step_number: int) -> tuple:
        """
        Parse LLM response to extract question, answer, documents, and confidence.
        
        Args:
            response: Raw LLM response
            step_number: Current step number
            
        Returns:
            Tuple of (question, answer, documents, confidence)
        """
        import re

        # Extract question (kept for backward compat, caller overrides it)
        question_match = re.search(r'QUESTION:\s*(.+?)(?=\nANSWER:|\n\n)', response, re.DOTALL | re.IGNORECASE)
        question = question_match.group(1).strip() if question_match else f"Why (step {step_number})?"

        # Extract answer — look for ANSWER: label, then capture until SUPPORTING_DOCUMENTS or CONFIDENCE
        answer_match = re.search(
            r'ANSWER:\s*(.+?)(?=\nSUPPORTING[_ ]DOCUMENTS:|\nCONFIDENCE:|\Z)',
            response, re.DOTALL | re.IGNORECASE
        )
        answer = answer_match.group(1).strip() if answer_match else response[:500]

        # Extract supporting documents
        docs_match = re.search(
            r'SUPPORTING[_ ]DOCUMENTS:\s*(.+?)(?=\nCONFIDENCE:|\Z)',
            response, re.DOTALL | re.IGNORECASE
        )
        docs_text = docs_match.group(1).strip() if docs_match else ""
        docs = [d.strip() for d in docs_text.split(',') if d.strip()]

        # Extract confidence
        conf_match = re.search(r'CONFIDENCE:\s*(\d+)', response, re.IGNORECASE)
        confidence = float(conf_match.group(1)) / 100.0 if conf_match else 0.7

        return question, answer, docs, confidence
    
    async def _generate_corrective_actions(
        self,
        equipment_name: str,
        root_cause: str,
        rag_context: str
    ) -> List[str]:
        """
        Generate corrective actions based on root cause.
        
        Args:
            equipment_name: Equipment name
            root_cause: Identified root cause
            rag_context: RAG context documents
            
        Returns:
            List of corrective actions
        """
        prompt = f"""You are an expert in industrial equipment maintenance and failure prevention.

Equipment: {equipment_name}
Root Cause Identified: {root_cause}

Relevant Technical Documentation:
{rag_context}

Task: Based on the root cause and the technical documentation, provide 3-5 specific, actionable corrective actions to:
1. Fix the immediate problem
2. Prevent recurrence
3. Improve monitoring/detection

Format your response as a numbered list:
1. [Action 1]
2. [Action 2]
...

Be specific and reference procedures from the documentation where applicable.
"""
        
        try:
            response = self._call_llm(prompt)
            
            # Parse numbered list
            import re
            actions = re.findall(r'^\d+\.\s*(.+)$', response, re.MULTILINE)
            
            return actions if actions else [response.strip()]
            
        except Exception as e:
            self.logger.error(f"Error generating corrective actions: {e}")
            return [f"Error generating actions: {str(e)}"]

    def _format_domain_insights(self, insights):
        """Format domain insights for LLM prompt."""
        sections = []
        sections.append("KEY FINDINGS FROM DOMAIN EXPERTS:")
        for finding in insights.key_findings[:5]:
            sections.append(f"  • {finding}")
        sections.append("\nSUSPECTED ROOT CAUSES:")
        for rc in insights.suspected_root_causes:
            sections.append(f"  • [{rc['domain'].upper()}] {rc['hypothesis']} (Confidence: {rc['confidence']*100:.0f}%)")
        sections.append("\nRECOMMENDED VERIFICATION CHECKS:")
        for check in insights.recommended_checks[:5]:
            sections.append(f"  • {check}")
        return "\n".join(sections)

    async def _summarize_why_step(self, step_number: int, full_answer: str) -> str:
        """
        Call the LLM (async) to produce a concise 2-sentence summary of a Why step answer.
        This summary is used in the final RCA report card; the full answer is
        preserved separately for the detailed reasoning panel.

        Returns:
            A 2-sentence summary string, or the original full_answer if summarization fails.
        """
        import re

        prompt = f"""You are summarising one step from a 5 Whys Root Cause Analysis for a formal industrial equipment failure report.

The following is the FULL detailed analysis for Why #{step_number}:

\"\"\"
{full_answer}
\"\"\"

Your task: Rewrite this as a concise 2-sentence summary for the report card that a plant manager will read.

Strict rules:
1. Write EXACTLY 2 complete sentences.
2. Sentence 1: State the core causal finding (what caused what and why).
3. Sentence 2: State the key evidence or mechanism that confirms this.
4. Do NOT use markdown, bullet points, asterisks, numbers, or bold/italic formatting.
5. Do NOT start with phrases like "In summary", "The answer is", "This step", etc.
6. Preserve critical technical terms and any measurement values.
7. Write in plain, professional English — clear to a non-specialist.

Respond with ONLY the 2-sentence summary. Nothing else."""

        try:
            # Use async generate() — never block the event loop with a sync call
            summary = await self.llm_adapter.generate(prompt)
            if summary:
                summary = summary.strip()
                # Strip any accidental markdown the LLM may have added
                summary = re.sub(r'^["\u2018\u2019\u201c\u201d]|["\u2018\u2019\u201c\u201d]$', '', summary)
                summary = re.sub(r'\*{1,2}([^*]+?)\*{1,2}', r'\1', summary)
                summary = summary.strip()
                # Only reject if obviously too short (LLM returned garbage)
                if len(summary) >= 20:
                    self.logger.info(f"Why #{step_number} summary generated ({len(summary)} chars)")
                    return summary
            self.logger.warning(f"Why #{step_number} summary too short or empty, using full answer")
            return full_answer
        except Exception as e:
            self.logger.warning(f"Why #{step_number} summary failed: {e} — using full answer")
            return full_answer
