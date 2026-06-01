"""The citation ledger: the single source of truth for what the agent actually
retrieved.

Every tool result is registered here. A claim or asset row may only cite source
ids that exist in this ledger; the :class:`ReliabilityGuard` enforces that. The
ledger also records *which* claims ended up citing each source, so the UI can
show provenance and the evals can measure citation coverage.
"""

from __future__ import annotations

from assetscope.models import Citation, ToolResult


class CitationLedger:
    def __init__(self) -> None:
        self._by_id: dict[str, Citation] = {}
        # citation id -> set of claim ids that referenced it
        self._references: dict[str, set[str]] = {}

    # -- registration ------------------------------------------------------
    def register(self, citation: Citation) -> None:
        # First writer wins on metadata, but we keep the richest title/url/snippet.
        existing = self._by_id.get(citation.id)
        if existing is None:
            self._by_id[citation.id] = citation
        else:
            self._by_id[citation.id] = Citation(
                id=existing.id,
                source_type=existing.source_type,
                source_id=existing.source_id,
                title=existing.title or citation.title,
                url=existing.url or citation.url,
                snippet=existing.snippet or citation.snippet,
            )

    def register_result(self, result: ToolResult) -> int:
        before = len(self._by_id)
        for item in result.items:
            self.register(item.citation)
        return len(self._by_id) - before

    # -- lookup ------------------------------------------------------------
    def has(self, citation_id: str) -> bool:
        return citation_id in self._by_id

    def get(self, citation_id: str) -> Citation | None:
        return self._by_id.get(citation_id)

    def resolve(self, ids: list[str]) -> tuple[list[str], list[str]]:
        """Split ids into (resolvable, unresolvable)."""
        ok = [i for i in ids if i in self._by_id]
        missing = [i for i in ids if i not in self._by_id]
        return ok, missing

    def note_reference(self, citation_id: str, claim_id: str) -> None:
        if citation_id in self._by_id:
            self._references.setdefault(citation_id, set()).add(claim_id)

    def all(self) -> list[Citation]:
        return list(self._by_id.values())

    def used(self) -> list[Citation]:
        return [self._by_id[cid] for cid in self._references if cid in self._by_id]

    def __len__(self) -> int:
        return len(self._by_id)
