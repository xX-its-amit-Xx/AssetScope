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
    anthropic_configured: bool
    model: str


class QueryResponse(BaseModel):
    landscape: Landscape
