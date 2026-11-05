from entendu.spotify import in_player, listened_range, moved_since, pick_episode, started_episodes


def _ep(id_, name, show="French with Félix", duration=1_800_000, release="2026-11-02", rp=None):
    ep = {"id": id_, "name": name, "duration_ms": duration, "release_date": release,
          "show": {"name": show}, "external_urls": {"spotify": f"https://open.spotify.com/episode/{id_}"}}
    if rp is not None:
        ep["resume_point"] = rp
    return ep


class FakeSpotify:
    def __init__(self, playback=None, shows=None):
        self._playback, self._shows = playback, shows or {}

    def current_playback(self, additional_types=None):
        return self._playback

    def current_user_saved_shows(self, limit=20):
        return {"items": [{"show": {"id": sid, "name": name}} for sid, (name, _) in self._shows.items()]}

    def show_episodes(self, show_id, limit=50, market=None):
        return {"items": self._shows[show_id][1][:limit]}


def test_player_episode_even_when_paused():
    sp = FakeSpotify(playback={"currently_playing_type": "episode", "is_playing": False,
                               "progress_ms": 754_000, "item": _ep("e1", "Le subjonctif")})
    ep = in_player(sp)
    assert ep.title == "Le subjonctif" and ep.position_ms == 754_000 and ep.source == "player"


def test_music_in_player_is_ignored():
    assert in_player(FakeSpotify(playback={"currently_playing_type": "track", "item": {}})) is None


def test_started_episodes_keeps_only_started_ones():
    shows = {"s1": ("French with Félix", [
        _ep("a", "Nouveau", release="2026-11-04", rp={"resume_position_ms": 0, "fully_played": False}),
        _ep("b", "Commencé", release="2026-11-02", rp={"resume_position_ms": 600_000, "fully_played": False}),
        _ep("c", "Fini", release="2026-10-28", rp={"resume_position_ms": 0, "fully_played": True}),
        None,
    ])}
    eps = started_episodes(FakeSpotify(shows=shows))
    assert [e.title for e in eps] == ["Commencé", "Fini"]
    assert eps[1].position_ms == eps[1].duration_ms and eps[1].progress == 100


def test_listened_range_uses_previous_position():
    sp = FakeSpotify(playback={"currently_playing_type": "episode", "progress_ms": 1_860_000,
                               "item": _ep("e1", "X", duration=3_000_000)})
    ep = in_player(sp)
    assert listened_range(ep, previous_ms=720_000) == (720_000, 1_860_000)       # 12:00 -> 31:00
    assert listened_range(ep, previous_ms=None, window_minutes=20) == (660_000, 1_860_000)
    assert listened_range(ep, previous_ms=2_000_000, window_minutes=20) == (660_000, 1_860_000)  # went back


def test_pick_prefers_player_then_the_only_moved_episode():
    shows = {"s1": ("Félix", [
        _ep("b", "Commencé", rp={"resume_position_ms": 900_000}),
        _ep("c", "Ancien", rp={"resume_position_ms": 300_000}),
    ])}
    sp = FakeSpotify(shows=shows)
    cands = started_episodes(sp)
    never = lambda *_: (_ for _ in ()).throw(AssertionError("should not ask"))
    # only "Commencé" moved since last run
    assert pick_episode(None, cands, {"b": 100_000, "c": 300_000}, never).title == "Commencé"
    assert [e.title for e in moved_since(cands, {"b": 100_000, "c": 300_000})] == ["Commencé"]


def test_pick_asks_when_ambiguous():
    shows = {"s1": ("Félix", [_ep("b", "Un", rp={"resume_position_ms": 9}), _ep("c", "Deux", rp={"resume_position_ms": 5})])}
    cands = started_episodes(FakeSpotify(shows=shows))
    asked = {}

    def choose(labels, prompt):
        asked["labels"] = labels
        return 1

    picked = pick_episode(None, cands, {}, choose)
    assert picked.title == cands[1].title and len(asked["labels"]) == 2
    assert pick_episode(None, cands, {}, lambda *_: None) is None
