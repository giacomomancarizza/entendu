from entendu.anki import export_anki
from entendu.config import Learner, Podcast
from entendu.extract import ClaudeExtractor, build_notes, norm
from entendu.feeds import list_episodes
from entendu.notify import build_payload
from entendu.render import to_html, to_markdown
from entendu.store import Store
from entendu.transcript import chunk_transcript, load_transcript

from conftest import FIXTURES


def _notes(fake_client, sample_notes, sample_vtt):
    t = load_transcript(sample_vtt)
    ex = ClaudeExtractor("m", Learner(), client=fake_client(sample_notes))
    return build_notes(ex, chunk_transcript(t, 1.5), t, podcast="Le Café du Lundi", title="Camille",
                       episode_key="k1", known=set(), max_vocab=50, max_expressions=50,
                       audio_url="https://cdn.example.com/a.mp3", workers=1)


def test_store_remembers_items_across_episodes(tmp_path, fake_client, sample_notes, sample_vtt):
    store = Store(tmp_path / "e.db")
    notes = _notes(fake_client, sample_notes, sample_vtt)
    added = store.save(notes)
    assert added == len(notes.vocabulary) + len(notes.expressions)
    assert norm("péter les plombs") in store.known_keys()
    assert store.is_processed("k1")
    assert store.episode_notes("k1").title == "Camille"
    assert store.save(notes) == 0  # second save adds nothing new


def test_anki_export(tmp_path, fake_client, sample_notes, sample_vtt):
    store = Store(tmp_path / "e.db")
    store.save(_notes(fake_client, sample_notes, sample_vtt))
    rows = store.items()
    out = tmp_path / "deck.txt"
    n = export_anki(rows, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["#separator:tab", "#html:true", "#tags column:3"]
    assert n == len(rows) == len(lines) - 3
    assert all(len(l.split("\t")) == 3 for l in lines[3:])
    pain = next(l for l in lines if l.startswith("avoir du pain sur la planche"))
    assert "<b>" in pain and "(00:11)" in pain and "familiar" in pain
    store.mark_exported([r["key"] for r in rows])
    assert store.items() == []


def test_html_and_markdown_sheets(fake_client, sample_notes, sample_vtt):
    notes = _notes(fake_client, sample_notes, sample_vtt)
    html = to_html(notes)
    for section in ("En bref", "Ce que tu as pu rater", "Expressions", "Vocabulaire"):
        assert section in html
    assert 'href="https://cdn.example.com/a.mp3#t=11"' in html
    md = to_markdown(notes)
    assert "| Mot | Sens | Entendu | Niveau |" in md and "`00:11`" in md


def test_make_payload(fake_client, sample_notes, sample_vtt):
    notes = _notes(fake_client, sample_notes, sample_vtt)
    p = build_payload(notes, "<html>", "# md")
    assert p["subject"].startswith("Entendu: Le Café du Lundi")
    assert p["counts"]["expressions"] == len(notes.expressions)
    assert {i["kind"] for i in p["items"]} == {"word", "expression"}


def test_feed_parsing_prefers_timed_transcript():
    eps = list_episodes(Podcast("Test", str(FIXTURES / "feed.xml")))
    assert [e.title for e in eps] == ["Ep 2", "Ep 1"]
    assert eps[0].audio_url.startswith("https://cdn.example.com/ep2.mp3")
    assert eps[0].transcript_url and eps[0].transcript_url.endswith(".vtt")
    assert eps[1].transcript_url is None
    assert eps[0].published.date().isoformat() == "2026-11-02"
