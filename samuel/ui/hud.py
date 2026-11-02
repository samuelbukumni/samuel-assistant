"""The main window: lays out the panels, owns the animation clock and
turns Bus signals into what you see."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QKeySequence, QPainter, QPixmap, QRadialGradient, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from samuel import personas
from samuel.ui.anim import Clock, ease_out_cubic, segment
from samuel.ui.paint import pen
from samuel.ui.theme import THEME
from samuel.ui.widgets.chrome import Banner, BootOverlay, CommandBar, HelpOverlay, Palette, Subtitle, TopBar
from samuel.ui.widgets.console import ConsolePanel
from samuel.ui.widgets.learning import LearningPanel
from samuel.ui.widgets.reactor import Reactor
from samuel.ui.widgets.telemetry import OpsPanel, TelemetryPanel

PALETTE_COMMANDS = [
    ("Teach me", "Start a lesson built from Wikipedia", "teach me about "),
    ("Next point", "Continue the active lesson", "next"),
    ("Quiz me", "Multiple-choice quiz on the active lesson", "quiz me"),
    ("Review flashcards", "Spaced-repetition review of due cards", "review my flashcards"),
    ("Progress", "Streak, due cards and mastery", "how am i doing"),
    ("Daily briefing", "Time, weather, timers and study queue", "daily briefing"),
    ("System status", "CPU, memory, temperature, battery", "system status"),
    ("Weather", "Current conditions (Open-Meteo)", "what's the weather"),
    ("Timer · 25 min", "Focus session timer", "set a timer for 25 minutes"),
    ("Switch persona", "JARVIS ⇄ FRIDAY", ":persona"),
    ("Take a note", "Append to study_notes.md", "take a note "),
    ("Read notes", "Read the latest study notes", "read my notes"),
    ("Push to talk", "Listen for one command (Ctrl+Space)", ":listen"),
    ("Screenshot", "Save a PNG of the HUD (Ctrl+S)", ":screenshot"),
    ("Fullscreen", "Toggle fullscreen (F11)", ":fullscreen"),
    ("Demo tour", "Scripted walkthrough, no microphone needed", ":demo"),
    ("Help", "Keyboard shortcuts and voice commands (F1)", ":help"),
    ("Quit", "Close S.A.M.U.E.L. (Ctrl+Q)", ":quit"),
]


class Root(QWidget):
    """Central widget; paints the background grid + vignette (cached)."""

    def __init__(self):
        super().__init__()
        self._bg: Optional[QPixmap] = None
        self._key = None
        THEME.changed.connect(self.update)

    def paintEvent(self, _):
        key = (self.width(), self.height(), THEME.version)
        if self._key != key:
            self._bg = self._render_bg()
            self._key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg)
        p.end()

    def _render_bg(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        w, h = self.width(), self.height()
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(QRectF(0, 0, w, h), THEME.c("bg0"))
        g = QRadialGradient(QPointF(w / 2, h * 0.42), max(w, h) * 0.65)
        g.setColorAt(0.0, THEME.c("bg1", 255))
        g.setColorAt(0.55, THEME.c("bg1", 90))
        g.setColorAt(1.0, THEME.c("bg0", 0))
        p.fillRect(QRectF(0, 0, w, h), QBrush(g))
        # dot grid
        p.setPen(Qt.PenStyle.NoPen)
        step = 24
        for y in range(step, h, step):
            for x in range(step, w, step):
                p.setBrush(THEME.c("primary", 22 if (x // step + y // step) % 4 else 34))
                p.drawRect(QRectF(x, y, 1.2, 1.2))
        # scanlines
        for y in range(0, h, 3):
            p.fillRect(QRectF(0, y, w, 1), THEME.c("bg0", 26))
        # corner frame marks
        p.setPen(pen(THEME.c("primary", 60), 1))
        L = 26
        for (x, y, dx, dy) in ((6, 6, 1, 1), (w - 6, 6, -1, 1), (6, h - 6, 1, -1), (w - 6, h - 6, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * L, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * L))
        p.end()
        return pm


class Hud(QMainWindow):
    command = pyqtSignal(str, str)      # text, source
    action = pyqtSignal(str, object)    # internal actions → app (listen, persona, demo, quit, answer, grade…)

    def __init__(self, settings, persona_key: str = "jarvis", boot: bool = True,
                 checks=None, demo: bool = False):
        super().__init__()
        self.s = settings
        self.demo = demo
        self.persona = personas.get_persona(persona_key)
        THEME.set_persona(self.persona.key, animate=False)
        self.setWindowTitle("S.A.M.U.E.L. — " + self.persona.callsign)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1180, 700)
        self.speaking = self.busy = self.listening = False
        self.alert_until = 0.0
        self.card_type = ""
        self.clock = Clock(settings.fps, settings.idle_fps)
        self.clock.standby_fps = 5 if getattr(settings, "lite", False) else 8
        self.last_activity = time.monotonic()
        self.STANDBY_AFTER = 45.0           # seconds of quiet before dropping to the standby frame rate

        root = Root()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 10, 20, 16)
        outer.setSpacing(10)
        self.topbar = TopBar()
        outer.addWidget(self.topbar)
        row = QHBoxLayout()
        row.setSpacing(14)
        outer.addLayout(row, 1)

        left = QVBoxLayout()
        left.setSpacing(12)
        self.telemetry = TelemetryPanel()
        self.ops = OpsPanel()
        left.addWidget(self.telemetry, 1)
        left.addWidget(self.ops)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(318)
        left.setContentsMargins(0, 0, 0, 0)

        centre = QVBoxLayout()
        centre.setContentsMargins(0, 0, 0, 0)
        centre.setSpacing(8)
        self.reactor = Reactor()
        self.subtitle = Subtitle()
        self.console = ConsolePanel()
        self.cmdbar = CommandBar()
        centre.addWidget(self.reactor, 1)
        centre.addWidget(self.subtitle)
        centre.addWidget(self.console)
        centre.addWidget(self.cmdbar)

        self.learning = LearningPanel()
        self.learning.setFixedWidth(380)

        row.addWidget(lw)
        row.addLayout(centre, 1)
        row.addWidget(self.learning)

        self.banner = Banner(root)
        self.palette = Palette(root, PALETTE_COMMANDS)
        self.help = HelpOverlay(root)
        self.boot_overlay: Optional[BootOverlay] = None
        self.boot_t = 99.0
        self._panels = [self.telemetry, self.ops, self.console, self.learning]
        if boot:
            self.boot_overlay = BootOverlay(root, checks or [])
            self.boot_t = 0.0
            for pnl in self._panels:
                pnl.reveal = 0.0
            self.reactor.boot = 0.0

        self._wire()
        self._apply_persona(self.persona.key, animate=False)
        self.clock.tick.connect(self._tick)

    # ------------------------------------------------------------ wiring
    def _wire(self):
        self.cmdbar.submitted.connect(lambda s: self.command.emit(s, "typed"))
        self.cmdbar.mic.connect(lambda: self.action.emit("listen", None))
        self.topbar.persona_clicked.connect(lambda k: self.action.emit("persona", k))
        self.topbar.window_action.connect(self.window_action)
        self.palette.run.connect(self._palette_run)
        cv = self.learning.card
        cv.answer.connect(lambda i: self.action.emit("answer", i))
        cv.grade.connect(lambda q: self.action.emit("grade", q))
        cv.reveal.connect(lambda: self.action.emit("reveal", None))
        cv.suggest.connect(lambda s: self.command.emit(s, "typed"))

        def sc(keys, fn):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)
            s.activated.connect(fn)

        sc("F11", lambda: self.window_action("fullscreen"))
        sc("Ctrl+K", self.palette.open)
        sc("F1", lambda: self.help.close_() if self.help.isVisible() and self.help.target else self.help.open())
        sc("Ctrl+P", lambda: self.action.emit("persona", "toggle"))
        sc("Ctrl+Space", lambda: self.action.emit("listen", None))
        sc("Ctrl+Q", lambda: self.action.emit("quit", None))
        sc("Ctrl+L", self.focus_input)
        sc("Ctrl+D", lambda: self.action.emit("demo", None))
        sc("Ctrl+S", lambda: self.action.emit("screenshot", None))
        sc("Esc", self._escape)

    def _palette_run(self, phrase: str):
        if phrase.startswith(":"):
            name = phrase[1:]
            if name == "help":
                self.help.open()
            elif name == "fullscreen":
                self.window_action("fullscreen")
            elif name == "persona":
                self.action.emit("persona", "toggle")
            else:
                self.action.emit(name, None)
        elif phrase.endswith(" "):          # needs completion, e.g. "teach me about "
            self.cmdbar.input.setText(phrase)
            self.focus_input()
        else:
            self.command.emit(phrase, "typed")

    def focus_input(self):
        self.cmdbar.input.setFocus()
        self.cmdbar.update()

    def _escape(self):
        if self.palette.isVisible() and self.palette.target:
            self.palette.close_()
        elif self.help.isVisible() and self.help.target:
            self.help.close_()
        elif self.isFullScreen():
            self.showNormal()
        else:
            self.cmdbar.input.clearFocus()
            self.action.emit("stop_speaking", None)

    def window_action(self, what: str):
        if what == "fullscreen":
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif what == "windowed":
            self.showNormal()
        elif what == "minimize":
            self.showMinimized()
        elif what == "close":
            self.action.emit("quit", None)

    def keyPressEvent(self, e):
        self.poke()
        k = e.key()
        if k == Qt.Key.Key_Slash:
            self.focus_input()
            return
        if Qt.Key.Key_1 <= k <= Qt.Key.Key_4:
            i = k - Qt.Key.Key_1
            if self.card_type == "quiz":
                self.action.emit("answer", i)
            elif self.card_type == "flash" and self.learning.card.card.get("revealed"):
                self.action.emit("grade", [1, 3, 4, 5][i])
            return
        if k == Qt.Key.Key_Space and self.card_type in ("quiz", "flash"):
            self.action.emit("reveal_or_next", None)
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        self.poke()
        self.cmdbar.input.clearFocus()
        self.setFocus()
        super().mousePressEvent(e)

    # ------------------------------------------------------------ bus slots
    def poke(self):
        self.last_activity = time.monotonic()

    def on_log(self, kind: str, text: str):
        self.poke()
        self.console.view.add(kind, text)

    def on_say(self, text: str):
        self.subtitle.set_text(text)
        self.console.view.add("ai", text)

    def on_heard(self, text: str, final: bool):
        self.subtitle.set_heard(text, final)

    def on_busy(self, v: bool):
        self.busy = v

    def on_speaking(self, v: bool):
        self.speaking = v
        if not v:
            self.reactor.set_energy(0.0)

    def on_listening(self, v: bool):
        self.listening = v
        self.cmdbar.mic_btn.active = v
        self.cmdbar.mic_btn.update()
        if v:
            self.subtitle.set_text("")
            self.subtitle.set_heard("Listening…", False)

    def on_energy(self, v: float):
        self.reactor.set_energy(v)
        if self.listening:
            self.cmdbar.mic_btn.level = v
            self.cmdbar.mic_btn.update()

    def on_persona(self, key: str):
        self._apply_persona(key, animate=True)

    def on_alert(self, title: str, text: str):
        self.banner.setGeometry(0, 60, self.centralWidget().width(), 90)
        self.banner.show_alert(title, text)
        self.alert_until = time.monotonic() + 3.0

    def on_card(self, c: Dict):
        self.poke()
        self.card_type = (c or {}).get("type", "")
        self.learning.card.set_card(c)

    def set_status(self, key: str, text: str, level: str):
        self.topbar.set_status(key, text, level)

    def _apply_persona(self, key: str, animate: bool):
        self.persona = personas.get_persona(key)
        THEME.set_persona(self.persona.key, animate=animate)
        self.topbar.set_persona(self.persona.key)
        self.reactor.set_callsign(".".join(self.persona.callsign) + ".")
        self.console.view.callsign = self.persona.callsign
        self.setWindowTitle("S.A.M.U.E.L. — " + self.persona.callsign)

    # ------------------------------------------------------------ animation
    def ui_state(self) -> str:
        if time.monotonic() < self.alert_until:
            return "alert"
        if self.speaking:
            return "speaking"
        if self.busy:
            return "thinking"
        if self.listening:
            return "listening"
        return "idle"

    def _tick(self, dt: float):
        THEME.tick(dt)
        state = self.ui_state()
        self.reactor.set_state(state)
        if self.boot_overlay is not None:
            self.boot_t += dt
            self.boot_overlay.setGeometry(self.centralWidget().rect())
            self.boot_overlay.advance(dt)
            t = self.boot_t - (BootOverlay.DURATION - 0.2)
            self.reactor.boot = ease_out_cubic(segment(t, 0.0, 1.8))
            for i, pnl in enumerate(self._panels):
                k = segment(t, 0.15 + i * 0.12, 0.75 + i * 0.12)
                if k != pnl.reveal:
                    pnl.reveal = k
                    pnl.update()
            if self.boot_overlay.done and self.reactor.boot >= 1 and all(p.reveal >= 1 for p in self._panels):
                self.boot_overlay.deleteLater()
                self.boot_overlay = None
                self.action.emit("booted", None)
        self.reactor.advance(dt)
        self.telemetry.advance(dt)
        self.learning.advance(dt)
        self.console.advance(dt)
        self.subtitle.advance(dt)
        for ov in (self.palette, self.help, self.banner):
            ov.advance(dt)
        active = (state != "idle" or self.boot_overlay is not None or THEME.animating or self.console.view.typing
                  or self.palette.isVisible() or self.help.isVisible() or self.banner.isVisible())
        now = time.monotonic()
        if active or self.cmdbar.input.hasFocus() and self.cmdbar.input.text():
            self.last_activity = now
        self.clock.set_active(active, standby=now - self.last_activity > self.STANDBY_AFTER)

    def second(self):
        self.topbar.update()
        self.ops.tick_second()

    # ------------------------------------------------------------ window state
    def changeEvent(self, e):
        from PyQt6.QtCore import QEvent
        if e.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self.clock.pause()
            else:
                self.clock.resume()
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        r = self.centralWidget().rect()
        for ov in (self.palette, self.help):
            if ov.isVisible():
                ov.setGeometry(r)
        self.banner.setGeometry(0, 60, r.width(), 90)
        h = self.height()
        self.console.setFixedHeight(max(140, min(230, int(h * 0.2))))

    def save_screenshot(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("SAMUEL_%Y%m%d_%H%M%S.png")
        self.grab().save(str(path))
        return path
