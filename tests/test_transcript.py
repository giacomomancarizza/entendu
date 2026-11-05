import json

from entendu.transcript import chunk_transcript, fmt_ts, load_transcript, parse_transcript


def test_vtt_parsing(sample_vtt):
    t = load_transcript(sample_vtt)
    assert len(t.segments) == 29
    first = t.segments[0]
    assert first.start == 1.0 and first.end == 6.5
    assert first.text.startswith("Salut tout le monde")
    assert t.timed


def test_srt_parsing():
    raw = "1\n00:00:01,000 --> 00:00:03,500\nBonjour <i>à tous</i>\n\n2\n00:01:02,000 --> 00:01:04,000\nÇa va ?\n"
    t = parse_transcript(raw, "application/x-subrip")
    assert [s.text for s in t.segments] == ["Bonjour à tous", "Ça va ?"]
    assert t.segments[1].start == 62.0


def test_podcasting2_json():
    raw = json.dumps({"version": "1.0.0", "segments": [
        {"speaker": "A", "startTime": 0.5, "endTime": 2.0, "body": "Salut"},
        {"speaker": "B", "startTime": 2.0, "endTime": 4.0, "body": " "},
        {"speaker": "B", "startTime": 4.0, "endTime": 6.0, "body": "Coucou"},
    ]})
    t = parse_transcript(raw, "application/json")
    assert [s.text for s in t.segments] == ["Salut", "Coucou"]


def test_plain_text_keeps_bracket_timestamps():
    t = parse_transcript("[01:05] Première phrase\nSans minutage\n[1:02:03] Tard", "txt")
    assert [s.start for s in t.segments] == [65.0, None, 3723.0]


def test_chunking_by_minutes(sample_vtt):
    t = load_transcript(sample_vtt)
    chunks = chunk_transcript(t, minutes=1.5)
    assert len(chunks) == 2
    assert chunks[0].start == 1.0
    assert chunks[1].start >= 90
    assert chunks[0].text.splitlines()[0].startswith("[00:01] ")
    # no segment lost or duplicated
    assert sum(len(c.text.splitlines()) for c in chunks) == len(t.segments)


def test_chunking_untimed_by_size():
    t = parse_transcript("\n".join(["phrase " * 20] * 30), "txt")
    chunks = chunk_transcript(t, max_chars=1000)
    assert len(chunks) > 1 and all(c.start is None for c in chunks)


def test_fmt_ts():
    assert fmt_ts(65) == "01:05"
    assert fmt_ts(3723) == "1:02:03"
    assert fmt_ts(None) == "--:--"
