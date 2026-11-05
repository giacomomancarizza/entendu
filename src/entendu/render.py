"""Study sheet as Markdown (for GitHub, Notion) and as a self-contained HTML page readable on a phone."""
from __future__ import annotations

import html
import re

from .models import EpisodeNotes
from .transcript import fmt_ts

REGISTER_LABEL = {"formal": "soutenu", "standard": "courant", "familiar": "familier", "slang": "argot"}


def lesson_name(n: EpisodeNotes, day: str) -> str:
    """File name readable in Finder: '2026-11-05 French with Félix, Titre de l'épisode'."""
    clean = lambda t: re.sub(r'[\\/:*?"<>|]+', " ", t).strip()
    return f"{day} {clean(n.podcast)}, {clean(n.title)}"[:120]


def slug(text: str) -> str:
    text = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return text[:60] or "episode"


def _ts_md(ts: float | None) -> str:
    return f"`{fmt_ts(ts)}` " if ts is not None else ""


def _meta(n: EpisodeNotes) -> list[str]:
    listened = None
    if n.listened_from is not None and n.listened_to is not None:
        listened = f"ascoltato dal {fmt_ts(n.listened_from)} al {fmt_ts(n.listened_to)}"
    return [m for m in [
        n.published and n.published[:10],
        listened or (n.duration and f"{int(n.duration // 60)} min"),
        f"transcript: {n.transcript_source}",
    ] if m]


