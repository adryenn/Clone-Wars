"""The audit trail and cost tally.

A plain, append-only log of what Trillion did and why — which tools ran, what the
heartbeat surfaced, what it asked you to confirm — plus a running model-cost tally
so a runaway loop is visible immediately. When something surprises you, this is
how you find out what happened.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trillion.llm import Usage


@dataclass
class CostTally:
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def add(self, usage: Usage, in_rate: float, out_rate: float) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.usd += (usage.input_tokens / 1_000_000) * in_rate
        self.usd += (usage.output_tokens / 1_000_000) * out_rate


class AuditLog:
    """Append-only JSONL. Human-greppable, machine-parseable."""

    def __init__(self, state_dir: Path, in_rate: float = 0.0, out_rate: float = 0.0) -> None:
        self._path = state_dir / "audit.log"
        self._in_rate = in_rate
        self._out_rate = out_rate
        self.cost = CostTally()

    @property
    def path(self) -> Path:
        return self._path

    def event(self, kind: str, **fields: Any) -> None:
        record = {"ts": time.time(), "iso": _now_iso(), "kind": kind, **fields}
        with open(self._path, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def model_call(self, usage: Usage) -> None:
        self.cost.add(usage, self._in_rate, self._out_rate)
        self.event(
            "model_call",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd_total=round(self.cost.usd, 4),
        )

    def tool_run(self, name: str, ok: bool, detail: str = "") -> None:
        self.event("tool_run", tool=name, ok=ok, detail=detail[:500])

    def confirmation(self, question: str, allowed: bool, reason: str) -> None:
        self.event("confirmation", question=question, allowed=allowed, reason=reason)

    def surfaced(self, check: str, level: str, message: str) -> None:
        self.event("surfaced", check=check, level=level, message=message[:500])

    def note(self, message: str) -> None:
        self.event("note", message=message)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
