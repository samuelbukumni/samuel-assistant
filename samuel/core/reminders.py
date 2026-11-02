"""Timers and reminders that survive a restart (stored as JSON).

Pure logic with an injectable clock, so it is unit-tested.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple


@dataclass
class Reminder:
    id: int
    due: float           # unix timestamp
    text: str
    kind: str = "reminder"   # "reminder" | "timer"
    created: float = 0.0


def next_clock_time(hour: int, minute: int, now: datetime) -> datetime:
    """The next occurrence of hh:mm after `now` (today or tomorrow)."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class ReminderBook:
    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.items: List[Reminder] = []
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = [Reminder(**r) for r in data]
        except (OSError, ValueError, TypeError):
            self.items = []

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps([asdict(r) for r in self.items], indent=1), encoding="utf-8")
        except OSError:
            pass

    def add_in(self, seconds: float, text: str, kind: str = "reminder") -> Reminder:
        return self._add(self.clock() + max(1.0, float(seconds)), text, kind)

    def add_at(self, hour: int, minute: int, text: str) -> Reminder:
        now = datetime.fromtimestamp(self.clock())
        return self._add(next_clock_time(hour, minute, now).timestamp(), text, "reminder")

    def _add(self, due: float, text: str, kind: str) -> Reminder:
        rid = max([r.id for r in self.items], default=0) + 1
        item = Reminder(id=rid, due=due, text=text, kind=kind, created=self.clock())
        self.items.append(item)
        self.items.sort(key=lambda r: r.due)
        self._save()
        return item

    def pop_due(self) -> List[Reminder]:
        now = self.clock()
        due = [r for r in self.items if r.due <= now]
        if due:
            self.items = [r for r in self.items if r.due > now]
            self._save()
        return due

    def upcoming(self, limit: int = 10) -> List[Reminder]:
        return sorted(self.items, key=lambda r: r.due)[:limit]

    def clear(self) -> int:
        n = len(self.items)
        self.items = []
        self._save()
        return n


def describe_due(due: float, now: float) -> Tuple[str, str]:
    """('in 5 minutes', '18:30') style strings for speech and display."""
    from samuel.core.telemetry import spoken_duration
    when = datetime.fromtimestamp(due).strftime("%H:%M")
    return f"in {spoken_duration(max(0, due - now))}", when