def to_markdown(n: EpisodeNotes) -> str:
    out = [f"# {n.podcast}: {n.title}", ""]
    meta = _meta(n)
    out += [" · ".join(meta), "", "## En bref", ""]
    out += [f"- {g}" for g in n.gist] + [""]

    if n.moments:
        out += ["## Ce que tu as pu rater", ""]
        for m in n.moments:
            out.append(f"- {_ts_md(m.timestamp)}**{m.summary}**  ")
            out.append(f"  > {m.quote}  ")
            out.append(f"  _{m.why_missed}_")
        out.append("")

    if n.expressions:
        out += ["## Expressions", ""]
        for e in n.expressions:
            lit = f" (lett. _{e.literal}_)" if e.literal else ""
            out.append(f"- **{e.expression}** [{REGISTER_LABEL[e.reg]}]: {e.meaning}{lit}  ")
            out.append(f"  {_ts_md(e.timestamp)}_{e.example}_" + (f"  \n  {e.note}" if e.note else ""))
        out.append("")

    if n.vocabulary:
        out += ["## Vocabulaire", "", "| Mot | Sens | Entendu | Niveau |", "|---|---|---|---|"]
        for v in n.vocabulary:
            word = f"**{v.lemma}**" + (f" ({v.gender})" if v.gender else "") + f" _{v.pos}_"
            meaning = v.meaning + (f" ({v.note})" if v.note else "")
            heard = f"{_ts_md(v.timestamp)}{v.example}".replace("|", "/")
            out.append(f"| {word} | {meaning} | {heard} | {v.level} |")
        out.append("")

    if n.questions:
        out += ["## Vérifie ta compréhension", ""]
        for i, q in enumerate(n.questions, start=1):
            out.append(f"{i}. {q.question}")
            out.append(f"   <details><summary>Réponse</summary>{q.answer}. {q.explanation} "
                       f"{'(' + fmt_ts(q.timestamp) + ') ' if q.timestamp is not None else ''}<i>« {q.quote} »</i></details>")
        out.append("")

    out.append(f"<sub>{len(n.vocabulary)} words, {len(n.expressions)} expressions. "
               f"{n.already_known} already known and skipped, {n.dropped} dropped because not found in the transcript.</sub>")
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#faf8f4;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e6e2da;--accent:#1f3a5f;--chip:#eef2f7;--warm:#b4532a}
@media (prefers-color-scheme:dark){:root{--bg:#15161a;--card:#1e2025;--ink:#ececf0;--muted:#a0a0a8;--line:#30323a;--accent:#8fb3e0;--chip:#262a33;--warm:#e89a72}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:28px 16px 48px}
header .kicker{color:var(--warm);font-weight:600;font-size:13px;letter-spacing:.06em;text-transform:uppercase}
h1{font-size:24px;line-height:1.25;margin:6px 0 6px}.meta{color:var(--muted);font-size:14px}
h2{font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin:34px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
ul.gist{padding-left:18px;margin:0}ul.gist li{margin:4px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}
.top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.term{font-weight:700;font-size:17px}
.ts{font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);background:var(--chip);border-radius:6px;padding:2px 6px;text-decoration:none}
.chip{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 8px}
.chip.slang,.chip.familiar{color:var(--warm);border-color:var(--warm)}
.meaning{margin:6px 0 4px}.quote{color:var(--muted);font-style:italic;margin:0}.note{font-size:14px;color:var(--muted);margin:6px 0 0}
.why{font-size:14px;color:var(--warm);margin:6px 0 0}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent);font-size:14px;font-weight:600}
footer{margin-top:36px;font-size:13px;color:var(--muted)}
"""


def _ts_html(ts: float | None, audio: str | None) -> str:
    if ts is None:
        return ""
    label = html.escape(fmt_ts(ts))
    if audio:
        # Media fragments: most mobile browsers open the audio file at this second
        return f'<a class="ts" href="{html.escape(audio)}#t={int(ts)}">{label}</a>'
    return f'<span class="ts">{label}</span>'


def to_html(n: EpisodeNotes) -> str:
    e_ = html.escape
    meta = " · ".join(_meta(n))
    parts = [f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e_(n.title)}</title><style>{CSS}</style></head>
<body><main><header><div class="kicker">{e_(n.podcast)}</div><h1>{e_(n.title)}</h1><div class="meta">{e_(meta)}</div></header>
<h2>En bref</h2><ul class="gist">{''.join(f'<li>{e_(g)}</li>' for g in n.gist)}</ul>"""]

    if n.moments:
        parts.append("<h2>Ce que tu as pu rater</h2>")
        for m in n.moments:
            parts.append(f'<div class="card"><div class="top">{_ts_html(m.timestamp, n.audio_url)}'
                         f'<span class="term">{e_(m.summary)}</span></div>'
                         f'<p class="quote">« {e_(m.quote)} »</p><p class="why">{e_(m.why_missed)}</p></div>')

    if n.expressions:
        parts.append("<h2>Expressions</h2>")
        for x in n.expressions:
            lit = f'<p class="note">Lett.: {e_(x.literal)}</p>' if x.literal else ""
            note = f'<p class="note">{e_(x.note)}</p>' if x.note else ""
            parts.append(f'<div class="card"><div class="top"><span class="term">{e_(x.expression)}</span>'
                         f'<span class="chip {x.reg}">{REGISTER_LABEL[x.reg]}</span>{_ts_html(x.timestamp, n.audio_url)}</div>'
                         f'<p class="meaning">{e_(x.meaning)}</p><p class="quote">« {e_(x.example)} »</p>{lit}{note}</div>')

    if n.vocabulary:
        parts.append("<h2>Vocabulaire</h2>")
        for v in n.vocabulary:
            g = f" ({v.gender})" if v.gender else ""
            note = f'<p class="note">{e_(v.note)}</p>' if v.note else ""
            parts.append(f'<div class="card"><div class="top"><span class="term">{e_(v.lemma)}{g}</span>'
                         f'<span class="chip">{e_(v.pos)}</span><span class="chip">{v.level}</span>{_ts_html(v.timestamp, n.audio_url)}</div>'
                         f'<p class="meaning">{e_(v.meaning)}</p><p class="quote">« {e_(v.example)} »</p>{note}</div>')

    if n.questions:
        parts.append("<h2>Vérifie ta compréhension</h2>")
        for i, q in enumerate(n.questions, start=1):
            parts.append(f'<div class="card"><div class="top"><span class="term">{i}. {e_(q.question)}</span></div>'
                         f'<details><summary>Réponse</summary><p class="meaning">{e_(q.answer)}. {e_(q.explanation)}</p>'
                         f'<p class="quote">{_ts_html(q.timestamp, n.audio_url)} « {e_(q.quote)} »</p></details></div>')

    parts.append(f"<footer>{len(n.vocabulary)} mots, {len(n.expressions)} expressions. "
                 f"{n.already_known} déjà connus, {n.dropped} écartés car introuvables dans la transcription.</footer>"
                 "</main></body></html>")
    return "\n".join(parts)
