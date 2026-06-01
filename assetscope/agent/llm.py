"""Pluggable LLM backend for the agent loop.

The loop is written against the Anthropic Messages API shape
(``client.messages.create(...)`` returning content blocks with ``.type`` /
``.text`` / ``.id`` / ``.name`` / ``.input`` and a ``stop_reason``). To run the
exact same loop against a **local, OpenAI-compatible** model server (e.g.
llama.cpp ``llama-server`` or Ollama), this module provides
:class:`LocalMessagesClient` — an adapter that:

1. Translates Anthropic-style ``system`` / ``messages`` / ``tools`` into an
   OpenAI ``chat/completions`` request, encoding the tools and a strict
   **JSON-action protocol** into the prompt (rather than relying on a small
   model's native function-calling, which is unreliable).
2. Parses the model's JSON reply back into Anthropic-style content blocks.

``make_llm_client(settings)`` returns the right backend based on
``ASSETSCOPE_LLM_BACKEND`` (``anthropic`` | ``openai``/``local``). The agent loop
and planner are unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from types import SimpleNamespace
from typing import Any

import httpx

from assetscope.config import Settings

logger = logging.getLogger("assetscope.agent.llm")

# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def make_llm_client(settings: Settings) -> Any:
    backend = (settings.llm_backend or "anthropic").lower()
    if backend in ("openai", "local", "llama", "llamacpp", "ollama", "vllm"):
        if not settings.llm_base_url:
            raise RuntimeError(
                "ASSETSCOPE_LLM_BACKEND is local/openai but ASSETSCOPE_LLM_BASE_URL is unset "
                "(e.g. http://127.0.0.1:8081/v1)."
            )
        return LocalMessagesClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            max_tokens_cap=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
    # default: Anthropic
    if not settings.has_anthropic:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it, or set ASSETSCOPE_LLM_BACKEND=local with "
            "ASSETSCOPE_LLM_BASE_URL to use a local OpenAI-compatible model."
        )
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> dict | None:
    """Return the first balanced top-level JSON object in ``text`` (tolerant of
    surrounding prose / markdown fences)."""
    t = text.strip()
    # Strip a leading ```lang fence and a trailing ``` fence if present (robustly,
    # without str.strip('`') which can eat backticks inside JSON string values).
    t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # brace-scan, skipping braces inside strings
    start = t.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(t[start : i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


# ---------------------------------------------------------------------------
# Local (OpenAI-compatible) adapter
# ---------------------------------------------------------------------------

PROTOCOL_HEADER = """\
You have access to the following tools. Choose ONE per step.

TOOLS:
{tools}

RESPONSE PROTOCOL — respond with EXACTLY ONE minified JSON object and nothing \
else (no markdown, no prose outside the JSON):
  {{"thought": "<one short sentence>", "tool": "<tool_name>", "args": {{ ...arguments matching that tool's schema... }}}}

Rules:
- "tool" MUST be one of the tool names above.
- "args" MUST match that tool's input schema. Use only fields that exist.
- When you have gathered enough evidence, call the tool "submit_landscape" with \
your final structured answer; cite only source ids you saw in tool results.
- Output valid JSON only. Do not wrap it in code fences.\
"""


class _Messages:
    def __init__(self, parent: LocalMessagesClient) -> None:
        self._p = parent

    def create(self, **kwargs: Any):
        return self._p._create(**kwargs)


class LocalMessagesClient:
    """Anthropic-Messages-compatible facade over an OpenAI chat endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "local",
        max_tokens_cap: int = 1536,
        temperature: float = 0.2,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens_cap = max_tokens_cap
        self.temperature = temperature
        self._http = httpx.Client(
            timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )
        self.messages = _Messages(self)
        self._counter = 0

    # -- main entrypoint (mirrors anthropic client.messages.create) --------
    def _create(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        system: str | None = None,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        **_ignored: Any,
    ):
        oai_messages = self._to_openai_messages(system, messages, tools, tool_choice)
        body: dict[str, Any] = {
            "model": self.model or model or "local",
            "messages": oai_messages,
            "temperature": self.temperature,
            "max_tokens": min(max_tokens, self.max_tokens_cap),
            "stream": False,
        }
        if tools:
            # constrain to a JSON object so parsing the action is reliable
            body["response_format"] = {"type": "json_object"}

        resp = self._http.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        content = (
            resp.json().get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        )

        if not tools:
            # planner / plain-text turn
            return SimpleNamespace(content=[_text_block(content)], stop_reason="end_turn")

        return self._parse_action(content, tools)

    # -- conversion --------------------------------------------------------
    def _to_openai_messages(
        self,
        system: str | None,
        messages: list[dict],
        tools: list[dict] | None,
        tool_choice: dict | None,
    ) -> list[dict]:
        sys_parts = [system] if system else []
        if tools:
            forced = tool_choice.get("name") if tool_choice else None
            # When a specific tool is forced, present ONLY that tool so a small
            # local model can't wander off and call something else.
            present = [t for t in tools if t["name"] == forced] if forced else tools
            present = present or tools
            tool_doc = "\n".join(
                f"- {t['name']}: {t.get('description', '')}\n"
                f"    input_schema: {json.dumps(t.get('input_schema', {}).get('properties', {}))}"
                f"  required: {t.get('input_schema', {}).get('required', [])}"
                for t in present
            )
            sys_parts.append(PROTOCOL_HEADER.format(tools=tool_doc))
            if forced:
                sys_parts.append(
                    f'You have reached your tool budget. You MUST now respond by calling ONLY '
                    f'the tool "{forced}" with your complete, final answer. Cite only source ids '
                    f'that appeared in earlier TOOL RESULT messages. Do not call any other tool.'
                )
        out: list[dict] = []
        if sys_parts:
            out.append({"role": "system", "content": "\n\n".join(sys_parts)})

        for m in messages:
            role = m["role"]
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue
            # content is a list of Anthropic blocks
            text_bits: list[str] = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    text_bits.append(block.get("text", ""))
                elif btype == "tool_use":
                    text_bits.append(
                        json.dumps({"tool": block.get("name"), "args": block.get("input", {})})
                    )
                elif btype == "tool_result":
                    body = block.get("content", "")
                    if isinstance(body, list):  # anthropic can nest blocks
                        body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                    text_bits.append(f"TOOL RESULT [{block.get('tool_use_id', '')}]:\n{body}")
            joined = "\n".join(t for t in text_bits if t)
            # tool_result blocks come back as role 'user'; keep that role.
            out.append({"role": role, "content": joined})
        return out

    # -- parsing the action ------------------------------------------------
    def _parse_action(self, content: str, tools: list[dict]):
        names = {t["name"] for t in tools}
        obj = _extract_json_object(content)
        if not obj or obj.get("tool") not in names:
            # Could not extract a valid tool action — return as text so the loop nudges.
            logger.warning("local model did not emit a valid tool action: %.200s", content)
            return SimpleNamespace(content=[_text_block(content or "(no action)")], stop_reason="end_turn")

        self._counter += 1
        blocks = []
        thought = obj.get("thought")
        if thought:
            blocks.append(_text_block(str(thought)))
        args = obj.get("args")
        if not isinstance(args, dict):
            args = {}
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                id=f"call_{self._counter}",
                name=obj["tool"],
                input=args,
            )
        )
        return SimpleNamespace(content=blocks, stop_reason="tool_use")


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)
