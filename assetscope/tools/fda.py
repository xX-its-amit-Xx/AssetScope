"""search_fda -> openFDA (Drugs@FDA approvals + Structured Product Labeling).

Docs: https://open.fda.gov/apis/
Endpoints used (no API key required for light use; an optional key raises limits):
  * GET https://api.fda.gov/drug/drugsfda.json  — approval/registration metadata:
    application number (NDA/BLA/ANDA), sponsor, products + marketing status,
    pharmacologic class (openfda.pharm_class_*).
  * GET https://api.fda.gov/drug/label.json      — label sections: indications and
    mechanism of action.

This is the regulatory-landscape source: who owns a drug, is it approved, which
products are marketed vs discontinued, its FDA-labeled indications and MoA.
"""

from __future__ import annotations

import re

import httpx

from assetscope.config import get_settings
from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool
from assetscope.tools.http import get_json

BASE = "https://api.fda.gov"


def _first(d: dict, key: str, default: str = "") -> str:
    v = d.get(key)
    if isinstance(v, list):
        return v[0] if v else default
    return v or default


def _join(seq, n: int = 3) -> str:
    seq = [s for s in (seq or []) if s]
    return ", ".join(seq[:n])


class FdaTool(Tool):
    name = "search_fda"
    description = (
        "Look up a drug in openFDA (the FDA's open data). Accepts a brand or "
        "generic drug name (e.g. 'Keytruda', 'pembrolizumab', 'sotorasib'). "
        "Returns FDA approval/registration facts from Drugs@FDA — application "
        "number (NDA/BLA/ANDA), sponsor, products and their marketing status "
        "(Prescription / Discontinued / Tentative Approval), and pharmacologic "
        "class — plus the FDA-labeled indications and mechanism of action. Use "
        "this to ground regulatory status, ownership, and approved indications."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "drug": {
                "type": "string",
                "description": "A brand or generic drug name.",
            },
            "max_results": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
        },
        "required": ["drug"],
    }

    def _ofda(self, path: str, params: dict) -> dict:
        key = get_settings().fda_api_key
        if key:
            params = {**params, "api_key": key}
        try:
            return get_json(f"{BASE}{path}", params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:  # openFDA returns 404 for zero hits
                return {}
            raise

    def _search(self, path: str, drug: str, limit: int) -> list[dict]:
        # Try generic name, then brand name (quoted phrase match).
        for field in ("openfda.generic_name", "openfda.brand_name"):
            data = self._ofda(path, {"search": f'{field}:"{drug}"', "limit": limit})
            results = data.get("results") or []
            if results:
                return results
        return []

    def run(self, drug: str, max_results: int = 3) -> ToolResult:
        limit = min(max(max_results, 1), 10)
        items: list[EvidenceItem] = []

        for app in self._search("/drug/drugsfda.json", drug, limit):
            appl = app.get("application_number", "")
            if not appl:
                continue
            sponsor = app.get("sponsor_name", "")
            openfda = app.get("openfda", {}) or {}
            products = app.get("products", []) or []
            brands = _join({p.get("brand_name") for p in products})
            statuses = _join({p.get("marketing_status") for p in products})
            ingredients = _join(
                {ai.get("name") for p in products for ai in (p.get("active_ingredients") or [])}
            )
            epc = _join(openfda.get("pharm_class_epc"))
            moa = _join(openfda.get("pharm_class_moa"))
            appl_no = re.sub(r"\D", "", appl)
            content = (
                f"FDA {appl}: {brands or _join(openfda.get('brand_name')) or drug}\n"
                f"Sponsor: {sponsor or 'N/A'}; Marketing status: {statuses or 'N/A'}\n"
                f"Active ingredient(s): {ingredients or _join(openfda.get('generic_name')) or 'N/A'}\n"
                f"Pharmacologic class: {epc or 'N/A'}; MoA class: {moa or 'N/A'}"
            )
            items.append(
                EvidenceItem(
                    citation=Citation(
                        id=appl,
                        source_type=SourceType.FDA,
                        source_id=appl,
                        title=f"Drugs@FDA: {brands or drug} ({appl})",
                        url=(
                            "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
                            f"?event=overview.process&ApplNo={appl_no}"
                        ),
                        snippet=content[:300],
                    ),
                    content=content,
                    fields={
                        "application_number": appl,
                        "sponsor": sponsor,
                        "marketing_status": statuses,
                        "pharm_class_epc": openfda.get("pharm_class_epc"),
                        "pharm_class_moa": openfda.get("pharm_class_moa"),
                    },
                )
            )

        # One label record for indications + mechanism of action.
        labels = self._search("/drug/label.json", drug, 1)
        if labels:
            lbl = labels[0]
            ofd = lbl.get("openfda", {}) or {}
            spl = _first(ofd, "spl_set_id")
            name = _first(ofd, "brand_name") or _first(ofd, "generic_name") or drug
            indications = " ".join(lbl.get("indications_and_usage", []) or [])[:600]
            moa_text = " ".join(lbl.get("mechanism_of_action", []) or [])[:400]
            if indications or moa_text:
                content = (
                    f"FDA label for {name}\n"
                    f"Indications: {indications or 'see label'}\n"
                    f"Mechanism of action: {moa_text or 'not stated in label'}"
                )
                cid = f"SPL:{spl}" if spl else f"FDALABEL:{name}"
                url = (
                    f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl}"
                    if spl
                    else f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={name}"
                )
                items.append(
                    EvidenceItem(
                        citation=Citation(
                            id=cid,
                            source_type=SourceType.FDA,
                            source_id=spl or name,
                            title=f"FDA label: {name}",
                            url=url,
                            snippet=content[:300],
                        ),
                        content=content,
                        fields={"indications": indications, "mechanism_of_action": moa_text},
                    )
                )

        return ToolResult(
            tool=self.name,
            args={"drug": drug, "max_results": max_results},
            items=items,
            summary=f"{len(items)} FDA record(s) for '{drug}'.",
        )
