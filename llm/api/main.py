"""
RCA System - FastAPI Server

Exposes the RCA analysis tools via REST API.
Includes SSE streaming endpoint for live status updates.
"""

import sys
import os
import json
import logging
import asyncio
from contextlib import asynccontextmanager

# Add llm/ directory to path so existing imports (tools.*, models.*, rag_manager, etc.) work
LLM_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, LLM_DIR)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv

# Load env from llm/.env
load_dotenv(os.path.join(LLM_DIR, ".env"))

from tools.five_whys_tool import FiveWhysTool
from tools.tool_registry import ToolRegistry
from tools.fishbone_tool import FishboneTool
from model_comparison.gemini_adapter import GeminiAdapter
from rag_manager import RAGManager
from domain_agents import MechanicalAgent, ElectricalAgent, ProcessAgent

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ── Globals (initialized at startup) ──
registry: ToolRegistry = None
rag: RAGManager = None


# ── Request / Response schemas ──

class AnalyzeRequest(BaseModel):
    equipment_name: str = Field(..., min_length=1)
    failure_description: str = Field(..., min_length=10)
    failure_timestamp: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    error_codes: List[str] = Field(default_factory=list)
    operator_observations: Optional[str] = None


# ── Lifespan: startup / shutdown ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    global registry, rag

    logger.info("Starting up — initializing RCA components...")

    # 1. Gemini LLM adapter
    gemini = GeminiAdapter()
    logger.info("Gemini adapter ready")

    # 2. RAG (Weaviate)
    rag = RAGManager()
    rag.connect()
    logger.info("RAG manager connected")

    # 3. Tools
    five_whys = FiveWhysTool(llm_adapter=gemini, rag_manager=rag)
    fishbone = FishboneTool(llm_adapter=gemini, rag_manager=rag)
    registry = ToolRegistry()
    registry.register_tool("5_whys", five_whys)
    registry.register_tool("fishbone", fishbone)

    # 4. Domain agents
    registry.register_tool("mechanical_agent", MechanicalAgent(llm_adapter=gemini, rag_manager=rag))
    registry.register_tool("electrical_agent", ElectricalAgent(llm_adapter=gemini, rag_manager=rag))
    registry.register_tool("process_agent", ProcessAgent(llm_adapter=gemini, rag_manager=rag))
    
    # 5. Integrated RCA pipeline (domain agents + 5 whys + fishbone)
    from tools.integrated_rca_tool import IntegratedRCATool
    integrated_rca = IntegratedRCATool(llm_adapter=gemini, rag_manager=rag)
    registry.register_tool("integrated_rca", integrated_rca)
    
    logger.info(f"Tools & agents registered: {registry.list_tools()}")

    yield  # app is running

    # Shutdown
    logger.info("Shutting down — disconnecting RAG...")
    rag.disconnect()


# ── App ──

app = FastAPI(
    title="RCA Analysis API",
    description="Root Cause Analysis system for industrial equipment failures",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helper: build failure text from request ──

def _build_failure_text(req: AnalyzeRequest) -> str:
    failure_text = req.failure_description
    if req.operator_observations:
        failure_text += f"\nOperator observations: {req.operator_observations}"
    if req.error_codes:
        failure_text += f"\nError codes: {', '.join(req.error_codes)}"
    return failure_text


# ── Endpoints ──

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "tools": registry.list_tools() if registry else [],
    }


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """Run RCA analysis (JSON response, no streaming)."""
    if registry is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    logger.info(f"Received analysis request for: {req.equipment_name}")
    failure_text = _build_failure_text(req)

    try:
        result = await registry.execute_tool(
            name="5_whys",
            failure_description=failure_text,
            equipment_name=req.equipment_name,
            symptoms=req.symptoms if req.symptoms else ["unspecified"],
        )

        if result.success:
            return {
                "status": "success",
                "equipment_name": req.equipment_name,
                "analysis_type": "5_whys",
                "execution_time_seconds": round(result.execution_time_seconds, 2),
                "tokens_used": result.tokens_used,
                "cost_usd": round(result.cost_usd, 6),
                "result": result.result,
            }
        else:
            raise HTTPException(status_code=500, detail=f"Analysis failed: {result.error}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-stream")
