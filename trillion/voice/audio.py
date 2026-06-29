"""Push-to-talk audio capture and playback.

Push-to-talk first: you hold a key, speak, release. We never have to guess when
you started or finished — a huge simplification, and it sidesteps the
"don't let it listen to itself" problem, since Trillion isn't capturing while it
speaks. Keep that property until everything else is solid.

All audio deps are imported lazily so importing this module never breaks the text
path.
"""

from __future__ import annotations

import io
import wave

SAMPLE_RATE = 16_000  # Deepgram-friendly
CHANNELS = 1
SAMPWIDTH = 2  # 16-bit


def audio_available() -> bool:
    try:
        import sounddevice  # noqa: F401

        return True
    except ImportError:
        return False


class PushToTalk:
    """Record while a key is held; stop on release.

    The interface layer decides how the key is read (terminal raw mode, a GUI
    hotkey, a hardware button). This class just owns start/stop/encode.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        try:
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "Push-to-talk needs 'sounddevice' and 'numpy'. See requirements.txt."
            ) from exc
        self._sample_rate = sample_rate
        self._frames: list = []
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        self._frames = []

        def _cb(indata, _frames, _time, _status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=CHANNELS,
            dtype="int16",
            callback=_cb,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Stop recording, return the captured audio as WAV bytes."""
        import numpy as np

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return _empty_wav(self._sample_rate)
        pcm = np.concatenate(self._frames, axis=0)
        return _pcm_to_wav(pcm.tobytes(), self._sample_rate)


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPWIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _empty_wav(sample_rate: int) -> bytes:
    return _pcm_to_wav(b"", sample_rate)
