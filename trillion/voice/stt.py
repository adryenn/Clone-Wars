"""Speech-to-text seam — Deepgram by default.

One job: "give me audio, get back text." Keep it behind this seam so the
transcriber can change without touching the rest of the harness. The Deepgram key
lives in an environment variable alongside the others, never in code.
"""

from __future__ import annotations


def transcribe_available() -> bool:
    try:
        import deepgram  # noqa: F401
        import sounddevice  # noqa: F401

        return True
    except ImportError:
        return False


class Transcriber:
    """Wraps Deepgram. Fast and streaming, which keeps the gap between releasing
    the push-to-talk key and Trillion understanding you short."""

    def __init__(self, api_key: str, model: str = "nova-2") -> None:
        try:
            from deepgram import DeepgramClient
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "Voice needs the 'deepgram-sdk' package. See requirements.txt."
            ) from exc
        self._client = DeepgramClient(api_key)
        self._model = model

    def transcribe(self, audio_wav: bytes) -> str:
        """Audio in (16-bit PCM WAV bytes), text out."""
        from deepgram import PrerecordedOptions

        options = PrerecordedOptions(model=self._model, smart_format=True, language="en")
        source = {"buffer": audio_wav, "mimetype": "audio/wav"}
        resp = self._client.listen.prerecorded.v("1").transcribe_file(source, options)
        try:
            return resp.results.channels[0].alternatives[0].transcript.strip()
        except (AttributeError, IndexError):
            return ""
