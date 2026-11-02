"""Lessons, flashcards and quiz questions built from a topic summary.

The source text comes from Wikipedia's REST summary endpoint (see
samuel/core/knowledge.py). No language model is needed: lessons are split into
short "points", flashcards are cloze deletions ("____ is the process...") and
quiz questions are multiple choice with distractors taken from other key terms.

Everything in this file is pure and unit-tested.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

_ABBREV = r"(?:e\.g|i\.e|etc|vs|Mr|Mrs|Dr|St|Jr|Sr|approx|c|ca|No|U\.S|U\.K)"

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has
have having he her here hers herself him himself his how i if in into is it its itself just me more
most my myself no nor not now of off on once only or other our ours ourselves out over own same she
should so some such than that the their theirs them themselves then there these they this those
through to too under until up very was we were what when where which while who whom why will with
would you your yours yourself yourselves known called used usually often generally typically one two
three many much several various however although though thus therefore since within without among
upon via per like also include includes including became become becomes made make makes form forms
""".split())


@dataclass
class Card:
    front: str
    back: str
    kind: str = "cloze"     # "cloze" | "define"


@dataclass
class Question:
    prompt: str
    options: List[str]
    answer_index: int
    explanation: str = ""

    @property
    def answer_letter(self) -> str:
        return "abcd"[self.answer_index]


@dataclass
class Lesson:
    topic: str
    title: str
    description: str
    summary: str
    url: str = ""
    points: List[str] = field(default_factory=list)


def split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    protected = re.sub(r"\b(" + _ABBREV + r")\.", lambda m: m.group(1) + "<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if len(p.strip()) > 2]


def make_points(summary: str, max_points: int = 8, max_chars: int = 240) -> List[str]:
    """Group sentences into short, speakable lesson points."""
    points: List[str] = []
    current = ""
    for sentence in split_sentences(summary):
        if current and len(current) + 1 + len(sentence) > max_chars:
            points.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
        if len(points) >= max_points:
            break
    if current and len(points) < max_points:
        points.append(current)
    return points


def build_lesson(topic: str, title: str, description: str, summary: str, url: str = "") -> Lesson:
    return Lesson(topic=topic, title=title, description=description or "",
                  summary=summary, url=url, points=make_points(summary))


_DETERMINERS = r"(?:the|a|an|its|their|his|her|this|these|those|our)"
_NOUN_SUFFIX = re.compile(r"(tion|sion|ity|ism|ence|ance|ment|ogy|ics|ure|ness|ist|cule|ule|ide|ium|ine|ase|um|us|on)$")
_WEAK = set("""inside outside around nearly even still ever never always something anything everything
nothing someone anyone everyone object objects thing things way ways part parts type types kind kinds
number amount term terms example examples result results process name names time times order use""".split())


def _content(word: str, title_words: set) -> bool:
    return (word not in STOPWORDS and word not in _WEAK and word not in title_words
            and not word.endswith("ly") and len(word) > 2)


def key_terms(sentence: str, title: str) -> List[str]:
    """Candidate answers in a sentence, best first: numbers/years, names,
    "called X" definitions, noun phrases after a determiner, then nouns
    recognised by suffix. Words from the lesson title are excluded (they
    would make every question trivial)."""
    title_words = {w.lower() for w in re.findall(r"[A-Za-z]+", title)}
    title_words |= {w + "s" for w in title_words} | {w.rstrip("s") for w in title_words}
    body = sentence
    terms: List[str] = []

    for m in re.finditer(r"\b(1[0-9]{3}|20[0-9]{2}|\d+(?:[.,]\d+)?(?:\s?(?:%|percent|km|kg|million|billion|degrees))?)\b", body):
        terms.append(m.group(0))

    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+(?:of|de|von|van|the)?\s*[A-Z][a-z]+)*)\b", body):
        phrase = m.group(1)
        if m.start() == 0 and " " not in phrase:
            continue      # a capital at the start of a sentence is not a name
        if {w.lower() for w in phrase.split()} <= title_words | STOPWORDS:
            continue
        terms.append(phrase)

    for m in re.finditer(r"\b(?:called|named|known as|termed)\s+(?:the\s+|an?\s+)?([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+)?)", body):
        words = m.group(1).split()
        if len(words) == 2 and not _content(words[1], title_words):
            words = words[:1]
        if all(_content(w, title_words) for w in words):
            terms.append(" ".join(words))

    for m in re.finditer(r"\b" + _DETERMINERS + r"\s+([a-z][a-z\-]+)(?:\s+([a-z][a-z\-]+))?", body):
        first, second = m.group(1), m.group(2)
        if not _content(first, title_words):
            continue
        words = [first]
        if second and _content(second, title_words) and not second.endswith(("ed", "ing")) \
                and (first.endswith(("al", "ic", "ar", "ive", "ous")) or _NOUN_SUFFIX.search(second)):
            words.append(second)
        term = " ".join(words)
        if len(term) >= 5 and not (len(words) == 1 and first.endswith(("ed", "ing"))):
            terms.append(term)

    for w in re.findall(r"\b[a-z][a-z\-]{5,}\b", body):
        if _content(w, title_words) and _NOUN_SUFFIX.search(w) and not w.endswith(("ed", "ing")):
            terms.append(w)

    seen, unique = set(), []
    for term in terms:
        k = term.lower()
        if k in seen or any(k in s.lower().split() for s in unique if " " in s):
            continue
        seen.add(k)
        unique.append(term)
    return unique


