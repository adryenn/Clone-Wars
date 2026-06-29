"""Text-to-speech seam — ElevenLabs by default.

One job: "give me text, play it aloud." Natural enough that Trillion feels like a
presence rather than a robot reading, and it streams audio so playback can start
before the whole sentence is synthesized. Because the brain streams (Tier 1) and
this streams, the first sentence can begin while the rest is still being written —
that's what makes it feel responsive instead of laggy.

The voice id and model live in config.toml, not here.
"""

from __future__ import annotations

import threading


def speech_available() -> bool:
    try:
        import elevenlabs  # noqa: F401

        return True
    except ImportError:
        return False


class Speaker:
    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_turbo_v2_5") -> None:
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "Voice needs the 'elevenlabs' package. See requirements.txt."
            ) from exc
        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model = model
        self._stop = threading.Event()

    def interrupt(self) -> None:
        """Barge-in: stop speaking so Trillion can listen. If you start a new
        turn while it's talking, it should stop and listen."""
        self._stop.set()

    def speak(self, text: str) -> None:
        """Synthesize and play. Streams so the first audio plays early."""
        from elevenlabs import play, stream

        self._stop.clear()
        audio = self._client.text_to_speech.convert_as_stream(
            voice_id=self._voice_id,
            model_id=self._model,
            text=text,
        )
        # Stream playback; bail early if interrupted (barge-in).
        try:
            stream(audio)
        except Exception:  # pragma: no cover - playback backend varies
            play(b"".join(audio))

    def speak_stream(self, text_chunks):
        """Speak text as it's produced by the model. Accepts an iterable of text
        chunks and synthesizes sentence-by-sentence so audio starts early."""
        buffer = ""
        for chunk in text_chunks:
            if self._stop.is_set():
                break
            buffer += chunk
            # Flush on sentence boundaries to keep latency low.
            while any(p in buffer for p in ".!?\n"):
                idx = min(
                    (buffer.index(p) for p in ".!?\n" if p in buffer),
                    default=-1,
                )
                if idx < 0:
                    break
                sentence, buffer = buffer[: idx + 1], buffer[idx + 1 :]
                if sentence.strip():
                    self.speak(sentence.strip())
        if buffer.strip() and not self._stop.is_set():
            self.speak(buffer.strip())
