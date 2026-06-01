"""search_open_targets -> Open Targets Platform GraphQL API.

Docs: https://platform-docs.opentargets.org/data-access/graphql-api
Endpoint: POST https://api.platform.opentargets.org/api/v4/graphql

Flow: resolve the free-text query to the best target/disease entity via the
``search`` query, then pull the relevant associations + tractability. Every row
becomes an evidence item citing the public platform page.
"""

from __future__ import annotations

from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool
from assetscope.tools.http import post_json

GQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

SEARCH_Q = """
query Resolve($q: String!) {
  search(queryString: $q, entityNames: ["target", "disease"], page: {index: 0, size: 5}) {
    hits { id entity name }
  }
}
"""

TARGET_Q = """
query T($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    tractability { label modality value }
    associatedDiseases(page: {index: 0, size: 12}) {
      rows { score disease { id name } }
    }
  }
}
"""

DISEASE_Q = """
query D($id: String!) {
  disease(efoId: $id) {
    id
    name
    associatedTargets(page: {index: 0, size: 15}) {
      rows { score target { id approvedSymbol approvedName } }
    }
  }
}
"""


class OpenTargetsTool(Tool):
    name = "search_open_targets"
    description = (
        "Query the Open Targets Platform for target-disease associations and "
        "target tractability (druggability). Accepts a gene/target symbol "
        "(e.g. 'GLP1R', 'KRAS', 'BTK') or a disease name (e.g. 'obesity', "
        "'non-small cell lung carcinoma'). Returns the top associated diseases "
        "for a target (with association scores + tractability), or the top "
        "associated targets for a disease. Use this to ground target biology "
        "and which targets matter for an indication."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "target_or_disease": {
                "type": "string",
                "description": "A target/gene symbol or a disease name.",
            }
        },
        "required": ["target_or_disease"],
    }

    def _resolve(self, query: str) -> dict | None:
        data = post_json(GQL_URL, {"query": SEARCH_Q, "variables": {"q": query}})
        hits = (((data or {}).get("data") or {}).get("search") or {}).get("hits") or []
        # prefer an exact-ish target match, else first hit
        for h in hits:
            if h.get("entity") == "target":
                return h
        return hits[0] if hits else None

    def run(self, target_or_disease: str) -> ToolResult:
        hit = self._resolve(target_or_disease)
        args = {"target_or_disease": target_or_disease}
        if not hit:
            return ToolResult(
                tool=self.name, args=args, summary=f"No Open Targets entity for '{target_or_disease}'."
            )

        entity, ent_id, ent_name = hit["entity"], hit["id"], hit.get("name", "")
        items: list[EvidenceItem] = []

        if entity == "target":
            data = post_json(GQL_URL, {"query": TARGET_Q, "variables": {"id": ent_id}})
            target = ((data or {}).get("data") or {}).get("target") or {}
            symbol = target.get("approvedSymbol", ent_name)
            tract = [
                f"{t.get('modality')}/{t.get('label')}={t.get('value')}"
                for t in (target.get("tractability") or [])
                if t.get("value")
            ]
            rows = ((target.get("associatedDiseases") or {}).get("rows")) or []
            url = f"https://platform.opentargets.org/target/{ent_id}"
            header = (
                f"Open Targets target {symbol} ({ent_id}) — {target.get('approvedName', '')}\n"
                f"Tractability: {', '.join(tract) or 'n/a'}"
            )
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=f"OT:{ent_id}",
                        source_type=SourceType.OPEN_TARGETS,
                        source_id=ent_id,
                        title=f"Open Targets: {symbol}",
                        url=url,
                        snippet=header[:300],
                    ),
                    content=header
                    + "\nTop associated diseases:\n"
                    + "\n".join(
                        f"- {(r.get('disease') or {}).get('name')} (score {(r.get('score') or 0.0):.3f})"
                        for r in rows
                        if (r.get("disease") or {}).get("name")
                    ),
                    fields={"symbol": symbol, "ensembl_id": ent_id, "tractability": tract},
                )
            )
        else:  # disease
            data = post_json(GQL_URL, {"query": DISEASE_Q, "variables": {"id": ent_id}})
            disease = ((data or {}).get("data") or {}).get("disease") or {}
            rows = ((disease.get("associatedTargets") or {}).get("rows")) or []
            url = f"https://platform.opentargets.org/disease/{ent_id}"
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=f"OT:{ent_id}",
                        source_type=SourceType.OPEN_TARGETS,
                        source_id=ent_id,
                        title=f"Open Targets: {disease.get('name', ent_name)}",
                        url=url,
                        snippet=f"Top targets for {disease.get('name', ent_name)}",
                    ),
                    content=f"Open Targets disease {disease.get('name', ent_name)} ({ent_id})\n"
                    + "Top associated targets:\n"
                    + "\n".join(
                        f"- {(r.get('target') or {}).get('approvedSymbol')} (score {(r.get('score') or 0.0):.3f})"
                        for r in rows
                        if (r.get("target") or {}).get("approvedSymbol")
                    ),
                    fields={"efo_id": ent_id, "name": disease.get("name", ent_name)},
                )
            )

        return ToolResult(
            tool=self.name,
            args=args,
            items=items,
            summary=f"Resolved '{target_or_disease}' to {entity} {ent_name} ({ent_id}).",
        )