def cloze(sentence: str, term: str) -> str:
    return re.sub(r"\b" + re.escape(term) + r"\b", "_____", sentence, count=1)


def make_cards(lesson: Lesson, limit: int = 8) -> List[Card]:
    cards: List[Card] = []
    if lesson.description:
        cards.append(Card(front=f"Define: {lesson.title}",
                          back=lesson.description[0].upper() + lesson.description[1:], kind="define"))
    used = set()
    for sentence in split_sentences(lesson.summary):
        if len(cards) >= limit:
            break
        if len(sentence) > 260 or len(sentence) < 30:
            continue
        for term in key_terms(sentence, lesson.title):
            if term.lower() in used:
                continue
            used.add(term.lower())
            cards.append(Card(front=cloze(sentence, term), back=term))
            break
    return cards


def make_questions(lesson: Lesson, extra_terms: Sequence[str] = (), count: int = 5,
                   rng: Optional[random.Random] = None) -> List[Question]:
    """Multiple-choice cloze questions. Distractors come from the other key
    terms in the lesson (same 'type' first: numbers with numbers, names with
    names), then from `extra_terms` (e.g. terms from earlier lessons)."""
    rng = rng or random.Random()
    sentences = [s for s in split_sentences(lesson.summary) if 30 <= len(s) <= 260]
    per_sentence = [(s, key_terms(s, lesson.title)) for s in sentences]
    pool = [t for _, terms in per_sentence for t in terms] + list(extra_terms)

    def kind(term: str) -> str:
        if re.match(r"^\d", term):
            return "num"
        if term[:1].isupper():
            return "name"
        return "word"

    questions: List[Question] = []
    used = set()
    for sentence, terms in per_sentence:
        if len(questions) >= count:
            break
        for answer in terms:
            if answer.lower() in used:
                continue
            same = [t for t in pool if t.lower() != answer.lower() and kind(t) == kind(answer)
                    and t.lower() not in sentence.lower()]
            other = [t for t in pool if t.lower() != answer.lower() and t not in same
                     and t.lower() not in sentence.lower()]
            distractors: List[str] = []
            for t in same + other:
                if t.lower() not in {d.lower() for d in distractors}:
                    distractors.append(t)
                if len(distractors) == 3:
                    break
            if len(distractors) < 3:
                continue
            used.add(answer.lower())
            options = distractors + [answer]
            rng.shuffle(options)
            questions.append(Question(prompt=cloze(sentence, answer), options=options,
                                      answer_index=options.index(answer), explanation=sentence))
            break
    return questions


def check_free_answer(given: str, expected: str) -> bool:
    """Lenient match for typed/spoken answers to a flashcard."""
    import difflib
    g = re.sub(r"[^a-z0-9 ]", "", given.lower()).strip()
    e = re.sub(r"[^a-z0-9 ]", "", expected.lower()).strip()
    if not g or not e:
        return False
    if g == e or e in g:
        return True
    return difflib.SequenceMatcher(None, g, e).ratio() >= 0.8
