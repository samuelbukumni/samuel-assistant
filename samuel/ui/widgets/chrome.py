"""Window chrome: top bar, subtitles, command bar, palette, banner, help, boot."""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QSizePolicy, QWidget

from samuel import __version__
from samuel.ui.anim import approach, ease_out_cubic, ease_out_expo, segment
from samuel.ui.paint import chamfer_path, glow_path, panel_frame, pen, wrap
from samuel.ui.theme import THEME, font

AL = Qt.AlignmentFlag


# ─────────────────────────────────────────────────────────── top bar
class TopBar(QWidget):
    persona_clicked = pyqtSignal(str)
    window_action = pyqtSignal(str)        # minimize | fullscreen | close

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setMouseTracking(True)
        self.persona = "jarvis"
        self.status: Dict[str, Tuple[str, str]] = {}   # key -> (text, level ok|warn|off)
        self.hover = ""
        self._hits: List[Tuple[QRectF, str]] = []
        self._press_pos = None

    def set_status(self, key: str, text: str, level: str) -> None:
        if self.status.get(key) != (text, level):
            self.status[key] = (text, level)
            self.update()

    def set_persona(self, key: str) -> None:
        self.persona = key
        self.update()

    def mouseMoveEvent(self, e):
        hit = next((k for r, k in self._hits if r.contains(e.position())), "")
        if hit != self.hover:
            self.hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self.hover = ""
        self.update()

    def mousePressEvent(self, e):
        hit = next((k for r, k in self._hits if r.contains(e.position())), "")
        if hit.startswith("persona:"):
            self.persona_clicked.emit(hit.split(":")[1])
        elif hit.startswith("win:"):
            self.window_action.emit(hit.split(":")[1])
        elif e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if not any(r.contains(e.position()) for r, _ in self._hits):
            self.window_action.emit("fullscreen")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hits = []
        w, h = self.width(), self.height()
        # baseline rule with a bright centre section
        y = h - 6
        p.setPen(pen(THEME.c("primary", 45), 1))
        p.drawLine(QPointF(0, y), QPointF(w, y))
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0.0, THEME.c("primary", 0))
        g.setColorAt(0.5, THEME.c("primary_hi", 200))
        g.setColorAt(1.0, THEME.c("primary", 0))
        p.setPen(pen(THEME.c("primary", 0), 1))
        p.fillRect(QRectF(w * 0.3, y - 0.5, w * 0.4, 1.5), QBrush(g))

        # wordmark
        x = 4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("primary_hi", 240))
        hexp = QPainterPath()
        cx, cy, r = x + 15, 26, 13
        for i in range(6):
            pt = QPointF(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30)))
            hexp.moveTo(pt) if i == 0 else hexp.lineTo(pt)
        hexp.closeSubpath()
        glow_path(p, hexp, THEME.c("primary_hi", 230), 1.6, 1.0)
        p.setBrush(THEME.c("primary_hi", 220))
        p.drawEllipse(QPointF(cx, cy), 4.2, 4.2)
        x += 40
        wf = font("display", 21, 700, 5)
        p.setFont(wf)
        p.setPen(THEME.c("text_hi", 252))
        word = "S.A.M.U.E.L."
        p.drawText(QRectF(x, 9, 400, 26), int(AL.AlignLeft | AL.AlignVCenter), word)
        ww = QFontMetricsF(wf).horizontalAdvance(word)
        p.setFont(font("ui", 11, 700, 2.4))
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(x + 1, 35, 520, 15), int(AL.AlignLeft | AL.AlignVCenter),
                   "SMART AUTONOMOUS MULTIMODAL ENGINE FOR LEARNING")
        p.setFont(font("mono", 9, 500))
        p.setPen(THEME.c("primary", 200))
        p.drawText(QRectF(x + ww + 8, 12, 60, 14), int(AL.AlignLeft | AL.AlignVCenter), f"v{__version__}")

        # right side: window buttons, clock
        rx = w
        for key, glyph in (("close", "x"), ("fullscreen", "[]"), ("minimize", "_")):
            br = QRectF(rx - 30, 12, 28, 24)
            self._hits.append((br, f"win:{key}"))
            hov = self.hover == f"win:{key}"
            col = "alert" if key == "close" and hov else "primary"
            p.setPen(pen(THEME.c(col, 200 if hov else 80), 1))
            p.setBrush(THEME.c(col, 40 if hov else 0))
            p.drawPath(chamfer_path(br, 5, "tl br"))
            p.setPen(pen(THEME.c("text_hi" if hov else "text_mid", 240), 1.3))
            c = br.center()
            if key == "close":
                p.drawLine(QPointF(c.x() - 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 4))
                p.drawLine(QPointF(c.x() - 4, c.y() + 4), QPointF(c.x() + 4, c.y() - 4))
            elif key == "fullscreen":
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(c.x() - 5, c.y() - 4, 10, 8))
            else:
                p.drawLine(QPointF(c.x() - 5, c.y() + 3), QPointF(c.x() + 5, c.y() + 3))
            rx -= 32
        rx -= 14
        now = datetime.now()
        cf = font("mono", 24, 300)
        p.setFont(cf)
        p.setPen(THEME.c("text_hi", 250))
        clock = now.strftime("%H:%M")
        sec = now.strftime(":%S")
        cw = QFontMetricsF(cf).horizontalAdvance(clock)
        sf = font("mono", 14, 400)
        sw = QFontMetricsF(sf).horizontalAdvance(sec)
        p.drawText(QRectF(rx - cw - sw, 6, cw, 30), int(AL.AlignLeft | AL.AlignVCenter), clock)
        p.setFont(sf)
        p.setPen(THEME.c("primary_hi", 230))
        p.drawText(QRectF(rx - sw, 10, sw, 26), int(AL.AlignLeft | AL.AlignVCenter), sec)
        p.setFont(font("ui", 11, 700, 2.0))
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(rx - 220, 36, 220, 14), int(AL.AlignRight | AL.AlignVCenter),
                   now.strftime("%a %d %b %Y").upper())
        rx -= max(cw + sw, 120) + 26

        # status pills (right-to-left)
        order = ["llm", "net", "tts", "stt"]
        names = {"stt": "VOICE IN", "tts": "VOICE OUT", "net": "LINK", "llm": "LLM"}
        for key in order:
            text, level = self.status.get(key, ("--", "off"))
            nf = font("ui", 10, 700, 1.6)
            vf = font("mono", 10, 500)
            tw = max(QFontMetricsF(nf).horizontalAdvance(names[key]), QFontMetricsF(vf).horizontalAdvance(text)) + 22
            r = QRectF(rx - tw, 12, tw, 38)
            col = {"ok": "ok", "warn": "accent", "off": "text_lo"}.get(level, "text_lo")
            p.setPen(pen(THEME.c("primary", 40), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(QPointF(r.x() - 7, 16), QPointF(r.x() - 7, 46))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c(col, 240))
            p.drawEllipse(QPointF(r.x() + 5, 21), 3, 3)
            if level == "ok":
                p.setBrush(THEME.c(col, 50))
                p.drawEllipse(QPointF(r.x() + 5, 21), 6, 6)
            p.setFont(nf)
            p.setPen(THEME.c("text_lo", 255))
            p.drawText(QRectF(r.x() + 14, 13, tw, 16), int(AL.AlignLeft | AL.AlignVCenter), names[key])
            p.setFont(vf)
            p.setPen(THEME.c("text_hi" if level != "off" else "text_mid", 235))
            p.drawText(QRectF(r.x() + 0, 31, tw, 16), int(AL.AlignLeft | AL.AlignVCenter), text)
            rx -= tw + 16
            if rx < x + 640:
                break

        # persona switch, centred
        sw_w, sw_h = 236, 34
        sx = max(x + ww + 80, (w - sw_w) / 2 - 40)
        if sx + sw_w < rx:
            outer = QRectF(sx, 13, sw_w, sw_h)
            p.setPen(pen(THEME.c("primary", 70), 1))
            p.setBrush(THEME.c("bg1", 160))
            p.drawPath(chamfer_path(outer, 8, "tl br"))
            for i, key in enumerate(("jarvis", "friday")):
                seg = QRectF(sx + 3 + i * (sw_w - 6) / 2, 16, (sw_w - 6) / 2, sw_h - 6)
                self._hits.append((seg, f"persona:{key}"))
                active = self.persona == key
                if active:
                    path = chamfer_path(seg, 6, "tl br")
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(THEME.c("primary", 70))
                    p.drawPath(path)
                    glow_path(p, path, THEME.c("primary_hi", 220), 1.0, 0.7)
                elif self.hover == f"persona:{key}":
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(THEME.c("primary", 24))
                    p.drawPath(chamfer_path(seg, 6, "tl br"))
                p.setFont(font("display", 11, 700, 2.4))
                p.setPen(THEME.c("text_hi" if active else "text_lo", 255))
                p.drawText(seg, int(AL.AlignCenter), key.upper())
        p.end()


# ─────────────────────────────────────────────────────────── subtitles
class Subtitle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.shown = 0.0
        self.heard = ""
        self.heard_final = True
        self.age = 0.0
        self.heard_t = 0.0
        self.setFixedHeight(96)

    def set_text(self, s: str):
        self.text, self.shown, self.age = s, 0.0, 0.0
        self.update()

    def set_heard(self, s: str, final: bool):
        self.heard, self.heard_final = s, final
        self.heard_t = time.monotonic()
        self.update()

    def advance(self, dt):
        self.age += dt
        if self.heard and self.heard_final and time.monotonic() - self.heard_t > 9:
            self.heard = ""
            self.update()
        if self.shown < len(self.text):
            self.shown = min(len(self.text), self.shown + 60 * dt)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        f = font("ui", 20, 600, 0.3)
        fm = QFontMetricsF(f)
        lines = wrap(fm, self.text[: int(self.shown)], w * 0.86, 2)
        full = wrap(fm, self.text, w * 0.86, 2)
        p.setFont(f)
        y = 6
        for i, line in enumerate(lines):
            p.setPen(THEME.c("text_hi", 250))
            p.drawText(QRectF(w * 0.07, y + i * 28, w * 0.86, 28), int(AL.AlignHCenter | AL.AlignVCenter),
                       line.ljust(len(full[i]) if i < len(full) else 0))
        if self.heard:
            hf = font("ui", 14, 500, 0.6)
            p.setFont(hf)
            col = THEME.c("text_mid", 230 if self.heard_final else 170)
            p.setPen(col)
            s = ("“" + self.heard + "”") if self.heard_final else ("… " + self.heard)
            s = wrap(QFontMetricsF(hf), s, w * 0.8, 1)
            p.drawText(QRectF(0, 66, w, 22), int(AL.AlignHCenter | AL.AlignVCenter), s[0] if s else "")
        p.end()


# ─────────────────────────────────────────────────────────── command bar
class MicButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(40, 40))
        self.active = False
        self.level = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Push to talk (Ctrl+Space)")

    def mousePressEvent(self, _):
        self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(20, 20)
        col = "primary_hi" if self.active else "primary"
        if self.active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(THEME.c("primary", 40 + 120 * self.level))
            p.drawEllipse(c, 18, 18)
        p.setPen(pen(THEME.c(col, 220), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 16, 16)
        p.setBrush(THEME.c(col, 240))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(16.5, 10, 7, 13), 3.5, 3.5)
        p.setPen(pen(THEME.c(col, 240), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(13, 14, 14, 13), 180 * 16, 180 * 16)
        p.drawLine(QPointF(20, 27), QPointF(20, 30))
        p.end()


class CommandBar(QWidget):
    submitted = pyqtSignal(str)
    mic = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 14, 6)
        lay.setSpacing(10)
        self.mic_btn = MicButton()
        self.mic_btn.clicked.connect(self.mic)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command or say “Samuel…”  —  e.g. teach me about photosynthesis")
        self.input.setFont(font("ui", 16, 500, 0.3))
        self.input.setFrame(False)
        self.input.returnPressed.connect(self._submit)
        self.input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.mic_btn)
        lay.addWidget(self.input, 1)
        self.history: List[str] = []
        self.h_index = 0
        self.input.installEventFilter(self)
        THEME.changed.connect(self._restyle)
        self._restyle()

    def _restyle(self):
        hi = THEME.c("text_hi").name()
        lo = THEME.c("text_lo").name()
        sel = THEME.c("primary", 90)
        self.input.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {hi}; border: none;"
            f" selection-background-color: rgba({sel.red()},{sel.green()},{sel.blue()},90); }}")
        pal = self.input.palette()
        pal.setColor(pal.ColorRole.PlaceholderText, THEME.c("text_lo", 230))
        self.input.setPalette(pal)
        self.update()

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.input and ev.type() == QEvent.Type.KeyPress and self.history:
            if ev.key() == Qt.Key.Key_Up:
                self.h_index = max(0, self.h_index - 1)
                self.input.setText(self.history[self.h_index])
                return True
            if ev.key() == Qt.Key.Key_Down:
                self.h_index = min(len(self.history), self.h_index + 1)
                self.input.setText(self.history[self.h_index] if self.h_index < len(self.history) else "")
                return True
        return super().eventFilter(obj, ev)

    def _submit(self):
        s = self.input.text().strip()
        if not s:
            return
        self.history.append(s)
        self.h_index = len(self.history)
        self.input.clear()
        self.submitted.emit(s)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        focus = self.input.hasFocus()
        path = chamfer_path(r, 10, "tl br")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("bg1", 200))
        p.drawPath(path)
        glow_path(p, path, THEME.c("primary", 200 if focus else 80), 1.0, 0.6 if focus else 0.2)
        p.setFont(font("mono", 10, 500))
        p.setPen(THEME.c("text_lo", 255))
        hint = "↵ SEND   CTRL+K COMMANDS   F1 HELP" if self.width() > 760 else "CTRL+K   F1"
        hw = QFontMetricsF(p.font()).horizontalAdvance(hint)
        p.drawText(QRectF(r.right() - hw - 16, 0, hw + 4, r.height()), int(AL.AlignRight | AL.AlignVCenter), hint)
        self.layout().setContentsMargins(10, 6, int(hw + 32), 6)
        p.end()


