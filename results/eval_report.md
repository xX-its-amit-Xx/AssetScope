# AssetScope Eval Report

- **Mode:** `replay`
- **Generated:** 2026-06-01 17:20 UTC
- **Queries:** 3

## Aggregate scorecard (macro-average)

| Metric | Score |
|---|---|
| Factual precision | 100.0% |
| Factual recall |  87.5% |
| Grounded recall |  87.5% |
| Asset recall |  87.5% |
| Citation coverage |  88.9% |
| Hallucination rate |   6.2% |
| Avg tool calls / query | 11.0 |
| Avg tool calls / asset | 1.5714 |

## Per-query scorecard

| query          | fact_P | fact_R | cite_cov | halluc | assets | tools | dropped |
|----------------|--------|--------|----------|--------|--------|-------|---------|
| btk_inhibitors | 100.0% |  87.5% |  88.9%   |   6.2% | 7/8    | 12    | 1       |
| glp1_obesity   | 100.0% |  87.5% |  88.9%   |   6.2% | 7/8    | 10    | 1       |
| kras_g12c      | 100.0% |  87.5% |  88.9%   |   6.2% | 7/8    | 11    | 1       |

Columns: fact_P/fact_R = factual precision/recall vs gold facts; cite_cov = % delivered claims with a valid source; halluc = hallucination rate (ungrounded or contradicted units); assets = gold assets found; tools = external tool calls; dropped = claims removed by the reliability guard.

> Factual precision is a conservative lower bound: a real asset absent
> from the (incomplete) hand-curated gold is not penalized as long as it
> is citation-grounded. See `assetscope/evals/metrics.py` for definitions.
