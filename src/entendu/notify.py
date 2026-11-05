"""Send the study sheet to a Make.com custom webhook (Make then emails it, saves it to Notion, etc.)."""
from __future__ import annotations

import httpx

from .models import EpisodeNotes


def build_payload(notes: EpisodeNotes, html_sheet: str, markdown_sheet: str) -> dict:
    return {
        "subject": f"Entendu: {notes.podcast}, {notes.title}",
        "podcast": notes.podcast,
        "episode": notes.title,
        "published": notes.published,
        "counts": {
            "words": len(notes.vocabulary),
            "expressions": len(notes.expressions),
            "moments": len(notes.moments),
        },
        "html": html_sheet,
        "markdown": markdown_sheet,
        "items": [
            {"kind": "word", "text": v.lemma, "meaning": v.meaning, "example": v.example} for v in notes.vocabulary
        ] + [
            {"kind": "expression", "text": e.expression, "meaning": e.meaning, "example": e.example} for e in notes.expressions
        ],
    }


def send_to_make(url: str, payload: dict) -> None:
    r = httpx.post(url, json=payload, timeout=30)
    r.raise_for_status()