async def analyze_stream(req: AnalyzeRequest):
    """
    Run RCA analysis with Server-Sent Events for live status updates.

    SSE event types:
      event: status   -> { "message": "..." }
      event: result   -> full analysis JSON
      event: error    -> { "detail": "..." }
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    failure_text = _build_failure_text(req)
    status_queue: asyncio.Queue = asyncio.Queue()

    async def _status_callback(msg: str):
        await status_queue.put(msg)

    async def _run_analysis():
        """Run analysis in background, push result/error to queue when done."""
        try:
            result = await registry.execute_tool(
                name="5_whys",
                failure_description=failure_text,
                equipment_name=req.equipment_name,
                symptoms=req.symptoms if req.symptoms else ["unspecified"],
                status_callback=_status_callback,
            )
            await status_queue.put(("__RESULT__", result))
        except Exception as e:
            await status_queue.put(("__ERROR__", str(e)))

    async def _event_generator():
        # Flush browser / proxy buffers with a ~2 KB padding comment.
        # Browsers won't fire the first onreadystatechange until they've
        # received enough bytes; this ensures the very first real event
        # arrives instantly.
        padding = ":" + " " * 2048 + "\n\n"
        yield padding
        await asyncio.sleep(0)

        # Start analysis as a background task
        task = asyncio.create_task(_run_analysis())

        # Yield SSE events as they arrive
        while True:
            item = await status_queue.get()

            # Final result
            if isinstance(item, tuple) and item[0] == "__RESULT__":
                result = item[1]
                if result.success:
                    payload = json.dumps({
                        "status": "success",
                        "equipment_name": req.equipment_name,
                        "analysis_type": "5_whys",
                        "execution_time_seconds": round(result.execution_time_seconds, 2),
                        "tokens_used": result.tokens_used,
                        "cost_usd": round(result.cost_usd, 6),
                        "result": result.result,
                    }, default=str)
                    yield f"event: result\ndata: {payload}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'detail': result.error})}\n\n"
                break

            # Error
            if isinstance(item, tuple) and item[0] == "__ERROR__":
                yield f"event: error\ndata: {json.dumps({'detail': item[1]})}\n\n"
                break

            # Status update string
            yield f"event: status\ndata: {json.dumps({'message': item})}\n\n"
            await asyncio.sleep(0)  # force flush each event immediately

        await task  # ensure task is fully done

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/analyze-integrated-stream")
async def analyze_integrated_stream(req: AnalyzeRequest):
    """
    Run integrated RCA pipeline (domain agents + 5 Whys) with SSE streaming.
    
    Pipeline:
    1. Domain agents analyze in parallel
    2. Aggregate domain insights
    3. Enhanced 5 Whys with domain context
    4. Return comprehensive root cause
    
    SSE event types:
      event: status   -> { "message": "..." }
      event: result   -> full analysis JSON
      event: error    -> { "detail": "..." }
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    failure_text = _build_failure_text(req)
    status_queue: asyncio.Queue = asyncio.Queue()

    async def _status_callback(msg: str):
        await status_queue.put(msg)

    async def _run_analysis():
        """Run integrated analysis in background."""
        try:
            result = await registry.execute_tool(
                name="integrated_rca",
                failure_description=failure_text,
                equipment_name=req.equipment_name,
                symptoms=req.symptoms if req.symptoms else ["unspecified"],
                status_callback=_status_callback,
            )
            await status_queue.put(("__RESULT__", result))
        except Exception as e:
            await status_queue.put(("__ERROR__", str(e)))

    async def _event_generator():
        # Flush browser / proxy buffers
        padding = ":" + " " * 2048 + "\n\n"
        yield padding
        await asyncio.sleep(0)

        # Start analysis as a background task
        task = asyncio.create_task(_run_analysis())

        # Yield SSE events as they arrive
        while True:
            item = await status_queue.get()

            # Final result
            if isinstance(item, tuple) and item[0] == "__RESULT__":
                result = item[1]
                if result.success:
                    payload = json.dumps({
                        "status": "success",
                        "equipment_name": req.equipment_name,
                        "analysis_type": "integrated_rca",
                        "execution_time_seconds": round(result.execution_time_seconds, 2),
                        "tokens_used": result.tokens_used,
                        "cost_usd": round(result.cost_usd, 6),
                        "result": result.result,
                    }, default=str)
                    yield f"event: result\ndata: {payload}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'detail': result.error})}\n\n"
                break

            # Error
            if isinstance(item, tuple) and item[0] == "__ERROR__":
                yield f"event: error\ndata: {json.dumps({'detail': item[1]})}\n\n"
                break

            # ── Intermediate: domain insights ready ──────────────────────────
            # Emitted as soon as domain agents finish, before 5 Whys starts.
            if isinstance(item, tuple) and item[0] == "__DOMAIN_INSIGHTS__":
                # Use mode='json' to serialize datetimes as ISO strings (not Python datetime objects)
                payload = json.dumps({"domain_insights": item[1]}, default=str)
                yield f"event: domain_insights\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

            # Status update string
            yield f"event: status\ndata: {json.dumps({'message': item})}\n\n"
            await asyncio.sleep(0)  # force flush each event immediately

        await task  # ensure task is fully done


    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Helper: auto-route to domain agents based on failure keywords ──

