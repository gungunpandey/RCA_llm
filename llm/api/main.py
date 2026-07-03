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
from rag_manager import RAGManager, extract_query_keywords
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


# ── Uploads ──
# Shared uploads volume (see docker-compose.yml). Falls back to the app's
# static/uploads dir for local (non-Docker) development.
_DEFAULT_UPLOADS = (
    "/app/static/uploads"
    if os.path.isdir("/app/static/uploads")
    else os.path.join(LLM_DIR, "..", "app", "static", "uploads")
)
UPLOADS_DIR = os.getenv("UPLOADS_DIR", _DEFAULT_UPLOADS)


def resolve_uploaded_image(image_name: Optional[str]) -> Optional[str]:
    """Resolve an uploaded image filename to a path inside UPLOADS_DIR.

    Any directory components are stripped, so clients can only reference
    files that live in the uploads directory — never arbitrary paths.
    """
    if not image_name:
        return None
    name = os.path.basename(image_name.replace("\\", "/"))
    if not name:
        return None
    path = os.path.join(UPLOADS_DIR, name)
    if not os.path.isfile(path):
        logger.warning(f"Uploaded image not found in uploads dir: {name}")
        return None
    return path


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
    image_name: Optional[str] = None   # filename of uploaded image (resolved inside UPLOADS_DIR)
    image_desc: Optional[str] = None   # user description of image
    pdf_text: Optional[str] = None     # extracted text from uploaded PDF document
    skip_history: bool = False         # if True, skip the historical incident lookup


class FinalizeRequest(BaseModel):
    """Phase 2 request — submits user answers and resumes the cached RCA."""
    session_id: str = Field(..., min_length=1)
    clarifications: List[ClarificationAnswer] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    # Optional uploads: [{type:'image'|'pdf', name, data(base64), mime}]
    attachments: Optional[List[Dict[str, Any]]] = None


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
                image_path=resolve_uploaded_image(req.image_name),
                image_desc=req.image_desc,
                skip_history=req.skip_history,
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
    # Phase-1 contract: a pre-computed, verified analysis bundle plus a
    # rule-based fallback. All fields optional so a malformed request degrades
    # rather than 422-ing the dashboard.
    analysis_bundle: Optional[Dict[str, Any]] = None
    deterministic_insights: Optional[List[Dict[str, Any]]] = None


@app.post("/dashboard-insights")
async def generate_dashboard_insights(req: DashboardDataRequest):
    """Narrate the pre-computed analysis bundle as insight cards.

    IMPORTANT: the LLM does NOT compute statistics. Every number is already in
    `analysis_bundle`; the model only rephrases verified facts into clear,
    actionable language. If anything goes wrong we return the deterministic
    insights the app already computed, so the panel always shows correct data.
    """
    fallback = req.deterministic_insights or []

    if llm_adapter is None or not req.analysis_bundle:
        # Nothing to narrate with, or no model — hand back the verified facts.
        return {"status": "success", "source": "rule_based", "insights": fallback}

    bundle_json = json.dumps(req.analysis_bundle, default=str)
    fallback_json = json.dumps(fallback, default=str)

    prompt = f"""You are ProdAI, a plant reliability analyst. You are given a VERIFIED analysis bundle that was computed deterministically from the maintenance database. Write 3-6 concise, actionable insight cards for a plant manager.

STRICT RULES:
1. Use ONLY the numbers, names, and facts present in the ANALYSIS BUNDLE below. NEVER invent, estimate, round differently, or extrapolate any number, percentage, equipment name, or date.
2. If a metric is missing or marked "reliable": false, do NOT present it as a confident trend. You may omit it, or mention it only as "early/low-confidence signal".
3. If "data_quality.low_volume_warning" is true, include exactly one caution card noting the sample is small and trends are indicative only.
4. Prefer the most decision-relevant items: un-implemented CAPA recurrences, repeat failures, risk_alerts, capa_effectiveness, then reliable equipment anomalies and correlations.
5. For risk_alerts, frame them as elevated risk based on recent activity — NEVER as a guaranteed prediction or forecast.
6. Every card must be self-explanatory to a manager who hasn't seen the data. NEVER write a bare "X → Y"; always say what the numbers mean, e.g. "up from 7 breakdowns last period to 8 now". Label every number with its unit/meaning (breakdowns, hours, %).
7. Order cards by importance: put the single most critical issue first.
8. Keep each card to one clear sentence. You may use <strong>...</strong> for emphasis. Do not output any number that is not in the bundle.

Assign each card a "type": "danger" (critical/repeat failures/overdue), "warning" (escalating), "success" (improvement), or "info" (status/context).
Choose a fitting "icon" emoji (e.g. 🏭, 🔧, 🔁, 📈, 🚧, ⚠️, ✅, ℹ️, 📍).

ANALYSIS BUNDLE (verified facts — your single source of truth):
{bundle_json}

For reference, here is a correct rule-based rendering of the same facts. You may improve the wording and prioritization, but you must not contradict its numbers:
{fallback_json}

Return VALID JSON ONLY (no markdown, no backticks):
{{"insights": [{{"icon": "...", "text": "...", "type": "..."}}]}}
"""
    try:
        content = await llm_adapter.generate(prompt, json_mode=True)
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
                for val in parsed.values():
                    if isinstance(val, list):
                        insights = val
                        break
        elif isinstance(parsed, list):
            insights = parsed

        # Validate shape; if the model returned junk, use the verified fallback.
        clean = [
            i for i in insights
            if isinstance(i, dict) and i.get("text") and i.get("type")
        ]
        if not clean:
            return {"status": "success", "source": "rule_based", "insights": fallback}
        return {"status": "success", "source": "ai", "insights": clean}
    except Exception as e:
        logger.error(f"Dashboard insights generation failed: {e}", exc_info=True)
        # Never 500 — the dashboard falls back to verified rule-based insights.
        return {"status": "success", "source": "rule_based", "insights": fallback}


