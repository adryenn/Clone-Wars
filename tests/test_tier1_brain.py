"""Tier 1 — the brain. A text conversation that remembers earlier turns."""

from __future__ import annotations

import pytest

from tests.conftest import FakeProvider, reply
from trillion.agent import Agent
from trillion.llm import LLMError


def test_remembers_earlier_turns():
    """The whole conversation is passed back each turn — history accumulates."""
    provider = FakeProvider(lambda system, messages, tools: reply("ok"))
    agent = Agent(provider, name="Trillion")

    agent.send("my name is Sam")
    agent.send("what did I just say?")

    # On the second call the provider saw the first user turn AND the first reply.
    second_call_messages = provider.calls[1]["messages"]
    user_texts = [m["content"] for m in second_call_messages if m["role"] == "user"]
    assert "my name is Sam" in user_texts
    assert any(m["role"] == "assistant" for m in second_call_messages)


def test_streaming_sink_receives_text():
    chunks: list[str] = []
    provider = FakeProvider(lambda s, m, t: reply("hello there"))
    agent = Agent(provider)

    out = agent.send("hi", on_text=chunks.append)

    assert out == "hello there"
    assert "".join(chunks) == "hello there"


def test_system_prompt_carries_identity():
    provider = FakeProvider(lambda s, m, t: reply("ok"))
    agent = Agent(provider, name="Trillion", persona="warm", purpose="a test assistant")
    agent.send("hi")
    system = provider.calls[0]["system"]
    assert "Trillion" in system and "test assistant" in system


def test_reset_forgets_history():
    provider = FakeProvider(lambda s, m, t: reply("ok"))
    agent = Agent(provider)
    agent.send("remember this")
    agent.reset()
    assert agent.history == []


def test_model_failure_is_raised_cleanly_not_crashed():
    def boom(s, m, t):
        raise LLMError("model unreachable")

    agent = Agent(FakeProvider(boom))
    with pytest.raises(LLMError):
        agent.send("hi")
    # The user turn is still recorded; the loop can be retried.
    assert agent.history[-1]["content"] == "hi"
