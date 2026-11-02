"""Scripted tour for --demo (and Ctrl+D): shows every HUD state without a
microphone, speaker or internet. Uses the bundled offline lesson."""
from __future__ import annotations

from PyQt6.QtCore import QTimer


class DemoDriver:
    def __init__(self, app):
        self.app = app
        self.bus = app.bus
        self.brain = app.brain
        self.running = False
        self.steps = [
            (0.0, lambda: self.bus.log.emit("sys", "Demo tour started — simulated voice, temporary data. Ctrl+D replays it.")),
            (0.5, lambda: self.brain.submit("system status")),
            (9.0, lambda: self._hear("teach me about spaced repetition")),
            (12.0, lambda: self.brain.call("sample_lesson")),
            (26.0, lambda: self.brain.submit("next")),
            (36.0, lambda: self.brain.submit("quiz me")),
            (49.0, lambda: self.brain.call("answer", 0)),
            (58.0, lambda: self.brain.submit("set a timer for 6 seconds")),
            (61.0, lambda: self.brain.submit("switch to friday")),
            (72.0, lambda: self.brain.submit("review my flashcards")),
            (82.0, lambda: self.brain.call("reveal")),
            (90.0, lambda: self.brain.call("grade", 4)),
            (98.0, lambda: self.brain.submit("how am i doing")),
            (106.0, lambda: self.brain.submit("jarvis, take over")),
            (112.0, self._done),
        ]

    def start(self):
        self.running = True
        for t, fn in self.steps:
            QTimer.singleShot(int(t * 1000), fn)

    def _hear(self, phrase: str, final_delay: float = 2.4):
        """Fake the listening state: partial transcript, then the final one."""
        self.bus.listening.emit(True)
        from samuel.voice.tts import _envelope
        for k in range(int(final_delay * 20)):        # simulated mic level while "speaking"
            QTimer.singleShot(int(k * 50), lambda t=k / 20: self.bus.energy.emit(0.8 * _envelope(t)))
        QTimer.singleShot(int(final_delay * 1000) + 60, lambda: self.bus.energy.emit(0.0))
        words = phrase.split()
        for i in range(1, len(words) + 1):
            QTimer.singleShot(int(i * final_delay / len(words) * 1000),
                              lambda s=" ".join(words[:i]): self.bus.heard.emit(s, False))
        QTimer.singleShot(int(final_delay * 1000) + 200, lambda: (self.bus.heard.emit(phrase, True),
                                                                  self.bus.listening.emit(False),
                                                                  self.bus.log.emit("user", phrase)))

    def _done(self):
        self.running = False
        self.bus.log.emit("sys", "Demo tour finished. Type a command or press F1 for the manual.")
