"""search_chembl -> ChEMBL REST API (EMBL-EBI).

Docs: https://www.ebi.ac.uk/chembl/api/data/docs
Base: https://www.ebi.ac.uk/chembl/api/data

Given a compound or target string, this resolves a molecule (name search) and
its mechanism(s) of action, and also resolves targets by name. Returns
molecule_chembl_id, pref_name, max_phase, mechanism_of_action and target ids,
each citing the ChEMBL explorer page.
"""

from __future__ import annotations

from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool
from assetscope.tools.http import get_json

BASE = "https://www.ebi.ac.uk/chembl/api/data"

_MAX_PHASE_LABEL = {
    4: "Approved (Phase 4)",
    3: "Phase 3",
    2: "Phase 2",
    1: "Phase 1",
    0: "Preclinical",
    -1: "Unknown",
    None: "Unknown",
}


class ChemblTool(Tool):
    name = "search_chembl"
    description = (
        "Look up a compound or target in ChEMBL, the EMBL-EBI database of "
        "bioactive molecules. Accepts a drug/compound name (e.g. 'ibrutinib') "
        "or a target name (e.g. 'BTK'). Returns the ChEMBL molecule id, "
        "preferred name, maximum clinical phase, and mechanism(s) of action "
        "(molecular target + action type). Use this for canonical mechanism / "
        "drug-class grounding and stable compound identifiers."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "compound_or_target": {
                "type": "string",
                "description": "A compound/drug name or a molecular target name.",
            },
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["compound_or_target"],
    }

    def _molecule_search(self, q: str, limit: int) -> list[dict]:
        data = get_json(f"{BASE}/molecule/search.json", params={"q": q, "limit": limit})
        return data.get("molecules", []) or []

    def _mechanisms(self, chembl_id: str) -> list[dict]:
        data = get_json(f"{BASE}/mechanism.json", params={"molecule_chembl_id": chembl_id})
        return data.get("mechanisms", []) or []

    def _target_search(self, q: str, limit: int) -> list[dict]:
        data = get_json(f"{BASE}/target/search.json", params={"q": q, "limit": limit})
        return data.get("targets", []) or []

    def run(self, compound_or_target: str, max_results: int = 5) -> ToolResult:
        limit = min(max(max_results, 1), 20)
        items: list[EvidenceItem] = []

        molecules = self._molecule_search(compound_or_target, limit)
        for mol in molecules[:limit]:
            chembl_id = mol.get("molecule_chembl_id")
            if not chembl_id:
                continue
            pref = mol.get("pref_name") or compound_or_target
            max_phase = mol.get("max_phase")
            try:
                max_phase_int = int(float(max_phase)) if max_phase is not None else None
            except (TypeError, ValueError):
                max_phase_int = None
            mechs = self._mechanisms(chembl_id)
            mech_str = "; ".join(
                f"{m.get('mechanism_of_action', '?')} "
                f"({m.get('action_type', '?')}, target {m.get('target_chembl_id', '?')})"
                for m in mechs
            )
            content = (
                f"ChEMBL {chembl_id}: {pref}\n"
                f"Max clinical phase: {_MAX_PHASE_LABEL.get(max_phase_int, 'Unknown')}\n"
                f"Mechanism(s): {mech_str or 'not annotated in ChEMBL'}"
            )
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=chembl_id,
                        source_type=SourceType.CHEMBL,
                        source_id=chembl_id,
                        title=f"ChEMBL: {pref}",
                        url=f"https://www.ebi.ac.uk/chembl/explore/compound/{chembl_id}",
                        snippet=content[:300],
                    ),
                    content=content,
                    fields={
                        "molecule_chembl_id": chembl_id,
                        "pref_name": pref,
                        "max_phase": max_phase_int,
                        "mechanisms": [m.get("mechanism_of_action") for m in mechs],
                        "target_chembl_ids": [m.get("target_chembl_id") for m in mechs],
                    },
                )
            )

        if not molecules:
            for tgt in self._target_search(compound_or_target, limit)[:limit]:
                tid = tgt.get("target_chembl_id")
                if not tid:
                    continue
                name = tgt.get("pref_name") or compound_or_target
                content = (
                    f"ChEMBL target {tid}: {name}\n"
                    f"Type: {tgt.get('target_type', '?')}; Organism: {tgt.get('organism', '?')}"
                )
                items.append(
                    EvidenceItem(
                        citation=Citation(
                            id=tid,
                            source_type=SourceType.CHEMBL,
                            source_id=tid,
                            title=f"ChEMBL target: {name}",
                            url=f"https://www.ebi.ac.uk/chembl/explore/target/{tid}",
                            snippet=content[:300],
                        ),
                        content=content,
                        fields={"target_chembl_id": tid, "pref_name": name},
                    )
                )

        return ToolResult(
            tool=self.name,
            args={"compound_or_target": compound_or_target, "max_results": max_results},
            items=items,
            summary=f"{len(items)} ChEMBL record(s) for '{compound_or_target}'.",
        )
