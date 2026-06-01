"""CLI: ``python -m assetscope.evals run`` — prints a scorecard and writes a report.

    python -m assetscope.evals run                 # replay bundled fixtures (default)
    python -m assetscope.evals run --live           # run the live agent (needs API key)
    python -m assetscope.evals run --out results/eval_report.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from assetscope.evals.metrics import QueryScore
from assetscope.evals.runner import EvalRun, run_suite

PCT = ["factual_precision", "factual_recall", "grounded_recall", "asset_recall",
       "citation_coverage", "hallucination_rate"]


def _fmt_pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def _scorecard_rows(scores: list[QueryScore], runs: list[EvalRun]) -> list[list[str]]:
    rows = []
    by_id = {r.query_id: r for r in runs}
    for s in scores:
        r = by_id.get(s.query_id)
        rows.append([
            s.query_id,
            _fmt_pct(s.factual_precision),
            _fmt_pct(s.factual_recall),
            _fmt_pct(s.citation_coverage),
            _fmt_pct(s.hallucination_rate),
            f"{s.found_assets}/{s.gold_assets}",
            str(s.tool_calls),
            str(r.claims_dropped if r else 0),
        ])
    return rows


HEADERS = ["query", "fact_P", "fact_R", "cite_cov", "halluc", "assets", "tools", "dropped"]


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    # Wrap the args in a list so max() has one iterable even when rows is empty.
    widths = [max([len(headers[i]), *(len(r[i]) for r in rows)]) for i in range(len(headers))]
    def line(cells):
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(headers), sep, *(line(r) for r in rows)])


def _markdown_report(result: dict) -> str:
    agg = result["aggregate"]
    scores: list[QueryScore] = result["scores"]
    runs: list[EvalRun] = result["runs"]
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rows = _scorecard_rows(scores, runs)

    lines = [
        "# AssetScope Eval Report",
        "",
        f"- **Mode:** `{result['mode']}`",
        f"- **Generated:** {now}",
        f"- **Queries:** {len(scores)}",
        "",
        "## Aggregate scorecard (macro-average)",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Factual precision | {_fmt_pct(agg['factual_precision'])} |",
        f"| Factual recall | {_fmt_pct(agg['factual_recall'])} |",
        f"| Grounded recall | {_fmt_pct(agg['grounded_recall'])} |",
        f"| Asset recall | {_fmt_pct(agg['asset_recall'])} |",
        f"| Citation coverage | {_fmt_pct(agg['citation_coverage'])} |",
        f"| Hallucination rate | {_fmt_pct(agg['hallucination_rate'])} |",
        f"| Avg tool calls / query | {agg['avg_tool_calls']} |",
        f"| Avg tool calls / asset | {agg['avg_calls_per_asset']} |",
        "",
        "## Per-query scorecard",
        "",
        _render_table(HEADERS, rows),
        "",
        "Columns: fact_P/fact_R = factual precision/recall vs gold facts; "
        "cite_cov = % delivered claims with a valid source; halluc = hallucination "
        "rate (ungrounded or contradicted units); assets = gold assets found; "
        "tools = external tool calls; dropped = claims removed by the reliability guard.",
        "",
        "> Factual precision is a conservative lower bound: a real asset absent",
        "> from the (incomplete) hand-curated gold is not penalized as long as it",
        "> is citation-grounded. See `assetscope/evals/metrics.py` for definitions.",
        "",
    ]
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace) -> int:
    if args.live and not args.replay:
        mode = "live"
    else:
        mode = "replay"
    result = run_suite(mode=mode, gold_dir=args.gold_dir, fixtures_dir=args.fixtures_dir)

    if not result["scores"]:
        src = args.gold_dir or "the bundled gold set"
        print(f"\nNo gold queries found in {src}. Nothing to score.")
        return 2

    rows = _scorecard_rows(result["scores"], result["runs"])
    print(f"\nAssetScope eval scorecard  (mode={mode})\n")
    print(_render_table(HEADERS, rows))
    agg = result["aggregate"]
    print("\nAggregate (macro-avg):")
    for k in PCT:
        print(f"  {k:20s} {_fmt_pct(agg[k])}")
    print(f"  {'avg_tool_calls':20s} {agg['avg_tool_calls']}")
    print(f"  {'avg_calls_per_asset':20s} {agg['avg_calls_per_asset']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_markdown_report(result), encoding="utf-8")
    print(f"\nWrote report -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assetscope.evals", description="AssetScope eval harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the eval suite and print a scorecard.")
    run_p.add_argument("--live", action="store_true", help="Run the live agent (needs ANTHROPIC_API_KEY).")
    run_p.add_argument("--replay", action="store_true", help="Score bundled fixtures (default).")
    run_p.add_argument("--gold-dir", default=None, help="Override gold dataset directory.")
    run_p.add_argument("--fixtures-dir", default=None, help="Override replay fixtures directory.")
    run_p.add_argument("--out", default="results/eval_report.md", help="Report output path.")
    run_p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
