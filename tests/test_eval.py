from assetscope.evals.runner import run_suite


def test_replay_suite_scores():
    result = run_suite(mode="replay")
    scores = result["scores"]
    assert len(scores) == 3
    agg = result["aggregate"]

    # Delivered (post-guard) answers are fully grounded.
    assert agg["citation_coverage"] == 1.0
    assert agg["hallucination_rate"] == 0.0
    assert agg["factual_precision"] == 1.0
    # Recall is below 100% because each fixture deliberately omits one asset.
    assert 0.7 <= agg["factual_recall"] < 1.0
    assert agg["avg_tool_calls"] > 0

    # Each landscape's over-reaching claim is dropped by the guard.
    for run in result["runs"]:
        assert run.claims_dropped == 1


def test_replay_per_query_ids():
    result = run_suite(mode="replay")
    ids = {s.query_id for s in result["scores"]}
    assert ids == {"glp1_obesity", "kras_g12c", "btk_inhibitors"}
