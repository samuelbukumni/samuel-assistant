"""JARVIS and FRIDAY: two personalities sharing one engine.

Each persona has its own name, palette, honorific, voice and phrasing.
Palettes are RGB tuples; the UI turns them into QColors and cross-fades
between them when you switch.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Persona:
    key: str
    name: str            # dotted display name
    callsign: str        # plain name used in logs and speech
    expansion: str
    palette: Dict[str, RGB]
    lines: Dict[str, List[str]] = field(default_factory=dict)

    def line(self, kind: str, **values) -> str:
        options = self.lines.get(kind) or [""]
        return random.choice(options).format(**values)


JARVIS = Persona(
    key="jarvis",
    name="J.A.R.V.I.S.",
    callsign="JARVIS",
    expansion="Just A Rather Very Intelligent System",
    palette={
        "bg0": (2, 6, 12),
        "bg1": (6, 18, 32),
        "primary": (64, 214, 255),
        "primary_hi": (178, 240, 255),
        "primary_lo": (18, 92, 128),
        "glow": (0, 170, 255),
        "text_hi": (226, 248, 255),
        "text_mid": (132, 196, 218),
        "text_lo": (70, 118, 140),
        "accent": (255, 182, 72),
        "alert": (255, 84, 96),
        "ok": (96, 255, 196),
    },
    lines={
        "greet": [
            "{tod}, {hon}. All systems are online.",
            "{tod}, {hon}. S.A.M.U.E.L. is at your service.",
        ],
        "late": ["It is rather late, {hon}. Shall we keep it brief?"],
        "wake": ["Yes, {hon}?", "At your service, {hon}.", "Listening, {hon}."],
        "ack": ["Right away, {hon}.", "Very well, {hon}.", "As you wish, {hon}."],
        "thanks": ["Always a pleasure, {hon}.", "Happy to help, {hon}."],
        "unknown": [
            "I'm afraid I don't have a protocol for that yet, {hon}.",
            "That is beyond my current protocols, {hon}. Try 'help' for what I can do.",
        ],
        "takeover": ["JARVIS online. Good to be back, {hon}."],
        "farewell": ["All systems going offline. Goodbye, {hon}."],
        "correct": ["Correct, {hon}.", "Precisely, {hon}.", "Well done, {hon}."],
        "wrong": ["Not quite, {hon}.", "I'm afraid not, {hon}."],
    },
)

FRIDAY = Persona(
    key="friday",
    name="F.R.I.D.A.Y.",
    callsign="FRIDAY",
    expansion="Female Replacement Intelligent Digital Assistant Youth",
    palette={
        "bg0": (9, 5, 4),
        "bg1": (26, 13, 8),
        "primary": (255, 158, 72),
        "primary_hi": (255, 222, 186),
        "primary_lo": (128, 62, 24),
        "glow": (255, 112, 36),
        "text_hi": (255, 244, 232),
        "text_mid": (226, 178, 140),
        "text_lo": (140, 98, 72),
        "accent": (96, 216, 255),
        "alert": (255, 72, 88),
        "ok": (150, 255, 170),
    },
    lines={
        "greet": [
            "{tod}, {hon}. FRIDAY here. What are we working on?",
            "{tod}, {hon}. Everything's up and running.",
        ],
        "late": ["Late one tonight, {hon}. I'll keep it quick."],
        "wake": ["Go ahead, {hon}.", "I'm here, {hon}.", "What do you need, {hon}?"],
        "ack": ["On it, {hon}.", "You got it, {hon}.", "Done and done, {hon}."],
        "thanks": ["Anytime, {hon}.", "No problem, {hon}."],
        "unknown": [
            "Not sure I can do that one yet, {hon}.",
            "That's not in my toolkit yet, {hon}. Say 'help' to see what is.",
        ],
        "takeover": ["FRIDAY online. I've got it from here, {hon}."],
        "farewell": ["Powering down. See you soon, {hon}."],
        "correct": ["Nailed it, {hon}.", "That's right, {hon}.", "Spot on, {hon}."],
        "wrong": ["Close, but no, {hon}.", "Not that one, {hon}."],
    },
)

PERSONAS: Dict[str, Persona] = {p.key: p for p in (JARVIS, FRIDAY)}


def get_persona(key: str) -> Persona:
    return PERSONAS.get((key or "").lower(), JARVIS)


def other(key: str) -> Persona:
    return FRIDAY if get_persona(key).key == "jarvis" else JARVIS


def time_of_day(hour: int) -> str:
    """Greeting for the hour (0-23): Good morning / afternoon / evening."""
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


def is_late(hour: int) -> bool:
    return hour >= 23 or hour < 4
