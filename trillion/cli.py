"""Command-line interface — the text path (always works) and the voice path.

The text interface is never deleted. It's how you debug every future change
without talking to your computer, and it's the graceful fallback when audio
misbehaves.
"""

from __future__ import annotations

import argparse
import sys

from trillion.app import App, build_app
from trillion.config import MissingSecret, load_config
from trillion.llm import LLMError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trillion", description="Your voice-first assistant.")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("chat", help="Text conversation (default).")
    sub.add_parser("talk", help="Push-to-talk voice conversation.")
    sub.add_parser("inbox", help="Show proactive items waiting for you.")
    d = sub.add_parser("dismiss", help="Dismiss a proactive item (or 'all').")
    d.add_argument("id")
    sub.add_parser("pause", help="Kill switch: pause all proactive behavior.")
    sub.add_parser("resume", help="Resume proactive behavior.")
    sub.add_parser("memory", help="Show what Trillion durably remembers.")
    sub.add_parser("audit", help="Show the audit log tail and cost so far.")

    args = parser.parse_args(argv)
    cmd = args.cmd or "chat"

    try:
        # Commands that don't need the model can skip building the provider.
        if cmd in {"inbox", "dismiss", "pause", "resume", "memory", "audit"}:
            return _run_no_model(cmd, args)
        app = build_app(confirmer=_console_confirmer)
    except (MissingSecret, LLMError) as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        return 2

    if cmd == "talk":
        return _run_talk(app)
    return _run_chat(app)


# --- text REPL (Tiers 1, 2, 4, 6) ---


