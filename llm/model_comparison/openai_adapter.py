"""
OpenAI Model Adapter (Standard OpenAI API, not Azure)

Handles communication with OpenAI API for RCA analysis.
"""

import os
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI


class OpenAIAdapter:
    """Adapter for standard OpenAI API."""
    
    def __init__(self, api_key: str = None):
        """Initialize OpenAI client."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        
        self.client = OpenAI(api_key=self.api_key)
        
        # Use GPT-4o (latest model)
        self.model_name = "gpt-4o"
        self.total_tokens = 0
        self.total_cost = 0.0
    
    def analyze_failure(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        context: Optional[str] = None,
        use_rag: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze a failure scenario.
        
        Args:
            failure_description: Description of the failure
            equipment_name: Name of the equipment
            symptoms: List of observed symptoms
            context: Optional RAG context
            use_rag: Whether RAG context is being used
            
        Returns:
            Dictionary with analysis results
        """
        start_time = time.time()
        
        # Build prompt
        if use_rag and context:
            prompt = f"""You are an expert in Root Cause Analysis for industrial equipment.

Equipment: {equipment_name}
Failure Description: {failure_description}
Symptoms: {', '.join(symptoms)}

Relevant Documentation:
{context}

Based on the above information and documentation, perform a thorough root cause analysis:

1. Identify the most likely root cause
2. Explain your reasoning step by step
3. Provide confidence level (0-100%)
4. Suggest corrective actions

Format your response as:
ROOT CAUSE: [your analysis]
REASONING: [step by step]
CONFIDENCE: [percentage]
CORRECTIVE ACTIONS: [suggestions]"""
        else:
            prompt = f"""You are an expert in Root Cause Analysis for industrial equipment.

Equipment: {equipment_name}
Failure Description: {failure_description}
Symptoms: {', '.join(symptoms)}

Perform a root cause analysis based on your general knowledge:

1. Identify the most likely root cause
2. Explain your reasoning step by step
3. Provide confidence level (0-100%)
4. Suggest corrective actions

Format your response as:
ROOT CAUSE: [your analysis]
REASONING: [step by step]
CONFIDENCE: [percentage]
CORRECTIVE ACTIONS: [suggestions]"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are an expert in industrial equipment failure analysis and root cause analysis."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            response_time = time.time() - start_time
            
            # Extract response
            content = response.choices[0].message.content
            
            # Calculate tokens and cost
            tokens_used = response.usage.total_tokens
            # GPT-4o pricing: $2.50/1M input, $10/1M output
            cost = (response.usage.prompt_tokens * 2.50 + response.usage.completion_tokens * 10.0) / 1_000_000
            
            self.total_tokens += tokens_used
            self.total_cost += cost
            
            # Parse response
            root_cause = self._extract_section(content, "ROOT CAUSE")
            reasoning = self._extract_section(content, "REASONING")
            confidence_str = self._extract_section(content, "CONFIDENCE")
            
            # Extract confidence percentage
            confidence = 0.0
            if confidence_str:
                import re
                match = re.search(r'(\d+)', confidence_str)
                if match:
                    confidence = float(match.group(1)) / 100.0
            
            return {
                "root_cause": root_cause or content[:200],
                "reasoning_steps": reasoning.split('\n') if reasoning else [content],
                "confidence": confidence,
                "response_time_seconds": response_time,
                "tokens_used": tokens_used,
                "cost_usd": cost,
                "raw_response": content,
                "model": "OpenAI GPT-4o"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "root_cause": f"Error: {e}",
                "reasoning_steps": [],
                "confidence": 0.0,
                "response_time_seconds": time.time() - start_time,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "raw_response": "",
                "model": "OpenAI GPT-4o"
            }
    
    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a section from the response."""
        import re
        pattern = f"{section_name}:(.+?)(?=\\n[A-Z]+:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost,
            "model": "OpenAI GPT-4o"
        }
