from assetscope.evals.metrics import _contains, aggregate, score_query

GOLD = {
    "id": "toy",
    "query": "toy landscape",
    "assets": [
        {
            "name": "druga",
            "aliases": ["A-1"],
            "facts": {
                "company": ["Acme"],
                "target": ["BTK"],
                "mechanism": ["covalent", "irreversible"],
                "phase": ["Approved"],
                "latest_readout": ["TRIAL-X"],
            },
            "sources": ["NCT1", "100"],
        },
        {
            "name": "drugb",
            "aliases": [],
            "facts": {"company": ["Beta"], "target": ["BTK"], "phase": ["Phase 2"]},
            "sources": ["NCT2"],
        },
    ],
    "contradictions": [{"terms": ["druga", "reversible"], "note": "A is irreversible"}],
}


def test_token_boundary_no_false_substring():
    # 'reversible' must not match inside 'irreversible'
    assert _contains("covalent irreversible inhibitor", "irreversible")
    assert not _contains("covalent irreversible inhibitor", "reversible")


def test_perfect_grounded_prediction():
    assets = [
        {
            "asset_name": "DrugA (A-1)",
            "company": "Acme",
            "target": "BTK",
            "mechanism": "covalent irreversible inhibitor",
            "phase": "Approved",
            "latest_readout": "TRIAL-X met endpoint",
            "source_ids": ["NCT1"],
        },
        {
            "asset_name": "DrugB",
            "company": "Beta",
            "target": "BTK",
            "phase": "Phase 2",
            "source_ids": ["NCT2"],
        },
    ]
    claims = [
        {"text": "DrugA is an approved covalent BTK inhibitor.", "source_ids": ["NCT1", "100"]},
        {"text": "DrugB is a phase 2 BTK inhibitor.", "source_ids": ["NCT2"]},
    ]
    valid = {"NCT1", "NCT2", "100"}
    s = score_query(GOLD, assets=assets, claims=claims, valid_source_ids=valid, tool_calls=6)
    assert s.factual_recall == 1.0
    assert s.grounded_recall == 1.0
    assert s.factual_precision == 1.0
    assert s.asset_recall == 1.0
    assert s.citation_coverage == 1.0
    assert s.hallucination_rate == 0.0
    assert s.tool_calls == 6


def test_ungrounded_claim_counts_as_hallucination():
    assets = [{"asset_name": "DrugA", "company": "Acme", "source_ids": ["NCT1"]}]
    claims = [
        {"text": "DrugA is approved.", "source_ids": ["NCT1"]},
        {"text": "DrugA cures everything.", "source_ids": ["MADEUP"]},
    ]
    s = score_query(GOLD, assets=assets, claims=claims, valid_source_ids={"NCT1"}, tool_calls=3)
    assert s.citation_coverage == 0.5          # 1 of 2 claims grounded
    assert s.hallucination_rate > 0.0


def test_contradiction_detected():
    assets = [
        {
            "asset_name": "DrugA",
            "company": "Acme",
            "mechanism": "reversible inhibitor",  # contradicts gold (irreversible)
            "source_ids": ["NCT1"],
        }
    ]
    claims = [{"text": "DrugA is a reversible inhibitor.", "source_ids": ["NCT1"]}]
    s = score_query(GOLD, assets=assets, claims=claims, valid_source_ids={"NCT1"}, tool_calls=2)
    assert s.details["contradiction_hits"] >= 1
    assert s.factual_precision < 1.0


def test_aggregate_keys():
    s = score_query(GOLD, assets=[], claims=[], valid_source_ids=set(), tool_calls=0)
    agg = aggregate([s])
    for k in ["factual_precision", "factual_recall", "citation_coverage", "hallucination_rate"]:
        assert k in agg
