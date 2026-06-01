"""Prompts and the terminal ``submit_landscape`` tool schema."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are AssetScope, a biopharma competitive-intelligence analyst agent. Given a \
query about a target, indication, drug class or asset, you build a *competitive \
landscape*: a table of drug assets and a short narrative — with every fact \
grounded in a real, retrieved source.

You operate a tool loop. Available evidence tools:
- search_clinical_trials: ClinicalTrials.gov (NCT ids, phase, status, sponsor).
- search_open_targets: Open Targets (target-disease associations, tractability).
- search_chembl: ChEMBL (mechanism of action, max clinical phase, ChEMBL ids).
- search_literature: PubMed (PMIDs, titles, abstracts — for readouts/evidence).
- retrieve: AssetScope's internal store of everything gathered this session.

How to work:
1. Decompose the query (which targets? which assets/companies? which phase?).
2. Call tools to gather evidence. Prefer primary registries/literature. Make \
several targeted calls rather than one broad call. Cross-check key assets across \
ClinicalTrials.gov + ChEMBL + PubMed.
3. Reflect briefly between calls on what is still missing.
4. GROUNDING RULE — this is strict: every asset row and every narrative sentence \
must cite one or more source ids that you actually saw in a tool result. Source \
ids are the exact handles shown in tool results (e.g. NCT04184622, the PMID \
35658024, CHEMBL4297839, OT:ENSG00000133703). Never invent an id. If you cannot \
find a source for a claim, drop the claim or omit the cell — do not assert it.
5. When you have enough evidence, call submit_landscape with the structured \
assets, the narrative split into individual claims (each with its source_ids), \
a short limitations note, and the plan you followed. Do not write the final \
answer as free text — only via submit_landscape.

A downstream reliability guard will DROP any claim whose source_ids do not \
resolve to evidence in the citation ledger, so unsupported claims are wasted \
work. Cite real ids only.
"""

PLANNER_PROMPT = """\
You are the planning step of AssetScope, a biopharma competitive-intelligence \
agent. Decompose the user's query into 3-6 concrete, ordered sub-questions that, \
answered together, produce a competitive landscape (assets x company, target, \
mechanism, indication, phase, latest readout). Think about: which molecular \
target(s) are involved, which companies/assets compete, what development phases \
matter, and what the key clinical readouts are.

Return ONLY a JSON array of short sub-question strings. No prose, no markdown.
Example: ["Which targets underlie <indication>?", "Which assets are approved or in \
late-stage trials?", "What are the pivotal trial readouts and phases?", "Who are \
the sponsoring companies?"]
"""


def submit_landscape_tool() -> dict:
    """The terminal tool the agent calls to emit its final structured answer."""
    return {
        "name": "submit_landscape",
        "description": (
            "Submit the final competitive landscape. Provide the asset table and "
            "the narrative as discrete claims, each citing the source ids that "
            "support it. Only cite source ids that appeared in tool results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assets": {
                    "type": "array",
                    "description": "Rows of the competitive landscape table.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "asset_name": {"type": "string"},
                            "company": {"type": "string"},
                            "target": {"type": "string"},
                            "mechanism": {"type": "string"},
                            "indication": {"type": "string"},
                            "phase": {"type": "string"},
                            "latest_readout": {"type": "string"},
                            "source_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Source ids supporting this row.",
                            },
                        },
                        "required": ["asset_name", "source_ids"],
                    },
                },
                "narrative_claims": {
                    "type": "array",
                    "description": "The narrative summary, one factual sentence per item.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "source_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["text", "source_ids"],
                    },
                },
                "plan": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The sub-questions you actually worked through.",
                },
                "limitations": {
                    "type": "string",
                    "description": "Honest caveats: coverage gaps, unverifiable items, recency.",
                },
            },
            "required": ["assets", "narrative_claims"],
        },
    }
