"""Storage backends for ingested evidence.

``VectorStore`` is the PostgreSQL + pgvector backend. ``InMemoryStore`` is a
dependency-light fallback (numpy cosine + rank_bm25) used automatically when no
database is reachable, so ``retrieve()`` always returns *something* during a run.
Both expose the same three methods used by :class:`HybridRetriever`:
``upsert_chunks``, ``vector_search`` and ``keyword_search``.
"""

from __future__ import annotations

import importlib.resources
import logging
from dataclasses import dataclass, field
from typing import Protocol

from assetscope.config import get_settings
from assetscope.models import Citation, SourceType

logger = logging.getLogger("assetscope.retrieval")


@dataclass
class ChunkRecord:
    """A chunk staged for ingestion."""

    citation: Citation
    content: str
    chunk_index: int = 0
    embedding: list[float] = field(default_factory=list)


@dataclass
class RetrievedChunk:
    """A search hit, with its provenance and per-modality score."""

    citation: Citation
    content: str
    score: float
    modality: str  # "vector" | "keyword"


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


class Store(Protocol):
    def upsert_chunks(self, records: list[ChunkRecord]) -> int: ...
    def vector_search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]: ...
    def keyword_search(self, query: str, k: int) -> list[RetrievedChunk]: ...
    @property
    def backend(self) -> str: ...


class VectorStore:
    """PostgreSQL + pgvector backend."""

    backend = "postgres+pgvector"

    def __init__(self, dsn: str | None = None) -> None:
        import psycopg  # local import so the package imports without psycopg present

        settings = get_settings()
        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn or settings.database_url, autocommit=True)
        self.ensure_schema()

    @staticmethod
    def schema_sql() -> str:
        return importlib.resources.files("assetscope.db").joinpath("schema.sql").read_text()

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(self.schema_sql())

    def upsert_chunks(self, records: list[ChunkRecord]) -> int:
        if not records:
            return 0
        n = 0
        with self._conn.cursor() as cur:
            for rec in records:
                c = rec.citation
                cur.execute(
                    """
                    INSERT INTO documents (source_type, source_id, citation_id, title, url)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (source_type, source_id)
                    DO UPDATE SET citation_id = EXCLUDED.citation_id,
                                  title = EXCLUDED.title,
                                  url = EXCLUDED.url
                    RETURNING id
                    """,
                    (c.source_type.value, c.source_id, c.id, c.title, c.url),
                )
                doc_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (document_id, chunk_index)
                    DO UPDATE SET content = EXCLUDED.content,
                                  embedding = EXCLUDED.embedding
                    """,
                    (doc_id, rec.chunk_index, rec.content, _vec_literal(rec.embedding)),
                )
                n += 1
        return n

    def _rows_to_hits(self, rows, modality: str) -> list[RetrievedChunk]:
        hits = []
        for source_type, source_id, citation_id, title, url, content, score in rows:
            hits.append(
                RetrievedChunk(
                    citation=Citation(
                        id=citation_id,
                        source_type=SourceType(source_type),
                        source_id=source_id,
                        title=title or "",
                        url=url or "",
                        snippet=content[:300],
                    ),
                    content=content,
                    score=float(score),
                    modality=modality,
                )
            )
        return hits

    def vector_search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.source_type, d.source_id, d.citation_id, d.title, d.url,
                       c.content, 1 - (c.embedding <=> %s::vector) AS score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (_vec_literal(query_embedding), _vec_literal(query_embedding), k),
            )
            return self._rows_to_hits(cur.fetchall(), "vector")

    def keyword_search(self, query: str, k: int) -> list[RetrievedChunk]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.source_type, d.source_id, d.citation_id, d.title, d.url,
                       c.content, ts_rank(c.tsv, websearch_to_tsquery('english', %s)) AS score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.tsv @@ websearch_to_tsquery('english', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (query, query, k),
            )
            return self._rows_to_hits(cur.fetchall(), "keyword")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


class InMemoryStore:
    """Fallback store: cosine over numpy + BM25 over rank_bm25. No DB required."""

    backend = "in-memory"

    def __init__(self) -> None:
        self._records: list[ChunkRecord] = []
        self._seen: set[tuple[str, int]] = set()

    def upsert_chunks(self, records: list[ChunkRecord]) -> int:
        n = 0
        for rec in records:
            key = (f"{rec.citation.source_type.value}:{rec.citation.source_id}", rec.chunk_index)
            if key in self._seen:
                continue
            self._seen.add(key)
            self._records.append(rec)
            n += 1
        return n

    def vector_search(self, query_embedding: list[float], k: int) -> list[RetrievedChunk]:
        import numpy as np

        if not self._records:
            return []
        q = np.asarray(query_embedding, dtype=float)
        mat = np.asarray([r.embedding for r in self._records], dtype=float)
        # embeddings are L2-normalized; guard query norm anyway.
        qn = q / (np.linalg.norm(q) or 1.0)
        sims = mat @ qn
        order = np.argsort(-sims)[:k]
        return [
            RetrievedChunk(
                citation=self._records[i].citation,
                content=self._records[i].content,
                score=float(sims[i]),
                modality="vector",
            )
            for i in order
        ]

    def keyword_search(self, query: str, k: int) -> list[RetrievedChunk]:
        if not self._records:
            return []
        try:
            from rank_bm25 import BM25Okapi
        except Exception:  # pragma: no cover
            return []
        corpus = [r.content.lower().split() for r in self._records]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query.lower().split())
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [
            RetrievedChunk(
                citation=self._records[i].citation,
                content=self._records[i].content,
                score=float(scores[i]),
                modality="keyword",
            )
            for i in ranked
            if scores[i] > 0
        ]


def get_store(prefer_db: bool = True) -> Store:
    """Return a Postgres-backed store if reachable, else an in-memory fallback."""
    if prefer_db:
        try:
            return VectorStore()
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Postgres unavailable (%s); using in-memory store.", exc)
    return InMemoryStore()
