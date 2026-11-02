import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from samuel.learning import lessons as L
from samuel.learning import srs
from samuel.learning.store import Store

SUMMARY = (
    "A black hole is an astronomical body so compact that its gravity prevents anything, including light, "
    "from escaping. Albert Einstein's theory of general relativity, which describes gravitation as the "
    "curvature of spacetime, predicts that any sufficiently compact mass will form a black hole. The "
    "boundary of no escape is called the event horizon. General relativity also predicts that every black "
    "hole should have a central singularity, where the curvature of spacetime is infinite. In 1971 the "
    "first black hole was identified by astronomers."
)


class SM2Tests(unittest.TestCase):
    def test_first_intervals_follow_the_paper(self):
        s = srs.SrsState()
        s = srs.review(s, 4)
        self.assertEqual((s.repetitions, s.interval), (1, 1))
        s = srs.review(s, 4)
        self.assertEqual((s.repetitions, s.interval), (2, 6))
        s = srs.review(s, 4)
        self.assertEqual(s.interval, 15)            # ceil(6 * 2.5)

    def test_ease_factor_formula(self):
        self.assertAlmostEqual(srs.review(srs.SrsState(), 5).ef, 2.6)
        self.assertAlmostEqual(srs.review(srs.SrsState(), 4).ef, 2.5)
        self.assertAlmostEqual(srs.review(srs.SrsState(), 3).ef, 2.36)

    def test_failure_resets_and_ef_floor(self):
        s = srs.SrsState(repetitions=5, interval=40, ef=1.35)
        s = srs.review(s, 0)
        self.assertEqual((s.repetitions, s.interval), (0, 1))
        self.assertEqual(s.ef, srs.MIN_EF)

    def test_quality_range(self):
        with self.assertRaises(ValueError):
            srs.review(srs.SrsState(), 6)

    def test_streak(self):
        today = date(2026, 11, 2)
        days = [today, today - timedelta(1), today - timedelta(2), today - timedelta(5)]
        self.assertEqual(srs.streak(days, today), 3)
        self.assertEqual(srs.streak([today - timedelta(1)], today), 1)   # still alive until tonight
        self.assertEqual(srs.streak([today - timedelta(2)], today), 0)


class LessonTests(unittest.TestCase):
    def setUp(self):
        self.lesson = L.build_lesson("black holes", "Black hole", "Compact astronomical body", SUMMARY)

    def test_sentences_and_points(self):
        self.assertEqual(len(L.split_sentences("Dr. Who met e.g. Mr. Smith. Then he left.")), 2)
        self.assertTrue(all(len(p) <= 240 for p in self.lesson.points))
        self.assertEqual(" ".join(self.lesson.points), " ".join(L.split_sentences(SUMMARY)))

    def test_key_terms_skip_title(self):
        terms = [t.lower() for t in L.key_terms(L.split_sentences(SUMMARY)[2], "Black hole")]
        self.assertIn("event horizon", terms)
        self.assertNotIn("black hole", terms)

    def test_cards(self):
        cards = L.make_cards(self.lesson)
        self.assertEqual(cards[0].kind, "define")
        for c in cards[1:]:
            self.assertIn("_____", c.front)
            self.assertNotIn(c.back, c.front)

    def test_questions_are_valid(self):
        qs = L.make_questions(self.lesson, rng=random.Random(3))
        self.assertGreaterEqual(len(qs), 3)
        for q in qs:
            self.assertEqual(len(q.options), 4)
            self.assertEqual(len({o.lower() for o in q.options}), 4)
            self.assertIn("_____", q.prompt)
            self.assertIn(q.options[q.answer_index], q.explanation)

    def test_free_answer(self):
        self.assertTrue(L.check_free_answer("the event horizon", "event horizon"))
        self.assertTrue(L.check_free_answer("singularty", "singularity"))
        self.assertFalse(L.check_free_answer("gravity", "event horizon"))


class StoreTests(unittest.TestCase):
    def test_roundtrip_and_scheduling(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.db")
            lesson = L.build_lesson("black holes", "Black hole", "Compact astronomical body", SUMMARY)
            today = date(2026, 11, 2)
            lid = store.save_lesson(lesson, L.make_cards(lesson), today)
            self.assertEqual(store.save_lesson(lesson, L.make_cards(lesson), today), lid)   # no duplicates
            due = store.due_cards(today)
            self.assertTrue(due)
            store.grade_card(due[0]["id"], 5, today)
            st = store.stats(today)
            self.assertEqual(st["due"], len(due) - 1)
            self.assertEqual(st["streak"], 1)
            self.assertEqual(st["reviews_today"], 1)
            self.assertEqual(store.find_lesson("BLACK HOLES")["title"], "Black hole")
            store.close()


if __name__ == "__main__":
    unittest.main()
