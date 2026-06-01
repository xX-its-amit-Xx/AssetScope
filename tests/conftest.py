"""Shared test config: force the torch-free hashing embedder so tests never try
to download a model, and never hit Postgres."""

import os

os.environ.setdefault("ASSETSCOPE_USE_FAKE_EMBEDDINGS", "1")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