class ReliabilityNarrativeRequest(BaseModel):
    analysis_bundle: Optional[Dict[str, Any]] = None
    analytics: Optional[Dict[str, Any]] = None
    deterministic_narrative: Optional[Dict[str, Any]] = None


@app.post("/reliability-review-narrative")
async def reliability_review_narrative(req: ReliabilityNarrativeRequest):
    """Write the prose blocks for the reliability-review PPTX (executive summary,
    root-cause analysis, recommended actions, management decisions).

    Numbers are NOT computed here — the model rewrites/expands the deterministic
    narrative using only facts in the verified bundle/analytics. Falls back to
    the deterministic narrative on any failure.
    """
    fallback = req.deterministic_narrative or {}
    if llm_adapter is None or not req.analysis_bundle:
        return {"status": "success", "source": "rule_based", "narrative": fallback}

    bundle_json = json.dumps(req.analysis_bundle, default=str)
    analytics_json = json.dumps(req.analytics or {}, default=str)
    fallback_json = json.dumps(fallback, default=str)

    prompt = f"""You are ProdAI, a plant reliability analyst writing a management reliability review. Produce concise, board-ready prose for four slide sections.

STRICT RULES:
1. Use ONLY facts/numbers present in the VERIFIED DATA below. Never invent or alter any number, name, percentage, or date.
2. Write for executives: punchy and scannable. Each bullet ONE short line, ~12 words max, and lead with the number/asset (e.g. "Raw Water Pump: 15 failures — schedule bearing inspection").
3. "recommended_actions" must be concrete maintenance/engineering actions. "management_decisions" must be decisions that need a manager's sign-off (budget, staffing, prioritization, deadlines).
4. Frame any risk as elevated risk based on recent activity, never a guaranteed forecast.
5. 3-5 bullets per section. No filler, no repetition of the charts — add insight.

VERIFIED ANALYSIS BUNDLE:
{bundle_json}

VERIFIED ANALYTICS (trends, top equipment, root-cause categories):
{analytics_json}

Deterministic baseline you may improve on (do not contradict its numbers):
{fallback_json}

Return VALID JSON ONLY (no markdown), with these exact keys, each a list of strings:
{{"executive_summary": [], "root_cause_analysis": [], "recommended_actions": [], "management_decisions": []}}
"""
    try:
        content = await llm_adapter.generate(prompt, json_mode=True)
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return {"status": "success", "source": "rule_based", "narrative": fallback}
        out = {}
        for key in ("executive_summary", "root_cause_analysis",
                    "recommended_actions", "management_decisions"):
            val = parsed.get(key)
            out[key] = [str(x) for x in val] if isinstance(val, list) and val else fallback.get(key, [])
        return {"status": "success", "source": "ai", "narrative": out}
    except Exception as e:
        logger.error(f"Reliability narrative generation failed: {e}", exc_info=True)
        return {"status": "success", "source": "rule_based", "narrative": fallback}


