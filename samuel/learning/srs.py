"""SuperMemo SM-2 spaced repetition, as published by Piotr Wozniak.

Source: https://www.super-memory.com/english/ol/sm2.htm and the original
Pascal code at https://super-memory.org/archive/english/ol/sm2source.htm

    quality q: 0..5 (5 perfect, 4 hesitation, 3 hard, <3 failed)
    I(1) = 1 day, I(2) = 6 days, I(n) = I(n-1) * EF  (fractions rounded up)
    EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02)), never below 1.3
    q < 3 restarts the repetitions (interval back to 1 day)

Like the original source code, EF is updated after every grade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

MIN_EF = 1.3
START_EF = 2.5
MASTERED_INTERVAL = 21   # days; a card this far apart counts as "mastered"


@dataclass(frozen=True)
class SrsState:
    repetitions: int = 0
    interval: int = 0      # days
    ef: float = START_EF


def review(state: SrsState, quality: int) -> SrsState:
    """Return the new state after grading a card with quality 0..5."""
    if not 0 <= int(quality) <= 5:
        raise ValueError("quality must be between 0 and 5")
    q = int(quality)
    if q >= 3:
        if state.repetitions == 0:
            interval = 1
        elif state.repetitions == 1:
            interval = 6
        else:
            interval = int(math.ceil(state.interval * state.ef))
        repetitions = state.repetitions + 1
    else:
        repetitions = 0
        interval = 1
    ef = state.ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return SrsState(repetitions, interval, max(MIN_EF, round(ef, 4)))


def due_date(today: date, state: SrsState) -> date:
    return today + timedelta(days=state.interval)


def streak(active_days, today: date) -> int:
    """Consecutive days with activity ending today (or yesterday, so the
    streak survives until you study today)."""
    days = set(active_days)
    start = today if today in days else today - timedelta(days=1)
    count = 0
    while start in days:
        count += 1
        start -= timedelta(days=1)
    return count
