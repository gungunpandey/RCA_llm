"""
Image Analysis Tool

Uses a vision-capable LLM (Qwen 3.5-9B via OpenRouter) to analyze
uploaded equipment images and produce structured damage assessments.

The output feeds into the 5 Whys root-cause analysis as additional evidence.
"""

import os
import re
import json
import base64
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load env — works whether called from llm/ or llm/api/
_LLM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_LLM_DIR, ".env"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.5-9b")
FALLBACK_VISION_MODEL = "qwen/qwen2.5-vl-72b-instruct"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ── Image utility ─────────────────────────────────────────────────────────────

def _image_to_base64(image_path: str) -> tuple:
    """Return (base64_data, mime_type)."""
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "bmp": "image/bmp",
        "webp": "image/webp",
    }
    mime = mime_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime


# ── Prompt ────────────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """\
You are an expert industrial equipment failure analyst.

Look at the image. Identify the component and any damage, tears, wear, corrosion, or defects.

You MUST respond with ONLY a raw JSON object. No markdown. No backticks. No bullet points.
No explanation text before or after. Start your response with { and end with }.

Required format:
{"component": "name of the part", "damage_type": "type of damage", "severity": "None|Minor|Moderate|Severe|Critical", "visual_symptoms": ["symptom1", "symptom2", "symptom3"], "possible_causes": ["cause1", "cause2", "cause3"], "description": "2-3 sentence plain English summary of the damage and why it matters"}

Rules:
- component: real part name e.g. ball bearing, conveyor belt, gear shaft, motor winding
- damage_type: short label e.g. cage fracture, surface pitting, belt tear, thermal cracking
- severity: pick one of None / Minor / Moderate / Severe / Critical
- visual_symptoms: 3-5 specific visible signs in the image
- possible_causes: 3-5 engineering root causes
- description: plain English, 2-3 sentences, no jargon
- If no damage visible: damage_type = "No damage detected", severity = "None"
- YOUR ENTIRE RESPONSE MUST BE VALID JSON ONLY. No text outside the JSON.
"""


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from model output."""
    # 1. Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        result = json.loads(clean)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 3. Find last {...} block
    for search_text in (text[-1500:], text):
        matches = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', search_text, re.DOTALL))
        if not matches:
            matches = list(re.finditer(r'\{[\s\S]*\}', search_text))
        if matches:
            for m in reversed(matches):
                try:
                    result = json.loads(m.group())
                    if isinstance(result, dict) and len(result) > 1:
                        return result
                except json.JSONDecodeError:
                    continue

    raise ValueError("Could not parse JSON from vision model response.")


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze_image(image_path: str, user_description: Optional[str] = None) -> dict:
    """
    Analyze an equipment image using the vision model.

    Args:
        image_path: Absolute path to the image file.
        user_description: Optional user-provided description of the image.

    Returns:
        dict with keys: component, damage_type, severity, visual_symptoms,
        possible_causes, ai_description, user_description, combined_observation,
        image_filename.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY not set in llm/.env — needed for image analysis"
        )

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image format: {ext}")

    logger.info(f"[ImageAnalysis] Analyzing: {os.path.basename(image_path)} (model: {VISION_MODEL})")
    img_b64, mime = _image_to_base64(image_path)

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "RCA Image Analyzer",
    }

    models_to_try = [VISION_MODEL]
    if FALLBACK_VISION_MODEL and FALLBACK_VISION_MODEL != VISION_MODEL:
        models_to_try.append(FALLBACK_VISION_MODEL)

    raw_text = None
    used_model = VISION_MODEL

    for model in models_to_try:
        payload["model"] = model
        try:
            resp = requests.post(
                OPENROUTER_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            resp_json = resp.json()

            choice = resp_json.get("choices", [{}])[0]
            message = choice.get("message", {})
            raw_text = (message.get("content") or message.get("reasoning") or "").strip()

            if not raw_text:
                raise ValueError(
                    f"Empty response — finish_reason={choice.get('finish_reason')}, "
                    f"message_keys={list(message.keys())}"
                )
            used_model = model
            if model != VISION_MODEL:
                logger.info(f"[ImageAnalysis] [FALLBACK] Succeeded with {model}")
            break

        except Exception as e:
            if model != models_to_try[-1]:
                logger.warning(f"[ImageAnalysis] {model} failed: {e}. Switching to fallback: {FALLBACK_VISION_MODEL}")
            else:
                logger.error(f"[ImageAnalysis] All models failed. Last error: {e}")
                raise ValueError(f"Vision model returned empty content. Tried: {models_to_try}")

    structured = _extract_json(raw_text)

    # Build combined observation
    ai_desc = structured.get("description", "")
    combined = ai_desc
    if user_description and user_description.strip():
        combined = (
            f"Visual AI analysis: {ai_desc} "
            f"Operator note: {user_description.strip()}"
        )

    result = {
        "component": structured.get("component", "Unknown"),
        "damage_type": structured.get("damage_type", "Unknown"),
        "severity": structured.get("severity", "Unknown"),
        "visual_symptoms": structured.get("visual_symptoms", []),
        "possible_causes": structured.get("possible_causes", []),
        "ai_description": ai_desc,
        "user_description": user_description or "",
        "combined_observation": combined,
        "image_filename": os.path.basename(image_path),
    }

    logger.info(
        f"[ImageAnalysis] Done (model: {used_model}) — component: {result['component']}, "
        f"damage: {result['damage_type']}, severity: {result['severity']}"
    )
    return result
