"""Comms log: timestamped lines with kind tags and a typewriter on the newest reply."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from samuel.ui.paint import pen, wrap
from samuel.ui.theme import THEME, font
from samuel.ui.widgets.panel import Panel

AL = Qt.AlignmentFlag
TAGS = {"user": ("YOU", "text_hi"), "ai": ("", "primary_hi"), "sys": ("SYS", "text_lo"),
        "warn": ("WARN", "accent"), "err": ("ERR", "alert")}
CPS = 95.0     # typewriter characters per second


class ConsoleView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lines: Deque[Dict] = deque(maxlen=240)
        self.callsign = "JARVIS"
        self.scroll = 0
        self.t = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(90)

    def add(self, kind: str, text: str) -> None:
        self.lines.append({"kind": kind, "text": text, "ts": time.strftime("%H:%M:%S"),
                           "shown": 0.0 if kind == "ai" else float(len(text)), "who": self.callsign})
        self.scroll = 0
        self.update()

    @property
    def typing(self) -> bool:
        return bool(self.lines) and self.lines[-1]["shown"] < len(self.lines[-1]["text"])

    def advance(self, dt: float) -> None:
        self.t += dt
        if self.typing:
            last = self.lines[-1]
            last["shown"] = min(len(last["text"]), last["shown"] + CPS * dt)
            self.update()

    def finish(self) -> None:
        for ln in self.lines:
            ln["shown"] = float(len(ln["text"]))
        self.update()

    def wheelEvent(self, e):
        self.scroll = max(0, min(len(self.lines) - 1, self.scroll + (1 if e.angleDelta().y() > 0 else -1)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        tf = font("mono", 10, 500)
        bf = font("ui", 14.5, 500, 0.2)
        fm = QFontMetricsF(bf)
        lh = fm.height() + 1
        x_text = 150
        y = h
        items = list(self.lines)
        if self.scroll:
            items = items[: len(items) - self.scroll]
        for ln in reversed(items):
            kind = ln["kind"]
            tag, col = TAGS.get(kind, ("", "text_mid"))
            if kind == "ai":
                tag = ln["who"]
            text = ln["text"][: int(ln["shown"])]
            wrapped = wrap(fm, text, w - x_text - 8) or [""]
            block = lh * len(wrapped) + 5
            y -= block
            if y < 0:
                break
            p.setFont(tf)
            p.setPen(THEME.c("text_lo", 230))
            p.drawText(QRectF(0, y, 62, lh), int(AL.AlignLeft | AL.AlignVCenter), ln["ts"])
            # tag chip
            p.setFont(font("ui", 10.5, 700, 1.6))
            tw = QFontMetricsF(p.font()).horizontalAdvance(tag) + 12
            chip = QRectF(70, y + (lh - 15) / 2, tw, 15)
            c = THEME.c(col, 255)
            p.setPen(pen(THEME.c(col, 110), 1))
            p.setBrush(THEME.c(col, 26))
            p.drawRect(chip)
            p.setPen(c)
            p.drawText(chip, int(AL.AlignCenter), tag)
            p.setFont(bf)
            alpha = 250 if kind in ("ai", "user") else 215
            p.setPen(THEME.c("text_hi" if kind != "sys" else "text_mid", alpha))
            if kind == "ai":
                p.setPen(THEME.c("text_hi", 250))
            for i, line in enumerate(wrapped):
                p.drawText(QRectF(x_text, y + i * lh, w - x_text, lh), int(AL.AlignLeft | AL.AlignVCenter), line)
            if ln is self.lines[-1] and ln["shown"] < len(ln["text"]):
                lw = fm.horizontalAdvance(wrapped[-1])
                if int(self.t * 3) % 2 == 0:
                    p.fillRect(QRectF(x_text + lw + 2, y + (len(wrapped) - 1) * lh + 3, 7, lh - 6), THEME.c("primary_hi", 220))
        # fade out at the top
        if self.scroll:
            p.setFont(font("mono", 9, 500))
            p.setPen(THEME.c("accent", 230))
            p.drawText(QRectF(0, 0, w, 14), int(AL.AlignRight | AL.AlignVCenter), f"▲ SCROLLED {self.scroll}")
        p.end()


class ConsolePanel(Panel):
    def __init__(self, parent=None):
        super().__init__("04", "COMMS LOG", "", parent)
        self.view = ConsoleView()
        self.body.setContentsMargins(16, 36, 16, 10)
        self.body.addWidget(self.view)

    def advance(self, dt):
        self.view.advance(dt)
