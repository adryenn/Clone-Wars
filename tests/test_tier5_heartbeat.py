"""Tier 5 — the heartbeat. Surfaces once, holds for catch-up, resumes across a
restart, doesn't refire, and is dismissible and pausable."""

from __future__ import annotations

import time

from trillion.checks import CheckContext
from trillion.heartbeat import CheckSpec, Heartbeat
from trillion.stores import Inbox, ReminderStore


def _make_heartbeat(state_dir, specs=None):
    reminders = ReminderStore(state_dir)
    inbox = Inbox(state_dir)
    specs = specs or [CheckSpec("due_reminders", interval_seconds=1, noteworthy="interrupt")]
    hb = Heartbeat(
        specs=specs,
        context=CheckContext(reminders=reminders),
        inbox=inbox,
        state_dir=state_dir,
        tick_seconds=1,
    )
    return hb, reminders, inbox


def test_due_reminder_surfaces_once_and_is_held(state_dir):
    hb, reminders, inbox = _make_heartbeat(state_dir)
    reminders.add("call mom", due=time.time() - 5)  # already due

    now = time.time() + 2  # past the initial one-interval delay
    surfaced = hb.tick(now=now)
    assert any("call mom" in s.message for s in surfaced)
    assert any("call mom" in i.message for i in inbox.pending())  # held in inbox

    # Second tick: must NOT surface the same reminder again.
    again = hb.tick(now=now + 2)
    assert not any("call mom" in s.message for s in again)


def test_schedule_persists_and_resumes_without_refiring(state_dir):
    hb, reminders, _ = _make_heartbeat(state_dir)
    reminders.add("ping", due=time.time() - 5)
    hb.tick(now=time.time() + 2)  # fires, marks reminder surfaced, advances schedule

    # "Restart": a fresh heartbeat over the same state dir.
    hb2, _, inbox2 = _make_heartbeat(state_dir)
    before = len(inbox2.pending())
    hb2.tick(now=time.time() + 3)  # schedule says not due yet → nothing new
    assert len(inbox2.pending()) == before  # didn't refire everything on boot


def test_no_overlap(state_dir):
    hb, _, _ = _make_heartbeat(state_dir)
    hb._running.add("due_reminders")  # pretend a run is in flight
    # ensure it's "due"
    hb._schedule._next_due["due_reminders"] = 0
    assert hb.tick(now=time.time() + 10) == []  # skipped, not stacked


def test_kill_switch_halts_ticks(state_dir):
    hb, reminders, inbox = _make_heartbeat(state_dir)
    reminders.add("urgent", due=time.time() - 5)
    hb.pause()
    assert hb.paused
    assert hb.tick(now=time.time() + 2) == []
    assert inbox.pending() == []
    hb.resume()
    assert not hb.paused


def test_inbox_dismiss(state_dir):
    inbox = Inbox(state_dir)
    it = inbox.add("something", level="log", check="x")
    assert inbox.pending()
    assert inbox.dismiss(it.id) is True
    assert inbox.pending() == []


def test_quiet_hours_window(state_dir):
    hb, _, _ = _make_heartbeat(state_dir)
    from datetime import datetime

    # default quiet hours 22–8
    assert hb.in_quiet_hours(datetime(2026, 1, 1, 23, 0)) is True
    assert hb.in_quiet_hours(datetime(2026, 1, 1, 3, 0)) is True
    assert hb.in_quiet_hours(datetime(2026, 1, 1, 12, 0)) is False


def test_does_not_fire_everything_on_first_boot(state_dir):
    """A brand-new check is scheduled one interval out, not fired immediately."""
    hb, reminders, inbox = _make_heartbeat(
        state_dir, specs=[CheckSpec("due_reminders", interval_seconds=60, noteworthy="interrupt")]
    )
    reminders.add("later", due=time.time() - 5)
    assert hb.tick(now=time.time()) == []  # not yet due on first boot
