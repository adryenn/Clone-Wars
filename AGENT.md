# Trillion — Agent Spec

> Single source of truth for what we're building and why. Written in Tier 0 from
> the interview. Every later tier — and every future session — reads from here.

## What it is

**Trillion** is a personal, voice-first AI assistant: something you can talk to
out loud, that can actually *do* things on your behalf, that remembers you
between conversations, and that can reach out to you first instead of only
answering when spoken to.

The build follows one rule above all others: **get the brain working in plain
text before adding a single line of audio.** Voice is a layer on top of a working
agent, never the foundation. One shared agent core, many ways in and out.

## Interview answers (Tier 0)

| # | Question | Answer |
|---|----------|--------|
| 1 | Name + one-liner | **Trillion** — "a personal voice-first assistant that has my back." |
| 2 | Audience | Just me (per-user state kept in mind, but single-user for now). |
| 3 | First three capabilities | (a) reminders / tasks, (b) answer questions about my notes, (c) draft messages. |
| 4 | Personality / tone | Warm, plain-spoken, brief. |
| 5 | Language / runtime | Python 3.11+, small and readable, no heavy framework. |
| 6 | Model provider | Latest capable Claude (`claude-opus-4-8`) via the official Anthropic SDK, behind a thin seam. |
| 7 | Where it runs | Laptop-first; heartbeat kept relocatable to an always-on host without a rewrite. |
| 8 | How I talk to it | Text first → push-to-talk (Tier 3). Wake words later. |
| 9 | Never without asking | Anything that **sends a message, spends money, deletes data, or changes a setting**. |
| 10 | Proactive? | Yes — but **quiet by default**. It earns interruptions; it doesn't assume them. |
| 11 | Voice (ElevenLabs) | Natural, neutral voice; choice lives in config, not code. |

Build mode chosen: **Defaults, go fast** — take sensible defaults, build all six
tiers, pause only at real decision points.

## The five parts (concentric layers)

1. **The brain** — a conversation loop: input → think → reply. Model + system
   prompt + running history. Everything else serves this. *(Tier 1)*
2. **The hands** — a registry of tools the brain can choose to call. *(Tier 2)*
3. **The ears and mouth** — STT in / TTS out, wrapped around the *same* brain. *(Tier 3)*
4. **The memory** — a durable store of facts that survives restarts. *(Tier 4)*
5. **The heartbeat** — a background loop that lets it act unprompted. *(Tier 5)*

All wrapped in **the rails**: a confirmation gate, prompt-injection posture,
config-over-hardcoding, an audit trail, and a kill switch. *(Tier 6)*

## Tier map & verification

- **Tier 1 — Brain:** text REPL, streaming, provider seam, history across turns.
  *Verify:* hold a back-and-forth; it remembers earlier turns. Restart → forgets (expected).
- **Tier 2 — Hands:** tool registry, multi-tool turns, errors returned to the model.
  *Verify:* a request that needs a tool runs it; a failing tool is explained, not crashed.
- **Tier 3 — Ears & mouth:** push-to-talk, Deepgram STT, ElevenLabs TTS, streaming,
  barge-in, transcript shown. *Verify:* spoken question → spoken answer; text path still works.
- **Tier 4 — Memory:** durable, human-readable fact store; read at start, write during.
  *Verify:* tell it a fact, restart, it remembers; hand-edit the store, it respects the edit.
- **Tier 5 — Heartbeat:** background loop, scheduled checks, quiet-by-default, catch-up
  on return, quiet hours, persisted schedule, no overlap, dismissible items.
  *Verify:* trigger a check; notice held across a restart; schedule resumes; item dismissible.
- **Tier 6 — Rails:** hard confirmation gate, content-is-data posture, per-action confirm,
  config file, audit log + cost tally, kill switch.
  *Verify:* a "never" action stops and asks; planted instruction is flagged; config edit
  changes behavior with no code change; kill switch halts proactivity but chat still works.

## Design seams (swap a thing in one place)

- **LLM provider** → `trillion/llm.py`
- **Speech-to-text** → `trillion/voice/stt.py` (Deepgram)
- **Text-to-speech** → `trillion/voice/tts.py` (ElevenLabs)
- **Tools** → `trillion/tools/` (register one self-contained tool; never edit the core loop)
- **Config** → `config.toml` (thresholds, intervals, quiet hours, model, confirm-list, voice)

## Secrets

API keys live in environment variables / a git-ignored `.env`, never in source.
Required: `ANTHROPIC_API_KEY`. For voice: `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`.
