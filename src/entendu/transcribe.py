"""Speech to text with faster-whisper, run locally (free, no audio leaves the machine)."""
from __future__ import annotations

from pathlib import Path

from .transcript import Segment, Transcript


def transcribe_audio(path: Path, model_size: str = "small", device: str = "auto", offset: float = 0.0) -> Transcript:
    """Transcribe in French. `offset` (seconds) is added to timestamps when `path` is a cut of the episode."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # optional dependency
        raise RuntimeError("Install the whisper extra: pip install -e '.[whisper]'") from exc

    model = WhisperModel(model_size, device=device, compute_type="int8")
    # vad_filter skips music and silence, which podcasts have a lot of at the start
    segments, _info = model.transcribe(str(path), language="fr", vad_filter=True, beam_size=5)
    out = [Segment(s.start + offset, s.end + offset, s.text.strip()) for s in segments if s.text.strip()]
    if not out:
        raise RuntimeError("Whisper returned an empty transcript")
    return Transcript(out, source="whisper")
