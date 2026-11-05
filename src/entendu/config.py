from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass
class Podcast:
    name: str
    feed: str


@dataclass
class Learner:
    level: str = "B2"
    native_language: str = "Italian"
    explain_in: str = "Italian"
    interests: str = ""


@dataclass
class Config:
    podcasts: list[Podcast]
    learner: Learner = field(default_factory=Learner)
    model: str = DEFAULT_MODEL
    whisper_model: str = "small"
    chunk_minutes: float = 8.0
    max_vocab: int = 25
    max_expressions: int = 15
    db_path: Path = Path("data/entendu.db")
    cache_dir: Path = Path("data/cache")
    output_dir: Path = Path("sheets")
    lessons_dir: Path = Path("~/Documents/Francese")
    spotify_token: str = "data/.spotify_token"
    window_minutes: float = 40
    pad_seconds: float = 90

    @property
    def feed_overrides(self) -> dict[str, str]:
        return {p.name: p.feed for p in self.podcasts}

    def podcast(self, name: str) -> Podcast:
        wanted = name.strip().lower()
        for p in self.podcasts:
            if p.name.lower() == wanted or wanted in p.name.lower():
                return p
        names = ", ".join(p.name for p in self.podcasts) or "none"
        raise KeyError(f"Unknown podcast '{name}'. Configured: {names}")


def load_config(path: str | Path = "config.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    podcasts = [Podcast(**p) for p in raw.get("podcasts") or []]
    learner = Learner(**(raw.get("learner") or {}))
    return Config(
        podcasts=podcasts,
        learner=learner,
        model=os.getenv("ENTENDU_MODEL", raw.get("model", DEFAULT_MODEL)),
        whisper_model=raw.get("whisper_model", "small"),
        chunk_minutes=float(raw.get("chunk_minutes", 8)),
        max_vocab=int(raw.get("max_vocab", 25)),
        max_expressions=int(raw.get("max_expressions", 15)),
        db_path=Path(os.getenv("ENTENDU_DB", raw.get("db_path", "data/entendu.db"))),
        cache_dir=Path(raw.get("cache_dir", "data/cache")),
        output_dir=Path(raw.get("output_dir", "sheets")),
        lessons_dir=Path(raw.get("lessons_dir", "~/Documents/Francese")).expanduser(),
        spotify_token=(raw.get("spotify") or {}).get("token_cache", "data/.spotify_token"),
        window_minutes=float((raw.get("spotify") or {}).get("window_minutes", 40)),
        pad_seconds=float((raw.get("spotify") or {}).get("pad_seconds", 90)),
    )
