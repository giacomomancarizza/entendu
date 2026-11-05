"""Read podcast RSS feeds and download episode audio or the publisher's transcript."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx

from .config import Podcast

USER_AGENT = "entendu/0.1 (podcast study tool)"


@dataclass
class Episode:
    podcast: str
    guid: str
    title: str
    published: datetime | None
    audio_url: str | None
    transcript_url: str | None
    transcript_type: str | None
    link: str | None

    @property
    def key(self) -> str:
        return hashlib.sha1(f"{self.podcast}|{self.guid}".encode()).hexdigest()[:16]


def _published(entry) -> datetime | None:
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*stamp[:6], tzinfo=timezone.utc) if stamp else None


def _audio(entry) -> str | None:
    for enc in entry.get("enclosures", []):
        if str(enc.get("type", "")).startswith("audio") or str(enc.get("href", "")).split("?")[0].endswith((".mp3", ".m4a")):
            return enc.get("href")
    return None


def _transcript(entry) -> tuple[str | None, str | None]:
    """Podcasting 2.0 <podcast:transcript url=... type=...>. Prefer timed formats."""
    found = []
    for key in ("podcast_transcript", "podcast:transcript"):
        val = entry.get(key)
        if isinstance(val, dict):
            found.append(val)
        elif isinstance(val, list):
            found.extend(v for v in val if isinstance(v, dict))
    for link in entry.get("links", []):
        if link.get("rel") == "transcript":
            found.append({"url": link.get("href"), "type": link.get("type", "")})
    rank = {"text/vtt": 0, "application/x-subrip": 1, "application/srt": 1, "application/json": 2, "text/plain": 3}
    found = [f for f in found if f.get("url") or f.get("href")]
    if not found:
        return None, None
    best = min(found, key=lambda f: rank.get(f.get("type", ""), 9))
    return best.get("url") or best.get("href"), best.get("type")


def list_episodes(podcast: Podcast, limit: int = 10) -> list[Episode]:
    parsed = feedparser.parse(podcast.feed, agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Could not read feed for {podcast.name}: {parsed.bozo_exception}")
    episodes = []
    for e in parsed.entries[:limit]:
        t_url, t_type = _transcript(e)
        episodes.append(Episode(
            podcast=podcast.name,
            guid=e.get("id") or e.get("link") or e.get("title", ""),
            title=e.get("title", "Untitled episode"),
            published=_published(e),
            audio_url=_audio(e),
            transcript_url=t_url,
            transcript_type=t_type,
            link=e.get("link"),
        ))
    return episodes


def download(url: str, dest: Path) -> Path:
    """Stream a file to disk once; reuse the cached copy afterwards."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for block in r.iter_bytes(1 << 16):
                fh.write(block)
    tmp.rename(dest)
    return dest


def fetch_text(url: str) -> str:
    r = httpx.get(url, follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.text
