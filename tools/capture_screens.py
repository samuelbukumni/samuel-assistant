#!/usr/bin/env python3
"""Render the HUD headlessly and save screenshots of each state.

    QT_QPA_PLATFORM=offscreen python tools/capture_screens.py [out_dir] [--size 1600x900]

Runs the real app in --demo mode (simulated voice, temporary data folder),
drives it through a fixed script and grabs the window at each step. Also
writes metrics.json with the process RAM (RSS) and CPU use while idle.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import samuel.app as A  # noqa: E402


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    size = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--size=")), "1600x900")
    out = Path(argv[0] if argv else ROOT / "screenshots")
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    sam = A.Samuel(A.parse_args(["--demo", "--size", size]), app)
    sam._on_action_orig = sam._on_action

    def no_auto_demo(name, arg):        # this script drives the tour itself
        if name == "booted":
            sam.brain.call("boot_greeting")
            return
        sam._on_action_orig(name, arg)
    sam.hud.action.disconnect()
    sam.hud.action.connect(no_auto_demo)
    sam._on_action = no_auto_demo
    sam.start()
    proc = psutil.Process()
    metrics = {"size": size}
    from samuel.demo import DemoDriver
    demo = DemoDriver(sam)

    def shot(name):
        path = out / f"{name}.png"
        sam.hud.grab().save(str(path))
        print("saved", path, flush=True)

    frames = {}

    def measure_start():
        proc.cpu_percent(None)
        frames["n"], frames["t"] = sam.hud.clock.frames, time.monotonic()

    def measure_end(tag):
        dt = time.monotonic() - frames["t"]
        metrics[f"{tag}_cpu_percent_of_one_core"] = round(proc.cpu_percent(None), 1)
        metrics[f"{tag}_frames_per_s"] = round((sam.hud.clock.frames - frames["n"]) / dt, 1)
        metrics[f"{tag}_window_s"] = round(dt, 1)
        metrics[f"{tag}_rss_mb"] = round(proc.memory_info().rss / 2**20, 1)

    def standby():
        sam.hud.STANDBY_AFTER = 0.0

    def wrong_answer():
        q = sam.brain.questions[sam.brain.q_index]
        sam.brain.call("answer", (q.answer_index + 1) % len(q.options))

    def palette():
        sam.hud.palette.open()
        sam.hud.palette.edit.setText("re")

    script = [
        (1.3, lambda: shot("01_boot")),
        (5.6, lambda: sam.brain.submit("system status")),
        (13.0, measure_start),
        (19.0, lambda: measure_end("idle")),
        (19.2, lambda: shot("02_jarvis_idle")),
        (19.5, lambda: demo._hear("teach me about spaced repetition", 2.6)),
        (21.0, lambda: shot("03_listening")),
        (22.6, lambda: sam.brain.call("sample_lesson")),
        (25.5, lambda: shot("04_lesson_speaking")),
        (40.0, lambda: sam.brain.submit("quiz me")),
        (43.0, lambda: shot("05_quiz")),
        (47.0, wrong_answer),
        (48.4, lambda: shot("06_quiz_answered")),
        (56.0, lambda: sam.brain.submit("set a timer for 4 seconds")),
        (57.0, lambda: sam.brain.submit("switch to friday")),
        (60.0, lambda: shot("07_friday")),
        (61.6, lambda: shot("08_friday_alert")),
        (70.0, lambda: sam.brain.submit("review my flashcards")),
        (73.0, lambda: shot("09_friday_flashcard")),
        (75.0, lambda: sam.brain.call("reveal")),
        (77.0, lambda: shot("10_friday_flashcard_revealed")),
        (78.0, palette),
        (79.0, lambda: shot("11_command_palette")),
        (79.2, sam.hud.palette.close_),
        (80.0, sam.hud.help.open),
        (81.0, lambda: shot("12_help")),
        (81.2, sam.hud.help.close_),
        (83.0, standby),
        (85.0, measure_start),
        (93.0, lambda: measure_end("standby")),
        (93.1, lambda: metrics.update(threads=proc.num_threads(), platform=QApplication.platformName())),
        (93.2, lambda: (out / "metrics.json").write_text(json.dumps(metrics, indent=2)) and print(json.dumps(metrics))),
        (93.5, app.quit),
    ]
    only = set(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--until="))
    for t, fn in script:
        if only and t > float(next(iter(only))):
            QTimer.singleShot(int(t * 1000), app.quit)
            break
        QTimer.singleShot(int(t * 1000), fn)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
