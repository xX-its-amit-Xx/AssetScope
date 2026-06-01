"""Tool protocol + registry.

A :class:`Tool` bundles an Anthropic-compatible JSON schema with a Python
implementation that returns a :class:`ToolResult`. The :class:`ToolRegistry`
exposes the schemas for the Anthropic ``tools`` parameter and dispatches calls
by name, normalizing any exception into a ``ToolResult`` with an ``error`` (so a
single failing tool call never crashes the agent loop).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from assetscope.models import ToolResult

logger = logging.getLogger("assetscope.tools")


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:  # pragma: no cover - abstract
        ...

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {t.name: t for t in tools}

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def anthropic_schemas(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(tool=name, args=args, error=f"Unknown tool: {name}")
        try:
            return self._tools[name].run(**args)
        except TypeError as exc:
            # bad/missing arguments from the model
            return ToolResult(tool=name, args=args, error=f"Invalid arguments: {exc}")
        except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
            logger.exception("Tool %s failed", name)
            return ToolResult(tool=name, args=args, error=f"{type(exc).__name__}: {exc}")


def build_default_registry(retriever: Any | None = None) -> ToolRegistry:
    """Construct the standard 5-tool registry.

    ``retriever`` (a :class:`HybridRetriever`) is injected into the ``retrieve``
    tool; if omitted, a default one is created lazily on first use.
    """
    # Imported here to avoid a circular import at module load time.
    from assetscope.tools.chembl import ChemblTool
    from assetscope.tools.clinical_trials import ClinicalTrialsTool
    from assetscope.tools.fda import FdaTool
    from assetscope.tools.literature import LiteratureTool
    from assetscope.tools.open_targets import OpenTargetsTool
    from assetscope.tools.retrieve import RetrieveTool

    return ToolRegistry(
        [
            ClinicalTrialsTool(),
            OpenTargetsTool(),
            ChemblTool(),
            LiteratureTool(),
            FdaTool(),
            RetrieveTool(retriever=retriever),
        ]
    )