def _run_chat(app: App) -> int:
    name = app.config.agent_name
    app.heartbeat.start()  # proactive loop runs alongside the chat
    _show_inbox(app, prefix="While you were away: ")  # catch-up-on-return
    print(f"\n{name} is here. Type your message, or 'quit' to leave.")
    if app.heartbeat.paused:
        print("(Proactive behavior is PAUSED — `trillion resume` to re-enable.)")
    print()
    try:
        while True:
            try:
                user = input("you › ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user:
                continue
            if user.lower() in {"quit", "exit", "bye"}:
                break
            if user.lower() == "inbox":
                _show_inbox(app, prefix="")
                continue

            print(f"{name.lower()} › ", end="", flush=True)
            try:
                reply = app.agent.send(user, on_text=lambda t: print(t, end="", flush=True))
                if not reply:
                    print("(no reply)", end="")
            except LLMError as exc:
                print(f"[{exc}]", end="")
            print("\n")
            _drain_interrupts(app)  # surface anything urgent the heartbeat noticed
    finally:
        app.heartbeat.stop()
        _print_cost(app)
    return 0


def _console_confirmer(question: str) -> bool:
    """Interactive confirmation for consequential tools. Per-action; never
    generalizes."""
    print(f"\n  ⚠  {question}")
    try:
        answer = input("  Allow this? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


# --- voice loop (Tier 3) ---


def _run_talk(app: App) -> int:
    from trillion.voice import speech_available, transcribe_available

    if not (transcribe_available() and speech_available()):
        print(
            "Voice isn't set up. Install the optional deps (see requirements.txt) "
            "and set DEEPGRAM_API_KEY and ELEVENLABS_API_KEY, then run `trillion talk`.\n"
            "Meanwhile, `trillion chat` gives you the exact same brain in text."
        )
        return 1

    from trillion.voice.audio import PushToTalk
    from trillion.voice.stt import Transcriber
    from trillion.voice.tts import Speaker

    cfg = app.config
    stt = Transcriber(cfg.require_env("DEEPGRAM_API_KEY"), model=cfg.voice.get("stt_model", "nova-2"))
    tts = Speaker(
        cfg.require_env("ELEVENLABS_API_KEY"),
        voice_id=cfg.voice.get("tts_voice_id", ""),
        model=cfg.voice.get("tts_model", "eleven_turbo_v2_5"),
    )
    ptt = PushToTalk()
    app.heartbeat.start()
    _show_inbox(app, prefix="While you were away: ")

    print(f"\n{cfg.agent_name} is listening. Press Enter to start/stop talking; 'quit' to leave.")
    try:
        while True:
            cmd = input("\n[Enter]=talk, q=quit › ").strip().lower()
            if cmd in {"q", "quit", "exit"}:
                break
            print("  ● recording… press Enter to stop", flush=True)
            ptt.start()
            input()
            audio = ptt.stop()

            print("  … transcribing", flush=True)
            heard = stt.transcribe(audio)
            if not heard:
                print("  (didn't catch that)")
                continue
            print(f"  you said: “{heard}”")  # show the transcript while building

            # Same brain as text. Speak the reply as it streams.
            chunks: list[str] = []
            reply = app.agent.send(heard, on_text=chunks.append)
            print(f"  {cfg.agent_name.lower()}: {reply}")
            tts.speak(reply)
            _drain_interrupts(app)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        app.heartbeat.stop()
        _print_cost(app)
    return 0


# --- non-model commands ---


def _run_no_model(cmd: str, args: argparse.Namespace) -> int:
    cfg = load_config()
    from trillion.stores import Inbox
    from trillion.memory import MemoryStore

    state = cfg.state_dir
    if cmd == "inbox":
        _print_inbox(Inbox(state))
    elif cmd == "dismiss":
        inbox = Inbox(state)
        if args.id == "all":
            n = inbox.dismiss_all()
            print(f"Dismissed {n} item(s).")
        else:
            print("Dismissed." if inbox.dismiss(args.id) else f"No item {args.id!r}.")
    elif cmd == "pause":
        (state / "PAUSED").touch()
        print("Proactive behavior PAUSED. You can still chat. `trillion resume` to re-enable.")
    elif cmd == "resume":
        (state / "PAUSED").unlink(missing_ok=True)
        print("Proactive behavior resumed.")
    elif cmd == "memory":
        facts = MemoryStore(state).all()
        if not facts:
            print("No durable memories yet.")
        for f in facts:
            print(f"[{f.id}] ({f.kind}) {f.statement}")
        print(f"\n(Edit by hand: {(state / 'memory.json')})")
    elif cmd == "audit":
        _tail_audit(state)
    return 0


# --- shared helpers ---


def _show_inbox(app: App, prefix: str) -> None:
    pending = app.inbox.pending()
    if not pending:
        return
    print(f"\n{prefix}{len(pending)} proactive item(s):")
    for it in pending:
        mark = "‼" if it.level == "interrupt" else "·"
        print(f"  {mark} [{it.id}] {it.message}")
    print("  (`trillion dismiss <id>` or type 'inbox' to review)")


def _print_inbox(inbox) -> None:
    pending = inbox.pending()
    if not pending:
        print("Inbox empty.")
        return
    for it in pending:
        mark = "‼" if it.level == "interrupt" else "·"
        print(f"{mark} [{it.id}] ({it.check}) {it.message}")


def _drain_interrupts(app: App) -> None:
    """Show any new interrupt-level items the heartbeat surfaced mid-session,
    respecting quiet hours for the loud ones."""
    for it in app.inbox.pending():
        if it.level == "interrupt" and not app.heartbeat.in_quiet_hours():
            print(f"  ‼ {it.message}  (dismiss with: trillion dismiss {it.id})")


def _print_cost(app: App) -> None:
    c = app.audit.cost
    if c.input_tokens or c.output_tokens:
        print(
            f"(session: {c.input_tokens}+{c.output_tokens} tokens, ~${c.usd:.4f}. "
            f"Full log: {app.audit.path})"
        )


def _tail_audit(state) -> None:
    path = state / "audit.log"
    if not path.exists():
        print("No audit log yet.")
        return
    lines = path.read_text().splitlines()
    for line in lines[-20:]:
        print(line)
    print(f"\n({len(lines)} total events — {path})")


if __name__ == "__main__":
    raise SystemExit(main())
