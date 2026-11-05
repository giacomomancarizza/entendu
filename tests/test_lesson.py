"""The whole button flow, offline: fake Spotify, local feed, publisher transcript, replayed Claude answers."""
import shutil
import subprocess

import pytest

from entendu import cli
from entendu.audio import cut
from entendu.config import Podcast
from entendu.feeds import list_episodes
from entendu.match import match_episode, similarity
from entendu.store import Store

from conftest import EXAMPLES, FIXTURES
from test_spotify import FakeSpotify, _ep


def test_match_episode_by_title_and_date():
    eps = list_episodes(Podcast("Test", str(FIXTURES / "feed.xml")))
    assert match_episode(eps, "Ep 2", "2026-11-02").title == "Ep 2"
    assert match_episode(eps, "EP 1 ", None).title == "Ep 1"
    assert match_episode(eps, "Something else entirely", None) is None
    assert similarity("Le Café du Lundi", "le cafe du lundi") > 0.8


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_cut_keeps_listened_part_with_margin(tmp_path):
    src = tmp_path / "ep.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=300",
                    str(src)], check=True)
    out = tmp_path / "part.wav"
    start = cut(src, out, start_ms=120_000, end_ms=180_000, pad_seconds=30)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(out)], capture_output=True, text=True).stdout)
    assert start == 90.0 and abs(dur - 120.0) < 0.5


def test_lesson_end_to_end(tmp_path, monkeypatch):
    sp = FakeSpotify(
        playback={"currently_playing_type": "episode", "is_playing": False, "progress_ms": 150_000,
                  "item": _ep("sp-ep2", "Ep 2", show="Test", duration=200_000)},
        shows={"s1": ("Test", [_ep("sp-ep2", "Ep 2", show="Test", duration=200_000,
                                   rp={"resume_position_ms": 150_000})])},
    )
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
podcasts:
  - name: Test
    feed: {FIXTURES / 'feed.xml'}
db_path: {tmp_path / 'e.db'}
lessons_dir: {tmp_path / 'Francese'}
""", encoding="utf-8")
    monkeypatch.setattr("entendu.spotify.connect", lambda *_a, **_k: sp)
    monkeypatch.setattr("entendu.feeds.fetch_text", lambda url: (EXAMPLES / "cafe-du-lundi.vtt").read_text("utf-8"))
    monkeypatch.setattr("entendu.macos.notify", lambda *a, **k: None)
    monkeypatch.setattr("entendu.macos.open_file", lambda *a, **k: None)

    code = cli.main(["--config", str(cfg_file), "lesson", "--chunk-minutes", "1.5",
                     "--replay", str(FIXTURES / "sample_notes.json")])
    assert code == 0
    lessons = list((tmp_path / "Francese").glob("*.html"))
    assert len(lessons) == 1 and "Test, Ep 2" in lessons[0].name
    html = lessons[0].read_text("utf-8")
    assert "Vérifie ta compréhension" in html and "ascoltato dal 00:00 al 02:30" in html
    # positions are remembered for next time
    assert Store(tmp_path / "e.db").positions() == {"sp-ep2": 150_000}


def test_lesson_dry_run_stops_before_download(tmp_path, monkeypatch, capsys):
    sp = FakeSpotify(playback={"currently_playing_type": "episode", "progress_ms": 60_000,
                               "item": _ep("x", "Ep 1", show="Test")})
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"podcasts:\n  - name: Test\n    feed: {FIXTURES / 'feed.xml'}\ndb_path: {tmp_path / 'e.db'}\n")
    monkeypatch.setattr("entendu.spotify.connect", lambda *_a, **_k: sp)
    monkeypatch.setattr("entendu.feeds.download", lambda *a, **k: pytest.fail("must not download"))
    assert cli.main(["--config", str(cfg_file), "lesson", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Tratto ascoltato: dal 00:00 al 01:00" in out and "Nel feed RSS: Ep 1 (audio)" in out
