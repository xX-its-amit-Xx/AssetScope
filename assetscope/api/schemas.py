"""Request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from assetscope.models import Landscape


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, examples=["competitive landscape for oral GLP-1 agonists in obesity"])


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict


class HealthResponse(BaseModel):
    status: str
    version: str
    backend: str            # "anthropic" | "local"/"openai"
    model: str              # the model the active backend will actually use
    llm_configured: bool    # is the active backend usable (key / base_url set)?
    anthropic_configured: bool


class QueryResponse(BaseModel):
    landscape: Landscape
    id: str | None = None  # persisted landscape id, if saved


class LandscapeSummary(BaseModel):
    id: str
    query: str
    created_at: str
    n_assets: int
    tool_calls: int
    dropped_claims: int


class DiffResponse(BaseModel):
    query: str
    new_id: str
    old_id: str
    added: list[dict]
    removed: list[dict]
    changed: list[dict]
    n_added: int
    n_removed: int
    n_changed: int
    unchanged: int
