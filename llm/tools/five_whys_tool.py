"""
5 Whys Analysis Tool

Implements the 5 Whys RCA methodology with RAG-enhanced analysis.
"""

from typing import List, Dict, Any
import logging

from tools.base_tool import BaseTool
from models.tool_results import ToolResult, FiveWhysResult, WhyStep
from tools.evidence_validator import (
    ConfidenceCalibrator,
    PlantFailureModeValidator,
    EvidenceGate,
    EvidenceType
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
        **kwargs
    ) -> ToolResult:
        """
        Perform 5 Whys analysis.
        
        Args:
            failure_description: Description of the failure
            equipment_name: Name of the equipment
            symptoms: List of observed symptoms
            **kwargs: Additional parameters
            
        Returns:
            ToolResult containing FiveWhysResult
        """
        async def _perform_analysis():
            # Step 1: Retrieve initial context from RAG
            self.logger.info(f"Starting 5 Whys analysis for {equipment_name}")
            rag_docs = await self._retrieve_context(equipment_name, symptoms, top_k=5)
            rag_context = self._format_context(rag_docs)
            
            # Collect document sources
            doc_sources = [doc.source for doc in rag_docs if hasattr(doc, 'source')]
            
            # Step 2: Perform 5 progressive "why" iterations
            why_steps = []
            current_answer = failure_description
            
            for step_num in range(1, 6):
                self.logger.info(f"Generating Why #{step_num}")
                
                # Generate why question and answer
                why_result = await self._generate_why_step(
                    step_number=step_num,
                    equipment_name=equipment_name,
                    failure_description=failure_description,
                    symptoms=symptoms,
                    previous_answer=current_answer,
                    rag_context=rag_context,
                    is_final=(step_num == 5)
                )
                
                why_steps.append(why_result)
                current_answer = why_result.answer
            
            # Step 3: Extract root cause from final why
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
                documents_used=list(set(doc_sources))  # Remove duplicates, keep unique only
            )
            
            return result.dict()
        
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
            is_final: Whether this is the final step (step 5)
            
        Returns:
            WhyStep with question, answer, and supporting documents
        """
        # Build prompt for this why step
        if step_number == 1:
            prompt = f"""You are performing a 5 Whys Root Cause Analysis for industrial equipment failure.

Equipment: {equipment_name}
Failure Description: {failure_description}
Observed Symptoms: {', '.join(symptoms)}

Relevant Technical Documentation:
{rag_context}

This is Why #1 of the 5 Whys analysis.

🚨 CRITICAL RULES FOR PLANT-CREDIBLE RCA:
1. NEVER use HTTP/API errors (503, 404, 500, etc.) as plant failure modes
2. Plant signal failures are: "Bad Quality", "Comm Fail", "Signal Unhealthy", "Input Forced", "Loss of Signal"
3. Base your answer on EVIDENCE:
   - Measured data (sensor readings, alarms, trends)
   - OEM manual rules (explicit causality statements)
   - Documented procedures
4. If inferring without direct evidence, state this clearly and use cautious language
5. Cite specific document names and page numbers when available

Task: Based on the failure description and symptoms, answer the question "Why did this failure occur?"

Provide your response in the following format:

QUESTION: Why did this failure occur?
ANSWER: [Your detailed answer, citing specific documents by name when possible. If inferring, state "Based on inference" or "Likely due to"]
SUPPORTING_DOCUMENTS: [List document names you referenced, e.g., "Rotary Kiln_Hongda_OEM Manual, ID&HR Fan_TLT_OEM Manual"]
CONFIDENCE: [Your confidence level as a percentage, e.g., 85]

Be specific and cite the technical documentation where applicable.
"""
        else:
            prompt = f"""You are performing a 5 Whys Root Cause Analysis for industrial equipment failure.

Equipment: {equipment_name}
Original Failure: {failure_description}

Relevant Technical Documentation:
{rag_context}

This is Why #{step_number} of the 5 Whys analysis.

Previous Answer (Why #{step_number-1}): {previous_answer}

🚨 CRITICAL RULES FOR PLANT-CREDIBLE RCA:
1. NEVER use HTTP/API errors (503, 404, 500, etc.) as plant failure modes
2. Plant signal failures are: "Bad Quality", "Comm Fail", "Signal Unhealthy", "Input Forced", "Loss of Signal"
3. Base your answer on EVIDENCE:
   - Measured data (sensor readings, alarms, trends)
   - OEM manual rules (explicit causality statements)
   - Documented procedures
4. If inferring without direct evidence, state this clearly and use cautious language
5. For root cause (Why #5), focus on SYSTEMIC issues (procedures, design, governance), not just triggers

Task: Drill deeper by asking "Why did {previous_answer}?" and provide a detailed answer.

{"🎯 This is the FINAL why. Your answer should identify the ROOT CAUSE - the systemic issue (poor design, missing procedure, inadequate governance) that allowed the failure, NOT just the immediate trigger." if is_final else ""}

Provide your response in the following format:

QUESTION: Why {previous_answer[:100]}...?
ANSWER: [Your detailed answer, citing specific documents by name when possible. If inferring, state "Based on inference" or "Likely due to"]
SUPPORTING_DOCUMENTS: [List document names you referenced, e.g., "Rotary Kiln_Hongda_OEM Manual, ID&HR Fan_TLT_OEM Manual"]
CONFIDENCE: [Your confidence level as a percentage, e.g., 85]

Be specific and cite the technical documentation where applicable.
"""
        
        # Call LLM
        try:
            # Use the LLM adapter's analyze_failure method
            # (We'll adapt it for this use case)
            response = self._call_llm(prompt)
            
            # Parse response
            question, answer, docs, confidence = self._parse_why_response(response, step_number)
            
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
                question=f"Why (step {step_number})?",
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
        
        # Extract question
        question_match = re.search(r'QUESTION:\s*(.+?)(?=\n|ANSWER:)', response, re.DOTALL | re.IGNORECASE)
        question = question_match.group(1).strip() if question_match else f"Why (step {step_number})?"
        
        # Extract answer
        answer_match = re.search(r'ANSWER:\s*(.+?)(?=\nSUPPORTING_DOCUMENTS:|CONFIDENCE:|$)', response, re.DOTALL | re.IGNORECASE)
        answer = answer_match.group(1).strip() if answer_match else response[:500]
        
        # Extract supporting documents
        docs_match = re.search(r'SUPPORTING_DOCUMENTS:\s*(.+?)(?=\nCONFIDENCE:|$)', response, re.DOTALL | re.IGNORECASE)
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
