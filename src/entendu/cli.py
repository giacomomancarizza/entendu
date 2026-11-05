"""Command line: entendu lesson | process | episodes | anki | stats."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import date
from pathlib import Path

from .config import Podcast, load_config
from .extract import ClaudeExtractor, ReplayClient, build_notes
from .render import lesson_name, slug, to_html, to_markdown
from .store import Store
from .transcript import chunk_transcript, load_transcript, parse_transcript


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def cmd_episodes(cfg, args) -> int:
    from .feeds import list_episodes

    for i, ep in enumerate(list_episodes(cfg.podcast(args.podcast), limit=args.limit), start=1):
        day = ep.published.date().isoformat() if ep.published else "????-??-??"
        has_t = "transcript" if ep.transcript_url else "audio only"
        print(f"{i:>2}. {day}  {ep.title}  [{has_t}]")
    return 0


def _get_transcript(cfg, args):
    """Returns (transcript, title, podcast name, episode key, published, link, audio_url)."""
    if args.transcript:
        t = load_transcript(args.transcript)
        title = args.title or Path(args.transcript).stem
        podcast = args.podcast or "Podcast"
        key = hashlib.sha1(Path(args.transcript).read_bytes()).hexdigest()[:16]
        return t, title, podcast, key, None, None, None

    if args.audio:
        from .transcribe import transcribe_audio

        print(f"Transcribing {args.audio} with Whisper ({cfg.whisper_model}), this takes a few minutes...")
        t = transcribe_audio(Path(args.audio), cfg.whisper_model)
        key = hashlib.sha1(Path(args.audio).read_bytes()[:1 << 20]).hexdigest()[:16]
        return t, args.title or Path(args.audio).stem, args.podcast or "Podcast", key, None, None, None

    if not args.podcast:
        raise SystemExit("Give a podcast name from config.yaml, or --transcript / --audio")
    from .feeds import download, fetch_text, list_episodes

    podcast: Podcast = cfg.podcast(args.podcast)
    episodes = list_episodes(podcast, limit=max(args.episode, 1))
    if len(episodes) < args.episode:
        raise SystemExit(f"Only {len(episodes)} episodes in the feed")
    ep = episodes[args.episode - 1]
    print(f"{podcast.name}: {ep.title}")
    published = ep.published.isoformat() if ep.published else None

    if ep.transcript_url:
        print("Using the publisher's transcript")
        t = parse_transcript(fetch_text(ep.transcript_url), ep.transcript_type or ep.transcript_url.rsplit(".", 1)[-1], "publisher")
    else:
        if not ep.audio_url:
            raise SystemExit("This episode has neither audio nor transcript in the feed")
        from .transcribe import transcribe_audio

        ext = ep.audio_url.split("?")[0].rsplit(".", 1)[-1][:4] or "mp3"
        audio = download(ep.audio_url, cfg.cache_dir / f"{ep.key}.{ext}")
        print(f"Transcribing with Whisper ({cfg.whisper_model}), this takes a few minutes...")
        t = transcribe_audio(audio, cfg.whisper_model)
    return t, ep.title, podcast.name, ep.key, published, ep.link, ep.audio_url


def _analyze(cfg, args, store: Store, transcript, *, podcast: str, title: str, key: str, **meta):
    """Transcript -> Claude -> grounded notes, saved in the database."""
    known = set() if args.include_known else store.known_keys()
    minutes = args.chunk_minutes or cfg.chunk_minutes
    chunks = chunk_transcript(transcript, minutes)
    if args.replay:
        import json

        recorded = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        extractor = ClaudeExtractor("replay", cfg.learner, client=ReplayClient(recorded))
        print(f"Replaying {len(recorded)} recorded responses (no API call)")
    else:
        extractor = ClaudeExtractor(cfg.model, cfg.learner)
        print(f"Analysing {len(chunks)} blocks with {cfg.model}...")
    notes = build_notes(extractor, chunks, transcript, podcast=podcast, title=title, episode_key=key,
                        known=known, max_vocab=cfg.max_vocab, max_expressions=cfg.max_expressions, **meta)
    added = store.save(notes)
    print(f"{len(notes.vocabulary)} words, {len(notes.expressions)} expressions, {len(notes.moments)} moments, "
          f"{len(notes.questions)} questions ({added} new in your deck, {notes.already_known} already known, "
          f"{notes.dropped} dropped as ungrounded)")
    return notes


def _write(notes, folder: Path, name: str) -> tuple[Path, str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    html_sheet, md_sheet = to_html(notes), to_markdown(notes)
    (folder / f"{name}.md").write_text(md_sheet, encoding="utf-8")
    html_path = folder / f"{name}.html"
    html_path.write_text(html_sheet, encoding="utf-8")
    return html_path, html_sheet, md_sheet


def _send(args, notes, html_sheet: str, md_sheet: str) -> None:
    if not getattr(args, "send", False):
        return
    from .notify import build_payload, send_to_make

    url = os.getenv("MAKE_WEBHOOK_URL")
    if not url:
        print("MAKE_WEBHOOK_URL is not set, skipping send", file=sys.stderr)
        return
    send_to_make(url, build_payload(notes, html_sheet, md_sheet))
    print("Sent to Make.com")


def cmd_process(cfg, args) -> int:
    store = Store(cfg.db_path)
    transcript, title, podcast, key, published, link, audio_url = _get_transcript(cfg, args)
    if store.is_processed(key) and not args.force:
        print("Episode already processed (use --force to redo it)")
        notes = store.episode_notes(key)
    else:
        notes = _analyze(cfg, args, store, transcript, podcast=podcast, title=title, key=key,
                         published=published, link=link, audio_url=audio_url)
    day = (notes.published or date.today().isoformat())[:10]
    html_path, html_sheet, md_sheet = _write(notes, cfg.output_dir, f"{day}-{slug(notes.title)}")
    print(f"Study sheet: {html_path}")
    _send(args, notes, html_sheet, md_sheet)
    return 0


def cmd_lesson(cfg, args) -> int:
    """The button: find what I just listened to on Spotify and turn that part into a lesson."""
    from .config import Podcast
    from .feeds import download, fetch_text, list_episodes
    from .macos import choose, notify, open_file
    from .match import find_feed, match_episode
    from .spotify import connect, in_player, listened_range, pick_episode, started_episodes
    from .transcript import Transcript, fmt_ts

    store = Store(cfg.db_path)

    # 1. Spotify: which episode, which part
    sp = connect(cfg.spotify_token)
    snapshot = store.positions()
    candidates = started_episodes(sp)
    ep = pick_episode(in_player(sp), candidates, snapshot, choose)
    if ep is None:
        print("Nessun episodio di podcast trovato su Spotify")
        return 1
    start_ms, end_ms = listened_range(ep, snapshot.get(ep.episode_id), cfg.window_minutes)
    print(f"Episodio: {ep.show}: {ep.title}")
    print(f"Tratto ascoltato: dal {fmt_ts(start_ms / 1000)} al {fmt_ts(end_ms / 1000)} (da: {ep.source})")

    # 2. The same episode in the public RSS feed
    feed = find_feed(ep.show, cfg.feed_overrides)
    if not feed:
        raise RuntimeError(f"Feed RSS non trovato per '{ep.show}': aggiungilo in config.yaml sotto podcasts")
    rss_ep = match_episode(list_episodes(Podcast(ep.show, feed), limit=60), ep.title, ep.release_date)
    if rss_ep is None:
        raise RuntimeError(f"'{ep.title}' non trovato nel feed {feed}")
    print(f"Nel feed RSS: {rss_ep.title} ({'trascrizione' if rss_ep.transcript_url else 'audio'})")
    if args.dry_run:
        print("Prova a secco: mi fermo prima di scaricare e trascrivere")
        return 0

    # 3. Transcript of that part only
    pad = cfg.pad_seconds
    if rss_ep.transcript_url:
        full = parse_transcript(fetch_text(rss_ep.transcript_url),
                                rss_ep.transcript_type or rss_ep.transcript_url.rsplit(".", 1)[-1], "publisher")
        lo, hi = start_ms / 1000 - pad, end_ms / 1000 + pad
        transcript = Transcript([s for s in full.segments if s.start is None or lo <= s.start <= hi], "publisher")
    else:
        if not rss_ep.audio_url:
            raise RuntimeError("Nel feed non c'è né audio né trascrizione per questo episodio")
        from .audio import cut
        from .transcribe import transcribe_audio

        ext = rss_ep.audio_url.split("?")[0].rsplit(".", 1)[-1][:4] or "mp3"
        audio = download(rss_ep.audio_url, cfg.cache_dir / f"{rss_ep.key}.{ext}")
        part = cfg.cache_dir / f"{rss_ep.key}-{start_ms // 1000}-{end_ms // 1000}.wav"
        offset = cut(audio, part, start_ms, end_ms, pad)
        notify("Trascrizione in corso, qualche minuto...")
        transcript = transcribe_audio(part, cfg.whisper_model, offset=offset)

    # 4. Lesson
    key = f"{ep.episode_id}-{start_ms // 1000}-{end_ms // 1000}"
    notes = _analyze(cfg, args, store, transcript, podcast=ep.show, title=ep.title, key=key,
                     published=ep.release_date, audio_url=rss_ep.audio_url, spotify_url=ep.url,
                     listened_from=start_ms / 1000, listened_to=end_ms / 1000)
    positions = {c.episode_id: c.position_ms for c in candidates}
    positions[ep.episode_id] = ep.duration_ms if ep.fully_played else ep.position_ms
    store.save_positions(positions)

    # 5. Save in the lessons folder and open it
    html_path, html_sheet, md_sheet = _write(notes, cfg.lessons_dir, lesson_name(notes, date.today().isoformat()))
    print(f"Lezione: {html_path}")
    notify(f"Lezione pronta: {ep.title}")
    _send(args, notes, html_sheet, md_sheet)
    if not args.no_open:
        open_file(html_path)
    return 0


def cmd_anki(cfg, args) -> int:
    from .anki import export_anki

    store = Store(cfg.db_path)
    rows = store.items(only_new=not args.all)
    if not rows:
        print("Nothing new to export")
        return 0
    out = Path(args.output or f"anki-{date.today().isoformat()}.txt")
    n = export_anki(rows, out)
    if not args.all:
        store.mark_exported([r["key"] for r in rows])
    print(f"{n} cards written to {out}. In Anki: File > Import, pick the file.")
    return 0


def cmd_stats(cfg, args) -> int:
    for k, v in Store(cfg.db_path).stats().items():
        print(f"{k:>14}: {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="entendu", description="Study notes from the French podcasts you listen to.")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("episodes", help="List the latest episodes of a podcast")
    e.add_argument("podcast")
    e.add_argument("-n", "--limit", type=int, default=10)

    pr = sub.add_parser("process", help="Build the study sheet for one episode")
    pr.add_argument("podcast", nargs="?", help="Podcast name from config.yaml")
    pr.add_argument("-e", "--episode", type=int, default=1, help="1 = latest episode (see 'entendu episodes')")
    pr.add_argument("--transcript", help="Use a transcript file (.vtt, .srt, .json, .txt) instead of the feed")
    pr.add_argument("--audio", help="Transcribe a local audio file with Whisper")
    pr.add_argument("--title", help="Episode title when using --transcript or --audio")
    pr.add_argument("--send", action="store_true", help="Send the sheet to MAKE_WEBHOOK_URL")
    pr.add_argument("--include-known", action="store_true", help="Do not skip words you already studied")
    pr.add_argument("--force", action="store_true", help="Process again even if already done")
    pr.add_argument("--chunk-minutes", type=float, help="Override chunk_minutes from config.yaml")
    pr.add_argument("--replay", help="Replay recorded model responses from a JSON file (offline demo)")

    le = sub.add_parser("lesson", help="The button: lesson from what you just listened to on Spotify")
    le.add_argument("--dry-run", action="store_true", help="Only show episode, part and feed match")
    le.add_argument("--no-open", action="store_true", help="Do not open the lesson when done")
    le.add_argument("--send", action="store_true", help="Also send it to MAKE_WEBHOOK_URL")
    le.add_argument("--include-known", action="store_true")
    le.add_argument("--chunk-minutes", type=float)
    le.add_argument("--replay", help=argparse.SUPPRESS)

    a = sub.add_parser("anki", help="Export new words and expressions for Anki")
    a.add_argument("-o", "--output")
    a.add_argument("--all", action="store_true", help="Export everything, not only new items")

    sub.add_parser("stats", help="What you have studied so far")

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    handlers = {"episodes": cmd_episodes, "process": cmd_process, "lesson": cmd_lesson,
                "anki": cmd_anki, "stats": cmd_stats}
    try:
        return handlers[args.cmd](cfg, args)
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
    except Exception as exc:  # friendly messages for the errors a user can fix
        name = type(exc).__name__
        if name == "AuthenticationError" or "authentication" in str(exc).lower():
            print("Claude API key missing or invalid: set ANTHROPIC_API_KEY in .env", file=sys.stderr)
        elif name in ("RuntimeError", "ExtractionError", "ValueError", "HTTPStatusError", "ConnectError",
                      "SpotifyException", "SpotifyOauthError"):
            print(f"{name}: {exc}", file=sys.stderr)
            if args.cmd == "lesson":
                from .macos import notify

                notify(f"Errore: {exc}"[:200])
        else:
            raise
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
