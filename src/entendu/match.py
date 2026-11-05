"""From a Spotify episode to the same episode in the podcast's public RSS feed (where the audio is)."""
from __future__ import annotations

from datetime import date, datetime
from difflib import SequenceMatcher

import httpx

from .extract import norm
from .feeds import Episode


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def find_feed(show: str, overrides: dict[str, str] | None = None) -> str | None:
    """Feed URL for a show: first config.yaml, then the free Apple Podcasts search API."""
    for name, url in (overrides or {}).items():
        if norm(name) == norm(show) or norm(name) in norm(show):
            return url
    r = httpx.get("https://itunes.apple.com/search", timeout=20,
                  params={"term": show, "media": "podcast", "entity": "podcast", "limit": 8})
    r.raise_for_status()
    results = [x for x in r.json().get("results", []) if x.get("feedUrl")]
    if not results:
        return None
    best = max(results, key=lambda x: similarity(x.get("collectionName", ""), show))
    return best["feedUrl"] if similarity(best.get("collectionName", ""), show) >= 0.6 else None


def _days_apart(a: str | None, b: datetime | None) -> int | None:
    if not a or not b:
        return None
    try:
        return abs((date.fromisoformat(a[:10]) - b.date()).days)
    except ValueError:
        return None


def match_episode(episodes: list[Episode], title: str, release_date: str | None) -> Episode | None:
    """Best title match; the publication date breaks ties and rescues renamed episodes."""
    best, best_score = None, 0.0
    for ep in episodes:
        score = similarity(ep.title, title)
        if score == 1.0:
            return ep  # identical title: nothing to weigh
        days = _days_apart(release_date, ep.published)
        if days is not None and days <= 2:
            score += 0.1  # tie breaker only: numbered titles like "Ep 1" and "Ep 2" look alike
        if score > best_score:
            best, best_score = ep, score
    return best if best_score >= 0.7 else None
