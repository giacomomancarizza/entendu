"""Transcript model, loaders for publisher formats (VTT, SRT, Podcasting 2.0 JSON, text) and chunking."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float | None  # seconds from episode start, None when the source has no timing
    end: float | None
    text: str


@dataclass
class Transcript:
    segments: list[Segment]
    source: str  # "publisher", "whisper" or "file"

    @property
    def timed(self) -> bool:
        return any(s.start is not None for s in self.segments)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


@dataclass
class Chunk:
    index: int
    start: float | None
    end: float | None
    text: str  # lines formatted as "[mm:ss] sentence" when timing is known


def fmt_ts(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_ts(value: str) -> float:
    """Parse 'hh:mm:ss.mmm', 'mm:ss', 'hh:mm:ss,mmm' into seconds."""
    value = value.strip().replace(",", ".")
    parts = [float(p) for p in value.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


_CUE_TIME = re.compile(r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}")
_TAGS = re.compile(r"<[^>]+>")


def _parse_cues(raw: str) -> list[Segment]:
    """Shared parser for WebVTT and SRT: blocks separated by blank lines with a 'start --> end' line."""
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n")):
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if _CUE_TIME.search(line):
                start_s, end_s = [p.split()[0] for p in line.split("-->")]
                text = _TAGS.sub("", " ".join(lines[i + 1 :])).strip()
                if text:
                    segments.append(Segment(parse_ts(start_s), parse_ts(end_s), text))
                break
    return segments


def _parse_json(raw: str) -> list[Segment]:
    data = json.loads(raw)
    items = data.get("segments", data) if isinstance(data, dict) else data
    segments = []
    for it in items:
        text = (it.get("body") or it.get("text") or "").strip()
        if not text:
            continue
        start = it.get("startTime", it.get("start"))
        end = it.get("endTime", it.get("end"))
        segments.append(Segment(float(start) if start is not None else None,
                                float(end) if end is not None else None, text))
    return segments


def _parse_text(raw: str) -> list[Segment]:
    """Plain text. Lines starting with [mm:ss] keep their timestamp."""
    segments = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\[(\d{1,2}(?::\d{2}){1,2})\]\s*(.+)$", line)
        if m:
            segments.append(Segment(parse_ts(m.group(1)), None, m.group(2)))
        else:
            segments.append(Segment(None, None, line))
    return segments


def load_transcript(path: str | Path, source: str = "file") -> Transcript:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    return parse_transcript(raw, path.suffix.lower(), source)


def parse_transcript(raw: str, kind: str, source: str = "file") -> Transcript:
    kind = kind.lower().lstrip(".")
    if kind in ("vtt", "srt") or any(k in kind for k in ("vtt", "srt", "subrip")):
        segments = _parse_cues(raw)
    elif "json" in kind:
        segments = _parse_json(raw)
    elif "html" in kind:
        from bs4 import BeautifulSoup

        segments = _parse_text(BeautifulSoup(raw, "html.parser").get_text("\n"))
    else:
        segments = _parse_text(raw)
    if not segments:
        raise ValueError("Transcript is empty or in an unsupported format")
    return Transcript(segments, source)


def chunk_transcript(t: Transcript, minutes: float = 8.0, max_chars: int = 9000) -> list[Chunk]:
    """Split into blocks of about `minutes` (or `max_chars` when untimed), never splitting a segment."""
    limit = minutes * 60
    chunks: list[Chunk] = []
    buf: list[Segment] = []

    def flush():
        if not buf:
            return
        lines = [f"[{fmt_ts(s.start)}] {s.text}" if s.start is not None else s.text for s in buf]
        starts = [s.start for s in buf if s.start is not None]
        ends = [s.end if s.end is not None else s.start for s in buf if s.start is not None]
        chunks.append(Chunk(len(chunks), min(starts) if starts else None,
                            max(ends) if ends else None, "\n".join(lines)))
        buf.clear()

    for seg in t.segments:
        if buf:
            first = next((s.start for s in buf if s.start is not None), None)
            too_long = first is not None and seg.start is not None and seg.start - first >= limit
            too_big = sum(len(s.text) for s in buf) + len(seg.text) > max_chars
            if too_long or too_big:
                flush()
        buf.append(seg)
    flush()
    return chunks
