"""Embeddings with a graceful, torch-free fallback.

The default path uses ``sentence-transformers`` (install the ``embeddings``
extra). When that package is unavailable, or ``ASSETSCOPE_USE_FAKE_EMBEDDINGS=1``
is set, we fall back to a deterministic hashing embedder so that the agent,
retrieval and tests still run end-to-end (with weaker semantic matching). Both
embedders are L2-normalized, so cosine similarity == dot product and the same
pgvector ``vector_cosine_ops`` index works for either.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from assetscope.config import get_settings


class Embedder:
    """Interface implemented by both the real and fallback embedders."""

    dim: int
    name: str

    def encode(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


class SentenceTransformerEmbedder(Embedder):
    """Wraps a sentence-transformers model (lazy-loaded)."""

    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer  # local import (heavy)

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension() or dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.astype(float).tolist() for v in vecs]


class HashingEmbedder(Embedder):
    """Deterministic, dependency-free embedder.

    Uses the hashing trick over word unigrams + bigrams into ``dim`` buckets,
    then L2-normalizes. Not semantically strong, but stable and fast — good
    enough for tests, CI and offline demos, and it never downloads a model.
    """

    name = "hashing-fallback"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        words = [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]
        bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        return words + bigrams

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in self._tokens(text):
                h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")
                idx = h % self.dim
                sign = 1.0 if (h >> 1) & 1 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


@lru_cache
def get_embedder() -> Embedder:
    """Return the configured embedder, falling back to hashing on any failure."""
    settings = get_settings()
    if settings.use_fake_embeddings:
        return HashingEmbedder(settings.embedding_dim)
    try:
        return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)
    except Exception:  # pragma: no cover - exercised only when torch is absent
        # sentence-transformers / torch not installed, or model download failed.
        return HashingEmbedder(settings.embedding_dim)
