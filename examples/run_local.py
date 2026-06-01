"""Run the AssetScope agent end-to-end against a local OpenAI-compatible model.

Usage (with a local llama-server / Ollama running):

    set ASSETSCOPE_LLM_BACKEND=local
    set ASSETSCOPE_LLM_BASE_URL=http://127.0.0.1:8081/v1
    python examples/run_local.py "competitive landscape for KRAS G12C inhibitors in NSCLC"

It streams the plan, tool calls, the reliability-guard report, and the final
citation-grounded landscape. Tools hit the real public APIs.
"""

from __future__ import annotations

import os
import sys

# Make the repo importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Be robust to non-UTF8 consoles (e.g. Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from assetscope.agent import AssetScopeAgent  # noqa: E402
from assetscope.agent.events import EventType  # noqa: E402


def main() -> int:
    query = (
        " ".join(sys.argv[1:])
        or "competitive landscape for KRAS G12C inhibitors in NSCLC"
    )
    agent = AssetScopeAgent()
    print(f"\n=== QUERY: {query}\n")
    landscape = None
    for ev in agent.run(query):
        if ev.type == EventType.PLAN:
            print("PLAN:")
            for i, p in enumerate(ev.data["plan"], 1):
                print(f"  {i}. {p}")
            print()
        elif ev.type == EventType.MESSAGE:
            print(f"  think: {ev.data['text'][:160]}")
        elif ev.type == EventType.TOOL_CALL:
            print(f"  -> #{ev.data['call_index']} {ev.data['tool']}({ev.data['args']})")
        elif ev.type == EventType.TOOL_RESULT:
            tag = "ERR" if ev.data.get("error") else "ok"
            print(f"     [{tag}] {ev.data['summary'] or ev.data.get('error')}")
        elif ev.type == EventType.GUARD:
            d = ev.data
            print(
                f"\nGUARD: coverage={d['citation_coverage']:.0%} "
                f"supported={d['supported_claims']} dropped={d['dropped_claims']} "
                f"flagged_assets={d['flagged_assets']}"
            )
        elif ev.type == EventType.LANDSCAPE:
            landscape = ev.data["landscape"]
        elif ev.type == EventType.STATUS:
            print(f"  . {ev.data['message']}")
        elif ev.type == EventType.ERROR:
            print(f"  XX {ev.data['message']}")

    if landscape:
        print("\n=== LANDSCAPE TABLE ===")
        for a in landscape["assets"]:
            flag = "" if a["verified"] else "  [UNVERIFIED]"
            print(f"- {a['asset_name']} | {a['company']} | {a['phase']} "
                  f"| sources={a['source_ids']}{flag}")
        print(f"\nclaims: {len(landscape['claims'])} | citations: {len(landscape['citations'])} "
              f"| tool_calls: {landscape['tool_calls']} | dropped: {landscape['dropped_claims']}")
        print("\nNarrative:")
        print(landscape["narrative"][:1200])
    else:
        print("\n(no landscape produced)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
