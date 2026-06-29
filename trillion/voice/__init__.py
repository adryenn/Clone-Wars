"""The ears and mouth — voice wrapped around the *same* brain.

Voice changes only the two ends of a turn: input arrives as transcribed speech
instead of typed text, and output gets spoken aloud. The brain in the middle is
untouched. Every provider sits behind a one-function seam so it can be swapped in
one place, and every dependency is imported lazily so the text path runs with
none of them installed.
"""

from trillion.voice.stt import Transcriber, transcribe_available
from trillion.voice.tts import Speaker, speech_available

__all__ = ["Transcriber", "Speaker", "transcribe_available", "speech_available"]
