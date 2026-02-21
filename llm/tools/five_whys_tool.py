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
            **kwargs: Additional parameters (status_callback, etc.)
            
        Returns:
            ToolResult containing FiveWhysResult
        """
        # Optional callback for live status updates (used by SSE endpoint)
        status_callback = kwargs.get('status_callback')

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
                    is_final=False  # No longer force systemic escalation
                )

                why_steps.append(why_result)
                current_answer = why_result.answer
                await _send_status(f"Why #{step_num} complete — confidence {why_result.confidence*100:.0f}%")

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

            # Step 3: Extract root cause from final why
            await _send_status("Compiling root cause and building report...")
            root_cause = why_steps[-1].answer
            root_cause_confidence = why_steps[-1].confidence
            
            # Step 4: Generate corrective actions (COMMENTED OUT - not needed for now)
            # corrective_actions = await self._generate_corrective_actions(
            #     equipment_name=equipment_name,
            #     root_cause=root_cause,
            #     rag_context=rag_context
            # )
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
    
    async def _generate_why_step(
        self,
        step_number: int,
        equipment_name: str,
        failure_description: str,
        symptoms: List[str],
        previous_answer: str,
        rag_context: str,
        domain_insights: Optional[DomainInsightsSummary] = None,
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
        domain_section = ""
        if domain_insights and domain_insights.key_findings:
            domain_section = f"\n\nDOMAIN EXPERT ANALYSIS (Pre-Analysis):\nThe following domain experts have already analyzed this failure:\n\n{self._format_domain_insights(domain_insights)}\n"

                # Build prompt for this why step
        if step_number == 1:
            prompt = f"""You are performing a 5 Whys Root Cause Analysis for industrial equipment failure.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}
{domain_section}
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
        
        Args:
            prompt: Prompt text
            
        Returns:
            LLM response text
        """
        # Check if adapter has a direct chat/completion method
        if hasattr(self.llm_adapter, 'client'):
            # Gemini adapter
            if hasattr(self.llm_adapter.client, 'models'):
                response = self.llm_adapter.client.models.generate_content(
                    model=self.llm_adapter.model_name,
                    contents=prompt
                )
                return response.text
        
        # Fallback: use analyze_failure method (less ideal but works)
        result = self.llm_adapter.analyze_failure(
            failure_description=prompt,
            equipment_name="",
            symptoms=[],
            use_rag=False
        )
        
        return result.get('raw_response', '')
    
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
