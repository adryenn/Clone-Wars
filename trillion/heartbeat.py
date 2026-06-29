"""The heartbeat — a background loop that lets Trillion act without being spoken
to. Separate from the conversation loop, by design, so it can be relocated to an
always-on machine later without a rewrite.

Hard-won lessons, all built in here rather than bolted on after it annoys you:
- Quiet by default: most checks produce nothing most of the time.
- Catch-up-on-return: noteworthy things are *held* in the inbox, never fired into
  the void. The CLI shows them when you come back.
- Quiet hours: non-urgent surfacing waits for waking hours; only "interrupt"-level
  items may break quiet hours, and even then they're held, not lost.
- Survive restarts: each check's next-due time is persisted, so restarting doesn't
  reset every timer or fire everything at once.
- No overlap: if a check is still running when its next turn comes due, skip it.
- Never block forever: the engine itself never waits on a human; consequential
  background actions use a confirmer that times out to a safe default elsewhere.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from trillion.audit import AuditLog
from trillion.checks import CHECKS, CheckContext, Surfacing
from trillion.stores import Inbox


@dataclass
class CheckSpec:
    name: str
    interval_seconds: int
    noteworthy: str  # default level: "log" or "interrupt"


class Schedule:
    """Persisted next-due times, so a restart resumes instead of refiring."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._next_due: dict[str, float] = {}
        if path.exists():
            try:
                self._next_due = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._next_due = {}

    def due(self, name: str, now: float) -> bool:
        return now >= self._next_due.get(name, 0.0)

    def ensure_initialized(self, name: str, interval: int, now: float) -> None:
        # Brand-new check: schedule it one interval out, so we don't fire
        # everything the moment the program boots.
        if name not in self._next_due:
            self._next_due[name] = now + interval
            self._save()

    def reschedule(self, name: str, interval: int, now: float) -> None:
        self._next_due[name] = now + interval
        self._save()

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._next_due, indent=2) + "\n")


class Heartbeat:
    def __init__(
        self,
        *,
        specs: list[CheckSpec],
        context: CheckContext,
        inbox: Inbox,
        state_dir: Path,
        tick_seconds: int = 30,
        quiet_hours: tuple[int, int] = (22, 8),
        audit: AuditLog | None = None,
    ) -> None:
        self._specs = specs
        self._ctx = context
        self._inbox = inbox
        self._tick = tick_seconds
        self._quiet = quiet_hours
        self._audit = audit
        self._schedule = Schedule(state_dir / "schedule.json")
        self._pause_flag = state_dir / "PAUSED"  # the kill switch (Tier 6)
        self._running: set[str] = set()  # checks currently executing (no overlap)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Set each check's baseline at boot (one interval out), so we don't fire
        # everything the moment the program starts. Idempotent across restarts:
        # ensure_initialized only sets a check that has no persisted next-due.
        boot = time.time()
        for spec in self._specs:
            self._schedule.ensure_initialized(spec.name, spec.interval_seconds, boot)

    # --- kill switch ---
    @property
    def paused(self) -> bool:
        return self._pause_flag.exists()

    def pause(self) -> None:
        self._pause_flag.touch()
        if self._audit:
            self._audit.note("heartbeat paused (kill switch)")

    def resume(self) -> None:
        self._pause_flag.unlink(missing_ok=True)
        if self._audit:
            self._audit.note("heartbeat resumed")

    # --- lifecycle ---
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self._tick)

    def tick(self, now: float | None = None) -> list[Surfacing]:
        """One pass over the checks. Returns whatever was surfaced this tick
        (also routed into the inbox). Exposed directly so tests can drive it
        without spinning the thread."""
        now = now if now is not None else time.time()
        if self.paused:  # kill switch: hold all background actions
            return []

        surfaced: list[Surfacing] = []
        for spec in self._specs:
            if not self._schedule.due(spec.name, now):
                continue
            with self._lock:
                if spec.name in self._running:  # don't stack overlapping runs
                    continue
                self._running.add(spec.name)
            try:
                surfaced.extend(self._run_check(spec, now))
            finally:
                with self._lock:
                    self._running.discard(spec.name)
                self._schedule.reschedule(spec.name, spec.interval_seconds, now)
        return surfaced

    def _run_check(self, spec: CheckSpec, now: float) -> list[Surfacing]:
        fn = CHECKS.get(spec.name)
        if fn is None:
            return []
        try:
            results = fn(self._ctx)
        except Exception as exc:  # noqa: BLE001 - a noisy check shouldn't kill the loop
            if self._audit:
                self._audit.note(f"check '{spec.name}' errored: {exc}")
            return []

        out: list[Surfacing] = []
        for s in results:
            level = s.level or spec.noteworthy
            # Catch-up-on-return: everything noteworthy is HELD in the inbox.
            # Nothing is delivered-once-and-lost.
            self._inbox.add(s.message, level=level, check=spec.name)
            if self._audit:
                self._audit.surfaced(spec.name, level, s.message)
            out.append(Surfacing(s.message, level))
        return out

    def in_quiet_hours(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        start, end = self._quiet
        h = now.hour
        if start <= end:
            return start <= h < end
        return h >= start or h < end  # window wraps midnight
