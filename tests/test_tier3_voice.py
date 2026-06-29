"""Tier 3 — the ears and mouth. The seams degrade gracefully when audio deps
aren't installed, and voice never forks the brain."""

from __future__ import annotations

import pytest

from tests.conftest import FakeProvider, reply
from trillion.agent import Agent
from trillion.voice import speech_available, transcribe_available


def test_availability_checks_are_booleans():
    # In a text-only environment these are False, and the CLI falls back to chat.
    assert isinstance(transcribe_available(), bool)
    assert isinstance(speech_available(), bool)


def test_missing_audio_deps_raise_clean_errors():
    if not transcribe_available():
        from trillion.voice.stt import Transcriber

        with pytest.raises(RuntimeError):
            Transcriber("fake-key")
    if not speech_available():
        from trillion.voice.tts import Speaker

        with pytest.raises(RuntimeError):
            Speaker("fake-key", "voice")


def test_transcribed_text_uses_the_same_entry_point():
    """A spoken turn is just text fed into agent.send — the same path a typed
    turn uses. No second brain."""
    provider = FakeProvider(lambda s, m, t: reply("heard you"))
    agent = Agent(provider)
    transcript = "what's on my list"  # pretend STT produced this
    assert agent.send(transcript) == "heard you"
    assert provider.calls[0]["messages"][0]["content"] == transcript
