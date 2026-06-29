"""Small durable stores for the first three capabilities and the proactive inbox.

Each is a plain JSON file under the state dir — human-readable, easy to inspect,
easy to delete. Reminders are shared between the reminder tools (Tier 2) and the
heartbeat's due-reminder check (Tier 5), which is why they live together here.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


# --- Reminders ----------------------------------------------------------------


@dataclass
class Reminder:
    id: str
    text: str
    due: float | None = None  # epoch seconds; None = no specific time
    done: bool = False
    surfaced: bool = False  # has the heartbeat already alerted on this?


class ReminderStore:
    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "reminders.json"
        self._items: dict[str, Reminder] = {}
        for raw in _read(self._path, {"items": []})["items"]:
            r = Reminder(**raw)
            self._items[r.id] = r

    def _save(self) -> None:
        _write(self._path, {"items": [asdict(r) for r in self._items.values()]})

    def add(self, text: str, due: float | None = None) -> Reminder:
        rid = _next_id(self._items, "r")
        r = Reminder(id=rid, text=text.strip(), due=due)
        self._items[rid] = r
        self._save()
        return r

    def list(self, include_done: bool = False) -> list[Reminder]:
        items = sorted(self._items.values(), key=lambda r: (r.due is None, r.due or 0))
        return [r for r in items if include_done or not r.done]

    def complete(self, rid: str) -> bool:
        r = self._items.get(rid)
        if not r:
            return False
        r.done = True
        self._save()
        return True

    def due_now(self, now: float | None = None) -> list[Reminder]:
        now = now if now is not None else time.time()
        return [
            r
            for r in self._items.values()
            if not r.done and not r.surfaced and r.due is not None and r.due <= now
        ]

    def mark_surfaced(self, rid: str) -> None:
        r = self._items.get(rid)
        if r:
            r.surfaced = True
            self._save()


# --- Notes --------------------------------------------------------------------


@dataclass
class Note:
    id: str
    text: str
    created: float = field(default_factory=time.time)


class NoteStore:
    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "notes.json"
        self._items: dict[str, Note] = {}
        for raw in _read(self._path, {"items": []})["items"]:
            n = Note(**raw)
            self._items[n.id] = n

    def _save(self) -> None:
        _write(self._path, {"items": [asdict(n) for n in self._items.values()]})

    def add(self, text: str) -> Note:
        nid = _next_id(self._items, "n")
        n = Note(id=nid, text=text.strip())
        self._items[nid] = n
        self._save()
        return n

    def search(self, query: str) -> list[Note]:
        terms = {t for t in query.lower().split() if t}
        scored = []
        for n in self._items.values():
            hay = n.text.lower()
            score = sum(1 for t in terms if t in hay)
            if score or not terms:
                scored.append((score, n))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [n for _, n in scored]

    def all(self) -> list[Note]:
        return list(self._items.values())


# --- Proactive inbox (Tier 5) -------------------------------------------------


@dataclass
class InboxItem:
    id: str
    message: str
    level: str  # "log" (calm) or "interrupt" (loud)
    check: str
    ts: float = field(default_factory=time.time)
    dismissed: bool = False


class Inbox:
    """Where the heartbeat routes anything noteworthy. Items are *held* until you
    see them (catch-up-on-return) and every item is dismissible."""

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "inbox.json"
        self._items: dict[str, InboxItem] = {}
        for raw in _read(self._path, {"items": []})["items"]:
            it = InboxItem(**raw)
            self._items[it.id] = it

    def _save(self) -> None:
        _write(self._path, {"items": [asdict(i) for i in self._items.values()]})

    def add(self, message: str, level: str, check: str) -> InboxItem:
        iid = _next_id(self._items, "i")
        it = InboxItem(id=iid, message=message, level=level, check=check)
        self._items[iid] = it
        self._save()
        return it

    def pending(self) -> list[InboxItem]:
        return [i for i in sorted(self._items.values(), key=lambda x: x.ts) if not i.dismissed]

    def dismiss(self, iid: str) -> bool:
        it = self._items.get(iid)
        if not it:
            return False
        it.dismissed = True
        self._save()
        return True

    def dismiss_all(self) -> int:
        n = 0
        for it in self._items.values():
            if not it.dismissed:
                it.dismissed = True
                n += 1
        if n:
            self._save()
        return n


def _next_id(items: dict[str, Any], prefix: str) -> str:
    n = 1
    while f"{prefix}{n}" in items:
        n += 1
    return f"{prefix}{n}"
