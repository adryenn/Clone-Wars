"""Configuration loading — config.toml plus a git-ignored .env for secrets.

Tier 6 principle: thresholds, intervals, quiet hours, the model name, and which
tools require confirmation all live in config, not scattered through the code.
This module is the one place that reads them.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't add a dependency for it.

    Only sets variables that aren't already in the environment, so a real
    environment variable always wins over the file.
    """
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    """Parsed config plus a couple of derived helpers."""

    raw: dict[str, Any]
    path: Path

    # --- convenience accessors (keep call sites readable) ---
    @property
    def agent_name(self) -> str:
        return self.section("agent").get("name", "Trillion")

    @property
    def persona(self) -> str:
        return self.section("agent").get("persona", "warm, plain-spoken, and brief")

    @property
    def purpose(self) -> str:
        return self.section("agent").get("purpose", "a personal assistant")

    @property
    def model(self) -> dict[str, Any]:
        return self.section("model")

    @property
    def voice(self) -> dict[str, Any]:
        return self.section("voice")

    @property
    def safety(self) -> dict[str, Any]:
        return self.section("safety")

    @property
    def heartbeat(self) -> dict[str, Any]:
        return self.section("heartbeat")

    @property
    def state_dir(self) -> Path:
        rel = self.section("paths").get("state_dir", "trillion_state")
        p = Path(rel)
        if not p.is_absolute():
            p = REPO_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def require_env(self, key: str) -> str:
        value = os.environ.get(key)
        if not value:
            raise MissingSecret(
                f"{key} is not set. Copy .env.example to .env and fill it in, "
                f"or export {key} in your shell."
            )
        return value


class MissingSecret(RuntimeError):
    """Raised when a required secret is absent. Caught and shown cleanly."""


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or DEFAULT_CONFIG_PATH
    _load_dotenv(REPO_ROOT / ".env")
    with open(cfg_path, "rb") as fh:
        raw = tomllib.load(fh)
    return Config(raw=raw, path=cfg_path)
