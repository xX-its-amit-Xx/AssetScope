"""Core data models shared across tools, the agent loop, guards, the API and evals.

These types are the contract that makes citations enforceable end-to-end:

* Every tool returns ``EvidenceItem``s, each of which carries a ``Citation``.
* The agent assembles ``Asset`` rows and narrative ``Claim``s that reference
  citations *by id*.
* The reliability guard checks that every claim's ``source_ids`` resolve to a
  real citation in the ledger; otherwise the claim is flagged or dropped.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    CLINICAL_TRIALS = "clinical_trials"
    OPEN_TARGETS = "open_targets"
    CHEMBL = "chembl"
    PUBMED = "pubmed"
    INTERNAL = "internal"  # pgvector hybrid retrieval over ingested docs


class Citation(BaseModel):
    """A single, addressable source. ``id`` is a short stable handle the agent
    cites (e.g. ``NCT05669599`` or ``PMID:36251794``)."""

    id: str
    source_type: SourceType
    source_id: str
    title: str = ""
    url: str = ""
    snippet: str = ""

    def as_markdown(self) -> str:
        label = self.title or self.id
        return f"[{label}]({self.url})" if self.url else label


class EvidenceItem(BaseModel):
    """A normalized unit of evidence returned by a tool: a citation plus the
    human-readable content that gets embedded into the vector store, plus any
    structured fields the agent finds useful (phase, sponsor, etc.)."""

    citation: Citation
    content: str
    fields: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """The structured result of one tool invocation."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    items: list[EvidenceItem] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None

    def citations(self) -> list[Citation]:
        return [item.citation for item in self.items]


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"     # >= 1 valid source in the ledger
    UNVERIFIED = "unverified"   # kept but flagged: no resolvable source
    DROPPED = "dropped"         # removed by the guard


class Claim(BaseModel):
    """A single factual statement in the narrative, tied to its sources."""

    id: str
    text: str
    source_ids: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.SUPPORTED
    guard_note: str = ""


class Asset(BaseModel):
    """One row of the competitive landscape table."""

    asset_name: str
    company: str = ""
    target: str = ""
    mechanism: str = ""
    indication: str = ""
    phase: str = ""
    latest_readout: str = ""
    source_ids: list[str] = Field(default_factory=list)
    # Populated by the guard: source_ids that did NOT resolve to a citation.
    unresolved_source_ids: list[str] = Field(default_factory=list)
    verified: bool = True


class Landscape(BaseModel):
    """The full structured answer: a table of assets + a cited narrative."""

    query: str
    plan: list[str] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    narrative: str = ""
    citations: list[Citation] = Field(default_factory=list)

    # Run metadata / telemetry (surfaced in the UI and used by tool-efficiency).
    tool_calls: int = 0
    iterations: int = 0
    dropped_claims: int = 0
    unverified_claims: int = 0
    limitations: str = ""

    def citation_index(self) -> dict[str, Citation]:
        return {c.id: c for c in self.citations}
