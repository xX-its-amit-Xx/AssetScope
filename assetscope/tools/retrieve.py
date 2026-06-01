"""retrieve -> internal pgvector hybrid retrieval over ingested docs.

This is the agent's memory of everything it has gathered this run (and in prior
runs, if a database is persisted): the executor ingests every tool's evidence
into the vector store, and ``retrieve`` searches it with hybrid BM25 + vector
fusion. It lets the agent re-find a fact it saw earlier without re-calling an
external API.
"""

from __future__ import annotations

from typing import Any

from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool


class RetrieveTool(Tool):
    name = "retrieve"
    description = (
        "Search AssetScope's internal evidence store (everything gathered so "
        "far this session, plus any pre-ingested documents) using hybrid "
        "keyword + semantic vector retrieval. Use this to recall facts you have "
        "already retrieved, to cross-check a claim, or to find supporting "
        "snippets before finalizing. Returns the best-matching passages with "
        "their original source citations."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look up in the evidence store."},
            "k": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    }

    def __init__(self, retriever: Any | None = None) -> None:
        self._retriever = retriever

    @property
    def retriever(self):
        if self._retriever is None:
            # Lazy import to avoid importing torch/psycopg at module load.
            from assetscope.retrieval import HybridRetriever

            self._retriever = HybridRetriever()
        return self._retriever

    def run(self, query: str, k: int = 6) -> ToolResult:
        hits = self.retriever.search(query, k=min(max(k, 1), 20))
        items: list[EvidenceItem] = []
        for h in hits:
            cit = h.citation
            if not isinstance(cit, Citation):  # defensive: in-memory store returns Citation already
                cit = Citation(
                    id=str(cit), source_type=SourceType.INTERNAL, source_id=str(cit)
                )
            items.append(
                EvidenceItem(
                    citation=cit,
                    content=h.content,
                    fields={
                        "rrf_score": round(h.rrf_score, 5),
                        "vector_score": h.vector_score,
                        "keyword_score": h.keyword_score,
                    },
                )
            )
        return ToolResult(
            tool=self.name,
            args={"query": query, "k": k},
            items=items,
            summary=(
                f"{len(items)} passage(s) from the internal store "
                f"(backend: {self.retriever.backend}) for '{query}'."
            ),
        )
