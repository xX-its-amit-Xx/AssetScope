"""search_clinical_trials -> ClinicalTrials.gov API v2.

Docs: https://clinicaltrials.gov/data-api/api
Endpoint: GET https://clinicaltrials.gov/api/v2/studies
No API key required. The JSON path to the fields we care about lives under
``study.protocolSection.*`` (identification, status, sponsor, conditions,
design/phases, arms/interventions).
"""

from __future__ import annotations

from typing import Any

from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool
from assetscope.tools.http import get_json

API_URL = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_NORMALIZE = {
    "1": "PHASE1",
    "2": "PHASE2",
    "3": "PHASE3",
    "4": "PHASE4",
    "PHASE 1": "PHASE1",
    "PHASE 2": "PHASE2",
    "PHASE 3": "PHASE3",
    "PHASE 4": "PHASE4",
}


def _g(d: dict, *path, default=None):
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


class ClinicalTrialsTool(Tool):
    name = "search_clinical_trials"
    description = (
        "Search ClinicalTrials.gov (the U.S. registry of clinical studies) for "
        "trials matching a free-text query, optionally filtered by phase and "
        "recruitment status. Returns trials with NCT id, title, phase, status, "
        "lead sponsor, conditions and interventions. Use this to find which "
        "assets are in development, for which indications, and at what phase."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text search, e.g. 'tirzepatide obesity' or 'KRAS G12C NSCLC'.",
            },
            "phase": {
                "type": "string",
                "description": "Optional phase filter.",
                "enum": ["1", "2", "3", "4", "PHASE1", "PHASE2", "PHASE3", "PHASE4"],
            },
            "status": {
                "type": "string",
                "description": "Optional recruitment-status filter (ClinicalTrials.gov enum).",
                "enum": [
                    "RECRUITING",
                    "ACTIVE_NOT_RECRUITING",
                    "COMPLETED",
                    "ENROLLING_BY_INVITATION",
                    "NOT_YET_RECRUITING",
                    "TERMINATED",
                    "WITHDRAWN",
                ],
            },
            "max_results": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
    }

    def run(
        self,
        query: str,
        phase: str | None = None,
        status: str | None = None,
        max_results: int = 10,
    ) -> ToolResult:
        max_results = min(max(max_results, 1), 50)
        wanted_phase = _PHASE_NORMALIZE.get((phase or "").upper().strip()) if phase else None
        # Phase is filtered client-side (the v2 API phase facet is unreliable),
        # so when a phase is requested we scan a larger pool — otherwise we'd
        # return 0-2 hits just because the top page happened to be other phases.
        page_size = min(200, max(max_results * 8, 50)) if wanted_phase else max_results
        params: dict[str, Any] = {
            "query.term": query,
            "pageSize": page_size,
            "countTotal": "true",
        }
        if status:
            params["filter.overallStatus"] = status

        data = get_json(API_URL, params=params)
        studies = data.get("studies", [])

        items: list[EvidenceItem] = []
        for study in studies:
            ps = study.get("protocolSection", {})
            nct = _g(ps, "identificationModule", "nctId", default="")
            if not nct:
                continue
            title = _g(ps, "identificationModule", "briefTitle", default="") or nct
            phases = _g(ps, "designModule", "phases", default=[]) or []
            if wanted_phase and wanted_phase not in [p.upper() for p in phases]:
                continue
            overall = _g(ps, "statusModule", "overallStatus", default="")
            sponsor = _g(ps, "sponsorCollaboratorsModule", "leadSponsor", "name", default="")
            conditions = _g(ps, "conditionsModule", "conditions", default=[]) or []
            interventions = [
                i.get("name", "")
                for i in _g(ps, "armsInterventionsModule", "interventions", default=[]) or []
            ]
            summary = _g(ps, "descriptionModule", "briefSummary", default="") or ""

            content = (
                f"Trial {nct}: {title}\n"
                f"Phase: {', '.join(phases) or 'N/A'}; Status: {overall or 'N/A'}\n"
                f"Lead sponsor: {sponsor or 'N/A'}\n"
                f"Conditions: {', '.join(conditions) or 'N/A'}\n"
                f"Interventions: {', '.join(i for i in interventions if i) or 'N/A'}\n"
                f"{summary}".strip()
            )
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=nct,
                        source_type=SourceType.CLINICAL_TRIALS,
                        source_id=nct,
                        title=title,
                        url=f"https://clinicaltrials.gov/study/{nct}",
                        snippet=content[:300],
                    ),
                    content=content,
                    fields={
                        "nct_id": nct,
                        "phase": phases,
                        "status": overall,
                        "lead_sponsor": sponsor,
                        "conditions": conditions,
                        "interventions": interventions,
                    },
                )
            )
            if len(items) >= max_results:
                break

        total = data.get("totalCount")
        if wanted_phase:
            summary = (
                f"{len(items)} {wanted_phase} trial(s) for '{query}' "
                f"(scanned {len(studies)} top text matches)."
            )
        else:
            extra = f" (~{total} total text matches)" if total is not None else ""
            summary = f"{len(items)} trial(s) for '{query}'{extra}."
        return ToolResult(
            tool=self.name,
            args={"query": query, "phase": phase, "status": status, "max_results": max_results},
            items=items,
            summary=summary,
        )
