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

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load env from llm/.env
load_dotenv(os.path.join(LLM_DIR, ".env"))

from tools.five_whys_tool import FiveWhysTool
from tools.tool_registry import ToolRegistry
from tools.fishbone_tool import FishboneTool
from tools.integrated_rca_tool import IntegratedRCATool
from rag_manager import RAGManager
from domain_agents import MechanicalAgent, ElectricalAgent, ProcessAgent
from models.tool_results import ClarificationAnswer
from tools import history_matcher
from api.session_cache import (
    SessionCache,
    SessionNotFoundError,
    SessionExpiredError,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ── Globals (initialized at startup) ──
registry: ToolRegistry = None
rag: RAGManager = None
active_llm_model: str = "unknown"
session_cache: SessionCache = None
integrated_rca: IntegratedRCATool = None
llm_adapter = None


# ── Request / Response schemas ──

class AnalyzeRequest(BaseModel):
    equipment_name: str = Field(..., min_length=1)
    failure_description: str = Field(..., min_length=10)
    # Legacy field kept for backward compat
    failure_timestamp: Optional[str] = None
    # New occurrence window fields
    occurrence_from: Optional[str] = None
    occurrence_to: Optional[str] = None
    # New meta fields
    department: Optional[str] = None
    total_downtime: Optional[str] = None
    production_loss: Optional[str] = None
    impact_top_line: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    error_codes: List[str] = Field(default_factory=list)
    operator_observations: Optional[str] = None
    image_path: Optional[str] = None   # absolute path to uploaded image
    image_desc: Optional[str] = None   # user description of image
    pdf_text: Optional[str] = None     # extracted text from uploaded PDF document


class FinalizeRequest(BaseModel):
    """Phase 2 request — submits user answers and resumes the cached RCA."""
    session_id: str = Field(..., min_length=1)
    clarifications: List[ClarificationAnswer] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


# ── Lifespan: startup / shutdown ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    global registry, rag, active_llm_model, session_cache, integrated_rca, llm_adapter

    logger.info("Starting up — initializing RCA components...")

    # 1. LLM adapter — controlled by LLM_PROVIDER env var
    llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if llm_provider == "openrouter":
        from model_comparison.openrouter_adapter import OpenRouterAdapter
        llm_adapter = OpenRouterAdapter()
        active_llm_model = f"OpenRouter/{llm_adapter.model_name}"
        logger.info(f"OpenRouter adapter ready (model: {llm_adapter.model_name})")
    else:
        from model_comparison.gemini_adapter import GeminiAdapter
        llm_adapter = GeminiAdapter()
        active_llm_model = f"Gemini/{llm_adapter.model_name}"
        logger.info(f"Gemini adapter ready (model: {llm_adapter.model_name})")

    gemini = llm_adapter  # keep local alias so existing code below stays unchanged

    # 2. RAG (Weaviate)
    rag = RAGManager()
    try:
        rag.connect()
        logger.info("RAG manager connected")
    except Exception as err:
        logger.warning(f"RAG manager failed to connect on startup: {err}. Continuing in offline mode.")


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
    
    # 5. Integrated RCA pipeline (domain agents + 5 whys + fishbone + chatbot)
    integrated_rca = IntegratedRCATool(llm_adapter=gemini, rag_manager=rag)
    registry.register_tool("integrated_rca", integrated_rca)

    # 6. Session cache for the two-phase /analyze-prepare → /analyze-finalize flow
    session_cache = SessionCache()
    logger.info(f"Session cache initialized (TTL: {session_cache.ttl_seconds}s)")

    logger.info(f"Tools & agents registered: {registry.list_tools()}")
    llm_adapter = gemini

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
    allow_origins=["*"],       # allow all origins in local dev
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)



# ── Helper: build failure text from request ──

def _build_failure_text(req: AnalyzeRequest) -> str:
    failure_text = req.failure_description
    if req.occurrence_from or req.occurrence_to:
        occurrence_window = " to ".join(
            [value for value in [req.occurrence_from, req.occurrence_to] if value]
        )
        failure_text += f"\nOccurrence window: {occurrence_window}"
    if req.department:
        failure_text += f"\nDepartment: {req.department}"
    if req.total_downtime:
        failure_text += f"\nTotal downtime: {req.total_downtime}"
    if req.production_loss:
        failure_text += f"\nProduction loss: {req.production_loss}"
    if req.impact_top_line:
        failure_text += f"\nOperational impact: {req.impact_top_line}"
    if req.operator_observations:
        failure_text += f"\nOperator observations: {req.operator_observations}"
    if req.error_codes:
        failure_text += f"\nError codes: {', '.join(req.error_codes)}"
    if req.image_desc:
        failure_text += f"\nImage description: {req.image_desc}"
    if req.pdf_text:
        failure_text += f"\n\nATTACHED DOCUMENT CONTENT:\n{req.pdf_text}"
    return failure_text


