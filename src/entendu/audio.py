"""Cut only the part I listened to, so transcription stays fast."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# The RSS audio can carry different ads than Spotify, so positions may shift a little.
# A margin on both sides makes sure the part I heard is inside the cut.
DEFAULT_PAD_SECONDS = 90


def cut_command(src: Path, dest: Path, start_s: float, duration_s: float) -> list[str]:
    return ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start_s:.1f}", "-i", str(src),
            "-t", f"{duration_s:.1f}", "-ac", "1", "-ar", "16000", str(dest)]


def cut(src: Path, dest: Path, start_ms: int, end_ms: int, pad_seconds: float = DEFAULT_PAD_SECONDS) -> float:
    """Write the segment to `dest` (mono 16 kHz wav, what Whisper wants). Returns its start in seconds."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found: install it with 'brew install ffmpeg'")
    start_s = max(0.0, start_ms / 1000 - pad_seconds)
    end_s = end_ms / 1000 + pad_seconds
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cut_command(src, dest, start_s, end_s - start_s), check=True)
    return start_s
