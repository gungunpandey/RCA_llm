"""
Azure OpenAI Model Adapter

Handles communication with Azure OpenAI API for RCA analysis.
"""

import os
import time
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI


class AzureOpenAIAdapter:
    """Adapter for Azure OpenAI API."""
    
    def __init__(self, api_key: str = None, endpoint: str = None):
        """Initialize Azure OpenAI client."""
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        
        if not self.api_key or not self.endpoint:
            raise ValueError("Azure OpenAI API key and endpoint required")
        
        self.client = AzureOpenAI(
            api_key=self.api_key,
            api_version="2024-08-01-preview",  # Latest stable API version
            azure_endpoint=self.endpoint
        )
        
        # Use deployment name from environment variable
        self.model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_GPT4", "gpt-4.1")
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
            # Azure OpenAI GPT-4 pricing: ~$0.03/1K input, ~$0.06/1K output
            cost = (response.usage.prompt_tokens * 0.03 + response.usage.completion_tokens * 0.06) / 1000
            
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
                "model": "Azure OpenAI GPT-4"
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
                "model": "Azure OpenAI GPT-4"
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
            "model": "Azure OpenAI GPT-4"
        }
