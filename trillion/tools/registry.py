"""The tool registry.

Each tool is registered with a clear name, a one-line description of *when* to
use it (written for a model to read, not a compiler), and a typed input schema.
The whole registry is handed to the model each turn so it knows what's available.

Every tool also declares a ``consequence``: ``None`` means read-only and safe to
run on its own; anything else ("send", "spend", "delete", "settings") must pass
the Tier 6 confirmation gate before it runs. We decide this per tool, here, at
definition time — not as an afterthought.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# A tool handler takes validated input and returns a plain string result.
ToolHandler = Callable[[dict[str, Any]], str]


@dataclass
class ToolResult:
    """What running a tool produced. Errors are data, not exceptions —
    they go back to the model so it can reason about them."""

    content: str
    is_error: bool = False


@dataclass
class Tool:
    name: str
    description: str
    # JSON-schema-style input spec, e.g.
    #   {"type": "object", "properties": {...}, "required": [...]}
    input_schema: dict[str, Any]
    handler: ToolHandler
    # None = safe/read-only. Otherwise one of the configured consequence kinds.
    consequence: str | None = None

    def to_provider_schema(self) -> dict[str, Any]:
        """The shape the model expects when listing available tools."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, raw_input: dict[str, Any]) -> ToolResult:
        """Run the handler, turning any failure into a plain-language result.

        A tool *will* fail — bad input, a network hiccup, a missing file. We
        catch it and hand the model a readable error rather than crashing, so the
        model can recover or explain it. The agent reasoning over a failed tool
        result is a feature, not a bug.
        """
        try:
            problem = self._validate(raw_input)
            if problem:
                return ToolResult(f"Invalid input: {problem}", is_error=True)
            return ToolResult(self.handler(raw_input))
        except Exception as exc:  # noqa: BLE001 - surface, don't crash
            return ToolResult(f"{type(exc).__name__}: {exc}", is_error=True)

    def _validate(self, raw_input: dict[str, Any]) -> str | None:
        """Light validation against the declared schema. Keeps the model honest
        without pulling in a full JSON-schema dependency."""
        if not isinstance(raw_input, dict):
            return "expected an object of named inputs"
        props: dict[str, Any] = self.input_schema.get("properties", {})
        for name in self.input_schema.get("required", []):
            if name not in raw_input or raw_input[name] in (None, ""):
                return f"missing required field '{name}'"
        for name, value in raw_input.items():
            spec = props.get(name)
            if not spec:
                continue
            expected = spec.get("type")
            if expected and not _type_ok(value, expected):
                return f"field '{name}' should be {expected}"
        return None


def _type_ok(value: Any, expected: str) -> bool:
    mapping = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    py = mapping.get(expected)
    if py is None:
        return True
    if expected == "integer" and isinstance(value, bool):
        return False  # bool is a subclass of int; don't let it pass as integer
    return isinstance(value, py)


class ToolRegistry:
    """The thing you extend forever. Register a tool; never touch the loop."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def add(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
        *,
        consequence: str | None = None,
    ) -> None:
        self.register(
            Tool(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=handler,
                consequence=consequence,
            )
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [t.to_provider_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)
