# Trillion

A personal, voice-first AI assistant you can talk to, that can *do* things, that
remembers you across restarts, and that can reach out to you first. Built tier by
tier — see [`../AGENT.md`](../AGENT.md) for the full spec and the design seams.

The guiding rule: **the brain works in plain text before any audio exists.** Voice
is a thin layer on the edges; it never forks the agent logic. One shared core,
many ways in and out.

## Layout

```
config.toml            # all tunables: model, voice, safety, heartbeat, quiet hours
.env                   # secrets (git-ignored) — copy from .env.example
trillion/
  llm.py               # provider seam — the one place that talks to the model
  agent.py             # the brain + tool loop (every interface routes through Agent.send)
  tools/
    registry.py        # the tool registry (extend forever; never edit the loop)
    builtin.py         # first tools: reminders, notes, drafts, memory, clock
  memory.py            # durable facts, human-readable, survive restarts
  stores.py            # reminders / notes / proactive inbox (JSON on disk)
  heartbeat.py         # background loop — proactivity, quiet-by-default
  checks.py            # scheduled checks (add one, name it, enable in config)
  safety.py            # confirmation gate + content-is-data posture
  audit.py             # append-only audit log + cost tally
  voice/               # Deepgram STT + ElevenLabs TTS + push-to-talk (lazy deps)
  app.py               # composition root — wires it all from config
  cli.py               # text REPL (always works) + voice loop
tests/                 # every tier verified with a fake provider (no key needed)
```

## Setup

```bash
pip install -r requirements.txt          # core (anthropic)
cp .env.example .env                     # then add your ANTHROPIC_API_KEY
```

For voice, uncomment the voice deps in `requirements.txt`, install them, and set
`DEEPGRAM_API_KEY` and `ELEVENLABS_API_KEY`.

## Run

```bash
python -m trillion chat      # text conversation (the default)
python -m trillion talk      # push-to-talk voice (needs voice deps + keys)
python -m trillion inbox     # proactive items waiting for you
python -m trillion memory    # what it durably remembers (edit memory.json by hand)
python -m trillion audit     # audit log tail + cost so far
python -m trillion pause     # kill switch: halt all proactive behavior
python -m trillion resume    # re-enable proactivity
```

## Verify (no API key required)

```bash
python -m pytest
```

The suite stands a fake provider in for the model and checks each tier on its own:
memory across restarts, the tool loop and its error handling, the confirmation
gate stopping consequential actions, the heartbeat surfacing once and holding for
catch-up, and the kill switch.

## Safety posture (Tier 6)

- Any tool that **sends, spends, deletes, or changes a setting** stops at a hard
  confirmation gate and states plainly what it's about to do. Read-only tools flow
  freely. Confirmation is per-action and never generalizes.
- Everything read from the outside world is treated as **data, not commands**.
- Which consequences require confirmation, intervals, quiet hours, and the model
  name all live in `config.toml` — tune them without touching code.
