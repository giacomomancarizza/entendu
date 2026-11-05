"""Which episode did I just listen to, and which part of it?

Spotify does not expose a listening history for podcast episodes, but it does expose:
- the player state (the episode in the player, even when paused, and its position);
- the resume point of every episode of the shows I follow (where I stopped).
Comparing resume points with the ones saved at the previous run tells which episode
moved and from which minute to which minute.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

SCOPES = " ".join([
    "user-read-playback-state",     # the player, even when paused
    "user-read-playback-position",  # resume point of each episode
    "user-library-read",            # the shows I follow
])
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"


@dataclass
class Listened:
    episode_id: str
    show: str
    title: str
    release_date: str | None
    duration_ms: int
    position_ms: int
    fully_played: bool
    url: str | None
    source: str  # "player" or "library"

    @property
    def progress(self) -> int:
        return 100 if self.fully_played else round(100 * self.position_ms / max(self.duration_ms, 1))

    def label(self) -> str:
        return f"{self.show}: {self.title} ({self.progress}%)"


def connect(token_cache: str = "data/.spotify_token"):
    """Spotify client. Reads SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET from the environment."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    os.makedirs(os.path.dirname(token_cache) or ".", exist_ok=True)
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        scope=SCOPES,
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", DEFAULT_REDIRECT),
        cache_path=token_cache,
    ))


def in_player(sp) -> Listened | None:
    state = sp.current_playback(additional_types="episode")
    if not state or state.get("currently_playing_type") != "episode" or not state.get("item"):
        return None
    ep = state["item"]
    return Listened(
        episode_id=ep["id"], show=ep["show"]["name"], title=ep["name"],
        release_date=ep.get("release_date"), duration_ms=ep["duration_ms"],
        position_ms=state.get("progress_ms") or 0, fully_played=False,
        url=(ep.get("external_urls") or {}).get("spotify"), source="player",
    )


def started_episodes(sp, per_show: int = 3) -> list[Listened]:
    """Latest episodes of the followed shows that have a resume point, newest first."""
    out: list[Listened] = []
    for item in sp.current_user_saved_shows(limit=50)["items"]:
        show = item["show"]
        for ep in sp.show_episodes(show["id"], limit=per_show, market="from_token")["items"]:
            if not ep:
                continue
            rp = ep.get("resume_point") or {}
            full = bool(rp.get("fully_played"))
            pos = int(rp.get("resume_position_ms") or 0)
            if pos > 0 or full:
                out.append(Listened(
                    episode_id=ep["id"], show=show["name"], title=ep["name"],
                    release_date=ep.get("release_date"), duration_ms=ep["duration_ms"],
                    position_ms=ep["duration_ms"] if full else pos, fully_played=full,
                    url=(ep.get("external_urls") or {}).get("spotify"), source="library",
                ))
    return sorted(out, key=lambda e: e.release_date or "", reverse=True)


def moved_since(candidates: list[Listened], snapshot: dict[str, int]) -> list[Listened]:
    """Episodes whose position changed since the last run (or that were never seen)."""
    return [c for c in candidates if snapshot.get(c.episode_id) != c.position_ms]


def listened_range(ep: Listened, previous_ms: int | None, window_minutes: float = 40) -> tuple[int, int]:
    """From where I was last time to where I am now; without history, the last `window_minutes`."""
    end = ep.duration_ms if ep.fully_played else ep.position_ms
    if previous_ms is not None and 0 <= previous_ms < end:
        start = previous_ms
    else:
        start = max(0, end - int(window_minutes * 60_000))
    return start, end


def pick_episode(player: Listened | None, candidates: list[Listened], snapshot: dict[str, int],
                 choose) -> Listened | None:
    """Decide which episode the lesson is about.

    1. the episode in the player, if any;
    2. the only episode that moved since last run;
    3. otherwise ask (choose receives labels and returns an index or None).
    """
    if player is not None:
        return player
    moved = moved_since(candidates, snapshot) if snapshot else []
    if len(moved) == 1:
        return moved[0]
    options = (moved or candidates)[:6]
    if not options:
        return None
    i = choose([o.label() for o in options], "Quale episodio hai ascoltato?")
    return options[i] if i is not None else None
