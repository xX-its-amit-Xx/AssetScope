"""MCP server entrypoint.

Exposes AssetScope's five evidence tools — and the full ``build_landscape``
agent — over the Model Context Protocol, so any MCP client (Claude Desktop,
Cursor, etc.) can use them. Run with::

    assetscope-mcp          # console script (stdio transport)
    python -m assetscope.mcp_server

See README "Connect via MCP" for client configuration.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from assetscope.tools import (
    ChemblTool,
    ClinicalTrialsTool,
    LiteratureTool,
    OpenTargetsTool,
    RetrieveTool,
)

mcp = FastMCP("assetscope")

_clinical = ClinicalTrialsTool()
_open_targets = OpenTargetsTool()
_chembl = ChemblTool()
_literature = LiteratureTool()
_retrieve = RetrieveTool()


def _dump(result) -> dict[str, Any]:
    return result.model_dump(mode="json")


@mcp.tool()
def search_clinical_trials(
    query: str, phase: str | None = None, status: str | None = None, max_results: int = 10
) -> dict:
    """Search ClinicalTrials.gov for trials (NCT id, phase, status, sponsor, conditions)."""
    return _dump(_clinical.run(query=query, phase=phase, status=status, max_results=max_results))


@mcp.tool()
def search_open_targets(target_or_disease: str) -> dict:
    """Query Open Targets for target-disease associations and tractability."""
    return _dump(_open_targets.run(target_or_disease=target_or_disease))


@mcp.tool()
def search_chembl(compound_or_target: str, max_results: int = 5) -> dict:
    """Look up a compound/target in ChEMBL (mechanism, max phase, ChEMBL ids)."""
    return _dump(_chembl.run(compound_or_target=compound_or_target, max_results=max_results))


@mcp.tool()
def search_literature(query: str, max_results: int = 6) -> dict:
    """Search PubMed for articles (PMID, title, journal, year, abstract)."""
    return _dump(_literature.run(query=query, max_results=max_results))


@mcp.tool()
def retrieve(query: str, k: int = 6) -> dict:
    """Hybrid keyword+vector search over AssetScope's internal evidence store."""
    return _dump(_retrieve.run(query=query, k=k))


@mcp.tool()
def build_landscape(query: str) -> dict:
    """Run the full AssetScope agent and return a citation-grounded competitive
    landscape (assets table + guarded narrative). Requires ANTHROPIC_API_KEY."""
    from assetscope.agent import AssetScopeAgent

    try:
        landscape = AssetScopeAgent().run_to_completion(query)
        return landscape.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
