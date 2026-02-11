"""
Google Gemini Model Adapter

Handles communication with Google Gemini API for RCA analysis.
Uses the new google.genai package.
"""

import os
import time
from typing import List, Dict, Any, Optional
from google import genai


class GeminiAdapter:
    """Adapter for Google Gemini API."""
    
    def __init__(self, api_key: str = None):
        """Initialize Gemini client."""
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            raise ValueError("Google API key required")
        
        # Use new google.genai package
        self.client = genai.Client(api_key=self.api_key)
        
        # Use Gemini 3 Flash Preview (as shown in screenshot)
        self.model_name = "gemini-3-flash-preview"
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
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            response_time = time.time() - start_time
            
            # Extract response
            content = response.text
            
            # Estimate tokens (Gemini doesn't provide exact count in free tier)
            # Rough estimate: ~4 chars per token
            tokens_used = len(prompt + content) // 4
            
            # Gemini Pro pricing: $0.00025/1K input, $0.0005/1K output (very cheap!)
            cost = (len(prompt) // 4 * 0.00025 + len(content) // 4 * 0.0005) / 1000
            
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
                "model": "Google Gemini 3 Flash"
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
                "model": "Google Gemini 3 Flash"
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
            "model": "Google Gemini Pro"
        }
