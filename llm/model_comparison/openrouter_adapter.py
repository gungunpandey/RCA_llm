"""
OpenRouter Model Adapter

Routes requests to OpenAI GPT-5 (or any OpenRouter model) via the
OpenRouter API, which is fully OpenAI-SDK-compatible.

Usage:
  Set OPENROUTER_API_KEY in your .env and optionally OPENROUTER_MODEL
  (defaults to openai/gpt-5).

OpenRouter model IDs for GPT-5 family:
  openai/gpt-5              — $1.25/M input  | $10.00/M output  (recommended)
  openai/gpt-5.2            — $1.75/M input  | $14.00/M output  (stronger agentic)
  openai/gpt-5-mini-2025-08-07 — $0.25/M input | $2.00/M output (cheapest, good for first tests)
"""

import os
import time
import asyncio
import re
from typing import List, Dict, Any, Optional

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Pricing per million tokens for each model (input, output)
_PRICING: Dict[str, tuple] = {
    "openai/gpt-5":                    (1.25, 10.00),
    "openai/gpt-5.2":                  (1.75, 14.00),
    "openai/gpt-5-mini-2025-08-07":    (0.25,  2.00),
    "openai/gpt-5.3-codex":            (2.00, 16.00),
}
_DEFAULT_PRICING = (1.25, 10.00)  # fall-back if model not in table


class OpenRouterAdapter:
    """
    Adapter for OpenAI GPT-5 (and other models) via OpenRouter.
    Implements the same interface as GeminiAdapter so it is a drop-in
    replacement everywhere in the RCA pipeline.
    """

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required — set OPENROUTER_API_KEY in .env"
            )

        self.model_name = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-5")

        # OpenAI SDK pointed at OpenRouter's base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                # OpenRouter recommends these headers for routing & analytics
                "HTTP-Referer": "https://github.com/rca-project",
                "X-Title": "RCA Analysis System",
            },
        )

        self.total_tokens = 0
        self.total_cost = 0.0

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _calc_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_price, output_price = _PRICING.get(self.model_name, _DEFAULT_PRICING)
        return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a labelled section from structured LLM output."""
        pattern = rf"{section_name}:(.+?)(?=\n[A-Z ]+:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _chat(
        self, prompt: str, max_tokens: int = 4096, json_mode: bool = False
    ) -> tuple[str, int, int]:
        """
        Synchronous chat completion call.
        Returns (content, prompt_tokens, completion_tokens).
        """
        kwargs: dict = dict(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert in industrial equipment failure analysis "
                        "and root cause analysis."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        content = choice.message.content or ""

        if not content:
            import logging
            logging.getLogger(__name__).warning(
                f"OpenRouter returned empty content — finish_reason={finish_reason!r}, "
                f"model={self.model_name}"
            )

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        return content, prompt_tokens, completion_tokens

    # ── Public interface (mirrors GeminiAdapter) ─────────────────────────────

    def generate_sync(
        self, prompt: str, json_mode: bool = False, max_tokens: int = 4096
    ) -> str:
        """
        Synchronous text generation — used by _call_llm() in domain agents
        and FiveWhysTool (which need a blocking call inside async context).
        """
        content, p_tokens, c_tokens = self._chat(
            prompt, json_mode=json_mode, max_tokens=max_tokens
        )
        cost = self._calc_cost(p_tokens, c_tokens)
        self.total_tokens += p_tokens + c_tokens
        self.total_cost += cost
        return content

    async def generate(
        self, prompt: str, json_mode: bool = False, max_tokens: int = 4096
    ) -> str:
        """
        Async text generation — used by FishboneTool, FiveWhysTool, domain agents.

        Runs the synchronous OpenAI SDK call in a thread executor so it
        doesn't block the event loop (identical pattern to GeminiAdapter).
        Set json_mode=True to force the model to return valid JSON (recommended
        for FishboneTool).
        """
        loop = asyncio.get_event_loop()
        content, p_tokens, c_tokens = await loop.run_in_executor(
            None, lambda: self._chat(prompt, json_mode=json_mode, max_tokens=max_tokens)
        )
        cost = self._calc_cost(p_tokens, c_tokens)
        self.total_tokens += p_tokens + c_tokens
        self.total_cost += cost
        return content

    def analyze_failure(
        self,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        context: Optional[str] = None,
        use_rag: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyze a failure scenario.

        Args:
            failure_description: Description of the failure.
            equipment_name:      Name of the equipment.
            symptoms:            List of observed symptoms.
            context:             Optional RAG context string.
            use_rag:             Whether RAG context is being used.

        Returns:
            Dictionary with analysis results (same schema as GeminiAdapter).
        """
        start_time = time.time()

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
            content, p_tokens, c_tokens = self._chat(prompt)
            response_time = time.time() - start_time
            cost = self._calc_cost(p_tokens, c_tokens)
            tokens_used = p_tokens + c_tokens
            self.total_tokens += tokens_used
            self.total_cost += cost

            root_cause = self._extract_section(content, "ROOT CAUSE")
            reasoning = self._extract_section(content, "REASONING")
            confidence_str = self._extract_section(content, "CONFIDENCE")

            confidence = 0.0
            if confidence_str:
                match = re.search(r"(\d+)", confidence_str)
                if match:
                    confidence = float(match.group(1)) / 100.0

            return {
                "root_cause": root_cause or content[:200],
                "reasoning_steps": reasoning.split("\n") if reasoning else [content],
                "confidence": confidence,
                "response_time_seconds": response_time,
                "tokens_used": tokens_used,
                "cost_usd": cost,
                "raw_response": content,
                "model": f"OpenRouter/{self.model_name}",
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
                "model": f"OpenRouter/{self.model_name}",
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get cumulative usage statistics."""
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "model": f"OpenRouter/{self.model_name}",
        }