# ─────────────────────────────────────────────────────────── overlays
class Overlay(QWidget):
    """Full-window dimming layer; subclasses paint their own card."""

    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.hide()
        self.k = 0.0
        self.target = 0.0

    def open(self):
        self.setGeometry(self.parent().rect())
        self.target = 1.0
        self.show()
        self.raise_()

    def close_(self):
        self.target = 0.0
        self.closed.emit()

    def advance(self, dt):
        if abs(self.k - self.target) > 0.002:
            self.k = approach(self.k, self.target, dt, 14)
            if self.target == 0 and self.k < 0.02:
                self.k = 0.0
                self.hide()
            self.update()

    def mousePressEvent(self, e):
        self.close_()

    def dim(self, p):
        p.fillRect(self.rect(), THEME.c("bg0", 175 * self.k))


Command = Tuple[str, str, str]   # title, description, phrase-or-action


class Palette(Overlay):
    run = pyqtSignal(str)

    def __init__(self, parent, commands: List[Command]):
        super().__init__(parent)
        self.commands = commands
        self.filtered = list(commands)
        self.sel = 0
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setFont(font("ui", 19, 500, 0.3))
        self.edit.setPlaceholderText("Search commands… or type anything and press Enter")
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)
        THEME.changed.connect(self._style)
        self._style()

    def _style(self):
        self.edit.setStyleSheet(f"QLineEdit {{ background: transparent; color: {THEME.c('text_hi').name()}; border: none; }}")
        pal = self.edit.palette()
        pal.setColor(pal.ColorRole.PlaceholderText, THEME.c("text_lo", 230))
        self.edit.setPalette(pal)

    def box(self) -> QRectF:
        w = min(640.0, self.width() - 80)
        return QRectF((self.width() - w) / 2, self.height() * 0.16, w, 70 + 46 * min(8, max(1, len(self.filtered))))

    def open(self):
        super().open()
        self.edit.clear()
        self._filter("")
        b = self.box()
        self.edit.setGeometry(int(b.x() + 48), int(b.y() + 12), int(b.width() - 64), 40)
        self.edit.setFocus()

    def _filter(self, s):
        s = s.lower().strip()
        self.filtered = [c for c in self.commands if not s or s in (c[0] + " " + c[1] + " " + c[2]).lower()]
        self.sel = 0
        self.update()

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.edit and ev.type() == QEvent.Type.KeyPress:
            k = ev.key()
            if k == Qt.Key.Key_Escape:
                self.close_()
                return True
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
                self.sel = min(len(self.filtered) - 1, self.sel + 1)
                self.update()
                return True
            if k == Qt.Key.Key_Up:
                self.sel = max(0, self.sel - 1)
                self.update()
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.filtered:
                    self.run.emit(self.filtered[self.sel][2])
                elif self.edit.text().strip():
                    self.run.emit(self.edit.text().strip())
                self.close_()
                return True
        return super().eventFilter(obj, ev)

    def mousePressEvent(self, e):
        b = self.box()
        if not b.contains(e.position()):
            self.close_()
            return
        i = int((e.position().y() - b.y() - 64) // 46)
        if 0 <= i < min(8, len(self.filtered)):
            self.run.emit(self.filtered[i][2])
            self.close_()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.dim(p)
        p.setOpacity(self.k)
        b = self.box()
        b.translate(0, (1 - self.k) * -16)
        panel_frame(p, b, 14, 1.4, 1.6)
        p.fillRect(QRectF(b.x(), b.y(), b.width(), b.height()), THEME.c("bg0", 120))
        panel_frame(p, b, 14, 1.4, 0.6)
        p.setPen(pen(THEME.c("primary_hi", 230), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(b.x() + 26, b.y() + 31), 7, 7)
        p.drawLine(QPointF(b.x() + 31, b.y() + 36), QPointF(b.x() + 36, b.y() + 41))
        p.setPen(pen(THEME.c("primary", 60), 1))
        p.drawLine(QPointF(b.x() + 14, b.y() + 60), QPointF(b.right() - 14, b.y() + 60))
        y = b.y() + 64
        for i, (title, desc, phrase) in enumerate(self.filtered[:8]):
            r = QRectF(b.x() + 10, y, b.width() - 20, 42)
            if i == self.sel:
                path = chamfer_path(r, 6, "tl br")
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(THEME.c("primary", 50))
                p.drawPath(path)
                p.fillRect(QRectF(r.x(), r.y() + 6, 2, r.height() - 12), THEME.c("primary_hi"))
            p.setFont(font("ui", 15.5, 700, 0.6))
            p.setPen(THEME.c("text_hi", 250))
            p.drawText(QRectF(r.x() + 16, r.y() + 2, r.width() * 0.5, 22), int(AL.AlignLeft | AL.AlignVCenter), title)
            p.setFont(font("ui", 12.5, 500, 0.3))
            p.setPen(THEME.c("text_lo", 255))
            p.drawText(QRectF(r.x() + 16, r.y() + 21, r.width() - 32, 18), int(AL.AlignLeft | AL.AlignVCenter), desc)
            p.setFont(font("mono", 10, 500))
            p.setPen(THEME.c("primary_hi", 220))
            label = phrase if not phrase.startswith(":") else phrase[1:].upper()
            p.drawText(QRectF(r.x(), r.y() + 2, r.width() - 14, 22), int(AL.AlignRight | AL.AlignVCenter), label[:34])
            y += 46
        if not self.filtered:
            p.setFont(font("ui", 14, 500))
            p.setPen(THEME.c("text_mid", 230))
            p.drawText(QRectF(b.x() + 24, y, b.width() - 48, 40), int(AL.AlignLeft | AL.AlignVCenter),
                       "No matching command — Enter sends it to S.A.M.U.E.L. as typed.")
        p.end()


class HelpOverlay(Overlay):
    KEYS = [("F11", "Fullscreen"), ("Esc", "Leave fullscreen / close overlay"), ("Ctrl+K", "Command palette"),
            ("Ctrl+P", "Switch JARVIS ⇄ FRIDAY"), ("Ctrl+Space", "Push to talk"), ("/  or Ctrl+L", "Focus the command line"),
            ("1 – 4", "Answer quiz / grade flashcard"), ("Space", "Flip card / next question"),
            ("Ctrl+D", "Run the demo tour"), ("Ctrl+S", "Screenshot of the HUD"), ("Ctrl+Q", "Quit")]
    VOICE = ["teach me about <topic>", "next / repeat", "quiz me (on <topic>)", "review my flashcards",
             "how am I doing", "remind me in 10 minutes to <task>", "set a timer for 25 minutes",
             "what's the weather", "system status / battery", "volume up · mute · brightness down",
             "open youtube · google <query>", "who is <person> · what is <thing>", "take a note <text>",
             "switch to Friday · Jarvis, take over", "daily briefing", "lock the screen · goodbye"]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.dim(p)
        p.setOpacity(self.k)
        w = min(900.0, self.width() - 80)
        h = min(560.0, self.height() - 80)
        b = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.fillRect(b, THEME.c("bg0", 200))
        panel_frame(p, b, 16, 1.4, 1.2)
        from samuel.ui.paint import header
        header(p, b, "F1", "OPERATOR MANUAL", "CLICK ANYWHERE TO CLOSE")
        col_w = (w - 64) / 2
        x1, x2, y0 = b.x() + 24, b.x() + 40 + col_w, b.y() + 50
        p.setFont(font("ui", 12, 700, 2))
        p.setPen(THEME.c("primary_hi", 240))
        p.drawText(QRectF(x1, y0, col_w, 16), int(AL.AlignLeft | AL.AlignVCenter), "KEYBOARD")
        p.drawText(QRectF(x2, y0, col_w, 16), int(AL.AlignLeft | AL.AlignVCenter), "SAY OR TYPE")
        y = y0 + 26
        for k, d in self.KEYS:
            p.setFont(font("mono", 11, 600))
            p.setPen(THEME.c("text_hi", 245))
            p.drawText(QRectF(x1, y, 130, 22), int(AL.AlignLeft | AL.AlignVCenter), k)
            p.setFont(font("ui", 14, 500, 0.3))
            p.setPen(THEME.c("text_mid", 240))
            p.drawText(QRectF(x1 + 132, y, col_w - 132, 22), int(AL.AlignLeft | AL.AlignVCenter), d)
            y += 28
        y = y0 + 26
        for v in self.VOICE:
            p.setFont(font("ui", 14, 500, 0.3))
            p.setPen(THEME.c("text_hi", 235))
            p.drawText(QRectF(x2, y, col_w, 22), int(AL.AlignLeft | AL.AlignVCenter), "› " + v)
            y += 26
        p.setFont(font("ui", 12.5, 500, 0.4))
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(x1, b.bottom() - 34, w - 48, 20), int(AL.AlignLeft | AL.AlignVCenter),
                   "Wake words: “Samuel”, “Jarvis” or “Friday”. Addressing the other assistant by name hands over to it.")
        p.end()


class Banner(QWidget):
    """Alert strip that slides down from the top bar (reminders, timers)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title, self.text = "", ""
        self.k, self.until = 0.0, 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def show_alert(self, title, text, seconds=7.0):
        self.title, self.text = title, text
        self.until = time.monotonic() + seconds
        self.show()
        self.raise_()

    def advance(self, dt):
        target = 1.0 if time.monotonic() < self.until else 0.0
        if self.isVisible():
            self.k = approach(self.k, target, dt, 10)
            if target == 0 and self.k < 0.02:
                self.hide()
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = min(620.0, self.width() - 40)
        k = ease_out_cubic(self.k)
        b = QRectF((self.width() - w) / 2, -60 + 70 * k, w, 56)
        p.setOpacity(k)
        path = chamfer_path(b, 12, "tl br")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(THEME.c("bg0", 235))
        p.drawPath(path)
        p.setBrush(THEME.c("accent", 40))
        p.drawPath(path)
        glow_path(p, path, THEME.c("accent", 240), 1.4, 1.2)
        pulse = 0.6 + 0.4 * math.sin(time.monotonic() * 8)
        p.setBrush(THEME.c("accent", 255 * pulse))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(b.x() + 16, b.y() + 16, 4, 24))
        p.setFont(font("ui", 12, 700, 2.4))
        p.setPen(THEME.c("accent", 255))
        p.drawText(QRectF(b.x() + 32, b.y() + 7, w - 40, 18), int(AL.AlignLeft | AL.AlignVCenter), self.title)
        p.setFont(font("ui", 17, 600, 0.3))
        p.setPen(THEME.c("text_hi", 250))
        p.drawText(QRectF(b.x() + 32, b.y() + 25, w - 40, 24), int(AL.AlignLeft | AL.AlignVCenter), self.text)
        p.end()


class BootOverlay(QWidget):
    """Opening sequence: wordmark resolves, real start-up checks tick off, then it fades."""

    DURATION = 2.4
    FADE = 0.6

    def __init__(self, parent, checks: List[Tuple[str, str, str]]):
        super().__init__(parent)
        self.checks = checks          # (label, result, level)
        self.t = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def done(self) -> bool:
        return self.t >= self.DURATION + self.FADE

    def advance(self, dt):
        self.t += dt
        if self.done:
            self.hide()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        fade = 1 - segment(self.t, self.DURATION, self.DURATION + self.FADE)
        p.setOpacity(fade)
        p.fillRect(self.rect(), THEME.c("bg0", 255))
        g = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.6)
        g.setColorAt(0, THEME.c("primary", 28))
        g.setColorAt(1, THEME.c("primary", 0))
        p.fillRect(self.rect(), QBrush(g))
        cx, cy = w / 2, h / 2 - 40
        # expanding rings
        for i in range(3):
            k = ease_out_expo(segment(self.t, 0.1 + i * 0.12, 1.2 + i * 0.12))
            r = 40 + 150 * k + i * 26
            p.setPen(pen(THEME.c("primary", 160 * (1 - 0.3 * i) * (0.4 + 0.6 * (1 - k))), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
        # wordmark with letters resolving
        word = "S.A.M.U.E.L."
        wf = font("display", 44, 700, 14 - 8 * ease_out_cubic(segment(self.t, 0.2, 1.3)))
        fm = QFontMetricsF(wf)
        p.setFont(wf)
        total = fm.horizontalAdvance(word)
        x = cx - total / 2
        glyphs = "#%&@$*+=?/"
        for i, ch in enumerate(word):
            reveal = segment(self.t, 0.25 + i * 0.06, 0.55 + i * 0.06)
            shown = ch if reveal >= 1 or ch == "." else (glyphs[int(self.t * 30 + i) % len(glyphs)] if reveal > 0 else " ")
            p.setPen(THEME.c("text_hi" if reveal >= 1 else "primary", 255 * max(0.15, reveal)))
            p.drawText(QPointF(x, cy + fm.capHeight() / 2), shown)
            x += fm.horizontalAdvance(ch)
        sub_k = segment(self.t, 0.9, 1.4)
        p.setFont(font("ui", 14, 700, 4.5))
        p.setPen(THEME.c("text_mid", 255 * sub_k))
        p.drawText(QRectF(0, cy + 40, w, 20), int(AL.AlignHCenter | AL.AlignVCenter),
                   "SMART AUTONOMOUS MULTIMODAL ENGINE FOR LEARNING")
        # progress bar
        bw = min(460.0, w * 0.5)
        bx, by = cx - bw / 2, cy + 86
        prog = ease_out_cubic(segment(self.t, 0.5, self.DURATION - 0.1))
        p.fillRect(QRectF(bx, by, bw, 2), THEME.c("primary", 40))
        p.fillRect(QRectF(bx, by, bw * prog, 2), THEME.c("primary_hi", 240))
        p.setFont(font("mono", 10, 500))
        p.setPen(THEME.c("primary_hi", 230))
        p.drawText(QRectF(bx, by + 6, bw, 16), int(AL.AlignRight | AL.AlignVCenter), f"{int(prog * 100):3d}%")
        p.setPen(THEME.c("text_lo", 255))
        p.drawText(QRectF(bx, by + 6, bw, 16), int(AL.AlignLeft | AL.AlignVCenter), "SYSTEMS CHECK")
        # check lines
        y = by + 32
        for i, (label, result, level) in enumerate(self.checks):
            k = segment(self.t, 0.6 + i * 0.16, 0.7 + i * 0.16)
            if k <= 0:
                break
            p.setOpacity(fade * k)
            p.setFont(font("mono", 11, 500))
            p.setPen(THEME.c("text_mid", 240))
            dots = label + " " + "." * max(2, 26 - len(label))
            p.drawText(QRectF(bx, y, bw, 18), int(AL.AlignLeft | AL.AlignVCenter), dots)
            col = {"ok": "ok", "warn": "accent", "off": "text_lo"}.get(level, "text_hi")
            p.setPen(THEME.c(col, 255))
            p.drawText(QRectF(bx, y, bw, 18), int(AL.AlignRight | AL.AlignVCenter), result)
            y += 20
        p.end()
