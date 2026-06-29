"""The first tools, drawn from the three interview capabilities:
reminders/tasks, answering questions about notes, and drafting messages — plus
memory management and a clock.

Each tool is self-contained and registered through ``build_registry``. Adding a
capability later means writing one of these and registering it; the core loop
never changes. Descriptions are written for the model to read.

Note the ``consequence`` on each registration: read-only tools are ``None`` and
flow freely; ``draft_message`` only *drafts* (safe), while actually sending would
be a separate "send" tool behind the confirmation gate.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from trillion.memory import MemoryStore
from trillion.stores import NoteStore, ReminderStore
from trillion.tools.registry import ToolRegistry


def build_registry(
    *,
    reminders: ReminderStore,
    notes: NoteStore,
    memory: MemoryStore,
) -> ToolRegistry:
    reg = ToolRegistry()

    # --- Capability 1: reminders / tasks ---
    def add_reminder(args: dict) -> str:
        due = _parse_when(args.get("when"))
        r = reminders.add(args["text"], due=due)
        when = _fmt_time(r.due) if r.due else "no specific time"
        return f"Reminder set [{r.id}]: {r.text} ({when})."

    reg.add(
        "add_reminder",
        "Set a reminder or task for the user. Use when they ask to be reminded of "
        "something or to add a to-do. 'when' is optional natural language like "
        "'in 10 minutes', 'tomorrow 9am', or 'friday'.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to be reminded of."},
                "when": {"type": "string", "description": "When, in natural language. Optional."},
            },
            "required": ["text"],
        },
        add_reminder,
    )

    def list_reminders(args: dict) -> str:
        items = reminders.list(include_done=bool(args.get("include_done")))
        if not items:
            return "Nothing on the list."
        lines = []
        for r in items:
            when = _fmt_time(r.due) if r.due else "anytime"
            lines.append(f"[{r.id}] {r.text} — {when}")
        return "\n".join(lines)

    reg.add(
        "list_reminders",
        "List the user's current reminders/tasks. Use to answer 'what's on my "
        "list' or 'what do I have today'.",
        {
            "type": "object",
            "properties": {
                "include_done": {"type": "boolean", "description": "Include completed items."}
            },
        },
        list_reminders,
    )

    def complete_reminder(args: dict) -> str:
        ok = reminders.complete(args["id"])
        return "Marked done." if ok else f"No reminder with id {args['id']!r}."

    reg.add(
        "complete_reminder",
        "Mark a reminder/task as done, by its id (e.g. 'r1').",
        {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        complete_reminder,
    )

    # --- Capability 2: answer questions about notes ---
    def save_note(args: dict) -> str:
        n = notes.add(args["text"])
        return f"Saved note [{n.id}]."

    reg.add(
        "save_note",
        "Save a note the user wants to keep — a thought, a fact, something to "
        "look up later.",
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        save_note,
    )

    def search_notes(args: dict) -> str:
        results = notes.search(args["query"])
        if not results:
            return "No matching notes."
        return "\n".join(f"[{n.id}] {n.text}" for n in results[:10])

    reg.add(
        "search_notes",
        "Search the user's saved notes to answer a question about them. Use "
        "whenever the user asks about something they told you to remember or note.",
        {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        search_notes,
    )

    # --- Capability 3: draft messages ---
    def draft_message(args: dict) -> str:
        # Drafting is safe — it only produces text. SENDING would be a separate
        # tool with consequence="send" behind the confirmation gate.
        return (
            f"Draft to {args.get('to', '(unspecified)')}:\n"
            f"---\n{args['body']}\n---\n"
            "(This is only a draft. I won't send anything without your go-ahead.)"
        )

    reg.add(
        "draft_message",
        "Draft a message (email, text, note) for the user to review. This only "
        "writes the draft; it does NOT send. Use when the user asks you to write "
        "or compose something to someone.",
        {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient. Optional."},
                "body": {"type": "string", "description": "The message text."},
            },
            "required": ["body"],
        },
        draft_message,
    )

    # --- Memory management (Tier 4) ---
    def remember_fact(args: dict) -> str:
        f = memory.remember(args["statement"], kind=args.get("kind", "preference"))
        return f"Got it, I'll remember that [{f.id}]."

    reg.add(
        "remember_fact",
        "Durably remember a fact about the user across sessions — a preference, "
        "an identity detail, a decision. Use for things worth keeping, not "
        "passing chatter.",
        {
            "type": "object",
            "properties": {
                "statement": {"type": "string", "description": "One clear plain statement."},
                "kind": {
                    "type": "string",
                    "description": "identity | preference | decision | world",
                },
            },
            "required": ["statement"],
        },
        remember_fact,
    )

    def update_memory(args: dict) -> str:
        ok = memory.update(args["id"], args["statement"])
        return "Updated." if ok else f"No fact with id {args['id']!r}."

    reg.add(
        "update_memory",
        "Correct or replace a stored fact by id when it's gone stale.",
        {
            "type": "object",
            "properties": {"id": {"type": "string"}, "statement": {"type": "string"}},
            "required": ["id", "statement"],
        },
        update_memory,
    )

    def forget_fact(args: dict) -> str:
        ok = memory.forget(args["id"])
        return "Forgotten." if ok else f"No fact with id {args['id']!r}."

    reg.add(
        "forget_fact",
        "Remove a stored fact by id when it's no longer true or wanted.",
        {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        forget_fact,
        # Deleting stored data is consequential — gate it.
        consequence="delete",
    )

    # --- A clock, so the model can reason about 'now' ---
    def get_time(_: dict) -> str:
        return datetime.now().strftime("%A %Y-%m-%d %H:%M")

    reg.add(
        "get_time",
        "Get the current local date and time. Use before reasoning about "
        "relative times like 'today' or 'in an hour'.",
        {"type": "object", "properties": {}},
        get_time,
    )

    return reg


# --- tiny natural-language time parser (good enough for the first tools) ---


def _parse_when(text: str | None) -> float | None:
    if not text:
        return None
    text = text.strip().lower()
    now = datetime.now()

    # "in N minutes/hours/days"
    parts = text.split()
    if parts and parts[0] == "in" and len(parts) >= 3:
        try:
            n = int(parts[1])
            unit = parts[2]
            if unit.startswith("min"):
                return (now + timedelta(minutes=n)).timestamp()
            if unit.startswith("hour"):
                return (now + timedelta(hours=n)).timestamp()
            if unit.startswith("day"):
                return (now + timedelta(days=n)).timestamp()
        except ValueError:
            pass

    base = now
    if "tomorrow" in text:
        base = now + timedelta(days=1)

    # a clock time like "9am", "9:30", "14:00"
    hour, minute = _extract_clock(text)
    if hour is not None:
        target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if "tomorrow" not in text and target <= now:
            target += timedelta(days=1)  # next occurrence
        return target.timestamp()

    if "tomorrow" in text:
        return base.replace(hour=9, minute=0, second=0, microsecond=0).timestamp()
    return None


def _extract_clock(text: str) -> tuple[int | None, int]:
    import re

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    suffix = m.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if 0 <= hour <= 23:
        return hour, minute
    return None, 0


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %H:%M")


def _now() -> float:
    return time.time()
