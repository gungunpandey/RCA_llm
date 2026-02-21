"""
test_fishbone.py — Direct test of FishboneTool in isolation.

Skips domain agents and 5 Whys entirely.
Uses hardcoded inputs (taken from a real previous pipeline run).

Usage:
    cd c:\\Users\\GUNGUN PANDEY\\OneDrive\\Desktop\\rca\\llm
    python test_fishbone.py
"""

import asyncio
import json
import logging
import os
import sys
import time

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
for noisy in ("httpx", "httpcore", "google_genai", "weaviate"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("test_fishbone")

# ── Imports ───────────────────────────────────────────────────────────────────
from model_comparison.gemini_adapter import GeminiAdapter
from rag_manager import RAGManager
from tools.fishbone_tool import FishboneTool
from models.tool_results import DomainInsightsSummary, DomainAnalysisResult

# ── Hardcoded scenario (from real previous pipeline run) ──────────────────────
EQUIPMENT_NAME = "Electrostatic Precipitator (ESP)"
FAILURE_DESCRIPTION = (
    "ESP TR Set 1 tripped on under-voltage Field 1. "
    "Spark rate high. Hopper High Level Alarm active."
)
SYMPTOMS = [
    "TR Set 1 under-voltage trip",
    "High spark rate on Field 1",
    "Hopper high level alarm",
    "Increased stack opacity",
]

# Root cause from the 5 Whys run
ROOT_CAUSE = (
    "The systemic root cause is a deficiency in the preventive maintenance "
    "strategy for hopper heaters and a failure in operational governance to "
    "enforce the mandatory four-hour pre-heating protocol. This allowed ash to "
    "reach the acid dew point and clump, creating a torque-related obstruction "
    "in the RAV. The heating system is critical for ensuring ash flowability to "
    "prevent motor overload. A systemic gap in the routine verification of "
    "safety interlocks (SL 7m) also contributed."
)

# Domain insights from the domain agent run (plain dict — matches DomainInsightsSummary)
DOMAIN_INSIGHTS_DICT = {
    "agents_analyzed": ["electrical_agent"],
    "domain_analyses": [],
    "key_findings": [
        "[ELECTRICAL] TR Set 1 executed a mandatory Secondary Under-voltage Trip "
        "per OEM interlock checklist SL NO 6. (CRITICAL)",
        "[ELECTRICAL] Electrical interlock 7e trips the TR set when dust reaches "
        "high-high threshold to prevent electrode damage. (CRITICAL)",
        "[ELECTRICAL] Failure in ash handling control logic / RAV operation "
        "(Interlock 7m) initiated field shutdown. (CRITICAL)",
        "[ELECTRICAL] Excessive ash accumulation created a low-impedance path "
        "causing high spark rates and secondary voltage drop. (WARNING)",
    ],
    "suspected_root_causes": [
        {
            "domain": "electrical",
            "hypothesis": (
                "Failure in the ash evacuation system (tripped RAV or ash conveyor) "
                "allowed ash to bridge discharge electrodes and hopper, creating a "
                "low-voltage path leading to high spark rates and Under-voltage trip."
            ),
            "confidence": 0.7,
        }
    ],
    "recommended_checks": [
        "Check RAV motor for thermal overload trip or ZSS activation (Interlock 7i/7j).",
        "Verify Level Switch High-High signal and probe condition in Field 1 hopper.",
        "Measure insulation resistance of TR Set secondary side after ash evacuation.",
    ],
    "documents_used": ["ESP_Thermax_OEM Manual"],
    "overall_confidence": 0.7,
    "analysis_timestamp": "2026-02-18T13:38:03",
}


async def status_cb(msg):
    if isinstance(msg, tuple):
        pass  # ignore sentinel events in this test
    else:
        print(f"  [STATUS] {msg}")


async def run_test():
    print("\n" + "=" * 60)
    print("🧪 FISHBONE TOOL — DIRECT ISOLATION TEST")
    print("=" * 60)
    print(f"Equipment  : {EQUIPMENT_NAME}")
    print(f"Root cause : {ROOT_CAUSE[:120]}...")
    print("=" * 60 + "\n")

    # ── Init ──────────────────────────────────────────────────────────────────
    print("⚙️  Initialising components...")
    gemini = GeminiAdapter()
    rag = RAGManager()
    rag.connect()
    print("   ✓ Ready\n")

    tool = FishboneTool(llm_adapter=gemini, rag_manager=rag)

    # Build DomainInsightsSummary from the hardcoded dict
    domain_insights = DomainInsightsSummary(**DOMAIN_INSIGHTS_DICT)

    # ── Run fishbone directly ─────────────────────────────────────────────────
    start = time.time()
    result = await tool.analyze(
        failure_description=FAILURE_DESCRIPTION,
        equipment_name=EQUIPMENT_NAME,
        symptoms=SYMPTOMS,
        root_cause=ROOT_CAUSE,
        domain_insights=domain_insights,
        status_callback=status_cb,
    )
    elapsed = round(time.time() - start, 1)

    # ── Results ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if not result.success:
        print(f"❌ FISHBONE FAILED ({elapsed}s)")
        print(f"   Error: {result.error}")
        rag.disconnect()
        return

    print(f"✅ FISHBONE COMPLETE in {elapsed}s")
    print("=" * 60)

    fb = result.result
    print(f"\n  Primary category : {fb.get('primary_category', 'N/A')}")
    print(f"  Summary          : {fb.get('summary', '')}")
    print()

    cats = fb.get("categories", {})
    for cat, causes in cats.items():
        if causes:
            print(f"  {cat:12s} ({len(causes)} cause(s)):")
            for c in causes:
                conf = int(c.get("confidence", 0) * 100)
                print(f"    [{conf}%] {c.get('cause', '')}")
                for sub in c.get("sub_causes", [])[:2]:
                    print(f"           → {sub}")

    # Save JSON
    dump_path = os.path.join(os.path.dirname(__file__), "test_fishbone_output.json")
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(fb, f, indent=2, default=str)
    print(f"\n📄 Full result saved to: {dump_path}")

    rag.disconnect()


if __name__ == "__main__":
    asyncio.run(run_test())
