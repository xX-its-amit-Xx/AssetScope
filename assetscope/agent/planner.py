"""The planner: decompose a query into ordered sub-questions before the tool loop."""

from __future__ import annotations

import json
import re

from assetscope.agent.prompts import PLANNER_PROMPT
from assetscope.config import Settings


def _fallback_plan(query: str) -> list[str]:
    return [
        f"Which molecular target(s) and disease biology underlie: {query}?",
        "Which assets are approved or in late-stage clinical development?",
        "What are the sponsoring companies, mechanisms and ChEMBL identifiers?",
        "What are the pivotal trial readouts (NCT ids) and PubMed evidence (PMIDs)?",
    ]


def make_plan(query: str, client, settings: Settings) -> list[str]:
    """Ask the planner model for sub-questions; degrade gracefully on any error."""
    try:
        resp = client.messages.create(
            model=settings.planner_model,
            max_tokens=600,
            system=PLANNER_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        plan = _extract_json_array(text)
        return plan or _fallback_plan(query)
    except Exception:
        return _fallback_plan(query)


def _extract_json_array(text: str) -> list[str]:
    # Strip markdown fences if present, then find the first JSON array.
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in data if str(x).strip()][:6]
