import array
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from samuel import personas
from samuel.config import Settings, load_settings
from samuel.core.reminders import ReminderBook, next_clock_time
from samuel.core.system_control import resolve_target
from samuel.core.telemetry import human_duration, human_rate, spoken_duration
from samuel.voice.audio import level, resample, rms


class FakeClock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class ReminderTests(unittest.TestCase):
    def test_due_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            clock = FakeClock()
            book = ReminderBook(Path(d) / "r.json", clock)
            book.add_in(60, "stretch")
            book.add_in(10, "tea", kind="timer")
            self.assertEqual([r.text for r in book.upcoming()], ["tea", "stretch"])
            clock.t += 11
            self.assertEqual([r.text for r in book.pop_due()], ["tea"])
            again = ReminderBook(Path(d) / "r.json", clock)       # survives restart
            self.assertEqual([r.text for r in again.upcoming()], ["stretch"])

    def test_next_clock_time(self):
        now = datetime(2026, 11, 2, 20, 0)
        self.assertEqual(next_clock_time(21, 30, now), datetime(2026, 11, 2, 21, 30))
        self.assertEqual(next_clock_time(7, 0, now), datetime(2026, 11, 3, 7, 0))


class AudioTests(unittest.TestCase):
    def test_resample_length_and_rms(self):
        tone = array.array("h", [1000, -1000] * 22050).tobytes()     # 1 s at 44.1 kHz
        out = resample(tone, 44100, 16000)
        self.assertEqual(len(out) // 2, 16000)
        self.assertAlmostEqual(rms(tone), 1000, delta=1)
        self.assertEqual(level(b""), 0.0)


class MiscTests(unittest.TestCase):
    def test_personas(self):
        self.assertEqual(personas.get_persona("FRIDAY").callsign, "FRIDAY")
        self.assertEqual(personas.other("friday").key, "jarvis")
        self.assertEqual(personas.time_of_day(9), "Good morning")
        self.assertEqual(personas.time_of_day(14), "Good afternoon")
        self.assertEqual(personas.time_of_day(20), "Good evening")
        line = personas.JARVIS.line("wake", hon="sir")
        self.assertIn("sir", line)

    def test_formatting(self):
        self.assertEqual(spoken_duration(5400), "1 hour and 30 minutes")
        self.assertEqual(spoken_duration(61), "1 minute and 1 second")
        self.assertEqual(human_duration(3725), "1h 02m")
        self.assertEqual(human_rate(2048), "2.0 KB/s")

    def test_open_targets(self):
        self.assertEqual(resolve_target("youtube")[:2], ("site", "https://www.youtube.com"))
        self.assertEqual(resolve_target("github.com")[:2], ("site", "https://github.com"))
        self.assertEqual(resolve_target("rm -rf /")[0], "unknown")

    def test_config_ignores_unknown_and_bad_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text('{"persona": "friday", "nonsense": 1}')
            s = load_settings(p)
            self.assertEqual(s.persona, "friday")
            p.write_text("{broken")
            self.assertTrue(load_settings(p).load_error)
            self.assertEqual(Settings().voice_for("friday").split("/")[-1], "en_GB-jenny_dioco-medium.onnx")


if __name__ == "__main__":
    unittest.main()


class ShutdownTests(unittest.TestCase):
    def test_thread_target_swallows_only_deleted_object_errors(self):
        from samuel.core.bus import thread_target

        def gone():
            raise RuntimeError("wrapped C/C++ object of type Bus has been deleted")

        def bug():
            raise RuntimeError("real bug")
        self.assertIsNone(thread_target(gone)())
        with self.assertRaises(RuntimeError):
            thread_target(bug)()

    def test_write_config_never_overwrites(self):
        from samuel.config import write_example_config
        with tempfile.TemporaryDirectory() as d:
            p = write_example_config(Path(d) / "c.json")
            self.assertTrue(p.exists())
            with self.assertRaises(SystemExit):
                write_example_config(p)
