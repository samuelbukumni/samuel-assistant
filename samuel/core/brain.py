"""The brain: takes a sentence, decides what to do, and answers.

Runs on one worker thread fed by a queue, so commands never block the HUD
and never run at the same time. It owns the SQLite learning store (which is
single-threaded by design) and checks reminders whenever it is idle.

Talks to the outside world only through the Bus signals.
"""
from __future__ import annotations

import os
import queue
import random
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from samuel import personas
from samuel.core import commands, knowledge, system_control
from samuel.core.reminders import ReminderBook, describe_due
from samuel.core.telemetry import Telemetry, spoken_duration
from samuel.core.weather import Weather, spoken as spoken_weather
from samuel.learning import lessons as L
from samuel.learning.store import Store, stamp
from samuel.core.bus import thread_target

HELP = [
    ("Learning", "teach me <topic> · next · repeat · quiz me · review flashcards · my progress"),
    ("Assistant", "briefing · what time is it · what's the date · weather · battery · system status"),
    ("Time", "set a timer for 10 minutes · remind me in 20 minutes to stretch · remind me at 18:30 to call mum"),
    ("Notes", "take a note <text> · read my notes"),
    ("Laptop", "open youtube · open terminal · volume up · mute · brightness down · screenshot · lock the screen"),
    ("Web", "who is <person> · what is <thing> · google <query> · play <song> on youtube"),
    ("Personas", "switch to friday · jarvis take over · Ctrl+P"),
]


