"""The five tools the agent can call. Each is a self-contained callable that
returns a :class:`~assetscope.models.ToolResult` whose every item carries a
citation with a real source URL/ID.

``build_default_registry`` wires them up; the agent loop is handed the registry
and never imports individual tools directly.
"""

from assetscope.tools.base import Tool, ToolRegistry, build_default_registry
from assetscope.tools.chembl import ChemblTool
from assetscope.tools.clinical_trials import ClinicalTrialsTool
from assetscope.tools.fda import FdaTool
from assetscope.tools.literature import LiteratureTool
from assetscope.tools.open_targets import OpenTargetsTool
from assetscope.tools.retrieve import RetrieveTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "build_default_registry",
    "ClinicalTrialsTool",
    "OpenTargetsTool",
    "ChemblTool",
    "LiteratureTool",
    "FdaTool",
    "RetrieveTool",
]
