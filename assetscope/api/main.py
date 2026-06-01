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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from assetscope import __version__
from assetscope.agent import AgentEvent, AssetScopeAgent
from assetscope.agent.events import EventType
from assetscope.api.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    ToolInfo,
)
from assetscope.config import get_settings
from assetscope.tools import build_default_registry

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
    return HealthResponse(
        status="ok",
        version=__version__,
        anthropic_configured=s.has_anthropic,
        model=s.anthropic_model,
    )


@app.get("/tools", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    registry = build_default_registry()
    return [ToolInfo(**schema) for schema in registry.anthropic_schemas()]


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Run the agent to completion and return the final, guarded landscape."""
    agent = AssetScopeAgent()
    landscape = agent.run_to_completion(req.query)
    return QueryResponse(landscape=landscape)


@app.post("/query/stream")
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
