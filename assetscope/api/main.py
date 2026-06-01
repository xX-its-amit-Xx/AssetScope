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
    QueryRequest,
    QueryResponse,
    ToolInfo,
)
from assetscope.config import get_settings
from assetscope.tools import build_default_registry


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


_LOCAL_BACKENDS = {"local", "openai", "llama", "llamacpp", "ollama", "vllm"}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    backend = (s.llm_backend or "anthropic").lower()
    if backend in _LOCAL_BACKENDS:
        model, configured = s.llm_model, bool(s.llm_base_url)
    else:
        backend, model, configured = "anthropic", s.anthropic_model, s.has_anthropic
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
    return QueryResponse(landscape=landscape)


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