def _process_attachments(attachments, user_text):
    """Turn uploaded files into text context: images via qwen vision
    (analyze_image, qwen3.5 -> qwen2.5 fallback), PDFs via text extraction.
    Returns (context_text, summary_list_for_ui)."""
    import base64
    import tempfile
    blocks, used = [], []
    for att in (attachments or []):
        kind = (att.get("type") or "").lower()
        name = att.get("name") or "attachment"
        data = att.get("data") or ""
        if data.strip().startswith("data:") and "," in data:
            data = data.split(",", 1)[1]   # strip data URL prefix
        try:
            raw = base64.b64decode(data)
        except Exception:
            continue

        if kind == "image":
            try:
                from tools.image_analysis_tool import analyze_image
                ext = os.path.splitext(name)[1].lower() or ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(raw)
                    tmp_path = tmp.name
                try:
                    r = analyze_image(tmp_path, user_description=user_text)
                finally:
                    try: os.unlink(tmp_path)
                    except OSError: pass
                blocks.append(
                    f"Image '{name}': component={r.get('component')}, "
                    f"damage={r.get('damage_type')}, severity={r.get('severity')}. "
                    f"{r.get('ai_description', '')}"
                )
                used.append({"type": "image", "name": name})
            except Exception as e:
                logger.warning(f"Image attachment analysis failed: {e}")
        elif kind == "pdf":
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                text = "\n".join((p.extract_text() or "") for p in reader.pages[:30]).strip()[:6000]
                if text:
                    blocks.append(f"PDF '{name}' contents:\n{text}")
                    used.append({"type": "pdf", "name": name})
            except Exception as e:
                logger.warning(f"PDF attachment extraction failed: {e}")

    return ("\n\n".join(blocks), used)


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if llm_adapter is None:
        raise HTTPException(status_code=503, detail="Server still initializing")
    
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
    latest_message = req.messages[-1].content

    # 0. Process uploaded attachments (images via qwen vision, PDFs as text).
    attachment_context, attachment_used = "", []
    if req.attachments:
        attachment_context, attachment_used = _process_attachments(req.attachments, latest_message)

    # 1. Retrieve manuals context (RAG). Strip the question to keywords first so
    #    BM25 focuses on the equipment/subject, and pull a few more chunks.
    rag_text = ""
    manual_sources = []
    if rag is not None:
        try:
            keywords = extract_query_keywords(latest_message)
            rag_docs = await rag.retrieve_equipment_context(keywords, [], top_k=8)
            rag_text = rag.format_context_for_llm(rag_docs)
            # Build a de-duplicated source list (manual + page) for the UI.
            seen = set()
            for d in rag_docs:
                key = (d.source, d.metadata.get("page"))
                if d.source and d.source != "Unknown" and key not in seen:
                    seen.add(key)
                    manual_sources.append({"title": d.source, "page": d.metadata.get("page")})
            manual_sources = manual_sources[:6]
        except Exception as e:
            logger.warning(f"RAG retrieval failed in chat: {e}")
            rag_text = ""

    # 2. Retrieve historical incidents context (Neo4j)
    history_text = ""
    try:
        _, history_text = await history_matcher.find_and_format("", latest_message, top_k=2)
    except Exception as e:
        logger.warning(f"History lookup failed in chat: {e}")
        history_text = ""

    # Combine reference material (used silently for grounding).
    attach_block = f"\n\nUSER-ATTACHED FILES (analyze and use directly):\n{attachment_context}" if attachment_context else ""
    grounding_context = f"PLANT MANUAL REFERENCE:\n{rag_text or '(none found)'}\n\nPLANT INCIDENT HISTORY:\n{history_text or '(none found)'}{attach_block}"

    # Conversation history
    history_lines = []
    for msg in req.messages[:-1]:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"{role_label}: {msg.content}")
    conversation_history = "\n".join(history_lines) if history_lines else "(No previous conversation)"

    system_msg = (
        "You are ProdAI, an expert assistant for industrial plant maintenance, "
        "reliability and root cause analysis. You answer as a single confident "
        "expert voice."
    )

    prompt = f"""Use the reference material below (plant manuals, incident history) and, when needed, current web knowledge to answer the user's question accurately and practically.

REFERENCE MATERIAL (for your grounding — do NOT quote or mention it):
{grounding_context}

CONVERSATION SO FAR:
{conversation_history}

RULES:
- Answer directly as one expert voice. NEVER mention manuals, excerpts, context, retrieval, databases, sources, or where the information came from. Never say information "is not available" or "wasn't provided" — just give the best correct answer. (Exception: you MAY naturally refer to a file the user attached in this message, e.g. "the photo you shared".)
- Prefer specifics relevant to this plant's equipment when the reference material supports them; otherwise give accurate industry best-practice / standards-based guidance.
- Be accurate. If a value genuinely depends on specifics, give typical ranges and state what determines the exact figure.
- Format the reply in clean Markdown for readability: short **bold** labels, bullet points, and small tables where useful. Keep it concise and skimmable. Do NOT use large headings (no '#'/'##'); use bold text instead.

User question: {latest_message}"""

    try:
        web_citations = []
        if hasattr(llm_adapter, "generate_with_web"):
            try:
                content, web_citations = await llm_adapter.generate_with_web(prompt, system=system_msg)
            except Exception as web_err:
                # Web plugin unavailable/errored — fall back to a normal answer.
                logger.warning(f"Web-augmented chat failed, falling back: {web_err}")
                content = await llm_adapter.generate(prompt)
                web_citations = []
        else:
            content = await llm_adapter.generate(prompt)
        return {
            "status": "success",
            "reply": content,
            "sources": {"manuals": manual_sources, "web": web_citations, "attachments": attachment_used},
            "has_rag_context": bool(manual_sources),
            "has_history_context": bool(history_text),
        }
    except Exception as e:
        logger.error(f"Chat generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Run ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
