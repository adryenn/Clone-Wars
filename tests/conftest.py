"""Shared test fixtures.

A FakeProvider stands in for the model so every tier is verifiable without a key
or a network. It's the same seam the real provider implements — proof that the
brain doesn't care which provider it talks to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from trillion.config import Config
from trillion.llm import LLMResponse, ToolCall, Usage

# A script decides what the fake model "says" given the conversation so far.
Script = Callable[[str, list[dict[str, Any]], list[dict[str, Any]] | None], LLMResponse]


class FakeProvider:
    """Records what it was asked and replies from a script."""

    def __init__(self, script: Script) -> None:
        self._script = script
        self.calls: list[dict[str, Any]] = []

    def run(self, *, system, messages, tools=None, on_text=None) -> LLMResponse:
        self.calls.append({"system": system, "messages": [m for m in messages], "tools": tools})
        resp = self._script(system, messages, tools)
        if on_text and resp.text:
            on_text(resp.text)  # exercise the streaming sink
        return resp


def reply(text: str, *, usage: Usage | None = None) -> LLMResponse:
    return LLMResponse(text=text, usage=usage or Usage(10, 5))


def tool_call(name: str, tool_input: dict, *, call_id: str = "tc_1") -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id=call_id, name=name, input=tool_input)],
        stop_reason="tool_use",
        usage=Usage(10, 5),
    )


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def test_config(state_dir: Path) -> Config:
    raw = {
        "agent": {"name": "Trillion", "persona": "warm", "purpose": "a test assistant"},
        "model": {
            "name": "fake-model",
            "max_tokens": 256,
            "input_cost_per_mtok": 5.0,
            "output_cost_per_mtok": 25.0,
        },
        "voice": {"tts_voice_id": "x"},
        "safety": {"confirm_consequences": ["send", "spend", "delete", "settings"]},
        "heartbeat": {
            "tick_seconds": 1,
            "quiet_hours_start": 22,
            "quiet_hours_end": 8,
            "checks": [
                {"name": "due_reminders", "interval_seconds": 1, "noteworthy": "interrupt"},
                {"name": "daily_summary", "interval_seconds": 100, "noteworthy": "log"},
            ],
        },
        "paths": {"state_dir": str(state_dir)},
    }
    return Config(raw=raw, path=Path("test-config.toml"))
