"""SQLite memory: processed episodes and every word or expression already studied."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .extract import norm
from .models import EpisodeNotes

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    key TEXT PRIMARY KEY,
    podcast TEXT NOT NULL,
    title TEXT NOT NULL,
    published TEXT,
    processed_at TEXT NOT NULL,
    transcript_source TEXT,
    notes_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    key TEXT PRIMARY KEY,               -- normalized lemma or expression
    kind TEXT NOT NULL,                 -- 'word' or 'expression'
    display TEXT NOT NULL,
    meaning TEXT NOT NULL,
    example TEXT NOT NULL,
    note TEXT,
    level TEXT,
    register TEXT,
    podcast TEXT,
    episode_key TEXT,
    episode_title TEXT,
    timestamp REAL,
    first_seen TEXT NOT NULL,
    exported INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS positions (  -- Spotify resume points seen at the last run
    episode_id TEXT PRIMARY KEY,
    position_ms INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def known_keys(self) -> set[str]:
        return {r["key"] for r in self.db.execute("SELECT key FROM items")}

    def is_processed(self, key: str) -> bool:
        return self.db.execute("SELECT 1 FROM episodes WHERE key = ?", (key,)).fetchone() is not None

    def save(self, notes: EpisodeNotes) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for v in notes.vocabulary:
            display = f"{v.lemma} ({v.gender})" if v.gender else v.lemma
            rows.append((norm(v.lemma), "word", display, v.meaning, v.example, v.note, v.level, None, v.timestamp))
        for e in notes.expressions:
            rows.append((norm(e.expression), "expression", e.expression, e.meaning, e.example, e.note, None, e.reg, e.timestamp))
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?,?,?)",
                (notes.episode_key, notes.podcast, notes.title, notes.published, now,
                 notes.transcript_source, notes.model_dump_json()),
            )
            cur = self.db.executemany(
                "INSERT OR IGNORE INTO items (key, kind, display, meaning, example, note, level, register, timestamp, "
                "podcast, episode_key, episode_title, first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [r + (notes.podcast, notes.episode_key, notes.title, now) for r in rows],
            )
        return cur.rowcount

    def items(self, only_new: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM items" + (" WHERE exported = 0" if only_new else "") + " ORDER BY first_seen, kind"
        return list(self.db.execute(sql))

    def mark_exported(self, keys: list[str]) -> None:
        with self.db:
            self.db.executemany("UPDATE items SET exported = 1 WHERE key = ?", [(k,) for k in keys])

    def stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]
        return {
            "episodes": q("SELECT COUNT(*) FROM episodes"),
            "words": q("SELECT COUNT(*) FROM items WHERE kind = 'word'"),
            "expressions": q("SELECT COUNT(*) FROM items WHERE kind = 'expression'"),
            "not_exported": q("SELECT COUNT(*) FROM items WHERE exported = 0"),
        }

    def positions(self) -> dict[str, int]:
        return {r["episode_id"]: r["position_ms"] for r in self.db.execute("SELECT * FROM positions")}

    def save_positions(self, positions: dict[str, int]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO positions VALUES (?,?,?)",
                                [(k, v, now) for k, v in positions.items()])

    def episode_notes(self, key: str) -> EpisodeNotes | None:
        row = self.db.execute("SELECT notes_json FROM episodes WHERE key = ?", (key,)).fetchone()
        return EpisodeNotes.model_validate(json.loads(row[0])) if row else None
