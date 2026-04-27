"""
Phase 1: Historical RCA PDF Extraction

Converts historical RCA PDFs to structured JSON using Qwen 3.5-9B vision
via OpenRouter.

Strategy:
  - Single API call for PDFs with ≤ 20 pages (all pages as images in one call)
  - Two-pass fallback for PDFs > 20 pages OR if single call fails:
      Pass 1: text/table pages (1-5) → structured data extraction
      Pass 2: remaining pages + Pass 1 JSON → proof image descriptions

Usage:
  python extract_rca_history.py                 # extract all PDFs
  python extract_rca_history.py --single "CPP1/15MW RCA 19-1-26.pdf"  # one file
"""

import os
import sys
import json
import re
import base64
import logging
import time
import argparse
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from pdf2image import convert_from_path
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_DIR = SCRIPT_DIR.parent.parent / "llm"
load_dotenv(LLM_DIR / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.5-9b")
FALLBACK_VISION_MODEL = "qwen/qwen2.5-vl-72b-instruct"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

DATA_DIR = SCRIPT_DIR / "history_data"
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "extracted_data.json"
STATUS_FILE = OUTPUT_DIR / "extraction_status.txt"

MAX_PAGES_SINGLE_CALL = 20
PDF_DPI = 200  # balance between quality and size

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Extraction Prompt ─────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are an expert industrial RCA (Root Cause Analysis) document parser.

You are given page images from an RCA report PDF used in Indian power/steel plants.
Extract ALL available information into a single JSON object.

The PDF may be in one of two formats:
- Format A (multi-page): Header info on page 1, 5 Whys on page 2, domain insights on page 3, fishbone on page 4, proof images on page 5+
- Format B (single-page): All information on one page including header, 5 Whys, root cause, CAPA

You MUST respond with ONLY a raw JSON object. No markdown, no backticks, no explanation.
Start your response with { and end with }.

Required JSON schema:
{
  "plant": "CPP1 or CPP2 or other plant name",
  "department": "Electrical / Mechanical / Process / Instrumentation / etc.",
  "equipment": "exact equipment name from the report",
  "occurrence_from": "ISO datetime or date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) or null",
  "occurrence_to": "ISO datetime or date string or null",
  "downtime_minutes": integer or null,
  "problem_statement": "the main problem/failure description",
  "opportunity_loss": "Speed Loss / Production Loss / etc. or null",
  "impact_on_production": "Yes / No / null",
  "chronology_of_events": ["event1", "event2", ...] or [],
  "observations_from_site": ["observation1", "observation2", ...] or [],
  "why_steps": [
    {"step": 1, "question": "Why ...?", "answer": "Because ..."},
    {"step": 2, "question": "Why ...?", "answer": "Because ..."}
  ],
  "root_cause": "the final identified root cause (MUST NOT be null)",
  "capa": [
    {"action": "corrective action text", "responsibility": "person name or null", "target_date": "YYYY-MM-DD or null", "status": "Completed / Pending / null"}
  ],
  "preventive_actions": [
    {"action": "preventive action text", "responsibility": "person name or null", "target_date": "YYYY-MM-DD or null", "status": "Completed / Pending / null"}
  ],
  "team_members": ["Name1", "Name2", ...] or [],
  "pm_frequency": "YEARLY / MONTHLY / QUARTERLY / etc. or null",
  "breakdown_history_6months": ["past incident 1", "past incident 2", ...] or [],
  "domain_expert_insights": {
    "mechanical": "text or null",
    "electrical": "text or null",
    "process": "text or null"
  },
  "proof_images_description": "description of any equipment photos/proof images visible, or null",
  "fishbone_categories": {
    "man": ["cause1", "cause2"] or [],
    "machine": ["cause1", "cause2"] or [],
    "method": ["cause1", "cause2"] or [],
    "material": ["cause1", "cause2"] or [],
    "mother_nature": ["cause1", "cause2"] or [],
    "measurement": ["cause1", "cause2"] or []
  }
}

Rules:
- Extract EXACTLY what is written. Do not hallucinate or infer missing data.
- For missing/empty fields, use null for strings/numbers and [] for arrays.
- Normalize downtime to minutes (e.g., "3 Hr 40 Min" → 220, "From 05:15 PM To 06:16 PM" → 61).
- Dates should be in YYYY-MM-DD format. Convert Indian date formats (DD-MM-YY, DD/MM/YYYY, etc.).
- For why_steps, extract each Why with its question and answer. There are typically 4-5 Whys.

CRITICAL RULES:
- root_cause MUST NEVER be null. If no explicit "Root Cause" field is found, derive it from the last answered why_step. A root cause can always be inferred from the 5 Whys chain.
- CAPA (Corrective Action & Preventive Action): Documents often have a combined CAPA section or separate "Corrective Action" and "Preventive Action" sections. Extract ALL items from CAPA tables. If the document has a separate "Preventive Actions" or "Preventive Action to be taken" section, put those in the "preventive_actions" array. If CAPA is combined, put corrective actions in "capa" and preventive actions in "preventive_actions".
- HANDWRITTEN vs PRINTED text: These are scanned documents. When you see printed/typed text that has been CROSSED OUT / STRUCK THROUGH and handwritten text written over or next to it, ALWAYS prefer the HANDWRITTEN text as the correct value. The handwritten text is the correction made by the engineer. Ignore the crossed-out printed text entirely.
- YOUR ENTIRE RESPONSE MUST BE VALID JSON ONLY.
"""

PROOF_IMAGE_PROMPT = """\
You are an expert industrial equipment failure analyst.

You were given additional pages from an RCA report that contain proof images
(equipment photos, relay panels, damaged parts, etc.).

Here is the structured data already extracted from the earlier pages:
{pass1_json}

Now look at these additional page images and:
1. Describe what equipment/damage is visible in the proof images
2. Note any additional information (signatures, stamps, dates) not in the extracted data

Respond with ONLY a raw JSON object:
{{
  "proof_images_description": "detailed description of all proof images and what they show",
  "additional_observations": ["any extra info found on these pages"]
}}
"""


# ── Utilities ─────────────────────────────────────────────────────────────────

def image_to_base64(img) -> tuple:
    """Convert a PIL Image to (base64_str, mime_type)."""
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, "image/jpeg"


def extract_json(text: str) -> dict:
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

    # 3. Brace-counting: find each top-level { and its matching }
    candidates = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            in_string = False
            escape = False
            for j in range(i, len(text)):
                c = text[j]
                if escape:
                    escape = False
                    continue
                if c == '\\' and in_string:
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        block = text[i:j+1]
                        try:
                            result = json.loads(block)
                            if isinstance(result, dict):
                                candidates.append(result)
                        except json.JSONDecodeError:
                            pass
                        break
            i = j + 1 if depth == 0 else i + 1
        else:
            i += 1

    # Pick the candidate with the most keys
    if candidates:
        candidates.sort(key=lambda d: len(d), reverse=True)
        return candidates[0]

    raise ValueError(f"Could not parse JSON from model response. First 500 chars: {text[:500]}")


# Minimum keys expected from a valid RCA extraction
REQUIRED_KEYS = {"equipment", "root_cause", "why_steps", "problem_statement"}


def validate_extraction(result: dict) -> bool:
    """Check that the parsed JSON is a full RCA extraction, not a fragment."""
    if not (len(result) >= 8 and REQUIRED_KEYS.issubset(result.keys())):
        return False
    # Enforce non-null root_cause: derive from last why_step if missing
    if not result.get("root_cause"):
        why_steps = result.get("why_steps", [])
        if why_steps:
            # Use the last answered why_step as root cause
            for ws in reversed(why_steps):
                if ws.get("answer"):
                    result["root_cause"] = ws["answer"]
                    logger.warning(f"  root_cause was null — derived from why_step {ws.get('step')}: {ws['answer'][:80]}")
                    break
        if not result.get("root_cause"):
            result["root_cause"] = result.get("problem_statement", "Root cause not identified")
            logger.warning(f"  root_cause was null — set to problem_statement")
    return True


def call_vision_api(messages_content: list, max_tokens: int = 4096, retries: int = 2) -> str:
    """Call OpenRouter vision API with retry logic."""
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a JSON extraction bot. You ONLY output valid JSON. No reasoning, no explanation, no markdown. Your entire response must be a single JSON object.",
            },
            {"role": "user", "content": messages_content},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "RCA History Extractor",
    }

    models_to_try = [VISION_MODEL]
    if FALLBACK_VISION_MODEL and FALLBACK_VISION_MODEL != VISION_MODEL:
        models_to_try.append(FALLBACK_VISION_MODEL)

    for model in models_to_try:
        payload["model"] = model
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    OPENROUTER_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                resp.raise_for_status()
                resp_json = resp.json()

                message = resp_json.get("choices", [{}])[0].get("message", {})
                raw = (message.get("content") or message.get("reasoning") or "").strip()
                if not raw:
                    raise ValueError("Vision model returned empty content.")
                if model != VISION_MODEL:
                    logger.info(f"  [FALLBACK] Succeeded with {model}")
                return raw

            except Exception as e:
                if attempt < retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"  Attempt {attempt+1} failed ({model}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    if model != models_to_try[-1]:
                        logger.warning(f"  {model} unavailable (503). Switching to fallback: {FALLBACK_VISION_MODEL}")
                        break  # try next model
                    raise


def log_status(source_file: str, status: str, key_count: int = 0):
    """Append extraction status to the status file."""
    if key_count:
        line = f"{source_file} — {status} ({key_count} keys)\n"
    else:
        line = f"{source_file} — {status}\n"
    with open(STATUS_FILE, "a", encoding="utf-8") as f:
        f.write(line)


# ── Core Extraction ──────────────────────────────────────────────────────────

def pdf_to_images(pdf_path: Path) -> list:
    """Convert all pages of a PDF to PIL Images."""
    return convert_from_path(str(pdf_path), dpi=PDF_DPI)


def build_image_content(images: list) -> list:
    """Build the OpenRouter message content array with images."""
    content = []
    for img in images:
        b64, mime = image_to_base64(img)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    return content


def extract_single_call(images: list, plant: str, filename: str) -> dict:
    """Single API call: send all pages, get full structured JSON."""
    content = build_image_content(images)
    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    logger.info(f"  Single-call extraction ({len(images)} pages)...")
    raw = call_vision_api(content, max_tokens=8192)
    result = extract_json(raw)
    if not validate_extraction(result):
        raise ValueError(f"Extraction returned incomplete data ({len(result)} keys: {list(result.keys())})")
    logger.info(f"  Parsed JSON keys ({len(result)}): {list(result.keys())}")
    return result


def extract_two_pass(images: list, plant: str, filename: str) -> dict:
    """Two-pass extraction for large PDFs or as fallback."""
    # Pass 1: text/table pages (first 5 or all if ≤ 5)
    text_pages = images[:5]
    proof_pages = images[5:]

    logger.info(f"  Pass 1: Extracting structured data from {len(text_pages)} text pages...")
    content = build_image_content(text_pages)
    content.append({"type": "text", "text": EXTRACTION_PROMPT})
    raw = call_vision_api(content, max_tokens=8192)
    result = extract_json(raw)
    if not validate_extraction(result):
        raise ValueError(f"Pass 1 returned incomplete data ({len(result)} keys: {list(result.keys())})")
    logger.info(f"  Pass 1 parsed JSON keys ({len(result)}): {list(result.keys())}")

    # Pass 2: proof image pages (if any)
    if proof_pages:
        logger.info(f"  Pass 2: Analyzing {len(proof_pages)} proof image pages...")
        pass1_summary = json.dumps(result, indent=2)
        prompt = PROOF_IMAGE_PROMPT.format(pass1_json=pass1_summary)

        content2 = build_image_content(proof_pages)
        content2.append({"type": "text", "text": prompt})

        try:
            raw2 = call_vision_api(content2, max_tokens=2048)
            proof_data = extract_json(raw2)
            # Merge proof image info
            if proof_data.get("proof_images_description"):
                result["proof_images_description"] = proof_data["proof_images_description"]
            if proof_data.get("additional_observations"):
                existing = result.get("observations_from_site") or []
                result["observations_from_site"] = existing + proof_data["additional_observations"]
        except Exception as e:
            logger.warning(f"  Pass 2 failed (non-critical): {e}")

    return result


def extract_file(file_path: Path, plant: str) -> Optional[dict]:
    """Extract structured data from a PDF or image file (JPG/JPEG/PNG)."""
    from PIL import Image

    filename = file_path.name
    logger.info(f"Processing: {plant}/{filename}")

    source_file = f"{plant}/{filename}"
    is_image = file_path.suffix.lower() in {".jpg", ".jpeg", ".png"}

    if is_image:
        # Direct image file -- load as single-page PIL Image
        try:
            img = Image.open(str(file_path)).convert("RGB")
            images = [img]
            logger.info(f"  Loaded image file directly ({img.size[0]}x{img.size[1]})")
        except Exception as e:
            logger.error(f"  Failed to load image file: {e}")
            log_status(source_file, "FAILED (image load)")
            return None
    else:
        # PDF -- convert to images using pdf2image
        try:
            images = pdf_to_images(file_path)
        except Exception as e:
            logger.error(f"  Failed to convert PDF to images: {e}")
            log_status(source_file, "FAILED (pdf2image)")
            return None

    num_pages = len(images)
    logger.info(f"  {num_pages} page(s) detected")

    result = None

    # Strategy: single call first for ≤ 20 pages, two-pass for > 20
    if num_pages <= MAX_PAGES_SINGLE_CALL:
        try:
            result = extract_single_call(images, plant, filename)
        except Exception as e:
            logger.warning(f"  Single-call failed: {e}. Falling back to two-pass...")
            try:
                result = extract_two_pass(images, plant, filename)
            except Exception as e2:
                logger.error(f"  Two-pass also failed: {e2}")
                log_status(source_file, "FAILED (both passes)")
                return None
    else:
        # Large PDF: go straight to two-pass
        try:
            result = extract_two_pass(images, plant, filename)
        except Exception as e:
            logger.error(f"  Two-pass extraction failed: {e}")
            log_status(source_file, "FAILED (two-pass)")
            return None

    # Add metadata
    result["source_file"] = source_file
    result["plant"] = result.get("plant") or plant
    result["extraction_method"] = "vision_llm"
    result["pages_extracted"] = num_pages

    log_status(source_file, "OK", len(result))
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def load_completed_from_status() -> set:
    """Read extraction_status.txt and return set of source_files marked OK."""
    completed = set()
    if STATUS_FILE.exists():
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if " — OK" in line:
                    completed.add(line.split(" — ")[0])
    return completed


# Supported file extensions for extraction
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def discover_files() -> list:
    """Find all PDFs and image files (JPG/JPEG/PNG) in history_data/ subfolders."""
    files = []
    for plant_dir in sorted(DATA_DIR.iterdir()):
        if not plant_dir.is_dir():
            continue
        plant = plant_dir.name  # CPP1, CPP2, DRI1
        for file_path in sorted(plant_dir.iterdir()):
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append((plant, file_path))
    return files


def main():
    parser = argparse.ArgumentParser(description="Extract RCA data from historical PDFs")
    parser.add_argument("--single", type=str, help="Extract a single file (e.g., 'CPP1/15MW RCA 19-1-26.pdf' or 'DRI1/RCA.jpeg')")
    parser.add_argument("--data-dir", type=str, help="Override data directory (default: history_data/)")
    args = parser.parse_args()

    global DATA_DIR
    if args.data_dir:
        DATA_DIR = Path(args.data_dir)

    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set in llm/.env")
        sys.exit(1)

    logger.info(f"Vision model: {VISION_MODEL}")
    logger.info(f"Data directory: {DATA_DIR}")

    # Load existing results (for incremental extraction)
    existing = []
    existing_files = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_files = {r["source_file"] for r in existing}
        logger.info(f"Found {len(existing)} existing records in {OUTPUT_FILE.name}")

    # Also read status file for completed files
    completed_files = load_completed_from_status()
    skip_files = existing_files | completed_files
    if completed_files - existing_files:
        logger.info(f"Found {len(completed_files - existing_files)} additional completed files in {STATUS_FILE.name}")

    if args.single:
        # Single file mode
        parts = args.single.replace("\\", "/").split("/", 1)
        if len(parts) != 2:
            logger.error("Use format: 'CPP1/filename.pdf' or 'DRI1/RCA.jpeg'")
            sys.exit(1)
        plant, fname = parts
        file_path = DATA_DIR / plant / fname
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.error(f"Unsupported file type: {file_path.suffix}. Supported: {SUPPORTED_EXTENSIONS}")
            sys.exit(1)

        result = extract_file(file_path, plant)
        if result:
            # Replace if already exists, else append
            existing = [r for r in existing if r["source_file"] != result["source_file"]]
            existing.append(result)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved to {OUTPUT_FILE}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            logger.error("Extraction failed.")
            sys.exit(1)
    else:
        # Full extraction mode
        files = discover_files()
        logger.info(f"Found {len(files)} files to process (PDFs + images)")

        results = list(existing)  # start with existing
        success = 0
        skipped = 0
        failed = 0

        for plant, file_path in files:
            source_file = f"{plant}/{file_path.name}"

            if source_file in skip_files:
                logger.info(f"Skipping (already extracted): {source_file}")
                skipped += 1
                continue

            result = extract_file(file_path, plant)
            if result:
                results.append(result)
                success += 1
                # Save after each PDF (incremental)
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
            else:
                failed += 1

            # Small delay between PDFs to avoid rate limits
            time.sleep(2)

        logger.info(f"\nDone! Success: {success}, Skipped: {skipped}, Failed: {failed}")
        logger.info(f"Total records in {OUTPUT_FILE.name}: {len(results)}")


if __name__ == "__main__":
    main()
