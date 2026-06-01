"""Eval metrics for citation-grounded competitive landscapes.

Unit of truth is the (asset, field) fact. Gold specifies, per asset, acceptable
substrings for each of: company, target, mechanism, phase, latest readout — plus
the real source ids that should ground that asset, and global "contradictions"
(statements that would be factually wrong).

Metrics (all in [0, 1] except tool counts):

* factual_recall   — fraction of gold (asset, field) facts the prediction covers.
* grounded_recall  — same, but only counting facts whose supporting row/claim is
                     itself citation-grounded (the metric that matters most).
* factual_precision— TP / (TP + FP). TP = grounded covered facts. FP = invented
                     (ungrounded) extra asset rows + contradiction hits. This is a
                     conservative LOWER BOUND: a true asset absent from the
                     (incomplete) gold is NOT penalized as long as it is grounded.
* asset_recall     — fraction of gold assets that appear in the prediction.
* citation_coverage— fraction of narrative claims carrying >= 1 valid source.
* hallucination_rate— fraction of claims+rows that are ungrounded or contradicted.
* tool_calls / calls_per_asset — tool efficiency.

These are deliberately substring/term based so the harness is deterministic and
needs no LLM judge. The conservative-precision caveat is documented in the README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FIELDS = ["company", "target", "mechanism", "phase", "latest_readout"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def _contains(text_norm: str, term: str) -> bool:
    """Token-boundary containment: 'reversible' must NOT match inside
    'irreversible'. Works for multi-word terms because the normalized text is a
    space-separated run of [a-z0-9] tokens.

    NOTE: hyphens are treated as token boundaries (``non-covalent`` -> tokens
    ``non`` ``covalent``), so a bare ``covalent`` term WILL match inside
    ``non-covalent``. Author gold/contradiction terms accordingly (e.g. use the
    distinctive token, or a multi-word phrase, not a substring that also appears
    in its negation)."""
    t = _norm(term)
    if not t:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text_norm) is not None


def _any(text_norm: str, terms: list[str]) -> bool:
    return any(_contains(text_norm, t) for t in terms)


@dataclass
class QueryScore:
    query_id: str
    factual_recall: float = 0.0
    grounded_recall: float = 0.0
    factual_precision: float = 0.0
    asset_recall: float = 0.0
    citation_coverage: float = 0.0
    hallucination_rate: float = 0.0
    tool_calls: int = 0
    calls_per_asset: float = 0.0
    # raw counts for aggregation / transparency
    gold_facts: int = 0
    covered_facts: int = 0
    grounded_covered_facts: int = 0
    gold_assets: int = 0
    found_assets: int = 0
    true_positives: int = 0
    false_positives: int = 0
    n_claims: int = 0
    grounded_claims: int = 0
    details: dict[str, Any] = field(default_factory=dict)


def _norm_units(assets: list[dict], claims: list[dict], valid: set[str]):
    """Normalize an (assets, claims) prediction into text + grounded flags, used
    for citation-coverage / hallucination scoring."""
    rows = [
        {
            "text_norm": _norm(" ".join(str(a.get(k, "")) for k in ["asset_name", *FIELDS])),
            "grounded": any(s in valid for s in (a.get("source_ids") or [])),
        }
        for a in assets
    ]
    cl = [
        {
            "text_norm": _norm(c.get("text", "")),
            "grounded": any(s in valid for s in (c.get("source_ids") or [])),
        }
        for c in claims
    ]
    return rows, cl


def score_query(
    gold: dict,
    *,
    assets: list[dict],
    claims: list[dict],
    valid_source_ids: set[str],
    tool_calls: int,
    grounding_assets: list[dict] | None = None,
    grounding_claims: list[dict] | None = None,
    dropped_claims: int = 0,
) -> QueryScore:
    """Score one query.

    ``assets``/``claims`` are the *delivered* (post-guard) prediction, scored for
    factual recall/precision/asset-recall. ``grounding_assets``/``grounding_claims``
    are what the agent *submitted before* the reliability guard ran — used for
    citation_coverage / hallucination so the harness can detect ungrounded claims
    the guard caught (or missed). If omitted they default to the delivered set.
    ``dropped_claims`` (live mode, where the raw submission isn't available) folds
    guard-dropped claims into coverage/hallucination as ungrounded units.
    ``valid_source_ids`` is the universe of ids the agent actually retrieved."""

    gold_assets = gold.get("assets", [])
    contradictions = gold.get("contradictions", [])

    # Pre-normalize the prediction.
    norm_rows = []
    for a in assets:
        text = " ".join(
            str(a.get(k, "")) for k in ["asset_name", *FIELDS]
        )
        norm_rows.append(
            {
                "name_norm": _norm(a.get("asset_name", "")),
                "text_norm": _norm(text),
                "source_ids": [str(s) for s in a.get("source_ids", []) or []],
                "grounded": any(s in valid_source_ids for s in a.get("source_ids", []) or []),
                "matched_gold": False,
            }
        )
    norm_claims = [
        {
            "text_norm": _norm(c.get("text", "")),
            "source_ids": [str(s) for s in c.get("source_ids", []) or []],
            "grounded": any(s in valid_source_ids for s in c.get("source_ids", []) or []),
        }
        for c in claims
    ]

    score = QueryScore(query_id=gold.get("id", gold.get("query", "?")))

    # --- recall + grounded recall over (asset, field) facts ---------------
    total_facts = 0
    covered = 0
    grounded_covered = 0
    found_assets = 0

    for ga in gold_assets:
        aliases = [ga["name"], *ga.get("aliases", [])]
        # Locate the predicted row / claims that talk about this asset.
        row = next((r for r in norm_rows if _any(r["name_norm"], aliases)), None)
        if row is None:
            row = next((r for r in norm_rows if _any(r["text_norm"], aliases)), None)
        asset_claims = [c for c in norm_claims if _any(c["text_norm"], aliases)]
        present = row is not None or bool(asset_claims)
        if present:
            found_assets += 1
            if row is not None:
                row["matched_gold"] = True

        # Pool of text + grounding for this asset.
        pool_text = " ".join(
            [row["text_norm"]] if row else []
        ) + " " + " ".join(c["text_norm"] for c in asset_claims)
        asset_grounded = (row["grounded"] if row else False) or any(
            c["grounded"] for c in asset_claims
        )

        for fkey in FIELDS:
            terms = ga.get("facts", {}).get(fkey)
            if not terms:
                continue
            total_facts += 1
            if _any(pool_text, terms):
                covered += 1
                if asset_grounded:
                    grounded_covered += 1

    score.gold_facts = total_facts
    score.covered_facts = covered
    score.grounded_covered_facts = grounded_covered
    score.gold_assets = len(gold_assets)
    score.found_assets = found_assets
    score.factual_recall = covered / total_facts if total_facts else 1.0
    score.grounded_recall = grounded_covered / total_facts if total_facts else 1.0
    score.asset_recall = found_assets / len(gold_assets) if gold_assets else 1.0

    # --- precision: TP grounded facts vs FP invented/contradicted ---------
    tp = grounded_covered
    fp = 0
    # invented extra asset rows: don't map to gold AND not citation-grounded.
    for r in norm_rows:
        if not r["matched_gold"] and not r["grounded"]:
            fp += 1
    # contradiction hits across all rows + claims.
    contradiction_hits = 0
    for contra in contradictions:
        terms = contra.get("terms", [])
        for r in norm_rows:
            if terms and all(_contains(r["text_norm"], t) for t in terms):
                contradiction_hits += 1
        for c in norm_claims:
            if terms and all(_contains(c["text_norm"], t) for t in terms):
                contradiction_hits += 1
    fp += contradiction_hits

    score.true_positives = tp
    score.false_positives = fp
    score.factual_precision = tp / (tp + fp) if (tp + fp) else 1.0

    # --- citation coverage + hallucination (over the PRE-guard agent output) ---
    g_assets = grounding_assets if grounding_assets is not None else assets
    g_claims = grounding_claims if grounding_claims is not None else claims
    grow, gcl = _norm_units(g_assets, g_claims, valid_source_ids)

    # Coverage = grounded claims / ALL submitted claims (incl. guard-dropped ones).
    grounded_claims = sum(1 for c in gcl if c["grounded"])
    total_claims = len(gcl) + dropped_claims
    score.n_claims = total_claims
    score.grounded_claims = grounded_claims
    score.citation_coverage = grounded_claims / total_claims if total_claims else 1.0

    # Hallucination = fraction of units that are bad, counting each unit ONCE
    # (ungrounded OR contradicted), plus guard-dropped claims as bad units.
    bad = 0
    for u in gcl + grow:
        contradicted = any(
            terms and all(_contains(u["text_norm"], t) for t in terms)
            for terms in [c.get("terms", []) for c in contradictions]
        )
        if (not u["grounded"]) or contradicted:
            bad += 1
    bad += dropped_claims
    units = len(gcl) + len(grow) + dropped_claims
    score.hallucination_rate = bad / units if units else 0.0

    # --- tool efficiency --------------------------------------------------
    score.tool_calls = tool_calls
    score.calls_per_asset = (tool_calls / len(assets)) if assets else float(tool_calls)

    score.details = {
        "contradiction_hits": contradiction_hits,
        "invented_rows": fp - contradiction_hits,
    }
    return score


_AGG_KEYS = [
    "factual_precision", "factual_recall", "grounded_recall", "asset_recall",
    "citation_coverage", "hallucination_rate", "avg_tool_calls", "avg_calls_per_asset",
]


def aggregate(scores: list[QueryScore]) -> dict[str, float]:
    """Macro-average the headline metrics across queries."""
    if not scores:
        return {k: 0.0 for k in _AGG_KEYS}
    n = len(scores)

    def avg(attr: str) -> float:
        return round(sum(getattr(s, attr) for s in scores) / n, 4)

    return {
        "factual_precision": avg("factual_precision"),
        "factual_recall": avg("factual_recall"),
        "grounded_recall": avg("grounded_recall"),
        "asset_recall": avg("asset_recall"),
        "citation_coverage": avg("citation_coverage"),
        "hallucination_rate": avg("hallucination_rate"),
        "avg_tool_calls": round(sum(s.tool_calls for s in scores) / n, 2),
        "avg_calls_per_asset": avg("calls_per_asset"),
    }
