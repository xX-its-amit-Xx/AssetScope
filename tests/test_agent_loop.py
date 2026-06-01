"""Exercise the full agent loop deterministically with a fake Anthropic client
and a fake tool — no network, no API key, no DB."""

from types import SimpleNamespace

from assetscope.agent import AssetScopeAgent
from assetscope.agent.events import EventType
from assetscope.agent.prompts import PLANNER_PROMPT
from assetscope.models import Citation, EvidenceItem, SourceType, ToolResult
from assetscope.tools.base import Tool, ToolRegistry


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool(id, name, inp):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=inp)


def _resp(blocks):
    return SimpleNamespace(content=blocks, stop_reason="tool_use")


class FakeClient:
    def __init__(self):
        self.exec_calls = 0
        self.messages = self

    def create(self, **kwargs):
        if kwargs.get("system") == PLANNER_PROMPT:
            return _resp([_text('["Which targets?", "Which assets and phases?"]')])
        self.exec_calls += 1
        if self.exec_calls == 1:
            return _resp([
                _text("I'll look up the pivotal trial."),
                _tool("t1", "search_clinical_trials", {"query": "ibrutinib CLL"}),
            ])
        return _resp([
            _tool("t2", "submit_landscape", {
                "assets": [{
                    "asset_name": "Ibrutinib",
                    "company": "AbbVie",
                    "target": "BTK",
                    "mechanism": "covalent BTK inhibitor",
                    "indication": "CLL",
                    "phase": "Approved",
                    "latest_readout": "RESONATE",
                    "source_ids": ["NCT1"],
                }],
                "narrative_claims": [
                    {"text": "Ibrutinib is an approved covalent BTK inhibitor.", "source_ids": ["NCT1"]},
                    {"text": "Ibrutinib cures all cancers.", "source_ids": ["GHOST"]},
                ],
                "limitations": "toy run",
            }),
        ])


class FakeTrialsTool(Tool):
    name = "search_clinical_trials"
    description = "fake"
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def run(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool=self.name,
            items=[EvidenceItem(
                citation=Citation(id="NCT1", source_type=SourceType.CLINICAL_TRIALS,
                                  source_id="NCT1", url="https://clinicaltrials.gov/study/NCT1",
                                  title="RESONATE"),
                content="RESONATE: ibrutinib vs ofatumumab in R/R CLL.",
            )],
            summary="1 trial",
        )


class FakeRetriever:
    backend = "test"

    def ingest(self, items):
        return len(items)


def _agent():
    return AssetScopeAgent(
        registry=ToolRegistry([FakeTrialsTool()]),
        retriever=FakeRetriever(),
        client=FakeClient(),
    )


def test_loop_runs_tools_and_guards():
    agent = _agent()
    events = list(agent.run("BTK inhibitors in CLL"))
    types = [e.type for e in events]
    assert EventType.PLAN in types
    assert EventType.TOOL_CALL in types
    assert EventType.TOOL_RESULT in types
    assert EventType.GUARD in types
    assert EventType.LANDSCAPE in types
    assert types[-1] == EventType.DONE

    ls = agent.last_landscape
    assert ls is not None
    assert [a.asset_name for a in ls.assets] == ["Ibrutinib"]
    # the unsupported "cures all cancers" claim is dropped by the guard
    assert ls.dropped_claims == 1
    assert all("cures all cancers" not in c.text for c in ls.claims)
    assert ls.tool_calls == 1
    assert any(c.id == "NCT1" for c in ls.citations)


def test_guard_event_reports_coverage():
    agent = _agent()
    guard_ev = next(e for e in agent.run("q") if e.type == EventType.GUARD)
    # 1 of 2 submitted claims grounded (the other dropped) -> coverage 0.5
    assert guard_ev.data["citation_coverage"] == 0.5
    assert guard_ev.data["dropped_claims"] == 1
