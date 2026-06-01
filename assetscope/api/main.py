"""FastAPI app: health, tool listing, and the streaming + non-streaming query
endpoints.

The agent loop is synchronous (blocking network I/O), so each query runs in a
worker thread that pushes :class:`AgentEvent`s onto an asyncio queue; the SSE
endpoint drains that queue without blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from assetscope import __version__
from assetscope.agent import AgentEvent, AssetScopeAgent
from assetscope.agent.events import EventType
from assetscope.agent.loop import AgentError
from assetscope.api.schemas import (
    HealthResponse,
    LandscapeSummary,
    QueryRequest,
    QueryResponse,
    ToolInfo,
)
from assetscope.config import get_settings
from assetscope.models import Landscape
from assetscope.storage import get_landscape_store
from assetscope.tools import build_default_registry

_LOCAL_BACKENDS = {"local", "openai", "llama", "llamacpp", "ollama", "vllm"}


def _active_backend_model() -> tuple[str, str]:
    s = get_settings()
    backend = (s.llm_backend or "anthropic").lower()
    if backend in _LOCAL_BACKENDS:
        return backend, s.llm_model
    return "anthropic", s.anthropic_model


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional API-key gate. If ASSETSCOPE_API_KEYS is set, a matching
    X-API-Key header is required; otherwise the endpoint is open."""
    keys = get_settings().api_key_set
    if keys and x_api_key not in keys:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")

logging.basicConfig(level=get_settings().log_level)

app = FastAPI(
    title="AssetScope API",
    version=__version__,
    description="An agentic competitive-intelligence engine for biopharma.",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    backend, model = _active_backend_model()
    configured = bool(s.llm_base_url) if backend in _LOCAL_BACKENDS else s.has_anthropic
    return HealthResponse(
        status="ok",
        version=__version__,
        backend=backend,
        model=model,
        llm_configured=configured,
        anthropic_configured=s.has_anthropic,
    )


@app.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    registry = build_default_registry()
    return [ToolInfo(**schema) for schema in registry.anthropic_schemas()]


@app.post("/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)])
def query(req: QueryRequest) -> QueryResponse:
    """Run the agent to completion and return the final, guarded landscape."""
    try:
        landscape = AssetScopeAgent().run_to_completion(req.query)
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        # e.g. no LLM backend configured (no ANTHROPIC_API_KEY / LLM base URL).
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Agent failed: {exc}") from exc
    id_ = _save_landscape(landscape)
    return QueryResponse(landscape=landscape, id=id_)


def _save_landscape(landscape: Landscape) -> str | None:
    """Persist a landscape to the history store (best-effort; never fatal)."""
    try:
        backend, model = _active_backend_model()
        return get_landscape_store().save(landscape, backend=backend, model=model)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("assetscope.api").warning("Landscape not saved: %s", exc)
        return None


@app.get("/landscapes", response_model=list[LandscapeSummary])
def list_landscapes(limit: int = 50) -> list[LandscapeSummary]:
    """List saved landscapes (most recent first) — the history library."""
    return [LandscapeSummary(**row) for row in get_landscape_store().list(limit=limit)]


@app.get("/landscapes/{landscape_id}", response_model=QueryResponse)
def get_landscape(landscape_id: str) -> QueryResponse:
    """Re-open a saved landscape by id without re-running the agent."""
    data = get_landscape_store().get(landscape_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Landscape not found.")
    return QueryResponse(landscape=Landscape.model_validate(data), id=landscape_id)


@app.post("/query/stream", dependencies=[Depends(require_api_key)])
async def query_stream(req: QueryRequest):
    """Stream the agent's plan, tool calls, guard report and final landscape as SSE."""

    async def event_generator():
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def worker() -> None:
            agent = AssetScopeAgent()
            try:
                for ev in agent.run(req.query):
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
                    # Persist the final landscape and tell the client its id.
                    if ev.type == EventType.LANDSCAPE:
                        try:
                            ls = Landscape.model_validate(ev.data["landscape"])
                            sid = _save_landscape(ls)
                            if sid:
                                loop.call_soon_threadsafe(
                                    queue.put_nowait,
                                    AgentEvent.status("Saved to library.", landscape_id=sid),
                                )
                        except Exception:  # noqa: BLE001
                            pass
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(
                    queue.put_nowait, AgentEvent.error(f"Agent crashed: {exc}")
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield {"event": ev.type.value, "data": ev.model_dump_json()}
            if ev.type == EventType.DONE:
                break

    return EventSourceResponse(event_generator())
