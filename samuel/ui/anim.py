"""One shared animation clock for the whole HUD.

A single QTimer drives every animated widget (instead of one timer each),
runs at `fps` while something is happening, drops to `idle_fps` when the
assistant is idle, and stops completely while the window is minimised.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class Clock(QObject):
    tick = pyqtSignal(float)        # dt in seconds

    def __init__(self, fps: int = 30, idle_fps: int = 20):
        super().__init__()
        self.fps = max(5, min(60, int(fps)))
        self.idle_fps = max(5, min(self.fps, int(idle_fps)))
        self.t = 0.0
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(self._timer.timerType().PreciseTimer)
        self._timer.timeout.connect(self._on_timeout)
        self._active = True
        self.standby = False
        self.standby_fps = 8
        self.frames = 0

    def start(self) -> None:
        self._last = time.monotonic()
        self._apply()

    def pause(self) -> None:
        self._timer.stop()

    def resume(self) -> None:
        if not self._timer.isActive():
            self._last = time.monotonic()
            self._apply()

    def set_active(self, active: bool, standby: bool = False) -> None:
        standby = standby and not active
        if active != self._active or standby != self.standby:
            self._active, self.standby = active, standby
            if self._timer.isActive():
                self._apply()

    @property
    def current_fps(self) -> int:
        return self.fps if self._active else self.standby_fps if self.standby else self.idle_fps

    def _apply(self) -> None:
        self._timer.start(int(1000 / self.current_fps))

    def _on_timeout(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self.t += dt
        self.frames += 1
        self.tick.emit(dt)


def approach(current: float, target: float, dt: float, speed: float) -> float:
    """Frame-rate independent exponential smoothing."""
    return target + (current - target) * math.exp(-speed * dt)


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_expo(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def segment(t: float, start: float, end: float) -> float:
    """Map t in [start, end] to 0..1 (clamped), for staggered timelines."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return max(0.0, min(1.0, (t - start) / (end - start)))
