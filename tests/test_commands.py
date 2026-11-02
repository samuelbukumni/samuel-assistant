import unittest

from samuel.core.commands import (clean, parse, parse_choice, parse_clock, parse_duration,
                                  parse_grade, words_to_numbers)

WAKE = ["samuel", "jarvis", "friday"]


def intent(text):
    return parse(text, WAKE)


class NumberTests(unittest.TestCase):
    def test_words_to_numbers(self):
        self.assertEqual(words_to_numbers("twenty five minutes"), "25 minutes")
        self.assertEqual(words_to_numbers("a minute"), "1 minute")
        self.assertEqual(words_to_numbers("half an hour"), "30 minutes")
        self.assertEqual(words_to_numbers("a cat"), "a cat")

    def test_duration(self):
        self.assertEqual(parse_duration("1 hour 30 minutes"), 5400)
        self.assertEqual(parse_duration("90 seconds"), 90)
        self.assertEqual(parse_duration("5m"), 300)
        self.assertIsNone(parse_duration("no time here"))

    def test_clock(self):
        self.assertEqual(parse_clock("at 18:30 to study"), (18, 30))
        self.assertEqual(parse_clock("at 6 30 pm"), (18, 30))
        self.assertEqual(parse_clock("at 12 am"), (0, 0))
        self.assertIsNone(parse_clock("at 25:00"))


class CleanTests(unittest.TestCase):
    def test_wake_word_and_fillers(self):
        self.assertEqual(clean("Hey Samuel, could you open YouTube please?", WAKE), ("open youtube", "samuel"))
        self.assertEqual(clean("Friday!", WAKE), ("", "friday"))

    def test_keeps_domain_dots(self):
        self.assertEqual(clean("open github.com.", WAKE)[0], "open github.com")


class IntentTests(unittest.TestCase):
    def check(self, text, name, **args):
        i = intent(text)
        self.assertEqual(i.name, name, f"{text!r} -> {i}")
        for k, v in args.items():
            self.assertEqual(i.args.get(k), v, f"{text!r} -> {i}")

    def test_v4_bug_timer_is_not_time(self):
        self.check("set a timer for five minutes", "timer", seconds=300)
        self.check("what time is it", "time")

    def test_reminders(self):
        self.check("remind me in ten minutes to call mum", "reminder", seconds=600, message="call mum")
        self.check("remind me to look for my keys in 5 minutes", "reminder", message="look for my keys")
        self.check("remind me at 6 30 pm to study", "reminder", clock=(18, 30), message="study")
        self.check("cancel all timers", "cancel_reminders")
        self.check("what are my reminders", "list_reminders")

    def test_learning(self):
        self.check("teach me about black holes", "teach", topic="black holes")
        self.check("explain photosynthesis", "teach", topic="photosynthesis")
        self.check("quiz me", "quiz", topic="")
        self.check("quiz me on the french revolution", "quiz", topic="the french revolution")
        self.check("review my flashcards", "review")
        self.check("next", "lesson_next")
        self.check("option b", "answer", choice="b")
        self.check("the answer is three", "answer", choice="c")
        self.check("easy", "grade", quality=5)
        self.check("show answer", "reveal")
        self.check("how am i doing", "progress")

    def test_personas(self):
        self.check("switch to friday", "persona", target="friday")
        self.check("Friday, take over", "persona", target="friday")
        self.check("toggle persona", "persona", target="toggle")
        self.assertEqual(intent("friday what time is it").addressed, "friday")

    def test_system(self):
        self.check("turn the volume up", "volume", action="up")
        self.check("set volume to 40 percent", "volume", action="set", value=40)
        self.check("mute", "volume", action="mute")
        self.check("brightness down", "brightness", action="down")
        self.check("lock the screen", "lock")
        self.check("take a screenshot", "screenshot")
        self.check("how much battery do i have", "battery")
        self.check("run diagnostics", "system")
        self.check("what's the weather like", "weather")
        self.check("go fullscreen", "window", mode="fullscreen")

    def test_web_and_knowledge(self):
        self.check("open youtube", "open", target="youtube")
        self.check("play lofi beats on youtube", "youtube", query="lofi beats")
        self.check("google python decorators", "google", query="python decorators")
        self.check("who is ada lovelace", "wiki", query="ada lovelace")
        self.check("what is the date", "date")

    def test_misc(self):
        self.check("", "wake")
        self.check("samuel", "wake")
        self.check("goodbye", "exit")
        self.check("take a note buy milk", "note", content="buy milk")
        self.check("read my notes", "read_notes")
        self.check("good morning", "greet")
        self.check("give me the daily briefing", "briefing")
        self.check("stop", "stop")
        self.check("sing me a song about rain", "chat")


class AnswerParsing(unittest.TestCase):
    def test_choices(self):
        for text, letter in [("a", "a"), ("bee", "b"), ("option c", "c"), ("4", "d"), ("it's two", "b")]:
            self.assertEqual(parse_choice(text), letter, text)
        self.assertIsNone(parse_choice("banana"))

    def test_grades(self):
        self.assertEqual(parse_grade("again"), 1)
        self.assertEqual(parse_grade("good"), 4)
        self.assertIsNone(parse_grade("great"))


if __name__ == "__main__":
    unittest.main()
