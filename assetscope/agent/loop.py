"""The AssetScope agent loop.

A deliberately framework-light loop so the control flow is legible:

    plan  ->  [ select tool -> call -> observe -> reflect ]*  ->  guard  ->  answer

The executor talks to the Anthropic Messages API with tool use. After every tool
call it (a) registers the returned citations in the ledger and (b) ingests the
evidence into the hybrid vector store, so ``retrieve`` can recall it later. When
the model calls the terminal ``submit_landscape`` tool — or the tool/iteration
budget is exhausted — the reliability guard runs and the final landscape is
emitted. The loop yields :class:`AgentEvent`s so callers can stream progress.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from assetscope.agent.events import AgentEvent, EventType
from assetscope.agent.planner import make_plan
from assetscope.agent.prompts import SYSTEM_PROMPT, submit_landscape_tool
from assetscope.config import Settings, get_settings
from assetscope.guards import CitationLedger, ReliabilityGuard
from assetscope.models import Asset, Claim, Landscape, ToolResult

logger = logging.getLogger("assetscope.agent")

_MAX_RESULT_CHARS = 320   # per evidence item appended back to the model
_MAX_RESULT_ITEMS = 6     # items echoed to the model (the rest still get ingested)


class AssetScopeAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        registry: Any | None = None,
        retriever: Any | None = None,
        guard: ReliabilityGuard | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._registry = registry
        self._retriever = retriever
        self.guard = guard or ReliabilityGuard(drop_unsupported=True)
        self._client = client
        self.last_landscape: Landscape | None = None

    # -- lazy heavy deps ---------------------------------------------------
    @property
    def retriever(self):
        if self._retriever is None:
            from assetscope.retrieval import HybridRetriever

            self._retriever = HybridRetriever()
        return self._retriever

    @property
    def registry(self):
        if self._registry is None:
            from assetscope.tools import build_default_registry

            self._registry = build_default_registry(retriever=self.retriever)
        return self._registry

    @property
    def client(self):
        if self._client is None:
            from assetscope.agent.llm import make_llm_client

            self._client = make_llm_client(self.settings)
        return self._client

    @property
    def model(self) -> str:
        """The executor model name to send (local backend ignores it)."""
        if (self.settings.llm_backend or "anthropic").lower() == "anthropic":
            return self.settings.anthropic_model
        return self.settings.llm_model

    # -- public API --------------------------------------------------------
    def run_to_completion(self, query: str) -> Landscape:
        for _ in self.run(query):
            pass
        assert self.last_landscape is not None
        return self.last_landscape

    def run(self, query: str) -> Iterator[AgentEvent]:
        ledger = CitationLedger()
        yield AgentEvent.status(f"Planning: {query}")

        plan = make_plan(query, self.client, self.settings)
        yield AgentEvent(type=EventType.PLAN, data={"plan": plan})

        tools = self.registry.anthropic_schemas() + [submit_landscape_tool()]
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n\nPlan to follow:\n"
                    + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(plan))
                    + "\n\nWork through the plan with the tools, then call submit_landscape."
                ),
            }
        ]

        tool_calls = 0
        submission: dict | None = None
        nudges = 0
        iterations = 0

        for _ in range(self.settings.max_iterations):
            iterations += 1
            force_submit = tool_calls >= self.settings.max_tool_calls
            if force_submit:
                yield AgentEvent.status("Budget reached — forcing finalization.")

            try:
                resp = self._create(messages, tools, force_submit)
            except Exception as exc:  # noqa: BLE001
                yield AgentEvent.error(f"Anthropic call failed: {exc}")
                break

            assistant_content: list[dict] = []
            tool_uses: list[Any] = []
            for block in resp.content:
                btype = getattr(block, "type", "")
                if btype == "text" and block.text.strip():
                    assistant_content.append({"type": "text", "text": block.text})
                    yield AgentEvent(type=EventType.MESSAGE, data={"text": block.text})
                elif btype == "tool_use":
                    assistant_content.append(
                        {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                    )
                    tool_uses.append(block)
            messages.append({"role": "assistant", "content": assistant_content})

            # No tool call this turn -> nudge toward finalizing.
            if not tool_uses:
                nudges += 1
                if nudges >= 2:
                    force_submit = True
                messages.append(
                    {
                        "role": "user",
                        "content": "Continue: call a tool to gather more evidence, or call "
                        "submit_landscape if you have enough.",
                    }
                )
                if nudges >= 3:
                    yield AgentEvent.status("Model did not finalize; stopping.")
                    break
                continue

            # Handle the submit_landscape terminal tool first if present.
            submit_block = next((b for b in tool_uses if b.name == "submit_landscape"), None)
            if submit_block is not None:
                submission = submit_block.input
                yield AgentEvent.status("Landscape submitted — running reliability guard.")
                break

            # Otherwise execute the evidence tools and feed results back.
            tool_results_content: list[dict] = []
            for block in tool_uses:
                tool_calls += 1
                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={"tool": block.name, "args": block.input, "call_index": tool_calls},
                )
                result = self.registry.dispatch(block.name, dict(block.input))
                self._observe(result, ledger)
                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={
                        "tool": block.name,
                        "summary": result.summary,
                        "error": result.error,
                        "citations": [c.model_dump() for c in result.citations()],
                        "n_items": len(result.items),
                    },
                )
                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": self._render_result(result),
                        "is_error": bool(result.error),
                    }
                )
            messages.append({"role": "user", "content": tool_results_content})

        # Build + guard the landscape.
        landscape = self._build_landscape(query, plan, submission, tool_calls, iterations)
        cleaned, report = self.guard.apply(landscape, ledger)
        self.last_landscape = cleaned

        yield AgentEvent(
            type=EventType.GUARD,
            data={
                "total_claims": report.total_claims,
                "supported_claims": report.supported_claims,
                "unverified_claims": report.unverified_claims,
                "dropped_claims": report.dropped_claims,
                "flagged_assets": report.flagged_assets,
                "citation_coverage": round(report.citation_coverage, 4),
                "notes": report.notes,
            },
        )
        yield AgentEvent(type=EventType.LANDSCAPE, data={"landscape": cleaned.model_dump(mode="json")})
        yield AgentEvent(type=EventType.DONE, data={"tool_calls": tool_calls})

    # -- internals ---------------------------------------------------------
    def _create(self, messages: list[dict], tools: list[dict], force_submit: bool):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.settings.max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": tools,
            "messages": messages,
        }
        if force_submit:
            kwargs["tool_choice"] = {"type": "tool", "name": "submit_landscape"}
        return self.client.messages.create(**kwargs)

    def _observe(self, result: ToolResult, ledger: CitationLedger) -> None:
        """Register citations and ingest evidence into the vector store."""
        ledger.register_result(result)
        if result.items:
            try:
                self.retriever.ingest(result.items)
            except Exception as exc:  # noqa: BLE001 - ingestion is best-effort
                logger.warning("Evidence ingestion skipped: %s", exc)

    @staticmethod
    def _render_result(result: ToolResult) -> str:
        if result.error:
            return f"ERROR: {result.error}"
        lines = [result.summary]
        for item in result.items[:_MAX_RESULT_ITEMS]:
            c = item.citation
            body = " ".join(item.content.split())[:_MAX_RESULT_CHARS]
            lines.append(f"[source_id={c.id}] {c.title}: {body}")
        extra = len(result.items) - _MAX_RESULT_ITEMS
        if extra > 0:
            lines.append(f"(+{extra} more results ingested; call retrieve to see them)")
        return "\n".join(lines)

    def _build_landscape(
        self,
        query: str,
        plan: list[str],
        submission: dict | None,
        tool_calls: int,
        iterations: int,
    ) -> Landscape:
        assets: list[Asset] = []
        claims: list[Claim] = []
        limitations = ""
        if submission:
            for a in submission.get("assets", []) or []:
                assets.append(
                    Asset(
                        asset_name=a.get("asset_name", "") or "(unnamed)",
                        company=a.get("company", ""),
                        target=a.get("target", ""),
                        mechanism=a.get("mechanism", ""),
                        indication=a.get("indication", ""),
                        phase=a.get("phase", ""),
                        latest_readout=a.get("latest_readout", ""),
                        source_ids=[str(s) for s in a.get("source_ids", []) or []],
                    )
                )
            for i, c in enumerate(submission.get("narrative_claims", []) or []):
                claims.append(
                    Claim(
                        id=f"c{i + 1}",
                        text=c.get("text", ""),
                        source_ids=[str(s) for s in c.get("source_ids", []) or []],
                    )
                )
            limitations = submission.get("limitations", "") or ""
            if submission.get("plan"):
                plan = [str(p) for p in submission["plan"]]
        return Landscape(
            query=query,
            plan=plan,
            assets=assets,
            claims=claims,
            limitations=limitations,
            tool_calls=tool_calls,
            iterations=iterations,
        )
