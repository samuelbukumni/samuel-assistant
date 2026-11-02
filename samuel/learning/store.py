"""Learning progress in SQLite (Python stdlib, no extra dependency).

Tables
------
lessons   one row per topic you studied, with its text cached so you can
          revise offline later
cards     flashcards with their SM-2 state and due date
reviews   every grade you gave (used for the streak and "today" counters)

A Store must be used from a single thread (the brain's worker thread).
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from samuel.learning import srs
from samuel.learning.lessons import Card, Lesson

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL UNIQUE,
    description TEXT,
    summary TEXT NOT NULL,
    url TEXT,
    points TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'cloze',
    repetitions INTEGER NOT NULL DEFAULT 0,
    interval INTEGER NOT NULL DEFAULT 0,
    ef REAL NOT NULL DEFAULT 2.5,
    due TEXT NOT NULL,
    lapses INTEGER NOT NULL DEFAULT 0,
    UNIQUE(lesson_id, front)
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    card_id INTEGER,
    ts REAL NOT NULL,
    day TEXT NOT NULL,
    quality INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'card'
);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due);
CREATE INDEX IF NOT EXISTS idx_reviews_day ON reviews(day);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ── lessons ─────────────────────────────────────────────────────
    def save_lesson(self, lesson: Lesson, cards: List[Card], today: Optional[date] = None) -> int:
        today = today or date.today()
        now = time.time()
        row = self.db.execute("SELECT id FROM lessons WHERE title = ?", (lesson.title,)).fetchone()
        if row:
            lesson_id = row["id"]
            self.db.execute(
                "UPDATE lessons SET topic=?, description=?, summary=?, url=?, points=?, updated=? WHERE id=?",
                (lesson.topic, lesson.description, lesson.summary, lesson.url,
                 json.dumps(lesson.points), now, lesson_id))
        else:
            cur = self.db.execute(
                "INSERT INTO lessons (topic, title, description, summary, url, points, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lesson.topic, lesson.title, lesson.description, lesson.summary, lesson.url,
                 json.dumps(lesson.points), now, now))
            lesson_id = cur.lastrowid
        for card in cards:
            self.db.execute(
                "INSERT OR IGNORE INTO cards (lesson_id, front, back, kind, due) VALUES (?, ?, ?, ?, ?)",
                (lesson_id, card.front, card.back, card.kind, today.isoformat()))
        self.db.commit()
        return lesson_id

    def find_lesson(self, topic: str) -> Optional[sqlite3.Row]:
        t = (topic or "").strip().lower()
        if not t:
            return None
        return self.db.execute(
            "SELECT * FROM lessons WHERE lower(topic) = ? OR lower(title) = ? ORDER BY updated DESC LIMIT 1",
            (t, t)).fetchone()

    def latest_lesson(self) -> Optional[sqlite3.Row]:
        return self.db.execute("SELECT * FROM lessons ORDER BY updated DESC LIMIT 1").fetchone()

    def lesson_by_id(self, lesson_id: int) -> Optional[sqlite3.Row]:
        return self.db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()

    def set_position(self, lesson_id: int, position: int) -> None:
        self.db.execute("UPDATE lessons SET position = ?, updated = ? WHERE id = ?",
                        (position, time.time(), lesson_id))
        self.db.commit()

    @staticmethod
    def as_lesson(row: sqlite3.Row) -> Lesson:
        return Lesson(topic=row["topic"], title=row["title"], description=row["description"] or "",
                      summary=row["summary"], url=row["url"] or "", points=json.loads(row["points"]))

    def all_terms(self, exclude_lesson: Optional[int] = None) -> List[str]:
        rows = self.db.execute("SELECT back FROM cards WHERE kind = 'cloze' AND (? IS NULL OR lesson_id != ?)",
                               (exclude_lesson, exclude_lesson)).fetchall()
        return [r["back"] for r in rows]

    # ── cards ───────────────────────────────────────────────────────
    def due_cards(self, today: Optional[date] = None, limit: int = 20) -> List[sqlite3.Row]:
        today = today or date.today()
        return self.db.execute(
            "SELECT cards.*, lessons.title AS lesson_title FROM cards JOIN lessons ON lessons.id = cards.lesson_id"
            " WHERE due <= ? ORDER BY due, cards.id LIMIT ?", (today.isoformat(), limit)).fetchall()

    def grade_card(self, card_id: int, quality: int, today: Optional[date] = None) -> srs.SrsState:
        today = today or date.today()
        row = self.db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            raise KeyError(card_id)
        state = srs.review(srs.SrsState(row["repetitions"], row["interval"], row["ef"]), quality)
        lapses = row["lapses"] + (1 if quality < 3 else 0)
        self.db.execute(
            "UPDATE cards SET repetitions=?, interval=?, ef=?, due=?, lapses=? WHERE id=?",
            (state.repetitions, state.interval, state.ef, srs.due_date(today, state).isoformat(),
             lapses, card_id))
        self.log_activity(quality, card_id=card_id, today=today)
        return state

    def log_activity(self, quality: int, card_id: Optional[int] = None, source: str = "card",
                     today: Optional[date] = None) -> None:
        today = today or date.today()
        self.db.execute("INSERT INTO reviews (card_id, ts, day, quality, source) VALUES (?, ?, ?, ?, ?)",
                        (card_id, time.time(), today.isoformat(), int(quality), source))
        self.db.commit()

    # ── progress ────────────────────────────────────────────────────
    def stats(self, today: Optional[date] = None) -> Dict:
        today = today or date.today()
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]   # noqa: E731
        days = [date.fromisoformat(r["day"]) for r in
                self.db.execute("SELECT DISTINCT day FROM reviews").fetchall()]
        week = [(today.toordinal() - d.toordinal()) for d in days]
        last7 = [any(w == i for w in week) for i in range(6, -1, -1)]   # oldest → today
        latest = self.latest_lesson()
        return {
            "lessons": q("SELECT COUNT(*) FROM lessons"),
            "cards": q("SELECT COUNT(*) FROM cards"),
            "due": q("SELECT COUNT(*) FROM cards WHERE due <= ?", today.isoformat()),
            "mastered": q("SELECT COUNT(*) FROM cards WHERE interval >= ?", srs.MASTERED_INTERVAL),
            "learning": q("SELECT COUNT(*) FROM cards WHERE repetitions > 0 AND interval < ?", srs.MASTERED_INTERVAL),
            "reviews_today": q("SELECT COUNT(*) FROM reviews WHERE day = ?", today.isoformat()),
            "correct_today": q("SELECT COUNT(*) FROM reviews WHERE day = ? AND quality >= 3", today.isoformat()),
            "streak": srs.streak(days, today),
            "last7": last7,
            "latest_title": latest["title"] if latest else "",
            "latest_position": latest["position"] if latest else 0,
            "latest_points": len(json.loads(latest["points"])) if latest else 0,
        }

    def close(self) -> None:
        self.db.close()


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