# ── Endpoints ──

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "llm_model": active_llm_model,
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


@app.post("/analyze-prepare-stream")
async def analyze_prepare_stream(req: AnalyzeRequest):
    """
    Phase 1 of the two-phase RCA pipeline.

    Runs historical lookup, domain agents, image analysis, and generates
    follow-up questions for the mandatory chatbot step. Caches the
    intermediate state under a session_id; the frontend must then submit
    the user's answers to /analyze-finalize-stream to complete the RCA.

    SSE event types:
      event: status                -> {"message": "..."}
      event: history_matches       -> {"history_matches": [...]}
      event: domain_insights       -> {"domain_insights": {...}}
      event: image_analysis        -> {"image_analysis": {...}}
      event: clarifying_questions  -> {"questions": [...]}
      event: prepare_complete      -> {"session_id", "expires_at"}
      event: error                 -> {"detail": "..."}
    """
    if integrated_rca is None or session_cache is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    failure_text = _build_failure_text(req)
    status_queue: asyncio.Queue = asyncio.Queue()

    async def _status_callback(msg):
        await status_queue.put(msg)

    async def _run_prepare():
        try:
            result = await integrated_rca.run_prepare(
                failure_description=failure_text,
                equipment_name=req.equipment_name,
                symptoms=req.symptoms if req.symptoms else ["unspecified"],
                status_callback=_status_callback,
                image_path=req.image_path,
                image_desc=req.image_desc,
            )
            await status_queue.put(("__RESULT__", result))
        except Exception as e:
            await status_queue.put(("__ERROR__", str(e)))

    async def _event_generator():
        # Flush browser / proxy buffers
        padding = ":" + " " * 2048 + "\n\n"
        yield padding
        await asyncio.sleep(0)

        task = asyncio.create_task(_run_prepare())

        while True:
            item = await status_queue.get()

            # Final prepare result — cache the session and emit prepare_complete
            if isinstance(item, tuple) and item[0] == "__RESULT__":
                result = item[1]
                if not result.success:
                    yield f"event: error\ndata: {json.dumps({'detail': result.error})}\n\n"
                    break
                p = result.result
                session = session_cache.create(
                    equipment_name=p["equipment_name"],
                    failure_text=p["failure_text"],
                    symptoms=p["symptoms"],
                    domain_insights=p["domain_insights"],
                    history_context=p["history_context"],
                    history_matches=p["history_matches"],
                    image_analysis=p["image_analysis"],
                    selected_agents=p["selected_agents"],
                    questions=p["questions"],
                )
                payload = json.dumps({
                    "session_id": session.session_id,
                    "expires_at": session_cache.expires_at(session),
                }, default=str)
                yield f"event: prepare_complete\ndata: {payload}\n\n"
                break

            if isinstance(item, tuple) and item[0] == "__ERROR__":
                yield f"event: error\ndata: {json.dumps({'detail': item[1]})}\n\n"
                break

            # Intermediate domain events — passthrough to named SSE events
            if isinstance(item, tuple) and item[0] == "__HISTORY_MATCHES__":
                payload = json.dumps({"history_matches": item[1]}, default=str)
                yield f"event: history_matches\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

            if isinstance(item, tuple) and item[0] == "__DOMAIN_INSIGHTS__":
                payload = json.dumps({"domain_insights": item[1]}, default=str)
                yield f"event: domain_insights\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

            if isinstance(item, tuple) and item[0] == "__IMAGE_ANALYSIS__":
                payload = json.dumps({"image_analysis": item[1]}, default=str)
                yield f"event: image_analysis\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

            if isinstance(item, tuple) and item[0] == "__CLARIFYING_QUESTIONS__":
                payload = json.dumps({"questions": item[1]}, default=str)
                yield f"event: clarifying_questions\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

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


