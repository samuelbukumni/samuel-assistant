"""Turn a typed or spoken sentence into an Intent.

Pure functions, no Qt, no I/O, so it is fully unit-tested
(tests/test_commands.py). Vosk outputs lower-case words with numbers spelled
out ("set a timer for five minutes"), so numbers are normalised first.

Rules are checked in order; the first match wins. v4 matched plain
substrings, so "timer" also matched "time"; here every rule uses word
boundaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class Intent:
    name: str
    args: Dict = field(default_factory=dict)
    text: str = ""            # the cleaned sentence the intent came from
    addressed: str = ""       # wake word the sentence started with, if any


# ── numbers ────────────────────────────────────────────────────────────
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_UNIT_WORDS = {"second", "seconds", "minute", "minutes", "hour", "hours", "sec", "secs", "min", "mins"}


def words_to_numbers(text: str) -> str:
    """'twenty five minutes' -> '25 minutes', 'a minute' -> '1 minute',
    'half an hour' -> '30 minutes'. Other words are left alone."""
    text = re.sub(r"\bhalf an hour\b", "30 minutes", text)
    text = re.sub(r"\ban hour and a half\b", "90 minutes", text)
    text = re.sub(r"\ba quarter of an hour\b|\ba quarter hour\b", "15 minutes", text)
    tokens = text.split()
    out: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok in ("a", "an") and nxt in _UNIT_WORDS:
            out.append("1")
            i += 1
            continue
        if tok in _TENS:
            value = _TENS[tok]
            if nxt in _ONES and 0 < _ONES[nxt] < 10:
                value += _ONES[nxt]
                i += 1
            out.append(str(value))
        elif tok in _ONES:
            out.append(str(_ONES[tok]))
        else:
            out.append(tok)
        i += 1
    return " ".join(out)


_DUR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b")
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> Optional[int]:
    """Total seconds in phrases like '1 hour 30 minutes', '90 seconds', '5m'."""
    total = 0.0
    found = False
    for number, unit in _DUR_RE.findall(text):
        found = True
        total += float(number) * _UNIT_SECONDS[unit[0]]
    return int(round(total)) if found and total > 0 else None


_CLOCK_RE = re.compile(
    r"\bat\s+(\d{1,2})(?:(?::|\s)(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?(?=\s|$)")


def parse_clock(text: str) -> Optional[Tuple[int, int]]:
    """'at 18:30' -> (18, 30); 'at 6 30 pm' -> (18, 30); 'at 7 am' -> (7, 0)."""
    match = _CLOCK_RE.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = (match.group(3) or "").replace(".", "")
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


# ── cleaning ───────────────────────────────────────────────────────────
_FILLERS = (
    "hey", "ok", "okay", "yo", "please", "can you", "could you", "would you",
    "will you", "kindly", "i want you to", "i need you to",
)


def clean(text: str, wake_words: Iterable[str] = ()) -> Tuple[str, str]:
    """Lower-case, strip punctuation and a leading wake word / filler.

    Returns (cleaned_text, wake_word_used)."""
    t = (text or "").lower().strip()
    t = t.replace("’", "'")
    t = re.sub(r"[!?,;\"“”]", " ", t)
    t = re.sub(r"\.(?=\s|$)", " ", t)       # sentence full stops, keep "github.com"
    t = re.sub(r"\s+", " ", t).strip()
    addressed = ""
    wakes = sorted({w.lower() for w in wake_words if w}, key=len, reverse=True)
    changed = True
    while changed and t:
        changed = False
        for filler in _FILLERS:
            if t == filler or t.startswith(filler + " "):
                t = t[len(filler):].strip()
                changed = True
        for wake in wakes:
            if t == wake or t.startswith(wake + " "):
                addressed = addressed or wake
                t = t[len(wake):].strip()
                changed = True
    t = re.sub(r"\s+(please|for me)$", "", t).strip()
    return t, addressed


# ── answers to quiz / flashcards ───────────────────────────────────────
_LETTERS = {
    "a": "a", "ay": "a", "eh": "a", "one": "a", "1": "a", "first": "a",
    "b": "b", "be": "b", "bee": "b", "two": "b", "2": "b", "second": "b",
    "c": "c", "see": "c", "sea": "c", "three": "c", "3": "c", "third": "c",
    "d": "d", "dee": "d", "four": "d", "4": "d", "fourth": "d",
}
_ANSWER_RE = re.compile(
    r"^(?:(?:it's|its|it is|is it|i think|i'd say|my answer is|the answer is|answer|option|letter)\s+)*"
    r"(?:option\s+)?(?P<a>[a-d1-4]|ay|eh|be|bee|see|sea|dee|one|two|three|four|first|second|third|fourth)"
    r"(?:\s+(?:option|one))?$")


def parse_choice(text: str) -> Optional[str]:
    """'b', 'option c', 'the answer is two' -> 'a'..'d'."""
    match = _ANSWER_RE.match(text.strip())
    if not match:
        return None
    return _LETTERS.get(match.group("a"))


_GRADES = {"again": 1, "forgot": 1, "no idea": 0, "hard": 3, "difficult": 3,
           "good": 4, "got it": 4, "easy": 5, "too easy": 5}


def parse_grade(text: str) -> Optional[int]:
    """Flashcard self-grade words -> SM-2 quality 0..5."""
    return _GRADES.get(text.strip())


# ── rules ──────────────────────────────────────────────────────────────
def _strip_lead(text: str, pattern: str) -> str:
    return re.sub(pattern, "", text, count=1).strip()


def _volume(t: str) -> Optional[Intent]:
    if not re.search(r"\b(volume|louder|quieter|softer|mute|unmute|sound (up|down))\b", t):
        return None
    m = re.search(r"\b(\d{1,3})\s*(%|percent)?", t)
    if re.search(r"\bunmute\b", t):
        action = "unmute"
    elif re.search(r"\bmute\b", t):
        action = "mute"
    elif m and re.search(r"\b(set|to|at)\b", t):
        return Intent("volume", {"action": "set", "value": max(0, min(150, int(m.group(1))))})
    elif re.search(r"\b(up|louder|raise|increase|turn up)\b", t):
        action = "up"
    elif re.search(r"\b(down|quieter|softer|lower|decrease|turn down)\b", t):
        action = "down"
    else:
        action = "get"
    return Intent("volume", {"action": action})


def _brightness(t: str) -> Optional[Intent]:
    if not re.search(r"\b(brightness|brighter|dimmer|dim the screen|screen (dim|bright))\b", t):
        return None
    m = re.search(r"\b(\d{1,3})\s*(%|percent)?", t)
    if m and re.search(r"\b(set|to|at)\b", t):
        return Intent("brightness", {"action": "set", "value": max(1, min(100, int(m.group(1))))})
    if re.search(r"\b(up|brighter|raise|increase)\b", t):
        return Intent("brightness", {"action": "up"})
    if re.search(r"\b(down|dimmer|dim|lower|decrease)\b", t):
        return Intent("brightness", {"action": "down"})
    return Intent("brightness", {"action": "up"})


_DUR_PHRASE = r"(?:\b(?:in|after|for)\s+)?" + _DUR_RE.pattern + r"(?:\s+(?:and\s+)?" + _DUR_RE.pattern + r")*(?:\s+from now)?"


def _reminder(t: str) -> Optional[Intent]:
    if not re.search(r"\bremind me\b", t):
        return None
    seconds = parse_duration(t)
    clock = parse_clock(t)
    message = _strip_lead(t, r"^.*?\bremind me\b")
    message = re.sub(_DUR_PHRASE, " ", message)
    message = _CLOCK_RE.sub(" ", message)
    message = re.sub(r"\s+", " ", message).strip()
    message = re.sub(r"^(to|that|about)\s+", "", message).strip()
    return Intent("reminder", {"seconds": seconds, "clock": clock, "message": message})


_WEBSITES = ("youtube", "github", "google", "gmail", "wikipedia", "stack overflow",
             "stackoverflow", "netflix", "twitter", "x", "linkedin", "whatsapp", "facebook",
             "instagram", "maps", "google maps", "reddit", "chatgpt", "spotify")


def parse(text: str, wake_words: Iterable[str] = ("samuel",)) -> Intent:
    raw_clean, addressed = clean(text, wake_words)
    t = words_to_numbers(raw_clean)

    def I(name: str, **args) -> Intent:   # noqa: E743 - tiny local helper
        return Intent(name, args, t, addressed)

    if not t:
        return I("wake")

    # conversation control
    if re.fullmatch(r"(stop|stop talking|quiet|silence|shut up|be quiet|enough|cancel that|never mind|nevermind)", t):
        return I("stop")
    if re.match(r"^(exit|quit|shut ?down|power down|go offline|terminate|goodbye|good bye|bye|that will be all|that's all for (now|today))\b", t):
        return I("exit")

    # persona switching ("friday take over", "switch to jarvis", "switch persona")
    m = re.search(r"\b(?:switch|change|swap)(?: over)?(?: to)? (friday|jarvis)\b", t) or \
        re.match(r"^(friday|jarvis),? (?:take over|you're up|your turn|take the wheel)\b", t)
    if m:
        return I("persona", target=m.group(1))
    if re.search(r"\b(switch|toggle|change|swap) (persona|personas|assistant|mode|voice)\b", t):
        return I("persona", target="toggle")
    if addressed in ("friday", "jarvis") and re.fullmatch(r"(take over|you're up|your turn|take the wheel)", t):
        return I("persona", target=addressed)

    if re.search(r"\b(help|what can you do|commands|capabilities|what do you do)\b", t):
        return I("help")
    if re.search(r"\b(briefing|brief me|status report|morning report|daily report|daily brief|sitrep|catch me up)\b", t):
        return I("briefing")
    if re.fullmatch(r"(run )?(the )?demo( mode)?", t):
        return I("demo")

    # learning
    m = re.match(r"^(?:teach me|give me a lesson (?:on|about)|a lesson (?:on|about)|lesson (?:on|about)|"
                 r"i want to learn|i'd like to learn|help me learn|let's learn|let us learn|learn|"
                 r"explain|study)\s+(?:about\s+|me\s+)?(?P<topic>.+)$", t)
    if m:
        return I("teach", topic=m.group("topic").strip())
    if re.fullmatch(r"(next|continue|go on|carry on|next point|next one|keep going|and then|more|tell me more)", t):
        return I("lesson_next")
    if re.fullmatch(r"(repeat|repeat that|say that again|again please|come again|pardon|what did you say)", t):
        return I("repeat")
    m = re.match(r"^(?:quiz me|test me|give me a quiz|start a quiz|quiz|test my knowledge)(?:\s+(?:on|about)\s+(?P<topic>.+))?$", t)
    if m:
        return I("quiz", topic=(m.group("topic") or "").strip())
    if re.search(r"\b(review|flash ?cards?|study cards|due cards|practice cards|practise|practice)\b", t):
        return I("review")
    if re.fullmatch(r"(show|show answer|show me|flip|flip it|reveal|reveal answer|answer|what's the answer|what is the answer)", t):
        return I("reveal")
    grade = parse_grade(t)
    if grade is not None:
        return I("grade", quality=grade)
    choice = parse_choice(t)
    if choice:
        return I("answer", choice=choice)
    if re.search(r"\b(progress|my stats|statistics|my streak|streak|how am i doing|learning report|what have i learned|what have i learnt)\b", t):
        return I("progress")

    # time management
    rem = _reminder(t)
    if rem:
        return rem
    if re.search(r"\b(cancel|clear|stop|delete|remove)\b.*\b(reminders?|timers?|alarms?|countdowns?)\b", t):
        return I("cancel_reminders")
    if re.search(r"\b(list|show|what are|what's|any|read)\b.*\b(reminders|timers|schedule)\b", t) or t in ("reminders", "timers"):
        return I("list_reminders")
    if re.search(r"\b(timer|countdown|count down)\b", t):
        return I("timer", seconds=parse_duration(t))

    # notes
    if re.search(r"\b(read|show|list|what are|open)\b.*\bnotes\b", t) or t in ("notes", "my notes"):
        return I("read_notes")
    m = re.match(r"^(?:take a note|make a note|note down|note that|note|write down|write that down|remember that|remember)\b\s*(?:that\s+)?(?P<c>.*)$", t)
    if m:
        return I("note", content=m.group("c").strip())

    # clock and calendar
    if re.search(r"\b(what(?:'s| is)? the time|what time is it|current time|tell me the time|the time now)\b", t) or t in ("time", "the time"):
        return I("time")
    if re.search(r"\b(what(?:'s| is)? (?:the |today's )?date|what day is it|which day is it|today's date|what's today|what is today)\b", t) or t in ("date", "the date"):
        return I("date")

    # environment and machine
    if re.search(r"\b(weather|forecast|is it raining|temperature outside|outside temperature|how hot is it outside|how cold is it)\b", t):
        return I("weather")
    if re.search(r"\b(battery|power level|charge level|charging|plugged in)\b", t):
        return I("battery")
    if re.search(r"\b(system|diagnostics?|cpu|processor|ram|memory usage|memory|performance|specs|temperature|how hot|disk|storage|uptime)\b", t):
        return I("system")
    vol = _volume(t)
    if vol:
        return Intent(vol.name, vol.args, t, addressed)
    bri = _brightness(t)
    if bri:
        return Intent(bri.name, bri.args, t, addressed)
    if re.search(r"\b(screenshot|screen shot|screen capture|snapshot|capture (?:the )?screen)\b", t):
        return I("screenshot")
    if re.search(r"\block (?:the |my )?(?:screen|computer|laptop|pc|machine)\b", t) or t == "lock":
        return I("lock")
    if re.search(r"\b(exit full ?screen|leave full ?screen|windowed)\b", t):
        return I("window", mode="windowed")
    if re.search(r"\b(full ?screen|maximi[sz]e)\b", t):
        return I("window", mode="fullscreen")
    if re.search(r"\b(minimi[sz]e|hide (?:the )?(?:hud|window|yourself))\b", t):
        return I("window", mode="minimize")

    # web and apps
    m = re.match(r"^(?:search )?youtube (?:for )?(?P<q>.+)$", t) or \
        re.match(r"^(?:play|search|find|look up|search for)\s+(?P<q>.+?)\s+on youtube$", t) or \
        re.match(r"^search youtube for (?P<q>.+)$", t)
    if m:
        return I("youtube", query=m.group("q").strip())
    m = re.match(r"^(?:google|search google for|search the web for|search online for|look up online|search for|search)\s+(?P<q>.+)$", t)
    if m and not re.match(r"^search wikipedia\b", t):
        return I("google", query=m.group("q").strip())
    m = re.match(r"^(?:open|launch|start|run|go to|navigate to|bring up|pull up)\s+(?:the\s+|my\s+)?(?P<target>.+)$", t)
    if m:
        return I("open", target=m.group("target").strip())
    if t in _WEBSITES:
        return I("open", target=t)

    # knowledge
    m = re.match(r"^(?:search wikipedia for|wikipedia|who is|who was|who are|who were|what is|what's|what are|what was|what were|"
                 r"tell me about|define|definition of|what does)\s+(?:a\s+|an\s+|the\s+)?(?P<q>.+?)(?:\s+mean)?$", t)
    if m:
        return I("wiki", query=m.group("q").strip())

    # small talk
    if re.search(r"\b(joke|make me laugh|something funny|cheer me up)\b", t):
        return I("joke")
    if re.match(r"^(hello|hi|hey there|hiya|good (?:morning|afternoon|evening|day)|greetings|wake up|you there|are you there|daddy's home)\b", t):
        return I("greet")
    if re.match(r"^(thanks|thank you|cheers|nice work|good job|well done|great job|brilliant)\b", t):
        return I("thanks")
    if re.search(r"\b(who are you|what are you|your name|introduce yourself)\b", t):
        return I("identity")

    return I("chat", text=raw_clean)
