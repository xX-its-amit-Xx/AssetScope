"""Streaming events emitted by the agent loop.

The FastAPI layer serializes these to SSE; the eval harness consumes the final
``landscape`` event. Keeping a single typed event object makes the stream easy
to render in the React UI (plan trace, tool calls, guard summary, answer)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    STATUS = "status"          # human-readable lifecycle note
    PLAN = "plan"              # the planner's sub-questions
    MESSAGE = "message"        # assistant free-text (reflection between tools)
    TOOL_CALL = "tool_call"    # the agent decided to call a tool
    TOOL_RESULT = "tool_result"  # the (summarized) result of that call
    GUARD = "guard"            # reliability guard report
    LANDSCAPE = "landscape"    # the final structured answer
    ERROR = "error"
    DONE = "done"


class AgentEvent(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def status(cls, message: str, **extra: Any) -> AgentEvent:
        return cls(type=EventType.STATUS, data={"message": message, **extra})

    @classmethod
    def error(cls, message: str, **extra: Any) -> AgentEvent:
        return cls(type=EventType.ERROR, data={"message": message, **extra})
