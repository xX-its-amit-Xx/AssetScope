"""Tests for the local OpenAI-compatible LLM adapter (no model needed)."""

import json

import httpx
import pytest
import respx

from assetscope.agent.llm import LocalMessagesClient, _extract_json_object, make_llm_client
from assetscope.config import Settings

URL = "http://local/v1/chat/completions"


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_extract_json_object():
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('prefix {"tool":"x","args":{}} suffix')["tool"] == "x"
    assert _extract_json_object('```json\n{"a": 2}\n```') == {"a": 2}
    assert _extract_json_object("no json at all") is None
    # braces inside strings must not confuse the scanner
    assert _extract_json_object('{"t":"a } b","v":1}')["v"] == 1


@respx.mock
def test_tool_action_becomes_tool_use_block():
    respx.post(URL).mock(
        return_value=_resp('{"thought":"look it up","tool":"search_chembl","args":{"compound_or_target":"ibrutinib"}}')
    )
    c = LocalMessagesClient(base_url="http://local/v1", model="m")
    tools = [{
        "name": "search_chembl", "description": "d",
        "input_schema": {"type": "object", "properties": {"compound_or_target": {"type": "string"}},
                         "required": ["compound_or_target"]},
    }]
    r = c._create(model="m", max_tokens=100, system="sys", messages=[{"role": "user", "content": "q"}], tools=tools)
    assert r.stop_reason == "tool_use"
    tu = [b for b in r.content if b.type == "tool_use"][0]
    assert tu.name == "search_chembl"
    assert tu.input == {"compound_or_target": "ibrutinib"}
    assert any(b.type == "text" for b in r.content)  # the "thought"


@respx.mock
def test_planner_mode_returns_text():
    respx.post(URL).mock(return_value=_resp('["q1", "q2"]'))
    c = LocalMessagesClient(base_url="http://local/v1", model="m")
    r = c._create(model="m", max_tokens=100, system="plan", messages=[{"role": "user", "content": "q"}])
    assert r.stop_reason == "end_turn"
    assert r.content[0].type == "text" and "q1" in r.content[0].text


@respx.mock
def test_invalid_action_falls_back_to_text():
    respx.post(URL).mock(return_value=_resp("I think we should search trials."))
    c = LocalMessagesClient(base_url="http://local/v1", model="m")
    tools = [{"name": "search_chembl", "description": "d", "input_schema": {}}]
    r = c._create(model="m", max_tokens=50, system="s", messages=[{"role": "user", "content": "q"}], tools=tools)
    assert r.stop_reason == "end_turn"  # no valid tool -> text, loop will nudge


@respx.mock
def test_forced_tool_choice_restricts_menu():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _resp('{"tool":"submit_landscape","args":{"assets":[],"narrative_claims":[]}}')

    respx.post(URL).mock(side_effect=handler)
    c = LocalMessagesClient(base_url="http://local/v1", model="m")
    tools = [
        {"name": "search_chembl", "description": "d", "input_schema": {}},
        {"name": "submit_landscape", "description": "final", "input_schema": {}},
    ]
    c._create(model="m", max_tokens=100, system="s", messages=[{"role": "user", "content": "q"}],
              tools=tools, tool_choice={"type": "tool", "name": "submit_landscape"})
    sysmsg = captured["body"]["messages"][0]["content"]
    assert "submit_landscape" in sysmsg
    assert "search_chembl" not in sysmsg  # other tools hidden when forced


@respx.mock
def test_anthropic_history_is_converted():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _resp('{"tool":"submit_landscape","args":{}}')

    respx.post(URL).mock(side_effect=handler)
    c = LocalMessagesClient(base_url="http://local/v1", model="m")
    tools = [{"name": "submit_landscape", "description": "x", "input_schema": {}}]
    messages = [
        {"role": "user", "content": "find btk drugs"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "search_chembl", "input": {"compound_or_target": "ibrutinib"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "CHEMBL1873475 ibrutinib"}]},
    ]
    c._create(model="m", max_tokens=80, system="s", messages=messages, tools=tools)
    body = captured["body"]["messages"]
    roles = [m["role"] for m in body]
    assert roles[0] == "system"
    # tool_use rendered as assistant JSON, tool_result rendered into a user turn
    assert any(m["role"] == "assistant" and "search_chembl" in m["content"] for m in body)
    assert any("TOOL RESULT" in m["content"] and "CHEMBL1873475" in m["content"] for m in body)


def test_make_llm_client_local_and_validation():
    s = Settings(llm_backend="local", llm_base_url="http://x/v1")
    assert isinstance(make_llm_client(s), LocalMessagesClient)
    with pytest.raises(RuntimeError):
        make_llm_client(Settings(llm_backend="local", llm_base_url=""))