AGENT_ROUTING = {
    "mechanical_agent": [
        "bearing", "vibration", "mechanical", "wear", "alignment",
        "shaft", "coupling", "lubrication", "fatigue", "corrosion",
        "gearbox", "impeller", "belt", "chain", "girth gear",
    ],
    "electrical_agent": [
        "motor", "electrical", "power", "current", "voltage",
        "interlock", "relay", "trip", "overcurrent", "VFD",
        "winding", "insulation", "contactor", "circuit", "fuse",
    ],
    "process_agent": [
        "temperature", "pressure", "flow", "process", "combustion",
        "emission", "feed", "composition", "setpoint", "heat",
        "flame", "damper", "draft", "kiln speed",
    ],
}


def _route_agents(req: AnalyzeRequest) -> List[str]:
    """Pick which domain agents to run based on failure keywords."""
    text = (
        f"{req.failure_description} {' '.join(req.symptoms)} "
        f"{req.operator_observations or ''}"
    ).lower()

    selected = []
    for agent_name, keywords in AGENT_ROUTING.items():
        if any(kw in text for kw in keywords):
            selected.append(agent_name)

    # Default to mechanical if nothing matched
    if not selected:
        selected.append("mechanical_agent")

    return selected


@app.post("/analyze-domain")
async def analyze_domain(req: AnalyzeRequest):
    """
    Run domain-specific agent analysis.

    Auto-routes to the right agent(s) based on failure keywords,
    runs them in parallel, and returns combined results.
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    failure_text = _build_failure_text(req)
    agent_names = _route_agents(req)
    logger.info(f"Domain analysis routed to: {agent_names}")

    async def _run_agent(name: str):
        return name, await registry.execute_tool(
            name=name,
            failure_description=failure_text,
            equipment_name=req.equipment_name,
            symptoms=req.symptoms if req.symptoms else ["unspecified"],
        )

    try:
        tasks = [_run_agent(name) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        domain_results = []
        for item in results:
            if isinstance(item, Exception):
                logger.error(f"Agent error: {item}")
                continue
            name, result = item
            if result.success:
                domain_results.append({
                    "agent": name,
                    "execution_time_seconds": round(result.execution_time_seconds, 2),
                    "tokens_used": result.tokens_used,
                    "cost_usd": round(result.cost_usd, 6),
                    "result": result.result,
                })

        return {
            "status": "success",
            "equipment_name": req.equipment_name,
            "agents_used": agent_names,
            "domain_analyses": domain_results,
        }

    except Exception as e:
        logger.error(f"Domain analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-domain-stream")
async def analyze_domain_stream(req: AnalyzeRequest):
    """
    Run domain agent analysis with SSE streaming for live status updates.
    """
    if registry is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    failure_text = _build_failure_text(req)
    agent_names = _route_agents(req)
    status_queue: asyncio.Queue = asyncio.Queue()

    async def _status_callback(msg: str):
        await status_queue.put(msg)

    async def _run_agents():
        try:
            async def _run_one(name: str):
                return name, await registry.execute_tool(
                    name=name,
                    failure_description=failure_text,
                    equipment_name=req.equipment_name,
                    symptoms=req.symptoms if req.symptoms else ["unspecified"],
                    status_callback=_status_callback,
                )

            tasks = [_run_one(n) for n in agent_names]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            domain_results = []
            for item in results:
                if isinstance(item, Exception):
                    continue
                name, result = item
                if result.success:
                    domain_results.append({
                        "agent": name,
                        "execution_time_seconds": round(result.execution_time_seconds, 2),
                        "tokens_used": result.tokens_used,
                        "cost_usd": round(result.cost_usd, 6),
                        "result": result.result,
                    })

            await status_queue.put(("__RESULT__", {
                "status": "success",
                "equipment_name": req.equipment_name,
                "agents_used": agent_names,
                "domain_analyses": domain_results,
            }))
        except Exception as e:
            await status_queue.put(("__ERROR__", str(e)))

    async def _event_generator():
        padding = ":" + " " * 2048 + "\n\n"
        yield padding
        await asyncio.sleep(0)

        task = asyncio.create_task(_run_agents())

        while True:
            item = await status_queue.get()

            if isinstance(item, tuple) and item[0] == "__RESULT__":
                payload = json.dumps(item[1], default=str)
                yield f"event: result\ndata: {payload}\n\n"
                break

            if isinstance(item, tuple) and item[0] == "__ERROR__":
                yield f"event: error\ndata: {json.dumps({'detail': item[1]})}\n\n"
                break

            yield f"event: status\ndata: {json.dumps({'message': item})}\n\n"
            await asyncio.sleep(0)

        await task

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Run ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
