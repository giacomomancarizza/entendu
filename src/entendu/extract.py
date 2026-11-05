"""Structured extraction with Claude, then grounding: every example must be found in the transcript."""
from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from .config import Learner
from .models import LEVELS, ChunkNotes, EpisodeNotes, Expression, Moment, Question, VocabItem
from .transcript import Chunk, Transcript

TOOL_NAME = "record_study_notes"

SYSTEM = """You are an experienced French teacher. You prepare study notes for one learner \
from the transcript of a podcast episode they listened to on a noisy metro.

Rules:
- Work only from the transcript. Never invent words, sentences or facts.
- Copy every example and quote exactly as it appears in the transcript, as one short sentence.
- The transcript may come from speech recognition and contain errors. If a word looks like a \
recognition error, skip it instead of teaching it.
- Prefer what a learner at the given level would not know yet: idiomatic, colloquial and \
spoken French (familiar register, argot, verlan, dropped "ne", contractions), false friends, \
and words that are frequent in real conversations. Skip basic vocabulary and proper nouns.
- Write meanings and explanations in the learner's explanation language."""


def tool_schema() -> dict:
    vocab = {
        "type": "object",
        "properties": {
            "term": {"type": "string", "description": "Word as heard"},
            "lemma": {"type": "string", "description": "Dictionary form"},
            "pos": {"type": "string", "enum": ["noun", "verb", "adjective", "adverb", "other"]},
            "gender": {"type": "string", "enum": ["m", "f"], "description": "Nouns only"},
            "meaning": {"type": "string"},
            "example": {"type": "string", "description": "Exact sentence from the transcript"},
            "level": {"type": "string", "enum": LEVELS},
            "note": {"type": "string", "description": "Optional: false friend, register, usage tip"},
        },
        "required": ["term", "lemma", "pos", "meaning", "example", "level"],
    }
    expr = {
        "type": "object",
        "properties": {
            "expression": {"type": "string"},
            "meaning": {"type": "string"},
            "literal": {"type": "string", "description": "Literal translation, if it helps"},
            "register": {"type": "string", "enum": ["formal", "standard", "familiar", "slang"]},
            "example": {"type": "string", "description": "Exact sentence from the transcript"},
            "note": {"type": "string", "description": "Optional: origin, verlan, when to use it"},
        },
        "required": ["expression", "meaning", "register", "example"],
    }
    moment = {
        "type": "object",
        "properties": {
            "quote": {"type": "string", "description": "Short exact quote where the moment starts"},
            "summary": {"type": "string", "description": "What is said, in the explanation language"},
            "why_missed": {"type": "string", "description": "Why it is easy to miss: fast speech, slang, irony, a number..."},
        },
        "required": ["quote", "summary", "why_missed"],
    }
    question = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Comprehension question in French"},
            "answer": {"type": "string", "description": "Short answer in French"},
            "explanation": {"type": "string", "description": "Explanation in the explanation language"},
            "quote": {"type": "string", "description": "Exact quote from the transcript that contains the answer"},
        },
        "required": ["question", "answer", "explanation", "quote"],
    }
    return {
        "name": TOOL_NAME,
        "description": "Record the study notes for one block of the transcript.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gist": {"type": "string", "description": "What this block is about, 1 or 2 sentences"},
                "vocabulary": {"type": "array", "items": vocab, "maxItems": 12},
                "expressions": {"type": "array", "items": expr, "maxItems": 8},
                "moments": {"type": "array", "items": moment, "maxItems": 4},
                "questions": {"type": "array", "items": question, "maxItems": 2},
            },
            "required": ["gist", "vocabulary", "expressions", "moments", "questions"],
        },
    }


def build_prompt(chunk: Chunk, learner: Learner, title: str, known: list[str]) -> str:
    known_part = ""
    if known:
        known_part = "\nThe learner already studied these words, skip them: " + ", ".join(known[:300]) + "\n"
    interests = f"\nLearner interests: {learner.interests}" if learner.interests else ""
    return f"""Learner level: {learner.level}. Native language: {learner.native_language}. \
Explanation language: {learner.explain_in}.{interests}
{known_part}
Episode: {title}
Block {chunk.index + 1}. Lines start with [mm:ss] when timing is known.

<transcript>
{chunk.text}
</transcript>

Call {TOOL_NAME} with:
- gist: what this block is about
- vocabulary: up to 12 useful words for this learner
- expressions: up to 8 idioms or fixed expressions, including familiar and slang ones
- moments: up to 4 key passages a tired listener in a noisy metro would likely miss
- questions: 1 or 2 comprehension questions in French on the content of this block"""


class ExtractionError(RuntimeError):
    pass


class ReplayClient:
    """Drop-in for anthropic.Anthropic that replays recorded tool inputs (one per block).

    Used for the offline demo and tests: no API key, no network, same code path.
    """

    def __init__(self, recorded: list[dict]):
        self._recorded = list(recorded)
        self._lock = __import__("threading").Lock()
        self.messages = self

    def create(self, **_kwargs):
        from types import SimpleNamespace

        with self._lock:
            if not self._recorded:
                raise ExtractionError("Replay file has fewer blocks than the transcript")
            data = self._recorded.pop(0)
        block = SimpleNamespace(type="tool_use", id="toolu_replay", name=TOOL_NAME, input=data)
        return SimpleNamespace(content=[block], stop_reason="tool_use")


