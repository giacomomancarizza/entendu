from entendu.config import Learner
from entendu.extract import ClaudeExtractor, build_notes, norm, tool_schema
from entendu.transcript import chunk_transcript, load_transcript


def _run(fake_client, responses, transcript, known=frozenset()):
    client = fake_client(responses)
    ex = ClaudeExtractor("test-model", Learner(), client=client)
    chunks = chunk_transcript(transcript, minutes=1.5)
    notes = build_notes(ex, chunks, transcript, podcast="Le Café du Lundi", title="Camille",
                        episode_key="k1", known=set(known), max_vocab=50, max_expressions=50,
                        audio_url="https://cdn.example.com/a.mp3", workers=1)
    return notes, client


def test_grounding_attaches_real_timestamps(fake_client, sample_notes, sample_vtt):
    t = load_transcript(sample_vtt)
    notes, _ = _run(fake_client, sample_notes, t)
    exprs = {e.expression: e for e in notes.expressions}
    assert exprs["avoir du pain sur la planche"].timestamp == 11.0
    assert exprs["un truc de ouf"].timestamp == 142.0
    moments = [m.timestamp for m in notes.moments]
    assert moments == sorted(moments) and moments[0] == 11.0


def test_hallucinated_item_is_dropped(fake_client, sample_notes, sample_vtt):
    notes, _ = _run(fake_client, sample_notes, load_transcript(sample_vtt))
    assert "trucmuche" not in [v.lemma for v in notes.vocabulary]
    assert notes.dropped == 1


def test_paraphrased_example_is_replaced_by_real_sentence(fake_client, sample_notes, sample_vtt):
    notes, _ = _run(fake_client, sample_notes, load_transcript(sample_vtt))
    abo = next(v for v in notes.vocabulary if v.lemma == "abonnement")
    assert abo.example.startswith("C'est une appli qui aide les gens")
    assert abo.timestamp == 46.5


def test_known_words_are_skipped(fake_client, sample_notes, sample_vtt):
    notes, client = _run(fake_client, sample_notes, load_transcript(sample_vtt),
                         known={norm("bosser"), norm("faire un carton")})
    assert "bosser" not in [v.lemma for v in notes.vocabulary]
    assert "faire un carton" not in [e.expression for e in notes.expressions]
    assert notes.already_known == 2
    # known words are also passed to the model so it does not waste slots on them
    assert "bosser" in client.calls[0]["messages"][0]["content"]


def test_tool_is_forced_and_schema_lists_levels(fake_client, sample_notes, sample_vtt):
    _, client = _run(fake_client, sample_notes, load_transcript(sample_vtt))
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_study_notes"}
    assert "C2" in str(tool_schema())


def test_invalid_output_is_retried_with_error_feedback(fake_client, sample_notes, sample_vtt):
    bad = {"gist": "x", "vocabulary": [{"term": "a"}], "expressions": [], "moments": []}
    t = load_transcript(sample_vtt)
    client = fake_client([bad, sample_notes[0]])
    ex = ClaudeExtractor("test-model", Learner(), client=client)
    chunk = chunk_transcript(t, minutes=1.5)[0]
    notes = ex.notes_for_chunk(chunk, "Camille", [])
    assert notes.gist.startswith("Camille")
    retry_msg = client.calls[1]["messages"][-1]["content"][0]
    assert retry_msg["type"] == "tool_result" and retry_msg["is_error"] is True
