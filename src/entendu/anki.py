"""Export studied items as an Anki import file (tab separated, with Anki's file headers)."""
from __future__ import annotations

import html
import re
from pathlib import Path

from .transcript import fmt_ts


def _highlight(example: str, term: str) -> str:
    """Bold the studied word in the sentence, even when it is conjugated or shortened."""
    safe = html.escape(example)
    words = term.split(" (")[0].split()
    candidates = [" ".join(words[i:]) for i in range(len(words) - 1)]  # "avoir du pain..." then "du pain..."
    candidates = [c for c in candidates if len(c.split()) >= 2] or []
    if len(words) == 1:
        stem = words[0][: max(3, len(words[0]) - 2)]  # bosser -> boss, matches "bossé"
        candidates = [words[0], stem]
    for c in candidates:
        pattern = r"\b" + re.escape(html.escape(c)) + (r"\w*" if len(words) == 1 else "")
        new, n = re.subn(pattern, lambda m: f"<b>{m.group(0)}</b>", safe, count=1, flags=re.IGNORECASE)
        if n:
            return new
    return safe


def export_anki(rows, path: Path) -> int:
    """Front: the word or expression plus the sentence heard. Back: meaning, note, source."""
    lines = ["#separator:tab", "#html:true", "#tags column:3"]
    for r in rows:
        front = f"{html.escape(r['display'])}<br><br><i>{_highlight(r['example'], r['display'])}</i>"
        back_parts = [html.escape(r["meaning"])]
        if r["note"]:
            back_parts.append(f"<small>{html.escape(r['note'])}</small>")
        where = f"{r['podcast']}: {r['episode_title']}"
        if r["timestamp"] is not None:
            where += f" ({fmt_ts(r['timestamp'])})"
        back_parts.append(f"<small>{html.escape(where)}</small>")
        tags = ["entendu", r["kind"], re.sub(r"\W+", "_", r["podcast"] or "").strip("_").lower()]
        if r["register"] in ("familiar", "slang"):
            tags.append(r["register"])
        row = [front, "<br>".join(back_parts), " ".join(t for t in tags if t)]
        lines.append("\t".join(c.replace("\t", " ").replace("\n", " ") for c in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 3
