"""Scheduled checks for the heartbeat.

Each check is a small unit: it looks at something and decides whether the outcome
is worth surfacing. It returns a list of surfacings (each a message and a level);
returning an empty list — the common case — means "nothing worth your attention",
which is the whole point of quiet-by-default.

A check NEVER surfaces the same thing twice (it marks state as it goes), so the
engine can run it on a schedule without spamming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from trillion.stores import ReminderStore


@dataclass
class CheckContext:
    reminders: ReminderStore


@dataclass
class Surfacing:
    message: str
    level: str | None = None  # None = use the check's configured default


# A check: look at the world, return what (if anything) is worth surfacing.
CheckFn = Callable[[CheckContext], list[Surfacing]]


def due_reminders(ctx: CheckContext) -> list[Surfacing]:
    out: list[Surfacing] = []
    for r in ctx.reminders.due_now():
        out.append(Surfacing(f"Reminder: {r.text}", level="interrupt"))
        ctx.reminders.mark_surfaced(r.id)  # never fire this one again
    return out


def daily_summary(ctx: CheckContext) -> list[Surfacing]:
    outstanding = ctx.reminders.list(include_done=False)
    if not outstanding:
        return []
    return [Surfacing(f"You have {len(outstanding)} thing(s) outstanding.", level="log")]


# The check registry. Adding a proactive behavior = write a function and name it
# here, then enable it in config.toml. The engine never changes.
CHECKS: dict[str, CheckFn] = {
    "due_reminders": due_reminders,
    "daily_summary": daily_summary,
}