@app.post("/analyze-finalize-stream")
async def analyze_finalize_stream(req: FinalizeRequest):
    """
    Phase 2 of the two-phase RCA pipeline.

    Loads the cached session created by /analyze-prepare-stream, validates
    that the user has answered every clarifying question, then runs 5 Whys
    + Fishbone with the user's answers folded into the failure context.

    SSE event types:
      event: status  -> {"message": "..."}
      event: result  -> full analysis JSON (same shape as legacy integrated RCA)
      event: error   -> {"detail": "..."}

    HTTP errors:
      404 if session_id is unknown
      410 if session_id has expired
      400 if clarifications are missing or incomplete
    """
    if integrated_rca is None or session_cache is None:
        raise HTTPException(status_code=503, detail="Server still initializing")

    try:
        session = session_cache.get(req.session_id)
    except SessionExpiredError:
        raise HTTPException(status_code=410, detail=f"Session expired: {req.session_id}")
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {req.session_id}")

    # Mandatory chatbot enforcement
    if session.questions:
        if not req.clarifications:
            raise HTTPException(
                status_code=400,
                detail="Clarifications are required — this session has unanswered questions",
            )
        provided_ids = {c.question_id for c in req.clarifications}
        expected_ids = {q.id for q in session.questions}
        missing = expected_ids - provided_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing answers for question ids: {sorted(missing)}",
            )

    status_queue: asyncio.Queue = asyncio.Queue()

    async def _status_callback(msg):
        await status_queue.put(msg)

    async def _run_finalize():
        try:
            result = await integrated_rca.run_finalize(
                equipment_name=session.equipment_name,
                failure_text=session.failure_text,
                symptoms=session.symptoms,
                domain_insights=session.domain_insights,
                history_context=session.history_context,
                image_analysis=session.image_analysis,
                selected_agents=session.selected_agents,
                clarifications=req.clarifications,
                history_matches=session.history_matches,   # for CAPA — past CAPAs
                status_callback=_status_callback,
            )
            await status_queue.put(("__RESULT__", result))
        except Exception as e:
            await status_queue.put(("__ERROR__", str(e)))
        finally:
            # Evict whether the run succeeded or failed — session is single-use
            session_cache.evict(req.session_id)

    async def _event_generator():
        padding = ":" + " " * 2048 + "\n\n"
        yield padding
        await asyncio.sleep(0)

        task = asyncio.create_task(_run_finalize())

        while True:
            item = await status_queue.get()

            if isinstance(item, tuple) and item[0] == "__RESULT__":
                result = item[1]
                if result.success:
                    payload = json.dumps({
                        "status": "success",
                        "equipment_name": session.equipment_name,
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

            if isinstance(item, tuple) and item[0] == "__ERROR__":
                yield f"event: error\ndata: {json.dumps({'detail': item[1]})}\n\n"
                break

            # Intermediate: CAPA plan ready (before final 'result' event)
            if isinstance(item, tuple) and item[0] == "__CAPA__":
                payload = json.dumps({"capa": item[1]}, default=str)
                yield f"event: capa\ndata: {payload}\n\n"
                await asyncio.sleep(0)
                continue

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


# ── Image Analysis endpoint ──────────────────────────────────────────────────

@app.post("/analyze-image")
async def analyze_image_endpoint(
    image: UploadFile = File(...),
    user_description: Optional[str] = Form(None),
):
    """
    Analyze an uploaded equipment image using the vision model.

    Accepts multipart form: image file + optional text description.
    Returns structured damage analysis JSON.
    """
    import os, tempfile
    from tools.image_analysis_tool import analyze_image, SUPPORTED_EXTENSIONS

    # Validate extension
    ext = os.path.splitext(image.filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        contents = await image.read()
        tmp.write(contents)
        tmp.close()

        result = analyze_image(tmp.name, user_description=user_description)
        result["image_filename"] = image.filename or "upload" + ext
        return {"status": "success", "image_analysis": result}
    except Exception as e:
        logger.error(f"Image analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ── Dashboard Insights endpoint ──────────────────────────────────────────────

class DashboardDataRequest(BaseModel):
    open_breakdowns: int
    capa_overdue: int
    avg_bd_hours: float
    total_failures: int
    top_equipment: List[Dict[str, Any]]
    failures_by_asset: List[Dict[str, Any]]

@app.post("/dashboard-insights")
async def generate_dashboard_insights(req: DashboardDataRequest):
    if llm_adapter is None:
        raise HTTPException(status_code=503, detail="LLM adapter not initialized")
    
    # Construct a prompt for the LLM
    prompt = f"""You are an expert maintenance analyzer. Given the following plant breakdown statistics:
- Open Breakdowns: {req.open_breakdowns}
- CAPA Overdue: {req.capa_overdue}
- Average Breakdown Hours (MTTR): {req.avg_bd_hours} hours
- Total Recent Failures: {req.total_failures}
- Top 5 Failing Equipment: {json.dumps(req.top_equipment)}
- Failures by Plant: {json.dumps(req.failures_by_asset)}

Provide 3 to 5 highly actionable, short, bulleted maintenance insights and recommendations. 
For each recommendation, assign a specific type from:
  - "danger" (for critical overdue tasks or very high failures)
  - "warning" (for escalating indicators)
  - "success" (for good performance metrics)
  - "info" (for general status)

You MUST select an appropriate icon for each (e.g. 🏭, 🔧, 🔴, ⏱️, ⚠️, ✅, 📍).
Format your response as a JSON object containing a list under the key "insights":
{{
  "insights": [
    {{"icon": "...", "text": "...", "type": "..."}}
  ]
}}
Your response must be VALID JSON ONLY. Do not include markdown formatting or backticks (no ```json).
"""
    try:
        content = await llm_adapter.generate(prompt, json_mode=True)
        # Parse it with safety fallbacks
        parsed = json.loads(content)
        insights = []
        if isinstance(parsed, dict):
            if "insights" in parsed:
                insights = parsed["insights"]
            elif "recommendations" in parsed:
                insights = parsed["recommendations"]
            elif "icon" in parsed and "text" in parsed and "type" in parsed:
                insights = [parsed]
            else:
                # Use the first list type value we find
                for val in parsed.values():
                    if isinstance(val, list):
                        insights = val
                        break
        elif isinstance(parsed, list):
            insights = parsed
            
        return {"status": "success", "insights": insights}
    except Exception as e:
        logger.error(f"Dashboard insights generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if llm_adapter is None:
        raise HTTPException(status_code=503, detail="Server still initializing")
    
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
    latest_message = req.messages[-1].content
    
    # 1. Retrieve manuals context (RAG)
    rag_text = ""
    if rag is not None:
        try:
            rag_docs = await rag.retrieve_equipment_context(latest_message, [], top_k=4)
            rag_text = rag.format_context_for_llm(rag_docs)
        except Exception as e:
            logger.warning(f"RAG retrieval failed in chat: {e}")
            rag_text = "No manual documents retrieved due to an error."
            
    # 2. Retrieve historical incidents context (Neo4j)
    history_text = ""
    try:
        _, history_text = await history_matcher.find_and_format("", latest_message, top_k=2)
    except Exception as e:
        logger.warning(f"History lookup failed in chat: {e}")
        history_text = "No historical incident records retrieved due to an error."
        
    # Combine context
    grounding_context = f"--- OEM MANUAL EXCERPTS ---\n{rag_text}\n\n{history_text}"
    
    # Format history
    history_lines = []
    for msg in req.messages[:-1]:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"{role_label}: {msg.content}")
    conversation_history = "\n".join(history_lines) if history_lines else "(No previous conversation)"
    
    # Build prompt
    prompt = f"""You are ProdAI, a helpful conversational AI assistant for industrial plant maintenance and root cause analysis (RCA).
You help engineers diagnose equipment failures, search OEM manual documentation, understand historical breakdowns, and suggest corrective and preventive actions (CAPA).

Use the following context to ground your answer. The context contains matching excerpts from OEM equipment manuals and details of similar past incidents:

{grounding_context}

If the context does not contain the answer, use your general industrial engineering knowledge, but make sure to distinguish between information retrieved from verified plant records/manuals and general recommendations. Be concise, professional, and practical.

CONVERSATION HISTORY:
{conversation_history}

User: {latest_message}
Assistant:"""

    try:
        content = await llm_adapter.generate(prompt)
        return {
            "status": "success",
            "reply": content,
            "has_rag_context": bool(rag_text and "No manual documents" not in rag_text),
            "has_history_context": bool(history_text and "No historical incident" not in history_text)
        }
    except Exception as e:
        logger.error(f"Chat generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Run ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
