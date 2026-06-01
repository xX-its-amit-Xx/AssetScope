"""Hybrid retrieval: dense vector search + keyword (BM25/ts_rank) fused by
Reciprocal Rank Fusion (RRF).

RRF is rank-based, so it is robust to the fact that cosine similarity and
ts_rank live on completely different scales — we never have to normalize one
into the other. For a document appearing at rank ``r`` (1-based) in a result
list, its contribution is ``1 / (k0 + r)`` with ``k0 = 60`` (the value from the
original Cormack et al. RRF paper); contributions across the vector and keyword
lists are summed.
"""

from __future__ import annotations

from dataclasses import dataclass

from assetscope.models import Citation, EvidenceItem
from assetscope.retrieval.embeddings import Embedder, get_embedder
from assetscope.retrieval.vector_store import ChunkRecord, RetrievedChunk, Store, get_store

RRF_K0 = 60


@dataclass
class FusedHit:
    citation: Citation
    content: str
    rrf_score: float
    vector_score: float | None = None
    keyword_score: float | None = None


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    # split on paragraph boundaries, then hard-wrap remaining long pieces
    out: list[str] = []
    buf = ""
    for para in text.split("\n"):
        if len(buf) + len(para) + 1 > max_chars and buf:
            out.append(buf.strip())
            buf = ""
        buf += para + "\n"
        while len(buf) > max_chars:
            out.append(buf[:max_chars].strip())
            buf = buf[max_chars:]
    if buf.strip():
        out.append(buf.strip())
    return out


class HybridRetriever:
    """Owns the embedder + store; ingests evidence and runs fused search."""

    def __init__(self, store: Store | None = None, embedder: Embedder | None = None) -> None:
        self.store = store or get_store()
        self.embedder = embedder or get_embedder()

    @property
    def backend(self) -> str:
        return self.store.backend

    # -- ingestion ---------------------------------------------------------
    def ingest(self, items: list[EvidenceItem]) -> int:
        records: list[ChunkRecord] = []
        for item in items:
            chunks = _chunk_text(item.content)
            if not chunks:
                continue
            embeddings = self.embedder.encode(chunks)
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
                records.append(
                    ChunkRecord(
                        citation=item.citation, content=chunk, chunk_index=idx, embedding=emb
                    )
                )
        if not records:
            return 0
        return self.store.upsert_chunks(records)

    # -- search ------------------------------------------------------------
    def search(self, query: str, k: int = 6, pool: int = 20) -> list[FusedHit]:
        query_emb = self.embedder.encode_one(query)
        vector_hits = self.store.vector_search(query_emb, pool)
        keyword_hits = self.store.keyword_search(query, pool)
        return self._rrf_merge(vector_hits, keyword_hits, k)

    @staticmethod
    def _rrf_merge(
        vector_hits: list[RetrievedChunk], keyword_hits: list[RetrievedChunk], k: int
    ) -> list[FusedHit]:
        fused: dict[str, FusedHit] = {}

        def key(h: RetrievedChunk) -> str:
            return f"{h.citation.source_type.value}:{h.citation.source_id}:{h.chunk_index}"

        for rank, hit in enumerate(vector_hits, start=1):
            entry = fused.setdefault(
                key(hit), FusedHit(citation=hit.citation, content=hit.content, rrf_score=0.0)
            )
            entry.rrf_score += 1.0 / (RRF_K0 + rank)
            entry.vector_score = hit.score

        for rank, hit in enumerate(keyword_hits, start=1):
            entry = fused.setdefault(
                key(hit), FusedHit(citation=hit.citation, content=hit.content, rrf_score=0.0)
            )
            entry.rrf_score += 1.0 / (RRF_K0 + rank)
            entry.keyword_score = hit.score

        ranked = sorted(fused.values(), key=lambda h: -h.rrf_score)
        return ranked[:k]
