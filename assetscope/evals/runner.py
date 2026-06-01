"""Eval runner: turn gold + (live agent | replay fixtures) into scored results.

Both modes funnel through the SAME reliability guard, so the scorecard always
reflects the *delivered* (post-guard) answer, with the guard's drops surfaced
separately. Replay mode is deterministic and needs no API key or database — it
scores the bundled fixtures (realistic agent submissions assembled from the real
public-API data), which is how the committed scorecard is produced.
"""

from __future__ import annotations

import importlib.resources
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assetscope.evals.metrics import QueryScore, aggregate, score_query
from assetscope.guards import CitationLedger, ReliabilityGuard
from assetscope.models import Asset, Citation, Claim, Landscape, SourceType


@dataclass
class EvalRun:
    query_id: str
    query: str
    assets: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    valid_source_ids: set[str] = field(default_factory=set)
    tool_calls: int = 0
    claims_dropped: int = 0
    mode: str = "replay"


def citation_from_id(cid: str) -> Citation:
    """Reconstruct a minimal citation (type + url) from a source id handle."""
    if cid.startswith("NCT"):
        return Citation(id=cid, source_type=SourceType.CLINICAL_TRIALS, source_id=cid,
                        url=f"https://clinicaltrials.gov/study/{cid}")
    if cid.startswith("CHEMBL"):
        return Citation(id=cid, source_type=SourceType.CHEMBL, source_id=cid,
                        url=f"https://www.ebi.ac.uk/chembl/explore/compound/{cid}")
    if cid.startswith("OT:") or cid.startswith("ENSG"):
        ens = cid.split(":", 1)[-1]
        return Citation(id=cid, source_type=SourceType.OPEN_TARGETS, source_id=ens,
                        url=f"https://platform.opentargets.org/target/{ens}")
    if cid.isdigit():
        return Citation(id=cid, source_type=SourceType.PUBMED, source_id=cid,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{cid}/")
    return Citation(id=cid, source_type=SourceType.INTERNAL, source_id=cid)


def _guard_submission(query: str, submission: dict, valid_ids: set[str], tool_calls: int) -> tuple[Landscape, int]:
    """Apply the real reliability guard to a raw submission, given the universe
    of valid source ids (the agent's would-be citation ledger)."""
    ledger = CitationLedger()
    for cid in valid_ids:
        ledger.register(citation_from_id(cid))

    assets = [
        Asset(
            asset_name=a.get("asset_name", ""),
            company=a.get("company", ""),
            target=a.get("target", ""),
            mechanism=a.get("mechanism", ""),
            indication=a.get("indication", ""),
            phase=a.get("phase", ""),
            latest_readout=a.get("latest_readout", ""),
            source_ids=[str(s) for s in a.get("source_ids", []) or []],
        )
        for a in submission.get("assets", [])
    ]
    claims = [
        Claim(id=f"c{i + 1}", text=c.get("text", ""),
              source_ids=[str(s) for s in c.get("source_ids", []) or []])
        for i, c in enumerate(submission.get("narrative_claims", submission.get("claims", [])))
    ]
    landscape = Landscape(query=query, assets=assets, claims=claims, tool_calls=tool_calls)
    cleaned, report = ReliabilityGuard(drop_unsupported=True).apply(landscape, ledger)
    return cleaned, report.dropped_claims


def _landscape_to_pred(landscape: Landscape) -> tuple[list[dict], list[dict], set[str]]:
    assets = [a.model_dump() for a in landscape.assets]
    claims = [{"text": c.text, "source_ids": c.source_ids} for c in landscape.claims]
    valid = {c.id for c in landscape.citations}
    for a in landscape.assets:
        valid.update(a.source_ids)
    for c in landscape.claims:
        valid.update(c.source_ids)
    return assets, claims, valid


# -- data loading ----------------------------------------------------------
def load_gold(gold_dir: str | None = None) -> list[dict]:
    if gold_dir:
        paths = sorted(Path(gold_dir).glob("*.json"))
        return [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    files = importlib.resources.files("assetscope.evals.gold")
    out = []
    for entry in sorted(files.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".json"):
            out.append(json.loads(entry.read_text(encoding="utf-8")))
    return out


def _load_fixture(query_id: str, fixtures_dir: str | None) -> dict:
    if fixtures_dir:
        return json.loads((Path(fixtures_dir) / f"{query_id}.json").read_text(encoding="utf-8"))
    text = importlib.resources.files("assetscope.evals.fixtures").joinpath(
        f"{query_id}.json"
    ).read_text(encoding="utf-8")
    return json.loads(text)


# -- run modes -------------------------------------------------------------
def _replay_run(gold: dict, fixtures_dir: str | None) -> EvalRun:
    fx = _load_fixture(gold["id"], fixtures_dir)
    valid_ids = set(fx.get("valid_source_ids", []))
    tool_calls = int(fx.get("tool_calls", 0))
    cleaned, dropped = _guard_submission(gold["query"], fx, valid_ids, tool_calls)
    assets, claims, valid = _landscape_to_pred(cleaned)
    return EvalRun(
        query_id=gold["id"], query=gold["query"], assets=assets, claims=claims,
        valid_source_ids=valid, tool_calls=tool_calls, claims_dropped=dropped, mode="replay",
    )


def _live_run(gold: dict) -> EvalRun:
    from assetscope.agent import AssetScopeAgent

    landscape = AssetScopeAgent().run_to_completion(gold["query"])
    assets, claims, valid = _landscape_to_pred(landscape)
    return EvalRun(
        query_id=gold["id"], query=gold["query"], assets=assets, claims=claims,
        valid_source_ids=valid, tool_calls=landscape.tool_calls,
        claims_dropped=landscape.dropped_claims, mode="live",
    )


def run_suite(
    mode: str = "replay",
    gold_dir: str | None = None,
    fixtures_dir: str | None = None,
) -> dict[str, Any]:
    gold_sets = load_gold(gold_dir)
    scores: list[QueryScore] = []
    runs: list[EvalRun] = []
    for gold in gold_sets:
        run = _replay_run(gold, fixtures_dir) if mode == "replay" else _live_run(gold)
        runs.append(run)
        scores.append(
            score_query(
                gold,
                assets=run.assets,
                claims=run.claims,
                valid_source_ids=run.valid_source_ids,
                tool_calls=run.tool_calls,
            )
        )
    return {"mode": mode, "scores": scores, "runs": runs, "aggregate": aggregate(scores)}