class ClaudeExtractor:
    def __init__(self, model: str, learner: Learner, client=None, max_retries: int = 1, max_tokens: int = 4096):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.learner = learner
        self.max_retries = max_retries
        self.max_tokens = max_tokens

    def notes_for_chunk(self, chunk: Chunk, title: str, known: list[str]) -> ChunkNotes:
        messages: list[dict] = [{"role": "user", "content": build_prompt(chunk, self.learner, title, known)}]
        error = "no tool call"
        for attempt in range(self.max_retries + 1):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM,
                tools=[tool_schema()],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=messages,
            )
            block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
            if block is not None:
                try:
                    return ChunkNotes.model_validate(dict(block.input))
                except ValidationError as exc:
                    error = str(exc)
                    # Give the model its own output and the validation error, ask for a corrected call
                    messages = messages + [
                        {"role": "assistant", "content": [{"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}]},
                        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                                      "content": f"Invalid fields: {error}. Call the tool again with corrected values."}]},
                    ]
        raise ExtractionError(f"Block {chunk.index + 1}: {error}")


# ---------- grounding ----------

def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^\w' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class _Index:
    """Normalized transcript with a map from character offset to segment start time."""
    text: str
    offsets: list[tuple[int, float | None, str]]  # (char offset, start, original segment text)

    @classmethod
    def build(cls, transcript: Transcript) -> "_Index":
        parts, offsets, pos = [], [], 0
        for seg in transcript.segments:
            n = norm(seg.text)
            offsets.append((pos, seg.start, seg.text))
            parts.append(n)
            pos += len(n) + 1
        return cls(" ".join(parts), offsets)

    def find(self, quote: str) -> tuple[float | None, str] | None:
        q = norm(quote)
        if len(q) < 2:
            return None
        i = self.text.find(q)
        if i < 0:
            return None
        start, original = None, ""
        for off, s, orig in self.offsets:
            if off > i:
                break
            start, original = s, orig
        return start, original


def ground(notes: list[ChunkNotes], transcript: Transcript) -> tuple[list[VocabItem], list[Expression], list[Moment], list[Question], int]:
    """Keep only items whose example is in the transcript; attach the real timestamp.

    If the example sentence was paraphrased but the word itself is in the transcript,
    the example is replaced with the real transcript segment instead of being trusted.
    """
    idx = _Index.build(transcript)
    vocab, exprs, moments, questions, dropped = [], [], [], [], 0

    def anchor(example: str, fallback: str):
        hit = idx.find(example)
        if hit:
            return hit[0], example
        hit = idx.find(fallback)
        if hit:
            return hit[0], hit[1]
        return None

    for n in notes:
        for v in n.vocabulary:
            a = anchor(v.example, v.term)
            if a is None:
                dropped += 1
                continue
            vocab.append(v.model_copy(update={"timestamp": a[0], "example": a[1]}))
        for e in n.expressions:
            a = anchor(e.example, e.expression)
            if a is None:
                dropped += 1
                continue
            exprs.append(e.model_copy(update={"timestamp": a[0], "example": a[1]}))
        for m in n.moments:
            hit = idx.find(m.quote)
            if hit is None:
                dropped += 1
                continue
            moments.append(m.model_copy(update={"timestamp": hit[0]}))
        for q in n.questions:
            hit = idx.find(q.quote)
            if hit is None:
                dropped += 1
                continue
            questions.append(q.model_copy(update={"timestamp": hit[0]}))
    return vocab, exprs, moments, questions, dropped


def dedupe(vocab: list[VocabItem], exprs: list[Expression], known: set[str]) -> tuple[list[VocabItem], list[Expression], int]:
    seen, out_v, out_e, skipped = set(), [], [], 0
    for v in vocab:
        key = norm(v.lemma)
        if key in known:
            skipped += 1
        elif key not in seen:
            seen.add(key)
            out_v.append(v)
    for e in exprs:
        key = norm(e.expression)
        if key in known:
            skipped += 1
        elif key not in seen:
            seen.add(key)
            out_e.append(e)
    return out_v, out_e, skipped


def build_notes(extractor, chunks: list[Chunk], transcript: Transcript, *, podcast: str, title: str,
                episode_key: str, known: set[str], max_vocab: int, max_expressions: int,
                published: str | None = None, link: str | None = None, audio_url: str | None = None,
                workers: int = 4, **extra) -> EpisodeNotes:
    known_list = sorted(known)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        chunk_notes = list(pool.map(lambda c: extractor.notes_for_chunk(c, title, known_list), chunks))

    vocab, exprs, moments, questions, dropped = ground(chunk_notes, transcript)
    vocab, exprs, already = dedupe(vocab, exprs, known)
    ends = [s.end or s.start for s in transcript.segments if s.start is not None]
    return EpisodeNotes(
        podcast=podcast, title=title, episode_key=episode_key, published=published, link=link, audio_url=audio_url,
        transcript_source=transcript.source, duration=max(ends) if ends else None,
        gist=[n.gist for n in chunk_notes],
        vocabulary=vocab[:max_vocab], expressions=exprs[:max_expressions],
        moments=sorted(moments, key=lambda m: (m.timestamp is None, m.timestamp or 0)),
        questions=questions, dropped=dropped, already_known=already, **extra,
    )
