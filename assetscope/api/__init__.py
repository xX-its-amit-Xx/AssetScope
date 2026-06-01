"""FastAPI application exposing the AssetScope agent over HTTP (with SSE streaming)."""

from assetscope.api.main import app

__all__ = ["app"]
