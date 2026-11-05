from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
Register = Literal["formal", "standard", "familiar", "slang"]
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


class VocabItem(BaseModel):
    term: str = Field(min_length=1, description="Word as heard in the episode")
    lemma: str = Field(min_length=1, description="Dictionary form")
    pos: str = Field(description="noun, verb, adjective, adverb, other")
    gender: Literal["m", "f"] | None = None
    meaning: str = Field(min_length=1)
    example: str = Field(min_length=3, description="Exact sentence from the transcript")
    level: Level
    note: str | None = None
    timestamp: float | None = None  # set by us from the transcript, never by the model

    @field_validator("term", "lemma", "meaning", "example")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("gender", mode="before")
    @classmethod
    def _gender(cls, v):
        return v if v in ("m", "f") else None


class Expression(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    expression: str = Field(min_length=2)
    meaning: str = Field(min_length=1)
    literal: str | None = None
    reg: Register = Field(alias="register")  # "register" would shadow a BaseModel attribute
    example: str = Field(min_length=3)
    note: str | None = None
    timestamp: float | None = None

    @field_validator("expression", "meaning", "example")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class Moment(BaseModel):
    quote: str = Field(min_length=3, description="Short exact quote that anchors the moment")
    summary: str = Field(min_length=5)
    why_missed: str = Field(min_length=3)
    timestamp: float | None = None


class Question(BaseModel):
    question: str = Field(min_length=5, description="Comprehension question, in French")
    answer: str = Field(min_length=1, description="Short answer, in French")
    explanation: str = Field(min_length=3, description="Why, in the explanation language")
    quote: str = Field(min_length=3, description="Exact quote that contains the answer")
    timestamp: float | None = None


class ChunkNotes(BaseModel):
    gist: str = Field(min_length=5)
    vocabulary: list[VocabItem] = Field(default_factory=list, max_length=15)
    expressions: list[Expression] = Field(default_factory=list, max_length=10)
    moments: list[Moment] = Field(default_factory=list, max_length=5)
    questions: list[Question] = Field(default_factory=list, max_length=3)


class EpisodeNotes(BaseModel):
    podcast: str
    title: str
    episode_key: str
    published: str | None = None
    link: str | None = None
    audio_url: str | None = None
    transcript_source: str
    duration: float | None = None
    gist: list[str]
    vocabulary: list[VocabItem]
    expressions: list[Expression]
    moments: list[Moment]
    questions: list[Question] = Field(default_factory=list)
    listened_from: float | None = None  # seconds, when the lesson covers only part of the episode
    listened_to: float | None = None
    spotify_url: str | None = None
    dropped: int = 0  # items removed because their quote was not found in the transcript
    already_known: int = 0
