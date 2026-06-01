"""AssetScope evaluation harness.

Measures the agent on the things that matter for a citation-grounded CI engine:
factual precision/recall vs a hand-curated gold set, citation coverage,
hallucination rate, and tool efficiency. Run with::

    python -m assetscope.evals run            # replay bundled fixtures (no API key)
    python -m assetscope.evals run --live      # run the live agent (needs API key)
"""

from assetscope.evals.metrics import QueryScore, score_query
from assetscope.evals.runner import EvalRun, run_suite

__all__ = ["QueryScore", "score_query", "EvalRun", "run_suite"]
