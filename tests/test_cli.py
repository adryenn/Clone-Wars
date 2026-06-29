"""CLI smoke tests for the no-model commands and graceful degradation.

The text interface is the path we debug everything else through, so its plumbing —
inbox, memory, the kill switch, and the clean 'no API key' failure — is worth
covering directly. These never touch the model.
"""

from __future__ import annotations

import pytest

import trillion.app as app_module
import trillion.cli as cli
from trillion.cli import main


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, test_config):
    """Point both config entry points at the test state dir so the CLI never
    reads the real config.toml or writes the repo's trillion_state/."""
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: test_config)
    monkeypatch.setattr(app_module, "load_config", lambda *a, **k: test_config)


def test_memory_command_empty(capsys):
    assert main(["memory"]) == 0
    assert "No durable memories yet." in capsys.readouterr().out


def test_inbox_command_empty(capsys):
    assert main(["inbox"]) == 0
    assert "Inbox empty." in capsys.readouterr().out


def test_pause_and_resume_toggle_kill_switch(capsys, state_dir):
    assert main(["pause"]) == 0
    assert (state_dir / "PAUSED").exists()  # kill switch engaged
    assert main(["resume"]) == 0
    assert not (state_dir / "PAUSED").exists()


def test_dismiss_unknown_item(capsys):
    assert main(["dismiss", "nope"]) == 0
    assert "No item" in capsys.readouterr().out


def test_chat_without_credentials_fails_cleanly(capsys, monkeypatch):
    """No key / no provider package → exit 2 with a readable message, never a
    traceback."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["chat"]) == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err or "anthropic" in err


def test_memory_command_shows_stored_fact(capsys, state_dir):
    from trillion.memory import MemoryStore

    MemoryStore(state_dir).remember("the user prefers tea", kind="preference")
    assert main(["memory"]) == 0
    assert "the user prefers tea" in capsys.readouterr().out
