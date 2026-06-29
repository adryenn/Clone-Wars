"""The provider seam.

Everything that talks to a language model goes through here. One small surface —
``LLMProvider.run`` — whose job is: "send this conversation (system prompt +
history + available tools), get back a reply or a request to use a tool." The
agent core never imports the Anthropic SDK directly. That's what lets us swap
models, add retries, and tally cost in exactly one place.

The ``anthropic`` import is deliberately lazy so the rest of the harness — and
the test suite, which injects a FakeProvider — loads without the SDK present.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

# A streamed-text sink: called with each chunk of assistant text as it arrives.
TextSink = Callable[[str], None]


@dataclass
class ToolCall:
    """The model asking us to run a tool."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    """One turn of model output: some text, and/or some tool calls."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMError(RuntimeError):
    """A failure talking to the provider. Caller shows a clean message."""


class LLMProvider(Protocol):
    def run(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: TextSink | None = None,
    ) -> LLMResponse: ...


class AnthropicProvider:
    """The default brain: latest capable Claude via the official SDK.

    Streams text so the assistant feels alive in text and so Tier 3 can begin
    speaking a sentence before the rest is written. Retries transient network
    failures with a short backoff rather than crashing the conversation.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> None:
        try:
            import anthropic  # lazy: only needed when actually calling the model
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise LLMError(
                "The 'anthropic' package isn't installed. Run "
                "`pip install -r requirements.txt`."
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_retries = max_retries

    def run(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: TextSink | None = None,
    ) -> LLMResponse:
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._run_once(system, messages, tools, on_text)
            except Exception as exc:  # noqa: BLE001 - normalize to LLMError below
                if not _is_retryable(exc) or attempt == self._max_retries - 1:
                    raise LLMError(_friendly(exc)) from exc
                last_err = exc
                time.sleep(2**attempt)  # 1s, 2s, 4s
        raise LLMError(_friendly(last_err))  # pragma: no cover

    def _run_once(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_text: TextSink | None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            system=system,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        if tools:
            kwargs["tools"] = tools

        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if (
                    event.type == "content_block_delta"
                    and getattr(event.delta, "type", None) == "text_delta"
                ):
                    if on_text:
                        on_text(event.delta.text)
            final = stream.get_final_message()

        return _from_anthropic_message(final)


def _from_anthropic_message(msg: Any) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in msg.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
    usage = Usage(
        input_tokens=getattr(msg.usage, "input_tokens", 0),
        output_tokens=getattr(msg.usage, "output_tokens", 0),
    )
    return LLMResponse(
        text="".join(text_parts),
        tool_calls=tool_calls,
        stop_reason=msg.stop_reason or "end_turn",
        usage=usage,
    )


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__
    # Connection/timeouts/5xx are worth a retry; auth/validation are not.
    return any(
        token in name
        for token in ("Connection", "Timeout", "InternalServer", "APIStatus", "Overloaded")
    )


def _friendly(exc: Exception | None) -> str:
    if exc is None:
        return "The model was unreachable. Please try again."
    name = type(exc).__name__
    if "Authentication" in name or "PermissionDenied" in name:
        return "The model rejected the API key. Check ANTHROPIC_API_KEY."
    if "RateLimit" in name:
        return "Rate limited by the provider. Give it a moment and retry."
    return f"Couldn't reach the model ({name}). Please try again."
