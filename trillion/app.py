"""Composition root — assemble the whole assistant from config.

This is the one place that knows how the parts fit together. Interfaces (the text
REPL, the voice loop) build an ``App`` and then just call ``agent.send`` and read
the inbox. Tests build the same pieces with a fake provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from trillion.agent import Agent
from trillion.audit import AuditLog
from trillion.checks import CheckContext
from trillion.config import Config, load_config
from trillion.heartbeat import CheckSpec, Heartbeat
from trillion.llm import AnthropicProvider, LLMProvider
from trillion.memory import MemoryStore
from trillion.safety import ConfirmationGate, Confirmer, always_deny
from trillion.stores import Inbox, NoteStore, ReminderStore
from trillion.tools.builtin import build_registry


@dataclass
class App:
    config: Config
    agent: Agent
    memory: MemoryStore
    reminders: ReminderStore
    notes: NoteStore
    inbox: Inbox
    audit: AuditLog
    heartbeat: Heartbeat
    gate: ConfirmationGate


def build_app(
    config: Config | None = None,
    *,
    provider: LLMProvider | None = None,
    confirmer: Confirmer | None = None,
) -> App:
    cfg = config or load_config()
    state = cfg.state_dir

    # Durable stores.
    memory = MemoryStore(state)
    reminders = ReminderStore(state)
    notes = NoteStore(state)
    inbox = Inbox(state)

    # Audit + cost tally.
    audit = AuditLog(
        state,
        in_rate=float(cfg.model.get("input_cost_per_mtok", 0.0)),
        out_rate=float(cfg.model.get("output_cost_per_mtok", 0.0)),
    )

    # The provider seam. Injectable for tests; built from config otherwise.
    if provider is None:
        provider = AnthropicProvider(
            api_key=cfg.require_env("ANTHROPIC_API_KEY"),
            model=cfg.model.get("name", "claude-opus-4-8"),
            max_tokens=int(cfg.model.get("max_tokens", 2048)),
            temperature=float(cfg.model.get("temperature", 0.7)),
        )

    # The hands.
    registry = build_registry(reminders=reminders, notes=notes, memory=memory)

    # The rails: confirmation gate. Default confirmer denies (safe) until an
    # interface supplies an interactive one.
    gate = ConfirmationGate(
        confirm_consequences=list(cfg.safety.get("confirm_consequences", [])),
        confirmer=confirmer or always_deny,
    )

    agent = Agent(
        provider,
        name=cfg.agent_name,
        persona=cfg.persona,
        purpose=cfg.purpose,
        registry=registry,
        memory=memory,
        gate=gate,
        audit=audit,
    )

    # The heartbeat.
    specs = [
        CheckSpec(
            name=c["name"],
            interval_seconds=int(c.get("interval_seconds", 60)),
            noteworthy=c.get("noteworthy", "log"),
        )
        for c in cfg.heartbeat.get("checks", [])
    ]
    heartbeat = Heartbeat(
        specs=specs,
        context=CheckContext(reminders=reminders),
        inbox=inbox,
        state_dir=state,
        tick_seconds=int(cfg.heartbeat.get("tick_seconds", 30)),
        quiet_hours=(
            int(cfg.heartbeat.get("quiet_hours_start", 22)),
            int(cfg.heartbeat.get("quiet_hours_end", 8)),
        ),
        audit=audit,
    )

    return App(
        config=cfg,
        agent=agent,
        memory=memory,
        reminders=reminders,
        notes=notes,
        inbox=inbox,
        audit=audit,
        heartbeat=heartbeat,
        gate=gate,
    )
