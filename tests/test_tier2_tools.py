"""Tier 2 — the hands. The model calls a tool; we run it; it reasons over the
result. A failing tool is explained, not crashed."""

from __future__ import annotations

from tests.conftest import FakeProvider, reply, tool_call
from trillion.agent import Agent
from trillion.tools.registry import ToolRegistry


def _registry_with(handler, *, consequence=None, name="do_thing"):
    reg = ToolRegistry()
    reg.add(
        name,
        "A test tool.",
        {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        handler,
        consequence=consequence,
    )
    return reg


def test_tool_runs_and_result_feeds_back():
    reg = _registry_with(lambda args: f"did {args['x']}")

    calls = {"n": 0}

    def script(system, messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return tool_call("do_thing", {"x": "laundry"})
        # second call: the tool_result is now in the history
        last = messages[-1]
        assert last["role"] == "user"
        assert last["content"][0]["type"] == "tool_result"
        assert "did laundry" in last["content"][0]["content"]
        return reply("Done — I did laundry.")

    agent = Agent(FakeProvider(script), registry=reg)
    out = agent.send("do the laundry")
    assert out == "Done — I did laundry."


def test_failing_tool_returns_error_to_model_not_crash():
    def boom(args):
        raise RuntimeError("disk on fire")

    reg = _registry_with(boom)

    seen_error = {}

    def script(system, messages, tools):
        if any(m["role"] == "assistant" for m in messages):
            tr = messages[-1]["content"][0]
            seen_error["is_error"] = tr["is_error"]
            seen_error["content"] = tr["content"]
            return reply("Something went wrong with that.")
        return tool_call("do_thing", {"x": "y"})

    agent = Agent(FakeProvider(script), registry=reg)
    out = agent.send("go")  # must not raise
    assert out == "Something went wrong with that."
    assert seen_error["is_error"] is True
    assert "disk on fire" in seen_error["content"]


def test_unknown_tool_is_handled():
    def script(system, messages, tools):
        if any(m["role"] == "assistant" for m in messages):
            return reply("recovered")
        return tool_call("nonexistent", {})

    agent = Agent(FakeProvider(script), registry=ToolRegistry())
    assert agent.send("go") == "recovered"


def test_input_validation_rejects_bad_types():
    reg = _registry_with(lambda args: "ok")
    tool = reg.get("do_thing")
    bad = tool.run({"x": 123})  # x should be a string
    assert bad.is_error and "should be string" in bad.content
    missing = tool.run({})
    assert missing.is_error and "missing required field" in missing.content


def test_multiple_tools_in_one_turn():
    reg = ToolRegistry()
    reg.add("a", "a", {"type": "object", "properties": {}}, lambda args: "A")
    reg.add("b", "b", {"type": "object", "properties": {}}, lambda args: "B")

    from trillion.llm import LLMResponse, ToolCall, Usage

    def script(system, messages, tools):
        if any(m["role"] == "assistant" for m in messages):
            results = messages[-1]["content"]
            assert len(results) == 2  # both tool results returned together
            return reply("both done")
        return LLMResponse(
            tool_calls=[ToolCall("1", "a", {}), ToolCall("2", "b", {})],
            stop_reason="tool_use",
            usage=Usage(1, 1),
        )

    agent = Agent(FakeProvider(script), registry=reg)
    assert agent.send("go") == "both done"
