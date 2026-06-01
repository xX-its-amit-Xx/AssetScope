"""In-process smoke test of the FastAPI app (the same app the Docker `api`
service runs), driven against the configured LLM backend. Validates /health,
/tools, and a real /query without starting a server. Keeps stdout tiny."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from assetscope.api.main import app  # noqa: E402

client = TestClient(app)


def main() -> int:
    q = " ".join(sys.argv[1:]) or "competitive landscape for KRAS G12C inhibitors sotorasib and adagrasib in NSCLC"
    h = client.get("/health").json()
    print(f"/health: status={h['status']} backend_model={h['model']} anthropic={h['anthropic_configured']}")
    tools = client.get("/tools").json()
    print(f"/tools: {len(tools)} tools -> {[t['name'] for t in tools]}")

    r = client.post("/query", json={"query": q})
    print(f"/query: HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return 1
    ls = r.json()["landscape"]
    out = "C:\\ai\\tmp\\api_landscape.json"
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ls, f, indent=2)
    except OSError:
        out = "(not saved)"
    print(f"  assets={len(ls['assets'])} claims={len(ls['claims'])} "
          f"citations={len(ls['citations'])} tool_calls={ls['tool_calls']} dropped={ls['dropped_claims']}")
    for a in ls["assets"][:4]:
        print(f"   - {a['asset_name']} | {a['company']} | sources={len(a['source_ids'])} | verified={a['verified']}")
    print(f"  full landscape JSON -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