class Brain:
    def __init__(self, bus, settings, telemetry: Optional[Telemetry] = None):
        self.bus = bus
        self.s = settings
        self.persona = personas.get_persona(settings.persona)
        self.telemetry = telemetry or Telemetry()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.notes_file = Path(settings.notes_dir) / "study_notes.md"
        self.log_file = Path(settings.notes_dir) / "command_log.txt"
        self.weather = Weather(settings.weather_city, settings.weather_lat, settings.weather_lon)
        self.llm = knowledge.LLM(settings)
        self.reminders = ReminderBook(self.data_dir / "reminders.json")
        self.store: Optional[Store] = None
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._last_said = ""
        self._history: List[Dict] = []
        # learning session state
        self.mode = ""                  # "" | "lesson" | "quiz" | "review"
        self.lesson_id: Optional[int] = None
        self.lesson: Optional[L.Lesson] = None
        self.lesson_pos = 0
        self.questions: List[L.Question] = []
        self.q_index = 0
        self.q_score = 0
        self.q_answered = False
        self.review_cards = []
        self.r_index = 0
        self.r_revealed = False
        self._thread = threading.Thread(target=thread_target(self._loop), name="brain", daemon=True)

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self) -> None:
        self._thread.start()

    def submit(self, text: str, source: str = "typed") -> None:
        self._q.put(("cmd", text, source))

    def call(self, name: str, *args) -> None:
        """Run an internal action on the brain thread (e.g. from a UI click)."""
        self._q.put(("call", name, args))

    def _loop(self) -> None:
        self.store = Store(self.data_dir / "samuel.db")
        self._push_learning()
        self._push_reminders()
        last_weather = 0.0
        while True:
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                job = None
            if job:
                self.bus.busy.emit(True)
                try:
                    if job[0] == "cmd":
                        self._handle(job[1], job[2])
                    else:
                        getattr(self, "_do_" + job[1])(*job[2])
                except Exception as exc:     # a bug in one skill must not kill the brain
                    self.bus.log.emit("err", f"{type(exc).__name__}: {exc}")
                    self.say("Something went wrong with that one. Details are in the console.")
                finally:
                    self.bus.busy.emit(False)
            self._check_reminders()
            if self.weather.configured and time.time() - last_weather > 900:
                last_weather = time.time()
                self.bus.weather.emit(self.weather.current())

    # ── helpers ──────────────────────────────────────────────────────
    @property
    def hon(self) -> str:
        return self.s.honorific(self.persona.key)

    def line(self, kind: str) -> str:
        return self.persona.line(kind, hon=self.hon, tod=personas.time_of_day(datetime.now().hour),
                                 name=self.s.user_name)

    def say(self, text: str) -> None:
        self._last_said = text
        self._history.append({"role": "assistant", "content": text})
        self.bus.say.emit(text)

    def sys(self, text: str) -> None:
        self.bus.log.emit("sys", text)

    def _log_command(self, text: str) -> None:
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")
        except OSError:
            pass

    # ── dispatch ─────────────────────────────────────────────────────
    def _handle(self, text: str, source: str) -> None:
        intent = commands.parse(text, self.s.wake_words)
        if intent.name != "wake":
            self.bus.log.emit("user", text.strip())
            self._log_command(intent.text)
            self._history.append({"role": "user", "content": intent.text})
        if intent.addressed in personas.PERSONAS and intent.addressed != self.persona.key \
                and intent.name != "persona":
            self._switch(intent.addressed, announce=intent.name == "wake")
            if intent.name == "wake":
                return
        # free-text answers while a flashcard / quiz is open
        if self.mode in ("review", "quiz") and intent.name in ("chat", "wiki") and intent.text:
            if self._free_answer(intent.text):
                return
        handler = getattr(self, "_i_" + intent.name, None)
        if handler is None:
            self._i_chat(intent)
        else:
            handler(intent)

    # ── conversation ─────────────────────────────────────────────────
    def _i_wake(self, intent) -> None:
        self.say(self.line("wake"))
        self.bus.ui.emit("arm_listen", None)

    def _i_stop(self, intent) -> None:
        self.bus.ui.emit("stop_speaking", None)

    def _i_exit(self, intent) -> None:
        self.say(self.line("farewell"))
        self.bus.ui.emit("quit", 2.6)

    def _i_greet(self, intent) -> None:
        hour = datetime.now().hour
        msg = self.persona.line("greet", hon=self.hon, tod=personas.time_of_day(hour))
        if personas.is_late(hour):
            msg += " " + self.line("late")
        self.say(msg)

    def _i_thanks(self, intent) -> None:
        self.say(self.line("thanks"))

    def _i_identity(self, intent) -> None:
        p = self.persona
        self.say(f"I'm {p.callsign}, {p.expansion}, running inside S.A.M.U.E.L., "
                 f"your Smart Autonomous Multimodal Engine for Learning, {self.hon}.")

    def _i_help(self, intent) -> None:
        for title, text in HELP:
            self.sys(f"{title.upper():<10} {text}")
        self.say("Here's what I can do. The full list is in the console, and Control K opens the command palette.")

    def _i_repeat(self, intent) -> None:
        self.say(self._last_said or "I haven't said anything yet.")

    def _i_joke(self, intent) -> None:
        self.say(knowledge.joke())

    def _i_demo(self, intent) -> None:
        self.bus.ui.emit("demo", None)

    def _i_chat(self, intent) -> None:
        text = intent.args.get("text") or intent.text
        if self.llm.enabled:
            self.sys(f"Asking {self.llm.label().lower()}…")
            system = (f"You are {self.persona.callsign}, a concise, witty personal AI assistant and tutor for "
                      f"{self.s.user_name}, whom you address as '{self.hon}'. Answer in at most 3 short sentences "
                      f"suitable for speaking aloud. If you are not sure, say so.")
            reply = self.llm.ask(text, system, self._history[:-1])
            if reply:
                self.say(reply)
                return
            self.bus.log.emit("warn", "The language model did not answer (is it running?).")
        self.say(self.line("unknown"))

    # ── personas ─────────────────────────────────────────────────────
    def _switch(self, key: str, announce: bool = True) -> None:
        self.persona = personas.get_persona(key)
        self.bus.persona.emit(self.persona.key)
        if announce:
            self.say(self.line("takeover"))

    def _i_persona(self, intent) -> None:
        target = intent.args.get("target")
        key = personas.other(self.persona.key).key if target == "toggle" else target
        if key == self.persona.key:
            self.say(f"{self.persona.callsign} is already online, {self.hon}.")
            return
        self._switch(key)

    def _do_persona(self, key: str) -> None:
        if key != self.persona.key:
            self._switch(key)

    # ── clock, briefing, environment ─────────────────────────────────
    def _i_time(self, intent) -> None:
        self.say(f"It's {datetime.now():%I:%M %p}, {self.hon}.".replace(" 0", " ", 1))

    def _i_date(self, intent) -> None:
        now = datetime.now()
        self.say(f"Today is {now:%A}, {now.day} {now:%B %Y}.")

    def _i_battery(self, intent) -> None:
        b = self.telemetry.sample().get("battery")
        if not b:
            self.say("I can't find a battery sensor on this machine.")
            return
        state = "charging" if b["plugged"] else "on battery"
        msg = f"Power at {round(b['percent'])} percent, {state}."
        if b.get("secsleft") and not b["plugged"]:
            msg += f" About {spoken_duration(b['secsleft'] // 60 * 60)} remaining."
        if b["percent"] < 20 and not b["plugged"]:
            msg += f" I'd plug in soon, {self.hon}."
        self.say(msg)

    def _i_system(self, intent) -> None:
        t = self.telemetry.sample()
        if not t.get("ok"):
            self.say("Telemetry is unavailable; psutil is not installed.")
            return
        msg = (f"CPU at {t['cpu']:.0f} percent. Memory {t['ram_used_mb']:.0f} of {t['ram_total_mb']:.0f} megabytes "
               f"in use.")
        if t.get("temp"):
            msg += f" Core temperature {t['temp']:.0f} degrees."
        if t.get("disk"):
            msg += f" {t['disk']['free_gb']:.0f} gigabytes free on disk."
        self.sys(f"CPU {t['cpu']:.0f}% · RAM {t['ram_used_mb']:.0f}/{t['ram_total_mb']:.0f} MB · "
                 f"procs {t['procs']} · up {spoken_duration(t['uptime'] // 60 * 60)}")
        self.say(msg)

    def _i_weather(self, intent) -> None:
        if not self.weather.configured:
            self.say("Weather is offline until you set weather_city in the config file.")
            self.sys('Add {"weather_city": "Your City"} to ~/.config/samuel/config.json (Open-Meteo, no key).')
            return
        w = self.weather.current(force=True)
        self.bus.weather.emit(w)
        self.say(spoken_weather(w) if w.get("ok") else "I can't reach the weather service right now.")

    def _i_briefing(self, intent) -> None:
        now = datetime.now()
        parts = [self.persona.line("greet", hon=self.hon, tod=personas.time_of_day(now.hour)).split(".")[0] + "."]
        parts.append(f"It's {now:%I:%M %p} on {now:%A}, {now.day} {now:%B}.".replace(" 0", " ", 1))
        t = self.telemetry.sample()
        if t.get("ok"):
            b = t.get("battery")
            if b:
                parts.append(f"Battery {round(b['percent'])} percent{', charging' if b['plugged'] else ''}.")
            parts.append(f"CPU {t['cpu']:.0f} percent, memory {t['ram_percent']:.0f} percent.")
        if self.weather.configured:
            w = self.weather.current()
            if w.get("ok"):
                parts.append(spoken_weather(w))
        up = self.reminders.upcoming(3)
        if up:
            when, _ = describe_due(up[0].due, time.time())
            parts.append(f"You have {len(up)} reminder{'s' if len(up) > 1 else ''}; next: {up[0].text} {when}.")
        st = self.store.stats()
        if st["due"]:
            parts.append(f"{st['due']} flashcard{'s are' if st['due'] != 1 else ' is'} due for review.")
        if st["streak"]:
            parts.append(f"Your study streak is {st['streak']} day{'s' if st['streak'] != 1 else ''}.")
        elif st["lessons"]:
            parts.append("Shall we keep your study streak going today?")
        else:
            parts.append("Say 'teach me' and any topic when you're ready to learn.")
        self.say(" ".join(parts))

    # ── time management ──────────────────────────────────────────────
    def _push_reminders(self) -> None:
        self.bus.reminders.emit([{"id": r.id, "text": r.text, "due": r.due, "kind": r.kind}
                                 for r in self.reminders.upcoming(6)])

    def _check_reminders(self) -> None:
        for r in self.reminders.pop_due():
            title = "TIMER COMPLETE" if r.kind == "timer" else "REMINDER"
            self.bus.alert.emit(title, r.text)
            system_control.notify(title.title(), r.text)
            self.say(f"{self.hon.capitalize()}, your {r.text} timer is done." if r.kind == "timer"
                     else f"Reminder, {self.hon}: {r.text}.")
            self._push_reminders()

    def _i_timer(self, intent) -> None:
        seconds = intent.args.get("seconds")
        if not seconds:
            self.say("For how long? For example, set a timer for 5 minutes.")
            return
        label = spoken_duration(seconds)
        self.reminders.add_in(seconds, label, kind="timer")
        self._push_reminders()
        self.say(f"Timer set for {label}.")

    def _i_reminder(self, intent) -> None:
        msg = intent.args.get("message") or "your reminder"
        if intent.args.get("seconds"):
            r = self.reminders.add_in(intent.args["seconds"], msg)
        elif intent.args.get("clock"):
            h, m = intent.args["clock"]
            r = self.reminders.add_at(h, m, msg)
        else:
            self.say("When should I remind you? Try: remind me in 20 minutes to stretch.")
            return
        when, clock = describe_due(r.due, time.time())
        self._push_reminders()
        self.say(f"{self.line('ack')} I'll remind you to {msg} {when}, at {clock}.")

    def _i_list_reminders(self, intent) -> None:
        up = self.reminders.upcoming()
        if not up:
            self.say("Your schedule is clear.")
            return
        now = time.time()
        for r in up:
            self.sys(f"{datetime.fromtimestamp(r.due):%H:%M}  {r.kind.upper():<8} {r.text}")
        first = up[0]
        self.say(f"You have {len(up)}. Next: {first.text} {describe_due(first.due, now)[0]}.")

    def _i_cancel_reminders(self, intent) -> None:
        n = self.reminders.clear()
        self._push_reminders()
        self.say(f"Cleared {n} reminder{'s' if n != 1 else ''}." if n else "There was nothing to cancel.")

    # ── notes ────────────────────────────────────────────────────────
    def _append_note(self, text: str) -> None:
        self.notes_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.notes_file, "a", encoding="utf-8") as f:
            f.write(text)

    def _i_note(self, intent) -> None:
        content = intent.args.get("content")
        if not content:
            self.say("What would you like me to note?")
            return
        self._append_note(f"\n- [{stamp()}] {content}\n")
        self.sys(f"Note saved → {self.notes_file}")
        self.say(f"Noted, {self.hon}.")

    def _i_read_notes(self, intent) -> None:
        try:
            lines = [l[2:].strip() for l in self.notes_file.read_text(encoding="utf-8").splitlines()
                     if l.startswith("- [")]
        except OSError:
            lines = []
        if not lines:
            self.say("You don't have any notes yet.")
            return
        for l in lines[-5:]:
            self.sys(l)
        last = lines[-1].split("] ", 1)[-1]
        self.say(f"You have {len(lines)} notes. The latest says: {last}.")

    # ── laptop control ───────────────────────────────────────────────
    def _i_open(self, intent) -> None:
        ok, msg = system_control.open_target(intent.args["target"])
        self.say(msg)

    def _i_youtube(self, intent) -> None:
        ok, msg = system_control.web_search("youtube", intent.args["query"])
        self.say(msg)

    def _i_google(self, intent) -> None:
        ok, msg = system_control.web_search("google", intent.args["query"])
        self.say(msg)

    def _i_volume(self, intent) -> None:
        if intent.args["action"] == "get":
            level = system_control.current_volume()
            self.say(f"Volume is at {level} percent." if level is not None else "I can't read the volume.")
            return
        ok, msg = system_control.volume(intent.args["action"], intent.args.get("value"))
        self.say(msg)

    def _i_brightness(self, intent) -> None:
        ok, msg = system_control.brightness(intent.args["action"], intent.args.get("value"))
        self.say(msg)

    def _i_lock(self, intent) -> None:
        ok, msg = system_control.lock_screen()
        self.say(msg)

    def _i_screenshot(self, intent) -> None:
        self.bus.ui.emit("screenshot", None)

    def _i_window(self, intent) -> None:
        self.bus.ui.emit(intent.args["mode"], None)

    # ── knowledge ────────────────────────────────────────────────────
    def _i_wiki(self, intent) -> None:
        query = intent.args["query"]
        self.sys(f"Searching Wikipedia: {query}")
        r = knowledge.wiki_summary(query)
        if not r["ok"]:
            if r["reason"] == "offline":
                cached = self.store.find_lesson(query)
                if cached:
                    self.say("I'm offline, but from your notes: " + L.split_sentences(cached["summary"])[0])
                    return
                self.say("I'm offline and have nothing cached on that.")
            else:
                self.say(f"No record found for {query}.")
            return
        sentences = L.split_sentences(r["extract"])
        answer = " ".join(sentences[:2])
        self._append_note(f"\n## {r['title']} ({stamp()})\n{answer}\n")
        self.sys(f"Source: {r['url']}")
        self.say(answer + f" Say 'teach me about {query}' for a full lesson.")

    # ── learning ─────────────────────────────────────────────────────
    def _push_learning(self) -> None:
        self.bus.learning.emit(self.store.stats())

    def _push_lesson(self) -> None:
        if not self.lesson:
            self.bus.lesson.emit({})
            return
        total = len(self.lesson.points)
        self.bus.lesson.emit({"title": self.lesson.title, "index": self.lesson_pos, "total": total,
                              "point": self.lesson.points[min(self.lesson_pos, total - 1)] if total else "",
                              "description": self.lesson.description})

    def _load_lesson(self, topic: str) -> bool:
        row = self.store.find_lesson(topic)
        r = knowledge.wiki_summary(topic)
        if r["ok"]:
            lesson = L.build_lesson(topic, r["title"], r["description"], r["extract"], r["url"])
            if not lesson.points:
                return False
            cards = L.make_cards(lesson)
            self.lesson_id = self.store.save_lesson(lesson, cards)
            self.lesson = lesson
            self.sys(f"Lesson source: {r['url']}  ·  {len(cards)} flashcards created")
            return True
        if row is not None:          # offline: use the cached copy
            self.lesson_id = row["id"]
            self.lesson = Store.as_lesson(row)
            self.sys("Offline — using the cached lesson.")
            return True
        if r["reason"] == "offline":
            self.say("I need the internet the first time I teach a topic, and I can't reach Wikipedia right now.")
        else:
            self.say(f"I couldn't find a good source on {topic}. Try wording it differently.")
        return False

    def _i_teach(self, intent) -> None:
        topic = intent.args["topic"]
        self.sys(f"Preparing a lesson on {topic}…")
        if not self._load_lesson(topic):
            return
        self.mode = "lesson"
        self.lesson_pos = 0
        self.store.set_position(self.lesson_id, 0)
        self.store.log_activity(4, source="lesson")
        self.bus.card.emit({})
        self._push_lesson()
        self._push_learning()
        n = len(self.lesson.points)
        intro = f"Lesson: {self.lesson.title}. {n} point{'s' if n != 1 else ''}. "
        self.say(intro + self.lesson.points[0] + (" Say 'next' to continue." if n > 1 else " Say 'quiz me' to test yourself."))

    def _i_lesson_next(self, intent) -> None:
        if self.mode == "quiz" and self.q_answered:
            self._next_question()
            return
        if self.mode == "review" and self.r_revealed:
            self._grade(4)
            return
        if not self.lesson:
            row = self.store.latest_lesson()
            if not row:
                self.say("There's no lesson in progress. Say 'teach me' and a topic.")
                return
            self.lesson_id, self.lesson = row["id"], Store.as_lesson(row)
            self.lesson_pos = row["position"]
            self.mode = "lesson"
            self._push_lesson()
            self.say(f"Resuming {self.lesson.title}. " + self.lesson.points[self.lesson_pos])
            return
        if self.lesson_pos + 1 >= len(self.lesson.points):
            self.say(f"That's the whole lesson on {self.lesson.title}. Say 'quiz me' to test yourself, "
                     f"or 'review' for your flashcards.")
            return
        self.lesson_pos += 1
        self.store.set_position(self.lesson_id, self.lesson_pos)
        self._push_lesson()
        last = self.lesson_pos + 1 == len(self.lesson.points)
        self.say(self.lesson.points[self.lesson_pos] + (" That's the last point. Ready for a quiz?" if last else ""))

    def _i_quiz(self, intent) -> None:
        topic = intent.args.get("topic")
        if topic:
            if not self._load_lesson(topic):
                return
        elif not self.lesson:
            row = self.store.latest_lesson()
            if not row:
                self.say("Teach me a topic first, then I can quiz you on it. For example: teach me black holes.")
                return
            self.lesson_id, self.lesson = row["id"], Store.as_lesson(row)
        self.questions = L.make_questions(self.lesson, self.store.all_terms(self.lesson_id))
        if not self.questions:
            self.say("That lesson is too short for a quiz. Try 'review' for flashcards instead.")
            return
        self.mode, self.q_index, self.q_score, self.q_answered = "quiz", 0, 0, False
        self.say(f"Quiz on {self.lesson.title}: {len(self.questions)} questions. Answer A, B, C or D.")
        self._ask_question()

    def _ask_question(self) -> None:
        q = self.questions[self.q_index]
        self.q_answered = False
        self.bus.card.emit({"type": "quiz", "title": self.lesson.title, "index": self.q_index,
                            "total": len(self.questions), "prompt": q.prompt, "options": q.options,
                            "selected": None, "answer": None, "score": self.q_score})
        opts = ". ".join(f"{'ABCD'[i]}: {o}" for i, o in enumerate(q.options))
        self.say(f"Question {self.q_index + 1}. {q.prompt.replace('_____', 'blank')} {opts}.")

    def _i_answer(self, intent) -> None:
        if self.mode == "review":
            self.say("For flashcards, say your answer, or 'show' to flip the card.")
            return
        if self.mode != "quiz" or not self.questions:
            self.say("There's no question open right now. Say 'quiz me' to start one.")
            return
        if self.q_answered:
            self._next_question()
            return
        self._answer_index("abcd".index(intent.args["choice"]))

    def _do_answer(self, index: int) -> None:
        if self.mode == "quiz" and not self.q_answered:
            self._answer_index(index)
        elif self.mode == "quiz":
            self._next_question()

    def _answer_index(self, index: int) -> None:
        q = self.questions[self.q_index]
        if index >= len(q.options):
            return
        correct = index == q.answer_index
        self.q_answered = True
        self.q_score += int(correct)
        self.store.log_activity(4 if correct else 1, source="quiz")
        self.bus.card.emit({"type": "quiz", "title": self.lesson.title, "index": self.q_index,
                            "total": len(self.questions), "prompt": q.prompt, "options": q.options,
                            "selected": index, "answer": q.answer_index, "score": self.q_score})
        self._push_learning()
        if correct:
            self.say(self.line("correct") + (" Next question." if self.q_index + 1 < len(self.questions) else ""))
        else:
            self.say(f"{self.line('wrong')} The answer was {'ABCD'[q.answer_index]}: {q.options[q.answer_index]}.")
        if self.q_index + 1 >= len(self.questions):
            self._finish_quiz()
        elif correct:
            time.sleep(0.4)
            self._next_question()

    def _next_question(self) -> None:
        if self.q_index + 1 >= len(self.questions):
            self._finish_quiz()
            return
        self.q_index += 1
        self._ask_question()

    def _finish_quiz(self) -> None:
        total = len(self.questions)
        pct = round(100 * self.q_score / total)
        verdict = "Outstanding." if pct >= 80 else "Good progress." if pct >= 50 else "We'll get there. Let's review."
        self.mode = ""
        self.bus.card.emit({"type": "result", "title": self.lesson.title, "score": self.q_score, "total": total})
        self.say(f"Quiz complete: {self.q_score} out of {total}. {verdict}")

    def _i_review(self, intent) -> None:
        self.review_cards = self.store.due_cards()
        if not self.review_cards:
            st = self.store.stats()
            self.say("No flashcards are due. " + ("Nice work, you're all caught up." if st["cards"]
                                                  else "Say 'teach me' and a topic to create some."))
            self.bus.card.emit({})
            return
        self.mode, self.r_index = "review", 0
        self.say(f"{len(self.review_cards)} card{'s' if len(self.review_cards) != 1 else ''} due. "
                 f"Answer aloud, or say 'show' to flip.")
        self._show_card()

    def _show_card(self, revealed: bool = False, verdict: Optional[bool] = None) -> None:
        c = self.review_cards[self.r_index]
        self.r_revealed = revealed
        self.bus.card.emit({"type": "flash", "title": c["lesson_title"], "index": self.r_index,
                            "total": len(self.review_cards), "front": c["front"], "back": c["back"],
                            "revealed": revealed, "verdict": verdict})
        if not revealed:
            self.say(c["front"].replace("_____", "blank"))

    def _i_reveal(self, intent) -> None:
        if self.mode != "review":
            if self.mode == "quiz" and self.questions:
                q = self.questions[self.q_index]
                self.say(f"The answer is {'ABCD'[q.answer_index]}: {q.options[q.answer_index]}.")
                return
            self.say("There's no card to flip. Say 'review' to start.")
            return
        self._do_reveal()

    def _do_reveal(self) -> None:
        if self.mode != "review" or not self.review_cards:
            return
        c = self.review_cards[self.r_index]
        self._show_card(revealed=True)
        self.say(f"{c['back']}. How was that: again, hard, good or easy?")

    def _free_answer(self, text: str) -> bool:
        if self.mode == "review" and self.review_cards and not self.r_revealed:
            c = self.review_cards[self.r_index]
            ok = L.check_free_answer(text, c["back"])
            self._show_card(revealed=True, verdict=ok)
            if ok:
                self.say(self.line("correct"))
                self._grade(4)
            else:
                self.say(f"{self.line('wrong')} It's {c['back']}. Say again, hard, good or easy.")
            return True
        if self.mode == "quiz" and self.questions and not self.q_answered:
            q = self.questions[self.q_index]
            for i, opt in enumerate(q.options):
                if L.check_free_answer(text, opt):
                    self._answer_index(i)
                    return True
        return False

    def _i_grade(self, intent) -> None:
        if self.mode != "review":
            self._i_repeat(intent)      # "again" outside a review means "say that again"
            return
        self._grade(intent.args["quality"])

    def _do_grade(self, quality: int) -> None:
        if self.mode == "review":
            self._grade(quality)

    def _grade(self, quality: int) -> None:
        c = self.review_cards[self.r_index]
        state = self.store.grade_card(c["id"], quality)
        self.sys(f"Card graded {quality}/5 → next review in {state.interval} day{'s' if state.interval != 1 else ''}")
        self._push_learning()
        self.r_index += 1
        if self.r_index >= len(self.review_cards):
            self.mode = ""
            self.bus.card.emit({"type": "result", "title": "Flashcards", "score": None,
                                "total": len(self.review_cards)})
            self.say("That's every due card. Review complete.")
            return
        self._show_card()

    def _do_reveal_or_next(self) -> None:
        if self.mode == "review" and not self.r_revealed:
            self._do_reveal()
        elif self.mode == "quiz" and self.q_answered:
            self._next_question()

    def _i_progress(self, intent) -> None:
        st = self.store.stats()
        self._push_learning()
        if not st["lessons"]:
            self.say("No lessons yet. Say 'teach me' and a topic to begin.")
            return
        self.say(f"{st['lessons']} lesson{'s' if st['lessons'] != 1 else ''}, {st['cards']} flashcards, "
                 f"{st['mastered']} mastered. {st['due']} due now. "
                 f"Streak: {st['streak']} day{'s' if st['streak'] != 1 else ''}. "
                 f"{st['reviews_today']} reviews today.")

    # ── boot greeting ────────────────────────────────────────────────
    def _do_sample_lesson(self) -> None:
        """Load the bundled offline lesson (used by the demo tour)."""
        from samuel.learning import sample
        lesson = L.build_lesson(sample.TOPIC, sample.TITLE, sample.DESCRIPTION, sample.TEXT)
        cards = L.make_cards(lesson)
        self.lesson_id = self.store.save_lesson(lesson, cards)
        self.lesson, self.lesson_pos, self.mode = lesson, 0, "lesson"
        self.questions = []
        self.sys(f"Built-in lesson loaded  ·  {len(cards)} flashcards created")
        self._push_lesson()
        self._push_learning()
        self.say(f"Lesson: {lesson.title}. {len(lesson.points)} points. {lesson.points[0]}")

    def _do_boot_greeting(self) -> None:
        hour = datetime.now().hour
        msg = self.persona.line("greet", hon=self.hon, tod=personas.time_of_day(hour))
        st = self.store.stats()
        if st["due"]:
            msg += f" {st['due']} flashcard{'s are' if st['due'] != 1 else ' is'} due today."
        if personas.is_late(hour):
            msg += " " + self.line("late")
        self.say(msg)
