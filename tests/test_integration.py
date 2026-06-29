"""End-to-end: build the whole assistant from config with a fake provider and
drive a real capability (reminders) through the registry, then have the heartbeat
surface it. Proves the parts wire together."""

from __future__ import annotations

import time

from tests.conftest import FakeProvider, reply, tool_call
from trillion.app import build_app


def test_full_loop_reminder_then_heartbeat(test_config):
    # The model decides to set a reminder due in the past, then confirms.
    calls = {"n": 0}

    def script(system, messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            # 'add_reminder' is read/write but not consequential → runs freely.
            return tool_call("add_reminder", {"text": "stretch", "when": "in 0 minutes"})
        return reply("Set a reminder to stretch.")

    app = build_app(test_config, provider=FakeProvider(script))
    out = app.agent.send("remind me to stretch")
    assert "stretch" in out.lower()
    assert app.reminders.list()  # the tool actually persisted it

    # Memory + audit are wired: a model call was tallied.
    assert app.audit.cost.input_tokens > 0

    # The heartbeat surfaces the now-due reminder, held in the inbox.
    surfaced = app.heartbeat.tick(now=time.time() + 5)
    assert any("stretch" in s.message for s in surfaced)
    assert any("stretch" in i.message for i in app.inbox.pending())


def test_system_prompt_includes_memory_after_remember(test_config):
    def script(system, messages, tools):
        if any(m["role"] == "assistant" for m in messages):
            return reply("noted")
        return tool_call("remember_fact", {"statement": "the user is named Sam"})

    app = build_app(test_config, provider=FakeProvider(script))
    app.agent.send("my name is Sam, remember it")

    # Next turn's system prompt should carry the stored fact.
    system = app.agent.build_system_prompt()
    assert "Sam" in system
