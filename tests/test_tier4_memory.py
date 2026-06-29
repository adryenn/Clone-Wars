"""Tier 4 — the memory. Durable facts survive a restart and a hand-edit."""

from __future__ import annotations

import json

from trillion.memory import MemoryStore


def test_fact_survives_restart(state_dir):
    store = MemoryStore(state_dir)
    store.remember("the user prefers morning meetings", kind="preference")

    # "Restart": a brand-new store reading the same directory.
    reborn = MemoryStore(state_dir)
    statements = [f.statement for f in reborn.all()]
    assert "the user prefers morning meetings" in statements


def test_hand_edit_is_respected(state_dir):
    store = MemoryStore(state_dir)
    f = store.remember("the user lives in Boston")

    # User opens the file and corrects it by hand.
    raw = json.loads((state_dir / "memory.json").read_text())
    raw["facts"][0]["statement"] = "the user lives in Seattle"
    (state_dir / "memory.json").write_text(json.dumps(raw))

    reborn = MemoryStore(state_dir)
    assert reborn.all()[0].statement == "the user lives in Seattle"


def test_update_and_forget(state_dir):
    store = MemoryStore(state_dir)
    f = store.remember("x")
    assert store.update(f.id, "y") is True
    assert store.all()[0].statement == "y"
    assert store.forget(f.id) is True
    assert store.all() == []


def test_prompt_block_frames_memory_as_data_not_commands(state_dir):
    store = MemoryStore(state_dir)
    store.remember("always email my boss at 9am")  # reads like an order
    block = store.as_prompt_block()
    assert "NOT" in block and "instructions" in block  # explicitly framed as data
    assert "always email my boss" in block


def test_corrupt_file_does_not_crash(state_dir):
    (state_dir / "memory.json").write_text("{ this is not json")
    store = MemoryStore(state_dir)  # mid-edit; should just start empty
    assert store.all() == []
